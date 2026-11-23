"""Ekstrak daftar uji DI/DO per device dari schematic diagram GAIA 2 (E2010-96563-DD-SC-0xx rev A2).

DI per titik (permintaan user 2026-11-23), DO per peralatan/lembar:
  - DI: 1 item per titik dengan nama sinyal dari drawing, mis. "P/DI1 · CB(-Q0) CLOSED · sh.061" (BCU, slot/DI)
    atau "OPTO5 · 50BF INITIATION · sh.035" (relay). Titik SPARE dilewati. Lembar DI tanpa label titik
    (mis. AVR N90) tetap 1 item per lembar.
  - DO: BCU 1 item per lembar control circuit (CB/DS/ES/OLTC/fan…); relay DO trip/lockout & DO sinyal.
Hasil: tools/dido_gaia2.json → dibaca tools/sas_checksheet_gaia2.py. Titik per lembar bisa dilihat di drawing (sh.xxx).

Pemakaian (butuh `pip install pymupdf`, hanya untuk tool ini):
  python tools/dido_from_schematic.py "<folder 3st_Rev A2_Schematic Diagram 3>" > tools/dido_gaia2.json
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

# model di teks lembar DI → kunci device mentah (dipetakan ke DEV per tipe panel oleh generator)
MODELS = [(r"PCS-?931", "PCS931"), (r"P841", "P841"), (r"P5F30", "P5F30"), (r"P643", "P643"),
          (r"P143", "P143"), (r"P746", "P746"), (r"C264|BAY CONTROL UNIT|DIU211", "C264")]
# tag device di lembar DO → kunci mentah
TAGS = {"-F87T": "P643", "-F501": "P5F30_HV", "-F502": "P5F30_LV", "-F50BF": "P841", "-F50": "F50",
        "-F87L": "PCS931", "-F87B1": "P746_1", "-F87B2": "P746_2", "-F87B3": "P746_3", "-A30": "C264",
        "-N90": "RTF"}
RE_DI_T = re.compile(r"DIGITAL\s+INPUT|BINARY\s+INPUT", re.I)
RE_CTRL_T = re.compile(r"CONTROL CIRCUIT|CTRL|CMD|COMMAND", re.I)
RE_TRIP_T = re.compile(r"TRIP|LOCKOUT|INTERTRIP|SEND", re.I)
RE_SIG_T = re.compile(r"SIGNALL", re.I)
RE_PT = re.compile(r"(?m)^(DI\d+|OPTO ?\d+|BI_\d+)$")
_LABEL = re.compile(r"^(DI\d+|OPTO ?\d+|BI_\d+)$")
_SKIP = re.compile(r"^(/\d{3}\.\d[A-F]|[A-Z]?\d{1,3}|[+\-♦#]|SLOT_\w+|COMMON)$")
_STOP = re.compile(r"^(-[A-Z0-9][\w.()/\-]*$|[A-Z0-9]+[+\-]$|=|NOTE|SLOT|DIU|INPUT UNIT|SHEE|SEE |DWG|RL\d|\d{2,}$|SCHEMATIC|E2010|"
                   r"PROJECT|CONTROL & PROTN)")


def di_points(text):
    """Teks lembar DI → {label: nama sinyal}. Urutan teks PDF: label, ref, pin, +/-, lalu nama sinyal."""
    lines = [x.strip() for x in text.split("\n")]
    out, i = {}, 0
    while i < len(lines):
        if not _LABEL.match(lines[i]):
            i += 1
            continue
        lab, j, sig = lines[i].replace(" ", ""), i + 1, []
        while j < len(lines) and len(sig) < 4:
            x = lines[j]
            if _LABEL.match(x):
                break
            if not x or _SKIP.match(x):
                if sig:
                    break
                j += 1
                continue
            if _STOP.match(x) or not re.search(r"[A-Za-z]", x):
                break
            sig.append(x)
            j += 1
        name = re.sub(r"\s+", " ", " ".join(sig)).strip()
        if name or lab not in out:          # label ganda di halaman: ambil yang ada namanya
            out[lab] = name
        i = j
    return out


def _pt_no(label):
    return int(re.sub(r"\D", "", label) or 0)
RE_OUT = re.compile(r"(?m)^(DO\d+|BO_\d+|Output-\d+|OUTPUT ?\d+|RL\d+)$")
RE_TAG = re.compile(r"(?m)^(-F87T|-F501|-F502|-F50BF|-F50|-F87L|-F87B[123]|-A30|-N90)(?=\s|\(|$)")


def load(pdf):
    import pymupdf
    doc = pymupdf.open(pdf)
    return [pg.get_text() for pg in doc]


def toc_of(texts, docno):
    lines = "\n".join(texts).split("\n")
    toc = {}
    for i in range(len(lines) - 8):
        a, b = lines[i].strip(), lines[i + 1].strip()
        if re.fullmatch(r"\d{3}", a) and b == docno:
            s = int(a)
        elif a == docno and re.fullmatch(r"\d{3}", b):
            s = int(b)
        else:
            continue
        seg = [x.strip() for x in lines[i + 2:i + 9]]
        r = next((j for j, x in enumerate(seg) if re.fullmatch(r"A\d?", x)), None)
        if r and r >= 3:
            toc.setdefault(s, re.sub(r"\s+", " ", seg[r - 1]))
    return toc


def pages_of(texts):
    out = {}
    for t in texts:
        m = re.search(r"\n(\d{3})\n(\d{3})\n", t)
        if m and int(m.group(2)) == int(m.group(1)) + 1:
            out.setdefault(int(m.group(1)), t)
    return out


def sh(nums):
    """[61, 62, 64] → 'sh.061–062, 064'"""
    nums, parts, i = sorted(set(nums)), [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        parts.append(f"{nums[i]:03d}" + (f"–{nums[j]:03d}" if j > i else ""))
        i = j + 1
    return "sh." + ", ".join(parts)


def pt_range(pts):
    if not pts:
        return ""
    key = lambda x: (re.sub(r"[\d ]", "", x), int(re.sub(r"\D", "", x)))
    pts = sorted(set(p.replace(" ", "") for p in pts), key=key)
    return f"{pts[0]}–{pts[-1]}" if len(pts) > 1 else pts[0]


def device_of_di(title, text):
    T = title.upper()
    if "AVR" in T or "N90" in T:
        return "RTF"
    if (m := re.search(r"F87B([123])", T)):
        return f"P746_{m.group(1)}"
    if "BCU" in T:
        return "C264"
    found = [k for rx, k in MODELS if re.search(rx, text, re.I)]
    found = [k for k in found if k != "C264"] or found
    if not found:
        return None
    k = found[0]
    if k == "P5F30":
        return "P5F30_LV" if re.search(r"\bLV\b|F502", T) else "P5F30_HV"
    return k


def extract(pdf):
    texts = load(pdf)
    docno = pathlib.Path(pdf).stem
    toc, pages = toc_of(texts, docno), pages_of(texts)
    di = {}     # (dev, slot) -> {"sheets": [], "pts": []}
    do = {}     # (dev, kind, label) -> sheets
    for s in sorted(toc):
        title, text = toc[s], pages.get(s, "")
        T = title.upper()
        if RE_DI_T.search(T) and "ANALOG" not in T:
            dev = device_of_di(title, text)
            if not dev:
                continue
            m = re.search(r"SLOT\s*:\s*(\w)", T)
            slot = m.group(1) if (m and dev == "C264") else ""
            e = di.setdefault((dev, slot), {"sheets": [], "pts": [], "named": []})
            e["sheets"].append(s)
            e["pts"] += RE_PT.findall(text)
            for lab, name in sorted(di_points(text).items(), key=lambda kv: _pt_no(kv[0])):
                e["named"].append((s, lab, name))
            continue
        if "MANUAL" in T:
            continue
        tags = {TAGS[t] for t in RE_TAG.findall(text)}
        if not RE_OUT.search(text):
            continue
        if RE_CTRL_T.search(T) or "OLTC" in T or "FAN" in T or "RESET" in T:
            if "C264" in tags:
                lbl = re.sub(r"\s*\((CMD|COMMAND) FROM MIMIC AND B(CU)?\)?|\s*CMD FROM MIMIC AND BCU\)?", "", title)
                lbl = re.sub(r"\s*CONTROL CIRCUIT|\s*CTRL( CIRCUIT)?|\s*MULTIPLICATION|\s*CIRCUIT", "", lbl,
                             flags=re.I).strip(" (")
                do.setdefault(("C264", "ctrl", lbl), []).append(s)
            for t in tags - {"C264"}:
                do.setdefault((t, "rctrl" if t == "RTF" else "trip", ""), []).append(s)
        elif RE_TRIP_T.search(T):
            for t in tags - {"C264"}:
                do.setdefault((t, "trip", ""), []).append(s)
        elif RE_SIG_T.search(T):
            for t in tags - {"C264"}:
                do.setdefault((t, "sig", ""), []).append(s)
    items = []   # [dev, deskripsi, kriteria, lembar pertama]
    for (dev, slot), e in di.items():
        c = "Status DI masuk BCU/HMI sesuai drawing" if dev == "C264" else "Status input terbaca di relay sesuai drawing"
        if not e["named"]:       # lembar tanpa label titik → 1 item per lembar
            items.append([dev, f"DI / input · {sh(e['sheets'])}", c, (min(e["sheets"]), 0)])
            continue
        for s, lab, name in e["named"]:
            if not name or name.upper() == "SPARE":
                continue
            lab_txt = f"{slot}/{lab}" if slot else lab
            items.append([dev, f"{lab_txt} · {name} · sh.{s:03d}", c, (s, _pt_no(lab))])
    for (dev, kind, lbl), sheets in do.items():
        if kind == "ctrl":
            it = [dev, f"DO {lbl} · {sh(sheets)}", "Perintah BCU/HMI → peralatan beroperasi"]
        elif kind == "rctrl":
            it = [dev, f"DO kontrol · {sh(sheets)}", "Output kontrol bekerja sesuai drawing"]
        elif kind == "trip":
            it = [dev, f"DO trip / lockout · {sh(sheets)}", "Kontak output bekerja (trip/lockout) sesuai drawing"]
        else:
            it = [dev, f"DO sinyal (DFR/common/alarm) · {sh(sheets)}", "Sinyal output diterima tujuan sesuai drawing"]
        items.append(it + [(min(sheets), 0)])
    items.sort(key=lambda it: (it[0], it[1].startswith("DO "), it[3]))   # per device: DI dulu, urut lembar & titik
    items = [it[:3] for it in items]
    tags = sorted(set(re.findall(r"=E[A-Z]{1,2}\d\d\+[A-Z]+\d", "\n".join(texts[:3]))))
    return {"doc": docno, "panels": tags, "items": items}


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1])
    out = {}
    for pdf in sorted(root.glob("*/*.pdf")):
        r = extract(str(pdf))
        if r["items"]:
            out[r["doc"]] = r
            print(f"{r['doc']}: {len(r['items'])} item, panel {r['panels']}", file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False, indent=1))
