#!/usr/bin/env python3
"""PreToolUse guard untuk PanelChecker.

1. File build yang sudah diserahkan (.dmg/.zip/.apk/.aab/.exe di root project)
   tidak boleh ditimpa/diubah → DENY. Dihapus/dipindah → ASK (user konfirmasi).
2. SQL ke Supabase produksi yang bisa menghapus/menimpa data
   (DROP, TRUNCATE, DELETE, UPDATE, ON CONFLICT DO UPDATE, ALTER … DROP) → ASK.
   Tool Supabase destruktif lain (pause, delete/reset branch, …) → ASK.

Output mengikuti format hook Claude Code (hookSpecificOutput.permissionDecision).
Kalau ada error internal, script diam (exit 0) supaya tidak memblokir kerja normal.
"""
import json
import os
import re
import shlex
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DELIV_EXT = (".dmg", ".zip", ".apk", ".aab", ".exe")


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    sys.exit(0)


# ---------------------------------------------------------------- deliverables
def root_deliverable(path, cwd):
    """Path → nama file kalau itu file build yang SUDAH ADA di root project."""
    if not path.lower().endswith(DELIV_EXT):
        return None
    p = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    if os.path.dirname(p) == ROOT and os.path.exists(p):
        return os.path.basename(p)
    return None


WRITE_DEST_CMDS = {"cp", "ditto", "rsync", "install", "ln"}   # argumen terakhir = tujuan
REMOVE_CMDS = {"rm", "unlink", "trash", "srm"}
MODIFY_CMDS = {"zip", "truncate", "touch", "tee", "dd", "shred", "chmod"}  # mengubah file di argumen


def check_bash(cmd, cwd):
    # pecah per perintah (; && || | dan subshell); lacak `cd` supaya path relatif benar
    for part in re.split(r"&&|\|\||;|\||\(|\)|\n", cmd):
        # redirect: > file / >> file
        for m in re.finditer(r"(?<![0-9&])>>?\s*([^\s;&|]+)", part):
            f = root_deliverable(m.group(1).strip("'\""), cwd)
            if f:
                decide("deny", f"Guard: '{f}' adalah build yang sudah diserahkan, tidak boleh ditimpa lewat redirect. Tulis ke nama baru (mis. _r2).")
        try:
            tok = shlex.split(part)
        except ValueError:
            tok = part.split()
        while tok and ("=" in tok[0] and not tok[0].startswith("-")):  # VAR=x cmd
            tok = tok[1:]
        if tok and tok[0] in ("sudo", "command", "builtin", "exec"):
            tok = tok[1:]
        if not tok:
            continue
        exe = os.path.basename(tok[0])
        if exe in ("cd", "pushd"):
            target = tok[1] if len(tok) > 1 and tok[1] != "-" else os.path.expanduser("~")
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
            continue
        args = [a for a in tok[1:] if not a.startswith("-")]
        if exe in WRITE_DEST_CMDS and len(args) >= 2:
            f = root_deliverable(args[-1], cwd)
            if f:
                decide("deny", f"Guard: '{f}' sudah ada dan mungkin sedang dipakai/di-mount user. Jangan ditimpa; salin ke nama baru (mis. _r2).")
        elif exe == "mv" and args:
            for a in args:
                f = root_deliverable(a, cwd)
                if f:
                    if a == args[-1]:
                        decide("deny", f"Guard: '{f}' sudah ada; mv akan menimpanya. Pakai nama baru.")
                    decide("ask", f"Guard: mv akan memindahkan/mengganti nama build yang sudah diserahkan '{f}'. Lanjutkan?")
        elif exe in REMOVE_CMDS:
            for a in args:
                f = root_deliverable(a, cwd)
                if f:
                    decide("ask", f"Guard: perintah ini menghapus build yang sudah diserahkan '{f}'. Yakin?")
        elif exe in MODIFY_CMDS:
            for a in args:
                f = root_deliverable(a, cwd)
                if f:
                    decide("deny", f"Guard: '{f}' adalah build yang sudah diserahkan; {exe} akan mengubahnya. Buat file baru dengan nama lain.")
        elif exe == "hdiutil" and len(tok) > 1 and tok[1] in ("create", "convert", "makehybrid"):
            for a in args[1:]:
                f = root_deliverable(a, cwd)
                if f:
                    decide("deny", f"Guard: hdiutil akan menimpa '{f}' yang sudah diserahkan. Pakai nama baru.")


def check_file_tool(path):
    f = root_deliverable(path, "/")
    if f:
        decide("deny", f"Guard: '{f}' adalah build yang sudah diserahkan; jangan ditulis ulang.")


# ---------------------------------------------------------------- supabase sql
def strip_sql(q):
    q = re.sub(r"--[^\n]*", " ", q)
    q = re.sub(r"/\*.*?\*/", " ", q, flags=re.S)
    q = re.sub(r"\$([A-Za-z_]*)\$.*?\$\1\$", " $body$ ", q, flags=re.S)  # function bodies
    q = re.sub(r"'(?:[^']|'')*'", "''", q)
    return q.lower()


def check_sql(q):
    s = strip_sql(q)
    found = []
    pats = [
        (r"\bdrop\s+(table|schema|column|function|policy|view|index|trigger|type|bucket)\b", "DROP"),
        (r"\btruncate\b", "TRUNCATE"),
        (r"\bdelete\s+from\b", "DELETE"),
        (r"\bupdate\s+[\w.\"]+\s+set\b", "UPDATE"),
        (r"\bon\s+conflict\b[^;]*\bdo\s+update\b", "ON CONFLICT DO UPDATE (menimpa)"),
        (r"\balter\s+table\b[^;]*\bdrop\b", "ALTER … DROP"),
        (r"\bdisable\s+row\s+level\s+security\b", "DISABLE RLS"),
    ]
    for p, name in pats:
        if re.search(p, s):
            found.append(name)
    if found:
        decide("ask", "Guard Supabase PRODUKSI: query ini mengandung " + ", ".join(found) +
               ". Data checking yang sudah ada tidak boleh ditimpa/dihapus. Konfirmasi dulu.")


DESTRUCTIVE_SUPABASE = {"pause_project", "delete_branch", "reset_branch", "merge_branch",
                        "rebase_branch", "delete_notebook", "delete_feedback"}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if tool == "Bash":
        check_bash(ti.get("command", ""), cwd)
    elif tool in ("Write", "Edit", "NotebookEdit"):
        check_file_tool(ti.get("file_path", "") or ti.get("notebook_path", ""))
    elif tool.startswith("mcp__") and "supabase" in tool.lower():
        short = tool.split("__")[-1]
        if short in ("execute_sql", "apply_migration"):
            check_sql(ti.get("query", "") or "")
        elif short in DESTRUCTIVE_SUPABASE:
            decide("ask", f"Guard Supabase: '{short}' mengubah project produksi. Konfirmasi dulu.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass
