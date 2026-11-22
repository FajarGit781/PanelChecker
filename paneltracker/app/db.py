"""Database layer (SQLite) — Panel Tracker v2 (Checking Panel & Punch List).

Semua data dalam satu file .db. Setiap record punya `uuid`, `updated_at` dan `deleted`
(soft delete) supaya nanti bisa disinkronkan ke cloud (offline-first).
"""
from __future__ import annotations

import datetime as dt
import getpass
import json
import sqlite3
import uuid as _uuid
from collections import defaultdict

from .i18n import TrDict
from .templates_default import DEFAULT_TEMPLATES, DEFAULT_TEMPLATES_EN

SCHEMA_VERSION = 2

DEFAULT_CATEGORIES = [
    "Wiring", "Mekanikal", "Setting Relay", "Komunikasi / IEC 61850", "SCADA / HMI", "Interlock",
    "Power Supply", "Material", "Dokumen", "Lainnya",
]
DEFAULT_PANEL_TYPES = ["CP", "RP", "CRP", "Marshalling", "RTU / Gateway", "AC/DC", "Lainnya"]

SEVERITIES = ["Critical", "Major", "Minor"]
SEV_LABEL = TrDict({"Critical": "A · Critical", "Major": "B · Major", "Minor": "C · Minor"})
SEV_SHORT = {"Critical": "A", "Major": "B", "Minor": "C"}
SEV_HINT = TrDict({"Critical": "Wajib selesai sebelum energize", "Major": "Wajib selesai sebelum serah terima",
            "Minor": "Perbaikan minor, bisa menyusul"})
ISSUE_STATUSES = ["Open", "In Progress", "Ready to Verify", "Closed"]
RESULTS = ["OK", "NG", "NA"]
PANEL_STATUSES = ["Tanpa checklist", "Belum dicek", "Sedang dicek", "Ada temuan", "Lulus", "Diterima"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS project (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE,
    code TEXT NOT NULL, name TEXT NOT NULL, client TEXT DEFAULT '', contractor TEXT DEFAULT '',
    location TEXT DEFAULT '', start_date TEXT, end_date TEXT, description TEXT DEFAULT '',
    issue_prefix TEXT DEFAULT 'PL', created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS site (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE,
    project_id INTEGER NOT NULL REFERENCES project(id), name TEXT NOT NULL, location TEXT DEFAULT '',
    sort INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS panel (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE,
    site_id INTEGER NOT NULL REFERENCES site(id), bay TEXT DEFAULT '', tag TEXT NOT NULL, name TEXT DEFAULT '',
    panel_type TEXT DEFAULT '', vendor TEXT DEFAULT '', serial_no TEXT DEFAULT '', remarks TEXT DEFAULT '',
    accepted_by TEXT DEFAULT '', accepted_at TEXT, sort INTEGER DEFAULT 0,
    created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS check_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE, name TEXT NOT NULL, description TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS check_template_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT, template_id INTEGER NOT NULL REFERENCES check_template(id) ON DELETE CASCADE,
    section TEXT DEFAULT '', description TEXT NOT NULL, criteria TEXT DEFAULT '', unit TEXT DEFAULT '',
    sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS panel_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE,
    panel_id INTEGER NOT NULL REFERENCES panel(id), section TEXT DEFAULT '', description TEXT NOT NULL,
    criteria TEXT DEFAULT '', unit TEXT DEFAULT '', sort INTEGER DEFAULT 0,
    result TEXT DEFAULT '', value TEXT DEFAULT '', remark TEXT DEFAULT '', checked_by TEXT DEFAULT '',
    checked_at TEXT, created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS issue (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE,
    project_id INTEGER NOT NULL REFERENCES project(id), site_id INTEGER, panel_id INTEGER, check_id INTEGER,
    code TEXT NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT '', category TEXT DEFAULT '',
    severity TEXT DEFAULT 'Minor', status TEXT DEFAULT 'Open', pic TEXT DEFAULT '', raised_by TEXT DEFAULT '',
    raised_date TEXT, due_date TEXT, closed_date TEXT, verified_by TEXT DEFAULT '', action TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attachment (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE,
    issue_id INTEGER, check_id INTEGER, kind TEXT DEFAULT 'before', filename TEXT, caption TEXT DEFAULT '',
    data BLOB, created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, project_id INTEGER, entity TEXT,
    entity_id INTEGER, action TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_site_p ON site(project_id);
CREATE INDEX IF NOT EXISTS ix_panel_s ON panel(site_id);
CREATE INDEX IF NOT EXISTS ix_check_p ON panel_check(panel_id);
CREATE INDEX IF NOT EXISTS ix_issue_p ON issue(project_id);
CREATE INDEX IF NOT EXISTS ix_issue_pn ON issue(panel_id);
CREATE INDEX IF NOT EXISTS ix_att_i ON attachment(issue_id);
CREATE INDEX IF NOT EXISTS ix_act_p ON activity(project_id);
"""


def today() -> str:
    return dt.date.today().isoformat()


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def stamp() -> str:
    """Timestamp UTC presisi mikrodetik untuk updated_at (dipakai sinkron last-write-wins)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Pengaturan yang dipakai bersama satu tim (ikut sinkron cloud). Sisanya (nama user, cursor sinkron,
# bahasa) tetap per laptop.
SHARED_SETTINGS = (
    "company_name", "company_address", "logo",
    "due_days_Critical", "due_days_Major", "due_days_Minor",
    "sign_prepared", "sign_checked", "sign_approved",
    "sign_prepared_title", "sign_checked_title", "sign_approved_title",
    "categories", "panel_types", "viewer_url",
)
OLD_STAMP = "2000-01-01T00:00:00.000000Z"   # "lebih lama dari apa pun di cloud"
SYNC_TABLES = ("project", "site", "panel", "check_template", "panel_check", "issue", "attachment")
_TPL_NS = _uuid.UUID("5b0f6c1e-2f0a-4c1b-9d8e-7a6b5c4d3e2f")


def _logo_hash(data) -> str:
    import hashlib
    return hashlib.sha1(data).hexdigest() if data else ""


def new_uuid() -> str:
    return str(_uuid.uuid4())


def parse_date(s):
    if not s:
        return None
    if isinstance(s, dt.datetime):
        return s.date()
    if isinstance(s, dt.date):
        return s
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def fmt_date(s) -> str:
    d = parse_date(s)
    return d.strftime("%d-%m-%Y") if d else ""


def _default_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "user"


class ReadOnlyError(Exception):
    """Dilempar saat user dengan peran viewer mencoba mengubah data."""


class Database:
    read_only = False  # True untuk peran viewer (diatur oleh UI)

    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, timeout=20)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        ver = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stage'").fetchone()
        if ver:
            raise RuntimeError("Database ini dari Panel Tracker v1 (format lama). Buat database baru untuk v2.")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._init_settings()
        first = not self.q1("SELECT 1 FROM check_template LIMIT 1")
        for name, desc, items in (DEFAULT_TEMPLATES if first else []) + DEFAULT_TEMPLATES_EN:
            # uuid deterministik: template bawaan sama di semua laptop → tidak dobel saat sinkron
            uid = str(_uuid.uuid5(_TPL_NS, name))
            if self.q1("SELECT 1 FROM check_template WHERE uuid=?", (uid,)):
                continue
            tid = self.add_template(name, desc, items, uuid=uid)
            # versi "lama" & tidak dirty: versi di cloud (kalau sudah diedit tim) selalu menang
            self.conn.execute("UPDATE check_template SET updated_at='2000-01-01T00:00:00.000000Z', dirty=0 "
                              "WHERE id=?", (tid,))
        self.conn.commit()

    def _migrate(self):
        """Tambah kolom sinkron (dirty, storage_path) untuk database lama."""
        for t in SYNC_TABLES:
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({t})")}
            if "dirty" not in cols:
                self.conn.execute(f"ALTER TABLE {t} ADD COLUMN dirty INTEGER DEFAULT 1")
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(attachment)")}
        if "storage_path" not in cols:
            self.conn.execute("ALTER TABLE attachment ADD COLUMN storage_path TEXT")
        self.conn.commit()

    def pending_changes(self) -> int:
        n = len(self.shared_settings_dirty())
        for t in SYNC_TABLES:
            extra = " AND kind<>'logo'" if t == "attachment" else ""
            n += self.q1(f"SELECT COUNT(*) c FROM {t} WHERE dirty=1{extra}")["c"]
        return n

    # ------------------------------------------------------------------ util
    def close(self):
        try:
            self.conn.commit()
            self.conn.close()
        except Exception:
            pass

    def q(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def q1(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def x(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur.lastrowid

    def _insert(self, table, data: dict) -> int:
        data = dict(data)
        data.setdefault("uuid", new_uuid())
        data.setdefault("created_at", now())
        data["updated_at"] = stamp()
        data["dirty"] = 1
        cols = ", ".join(data)
        qs = ", ".join("?" * len(data))
        return self.x(f"INSERT INTO {table}({cols}) VALUES({qs})", tuple(data.values()))

    def _update(self, table, rid, data: dict):
        data = dict(data)
        data["updated_at"] = stamp()
        data["dirty"] = 1
        cols = ", ".join(f"{k}=?" for k in data)
        self.x(f"UPDATE {table} SET {cols} WHERE id=?", (*data.values(), rid))

    def backup(self, dest: str):
        self.conn.commit()
        bk = sqlite3.connect(dest)
        with bk:
            self.conn.backup(bk)
        bk.close()

    # -------------------------------------------------------------- settings
    def _init_settings(self):
        defaults = {
            "schema_version": str(SCHEMA_VERSION),
            "company_name": "PT Nama Perusahaan",
            "company_address": "",
            "user_name": _default_user(),
            "categories": json.dumps(DEFAULT_CATEGORIES),
            "panel_types": json.dumps(DEFAULT_PANEL_TYPES),
            "due_days_Critical": "3", "due_days_Major": "7", "due_days_Minor": "14",
            "sign_prepared": "", "sign_checked": "", "sign_approved": "",
            "sign_prepared_title": "Commissioning Engineer",
            "sign_checked_title": "Vendor / Kontraktor",
            "sign_approved_title": "Owner / Client",
        }
        for k, v in defaults.items():
            self.conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(settings)")}
        if "dirty" not in cols:
            # v2.7: pengaturan bersama ikut sinkron. Nilai yang sudah diubah di laptop ini dikirim sekali
            # dengan cap waktu lama → kalau tim sudah punya nilai di cloud, nilai cloud yang menang.
            self.conn.execute("ALTER TABLE settings ADD COLUMN updated_at TEXT")
            self.conn.execute("ALTER TABLE settings ADD COLUMN dirty INTEGER DEFAULT 0")
            for k in SHARED_SETTINGS:
                if k in defaults:
                    self.conn.execute("UPDATE settings SET updated_at=?, dirty=1 WHERE key=? AND COALESCE(value,'')<>?",
                                      (OLD_STAMP, k, defaults[k]))
            logo = self.get_logo()
            if logo:
                self.conn.execute("INSERT OR REPLACE INTO settings(key,value,updated_at,dirty) VALUES('logo',?,?,1)",
                                  (_logo_hash(logo), OLD_STAMP))
        self.conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('logo','')")

    def get_setting(self, key, default=""):
        r = self.q1("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r and r["value"] is not None else default

    def set_setting(self, key, value):
        if key in SHARED_SETTINGS:
            if self.get_setting(key, None) == value:
                return   # tidak berubah → tidak perlu dikirim ulang
            self.x("INSERT OR REPLACE INTO settings(key,value,updated_at,dirty) VALUES(?,?,?,1)", (key, value, stamp()))
        else:
            self.x("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))

    def shared_settings_dirty(self):
        return self.q("SELECT key, value, updated_at FROM settings WHERE dirty=1 AND key IN (%s)"
                      % ",".join("?" * len(SHARED_SETTINGS)), SHARED_SETTINGS)

    def apply_remote_setting(self, key, value, updated_at) -> bool:
        """Nilai dari cloud. Diterapkan kalau lebih baru dari nilai lokal (last-write-wins)."""
        if key not in SHARED_SETTINGS:
            return False
        r = self.q1("SELECT updated_at FROM settings WHERE key=?", (key,))
        if r and r["updated_at"] and r["updated_at"] >= (updated_at or ""):
            return False
        if key == "logo":
            import base64
            data = base64.b64decode(value) if value else None
            self._store_logo(data)
            value = _logo_hash(data)
        self.conn.execute("INSERT OR REPLACE INTO settings(key,value,updated_at,dirty) VALUES(?,?,?,0)",
                          (key, value, updated_at))
        return True

    def get_list_setting(self, key):
        try:
            return list(json.loads(self.get_setting(key, "[]")))
        except Exception:
            return []

    def get_logo(self):
        r = self.q1("SELECT data FROM attachment WHERE kind='logo' AND deleted=0 LIMIT 1")
        return bytes(r["data"]) if r else None

    def set_logo(self, data, filename=""):
        if _logo_hash(data) == self.get_setting("logo", ""):
            return
        self._store_logo(data, filename)
        self.set_setting("logo", _logo_hash(data))   # tandai untuk dikirim ke tim

    def _store_logo(self, data, filename=""):
        self.conn.execute("DELETE FROM attachment WHERE kind='logo'")
        if data:
            self.conn.execute("INSERT INTO attachment(uuid,kind,filename,data,created_at,updated_at,dirty) "
                              "VALUES(?,?,?,?,?,?,0)", (new_uuid(), "logo", filename, data, now(), now()))
        self.conn.commit()

    @property
    def user(self):
        return self.get_setting("user_name", _default_user())

    def default_due(self, severity) -> str:
        try:
            n = int(self.get_setting(f"due_days_{severity}", "7"))
        except ValueError:
            n = 7
        return (dt.date.today() + dt.timedelta(days=n)).isoformat()

    # -------------------------------------------------------------- activity
    def log(self, project_id, entity, entity_id, action, detail=""):
        self.conn.execute(
            "INSERT INTO activity(ts,user,project_id,entity,entity_id,action,detail) VALUES(?,?,?,?,?,?,?)",
            (now(), self.user, project_id, entity, entity_id, action, detail))
        self.conn.commit()

    def activities(self, project_id, limit=300):
        return self.q("SELECT * FROM activity WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))

    # --------------------------------------------------------------- project
    def projects(self):
        return self.q("SELECT * FROM project WHERE deleted=0 ORDER BY id")

    def project(self, pid):
        return self.q1("SELECT * FROM project WHERE id=?", (pid,))

    def add_project(self, code, name, **f) -> int:
        pid = self._insert("project", dict(code=code, name=name, **f))
        self.log(pid, "project", pid, "create", f"{code} - {name}")
        return pid

    def update_project(self, pid, **f):
        self._update("project", pid, f)
        self.log(pid, "project", pid, "update", "")

    def delete_project(self, pid):
        self._update("project", pid, {"deleted": 1})

    # ----------------------------------------------------------------- sites
    def sites(self, project_id):
        return self.q("SELECT * FROM site WHERE project_id=? AND deleted=0 ORDER BY sort, id", (project_id,))

    def site(self, sid):
        return self.q1("SELECT * FROM site WHERE id=?", (sid,))

    def add_site(self, project_id, name, location="") -> int:
        mx = self.q1("SELECT COALESCE(MAX(sort),0)+1 m FROM site WHERE project_id=?", (project_id,))["m"]
        sid = self._insert("site", dict(project_id=project_id, name=name, location=location, sort=mx))
        self.log(project_id, "site", sid, "create", f"Site ditambahkan: {name}")
        return sid

    def get_or_create_site(self, project_id, name) -> int:
        r = self.q1("SELECT id FROM site WHERE project_id=? AND deleted=0 AND lower(name)=lower(?)",
                    (project_id, name.strip()))
        return r["id"] if r else self.add_site(project_id, name.strip())

    def update_site(self, sid, name, location=""):
        self._update("site", sid, dict(name=name, location=location))
        self.log(self.site(sid)["project_id"], "site", sid, "update", name)

    def delete_site(self, sid):
        s = self.site(sid)
        self._update("site", sid, {"deleted": 1})
        for p in self.q("SELECT id FROM panel WHERE site_id=? AND deleted=0", (sid,)):
            self.delete_panel(p["id"], log=False)
        self.log(s["project_id"], "site", sid, "delete", s["name"])

    def move_site(self, sid, direction):
        s = self.site(sid)
        rows = [r["id"] for r in self.sites(s["project_id"])]
        i = rows.index(sid)
        j = i + direction
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
            for k, rid in enumerate(rows):
                self.conn.execute("UPDATE site SET sort=?, updated_at=?, dirty=1 WHERE id=?", (k, stamp(), rid))
            self.conn.commit()

    # ---------------------------------------------------------------- panels
    def panels(self, project_id, site_id=None):
        sql = ("SELECT p.*, s.name AS site_name, s.project_id FROM panel p JOIN site s ON s.id=p.site_id "
               "WHERE s.project_id=? AND p.deleted=0 AND s.deleted=0")
        params = [project_id]
        if site_id:
            sql += " AND s.id=?"
            params.append(site_id)
        return self.q(sql + " ORDER BY s.sort, s.id, p.sort, p.id", params)

    def panel(self, pid):
        return self.q1("SELECT p.*, s.name AS site_name, s.project_id FROM panel p JOIN site s ON s.id=p.site_id "
                       "WHERE p.id=?", (pid,))

    def add_panel(self, site_id, tag, template_id=None, **f) -> int:
        mx = self.q1("SELECT COALESCE(MAX(sort),0)+1 m FROM panel WHERE site_id=?", (site_id,))["m"]
        pid = self._insert("panel", dict(site_id=site_id, tag=tag, sort=mx, **f))
        if template_id:
            self.apply_template(pid, template_id, log=False)
        self.log(self.site(site_id)["project_id"], "panel", pid, "create", f"Panel ditambahkan: {tag}")
        return pid

    def update_panel(self, pid, **f):
        self._update("panel", pid, f)
        p = self.panel(pid)
        self.log(p["project_id"], "panel", pid, "update", f"Data panel diubah: {p['tag']}")

    def delete_panel(self, pid, log=True):
        p = self.panel(pid)
        self._update("panel", pid, {"deleted": 1})
        self.conn.execute("UPDATE panel_check SET deleted=1, updated_at=?, dirty=1 WHERE panel_id=? AND deleted=0",
                          (stamp(), pid))
        self.conn.commit()
        if log and p:
            self.log(p["project_id"], "panel", pid, "delete", f"Panel dihapus: {p['tag']}")

    def set_accepted(self, pid, by: str | None):
        if by:
            self._update("panel", pid, dict(accepted_by=by, accepted_at=today()))
        else:
            self._update("panel", pid, dict(accepted_by="", accepted_at=None))
        p = self.panel(pid)
        self.log(p["project_id"], "panel", pid, "accept" if by else "unaccept",
                 f"Panel {p['tag']} diterima oleh {by}" if by else f"Penerimaan {p['tag']} dibatalkan")

    def find_panel(self, project_id, text):
        """Cari panel dari isi QR / tag.

        QR v2.7.2+ (bila alamat viewer web diisi): "https://<viewer>/?p=<uuid>". QR v2.7.1+: "PT:<uuid>:<tag>" (uuid sama di semua laptop & HP). Label lama: "PT:<id lokal>:<tag>". Id lokal
        BERBEDA tiap laptop, jadi untuk label lama yang dipakai tag-nya, bukan nomornya."""
        text = (text or "").strip()
        tag = text
        if text.lower().startswith(("http://", "https://")):
            # label v2.7.2+: link viewer web ".../?p=<uuid>"
            import re
            m = re.search(r"[?&](?:p|panel)=([0-9a-fA-F-]{36})", text)
            text = f"PT:{m.group(1)}:" if m else ""
            tag = ""
        if text.upper().startswith("PT:"):
            parts = text.split(":", 2)
            key = parts[1].strip().lower() if len(parts) > 1 else ""
            tag = parts[2] if len(parts) > 2 else ""
            if len(key) == 36 and key.count("-") == 4:
                p = self.q1("SELECT p.*, s.name AS site_name, s.project_id FROM panel p JOIN site s ON s.id=p.site_id "
                            "WHERE lower(p.uuid)=? AND p.deleted=0", (key,))
                if p:
                    return p
        tag = " ".join(tag.split()).lower()
        if not tag:
            return None
        rows = self.q("SELECT p.*, s.name AS site_name, s.project_id FROM panel p JOIN site s ON s.id=p.site_id "
                      "WHERE p.deleted=0 AND s.deleted=0 ORDER BY (s.project_id=?) DESC, p.id", (project_id,))
        for p in rows:   # cocokkan tag dengan spasi/baris baru dirapikan
            if " ".join((p["tag"] or "").split()).lower() == tag:
                return p
        return None

    # ------------------------------------------------------------- templates
    def templates(self):
        return self.q("SELECT t.*, (SELECT COUNT(*) FROM check_template_item i WHERE i.template_id=t.id) n "
                      "FROM check_template t WHERE deleted=0 ORDER BY id")

    def template(self, tid):
        return self.q1("SELECT * FROM check_template WHERE id=?", (tid,))

    def template_items(self, tid):
        return self.q("SELECT * FROM check_template_item WHERE template_id=? ORDER BY sort, id", (tid,))

    def add_template(self, name, description="", items=(), uuid=None) -> int:
        d = dict(name=name, description=description)
        if uuid:
            d["uuid"] = uuid
        tid = self._insert("check_template", d)
        self._write_template_items(tid, items)
        return tid

    def save_template(self, tid, name, description, items):
        self._update("check_template", tid, dict(name=name, description=description))
        self.conn.execute("DELETE FROM check_template_item WHERE template_id=?", (tid,))
        self._write_template_items(tid, items)

    def _write_template_items(self, tid, items):
        for i, (sec, desc, crit, unit) in enumerate(items):
            self.conn.execute("INSERT INTO check_template_item(template_id,section,description,criteria,unit,sort) "
                              "VALUES(?,?,?,?,?,?)", (tid, sec, desc, crit, unit, i))
        self.conn.commit()

    def delete_template(self, tid):
        self._update("check_template", tid, {"deleted": 1})

    def apply_template(self, panel_id, template_id, replace=False, log=True) -> int:
        """Salin item template ke checklist panel. Item yang sudah ada (section+deskripsi sama) dilewati."""
        if replace:
            self.conn.execute("UPDATE panel_check SET deleted=1, updated_at=?, dirty=1 WHERE panel_id=? AND deleted=0",
                              (stamp(), panel_id))
        existing = {(r["section"].strip().lower(), r["description"].strip().lower())
                    for r in self.panel_checks(panel_id)}
        mx = self.q1("SELECT COALESCE(MAX(sort),0) m FROM panel_check WHERE panel_id=? AND deleted=0",
                     (panel_id,))["m"]
        n = 0
        for it in self.template_items(template_id):
            key = (it["section"].strip().lower(), it["description"].strip().lower())
            if key in existing:
                continue
            mx += 1
            self.conn.execute(
                "INSERT INTO panel_check(uuid,panel_id,section,description,criteria,unit,sort,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (new_uuid(), panel_id, it["section"], it["description"], it["criteria"], it["unit"], mx, now(), stamp()))
            n += 1
        self.conn.commit()
        if log:
            p = self.panel(panel_id)
            self.log(p["project_id"], "panel", panel_id, "template",
                     f"{p['tag']}: +{n} item dari '{self.template(template_id)['name']}'")
        return n

    # ---------------------------------------------------------------- checks
    def panel_checks(self, panel_id):
        return self.q("SELECT * FROM panel_check WHERE panel_id=? AND deleted=0 ORDER BY sort, id", (panel_id,))

    def check(self, cid):
        return self.q1("SELECT * FROM panel_check WHERE id=?", (cid,))

    def set_check(self, cid, **f):
        """f: result/value/remark. Mengisi checked_by/checked_at otomatis saat result diubah."""
        if "result" in f:
            if f["result"]:
                f.setdefault("checked_by", self.user)
                f.setdefault("checked_at", now())
            else:
                f["checked_by"], f["checked_at"] = "", None
        self._update("panel_check", cid, f)
        if "result" in f:
            c = self.check(cid)
            p = self.panel(c["panel_id"])
            self.log(p["project_id"], "check", cid, "result",
                     f"{p['tag']} · {c['description'][:50]} → {f['result'] or 'reset'}")

    def bulk_set_result(self, check_ids, result, only_empty=True):
        n = 0
        for cid in check_ids:
            c = self.check(cid)
            if only_empty and c["result"]:
                continue
            self.set_check(cid, result=result)
            n += 1
        return n

    def add_check_item(self, panel_id, section, description, criteria="", unit="") -> int:
        mx = self.q1("SELECT COALESCE(MAX(sort),0)+1 m FROM panel_check WHERE panel_id=?", (panel_id,))["m"]
        # taruh di akhir section yang sama kalau ada
        last = self.q1("SELECT MAX(sort) m FROM panel_check WHERE panel_id=? AND section=? AND deleted=0",
                       (panel_id, section))
        if last and last["m"] is not None:
            self.conn.execute("UPDATE panel_check SET sort=sort+1, updated_at=?, dirty=1 WHERE panel_id=? AND sort>?",
                              (stamp(), panel_id, last["m"]))
            mx = last["m"] + 1
        return self._insert("panel_check", dict(panel_id=panel_id, section=section, description=description,
                                                criteria=criteria, unit=unit, sort=mx))

    def update_check_item(self, cid, **f):
        self._update("panel_check", cid, f)

    def delete_check_item(self, cid):
        self._update("panel_check", cid, {"deleted": 1})

    def check_stats(self, rows):
        s = {"total": len(rows), "OK": 0, "NG": 0, "NA": 0}
        for r in rows:
            if r["result"] in s:
                s[r["result"]] += 1
        s["checked"] = s["OK"] + s["NG"] + s["NA"]
        s["pending"] = s["total"] - s["checked"]
        s["pct"] = 100.0 * s["checked"] / s["total"] if s["total"] else 0.0
        return s

    # ---------------------------------------------------------- panel status
    def panel_overview(self, project_id, site_id=None):
        """List dict per panel: stats checklist, punch open, status."""
        pans = self.panels(project_id, site_id)
        checks = defaultdict(list)
        for r in self.q("SELECT c.panel_id, c.result FROM panel_check c JOIN panel p ON p.id=c.panel_id "
                        "JOIN site s ON s.id=p.site_id WHERE s.project_id=? AND c.deleted=0", (project_id,)):
            checks[r["panel_id"]].append(r)
        punch = defaultdict(lambda: {"open": 0, "Critical": 0, "Major": 0, "Minor": 0, "total": 0, "overdue": 0})
        t = today()
        for i in self.issues(project_id):
            if not i["panel_id"]:
                continue
            d = punch[i["panel_id"]]
            d["total"] += 1
            if i["status"] != "Closed":
                d["open"] += 1
                d[i["severity"]] = d.get(i["severity"], 0) + 1
                if i["due_date"] and i["due_date"] < t:
                    d["overdue"] += 1
        out = []
        for p in pans:
            st = self.check_stats(checks[p["id"]])
            pu = punch[p["id"]]
            if p["accepted_at"]:
                status = "Diterima"
            elif st["NG"] > 0 or pu["open"] > 0:
                # temuan selalu diutamakan, juga saat checking belum selesai / panel tanpa checklist
                status = "Ada temuan"
            elif st["total"] == 0:
                status = "Tanpa checklist"
            elif st["checked"] == 0:
                status = "Belum dicek"
            elif st["pending"] > 0:
                status = "Sedang dicek"
            else:
                status = "Lulus"
            out.append({"panel": p, "stats": st, "punch": dict(pu), "status": status})
        return out

    def overall(self, project_id, site_id=None):
        ov = self.panel_overview(project_id, site_id)
        iss = self.issues(project_id, site_id=site_id)
        t = today()
        open_i = [i for i in iss if i["status"] != "Closed"]
        items = {"total": 0, "OK": 0, "NG": 0, "NA": 0, "checked": 0}
        for o in ov:
            for k in items:
                items[k] += o["stats"][k]
        return {
            "panels": len(ov),
            "panel_status": {s: sum(1 for o in ov if o["status"] == s) for s in PANEL_STATUSES},
            "panels_started": sum(1 for o in ov if o["stats"]["checked"] > 0),
            "panels_done": sum(1 for o in ov if o["status"] in ("Lulus", "Diterima")),
            "items": items,
            "items_pct": 100.0 * items["checked"] / items["total"] if items["total"] else 0.0,
            "issues_total": len(iss),
            "issues_open": len(open_i),
            "issues_closed": len(iss) - len(open_i),
            "issues_overdue": sum(1 for i in open_i if i["due_date"] and i["due_date"] < t),
            "by_severity": {s: sum(1 for i in open_i if i["severity"] == s) for s in SEVERITIES},
            "by_status": {s: sum(1 for i in iss if i["status"] == s) for s in ISSUE_STATUSES},
        }

    def punch_trend(self, project_id, site_id=None, weeks=10):
        """Jumlah punch dibuka & ditutup per minggu (Senin-Minggu) untuk N minggu terakhir."""
        tdy = dt.date.today()
        start = tdy - dt.timedelta(days=tdy.weekday()) - dt.timedelta(weeks=weeks - 1)
        buckets = []
        for k in range(weeks):
            a = start + dt.timedelta(weeks=k)
            buckets.append([a, 0, 0])
        for i in self.issues(project_id, site_id=site_id):
            for idx, key in ((1, "raised_date"), (2, "closed_date")):
                d = parse_date(i[key])
                if d and d >= start:
                    k = (d - start).days // 7
                    if 0 <= k < weeks:
                        buckets[k][idx] += 1
        return buckets

    # ---------------------------------------------------------------- issues
    def issues(self, project_id, site_id=None, panel_id=None, check_id=None):
        sql = ("SELECT i.*, s.name AS site_name, p.tag AS panel_tag, p.bay AS panel_bay, "
               "c.description AS check_desc FROM issue i LEFT JOIN site s ON s.id=i.site_id "
               "LEFT JOIN panel p ON p.id=i.panel_id LEFT JOIN panel_check c ON c.id=i.check_id "
               "WHERE i.project_id=? AND i.deleted=0")
        params = [project_id]
        for col, v in (("site_id", site_id), ("panel_id", panel_id), ("check_id", check_id)):
            if v:
                sql += f" AND i.{col}=?"
                params.append(v)
        return self.q(sql + " ORDER BY i.id", params)

    def issue(self, iid):
        return self.q1("SELECT i.*, s.name AS site_name, p.tag AS panel_tag, c.description AS check_desc "
                       "FROM issue i LEFT JOIN site s ON s.id=i.site_id LEFT JOIN panel p ON p.id=i.panel_id "
                       "LEFT JOIN panel_check c ON c.id=i.check_id WHERE i.id=?", (iid,))

    def next_issue_code(self, project_id):
        pr = self.project(project_id)
        prefix = (pr["issue_prefix"] or "PL").strip()
        mx = 0
        for r in self.q("SELECT code FROM issue WHERE project_id=?", (project_id,)):
            tail = r["code"].split("-")[-1]
            if tail.isdigit():
                mx = max(mx, int(tail))
        return f"{prefix}-{mx + 1:04d}"

    def add_issue(self, project_id, **f) -> int:
        f.setdefault("code", self.next_issue_code(project_id))
        f.setdefault("raised_date", today())
        f.setdefault("raised_by", self.user)
        if f.get("panel_id") and not f.get("site_id"):
            f["site_id"] = self.panel(f["panel_id"])["site_id"]
        iid = self._insert("issue", dict(project_id=project_id, **f))
        self.log(project_id, "issue", iid, "create", f"Punch baru {f['code']}: {f.get('title', '')}")
        return iid

    def update_issue(self, iid, **f):
        old = self.issue(iid)
        if "status" in f:
            if f["status"] == "Closed":
                if not f.get("closed_date"):
                    f["closed_date"] = old["closed_date"] or today()
            else:
                f["closed_date"] = None
        if f.get("panel_id"):
            f["site_id"] = self.panel(f["panel_id"])["site_id"]
        self._update("issue", iid, f)
        det = old["code"]
        if "status" in f and f["status"] != old["status"]:
            det += f": {old['status']} → {f['status']}"
        self.log(old["project_id"], "issue", iid, "update", det)

    def delete_issue(self, iid):
        old = self.issue(iid)
        self._update("issue", iid, {"deleted": 1})
        self.conn.execute("UPDATE attachment SET deleted=1, updated_at=?, dirty=1 WHERE issue_id=? AND deleted=0",
                          (stamp(), iid))
        self.conn.commit()
        self.log(old["project_id"], "issue", iid, "delete", old["code"])

    def distinct_values(self, project_id, col):
        assert col in ("pic", "raised_by", "verified_by", "category")
        return [r["v"] for r in self.q(f"SELECT DISTINCT {col} v FROM issue WHERE project_id=? AND deleted=0 "
                                       f"AND {col}<>'' ORDER BY 1", (project_id,))]

    # ----------------------------------------------------------- attachments
    def attachments(self, issue_id):
        return self.q("SELECT id, kind, filename, caption, created_at FROM attachment "
                      "WHERE issue_id=? AND deleted=0 ORDER BY id", (issue_id,))

    def attachment_data(self, aid):
        r = self.q1("SELECT data FROM attachment WHERE id=?", (aid,))
        return bytes(r["data"]) if r and r["data"] else b""

    def add_attachment(self, issue_id, filename, data, kind="before", caption=""):
        return self._insert("attachment", dict(issue_id=issue_id, kind=kind, filename=filename, caption=caption,
                                               data=data))

    def update_attachment(self, aid, kind=None, caption=None):
        f = {}
        if kind is not None:
            f["kind"] = kind
        if caption is not None:
            f["caption"] = caption
        if f:
            self._update("attachment", aid, f)

    def delete_attachment(self, aid):
        self._update("attachment", aid, {"deleted": 1})

    def attachment_count(self, project_id):
        rows = self.q("SELECT a.issue_id, COUNT(*) c FROM attachment a JOIN issue i ON i.id=a.issue_id "
                      "WHERE i.project_id=? AND a.deleted=0 GROUP BY a.issue_id", (project_id,))
        return {r["issue_id"]: r["c"] for r in rows}


# ---------------------------------------------------------------- mode baca-saja (viewer)
_WRITE_METHODS = [n for n in dir(Database) if n.split("_")[0] in ("add", "update", "delete", "move", "apply",
                  "save", "bulk", "set", "get") and callable(getattr(Database, n))]
_WRITE_METHODS = [n for n in _WRITE_METHODS if not n.startswith("get_") and n not in ("set_setting", "set_logo")]
_WRITE_METHODS += ["_insert", "_update"]


def _guard(fn):
    import functools

    @functools.wraps(fn)
    def w(self, *a, **k):
        if self.read_only:
            raise ReadOnlyError("Mode viewer: data hanya bisa dilihat.")
        return fn(self, *a, **k)
    return w


for _n in _WRITE_METHODS:
    setattr(Database, _n, _guard(getattr(Database, _n)))
