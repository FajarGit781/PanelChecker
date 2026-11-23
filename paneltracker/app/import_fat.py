"""Import punch list FAT dari Excel (format: satu sheet per panel, kolom
No | Deskripsi Temuan | Dokumentasi Temuan | Rencana Tindakan | Dokumentasi Penyelesaian | Status | Remark).

- Foto yang ditempel *di dalam sel* (Excel "Place in Cell" / IMAGE) ikut diambil:
  kolom Dokumentasi Temuan → foto SEBELUM, kolom Dokumentasi Penyelesaian → foto SESUDAH.
- ID (uuid) dibuat deterministik dari nama file + sheet + baris, jadi import ulang file yang sama
  tidak membuat data dobel (record yang sudah ada dilewati).
- Kategori A/B/C dan kategori temuan ditebak dari kata kunci; bisa diubah di aplikasi.
"""
from __future__ import annotations

import datetime as dt
import os
import posixpath
import re
import uuid as _uuid
import xml.etree.ElementTree as ET
import zipfile

from openpyxl import load_workbook

from .db import Database, now, stamp

NS = _uuid.UUID("0d1c6f7a-5e2b-4a8d-9c3e-1f2a3b4c5d6e")
STATUS_MAP = {"close": "Closed", "closed": "Closed", "done": "Closed", "selesai": "Closed",
              "open": "Open", "proses": "In Progress", "progress": "In Progress", "on progress": "In Progress",
              "in progress": "In Progress", "verify": "Ready to Verify", "ready to verify": "Ready to Verify"}

# (nama sheet tanpa "Punchlist ") → (tag, nama, bay, tipe)  — None = punch umum (tanpa panel)
PANEL_HINTS = {
    "general": None,
    "trafo": ("TRAFO-9", "Panel Control & Protection Trafo #9", "Trafo #9", "CRP"),
    "buspro": ("BUSPRO-1", "Panel Busbar Protection #1", "Busbar", "RP"),
    "common": ("COMMON", "Panel Common IED", "Common", "CP"),
    "ugc": ("UGC", "Panel UGC", "UGC", "CRP"),
    "sas1": ("SAS-1", "Panel SAS 1", "SAS", "RTU / Gateway"),
    "sas2": ("SAS-2", "Panel SAS 2", "SAS", "RTU / Gateway"),
    "section": ("SECTION", "Panel Section", "Section", "CRP"),
    "coupler": ("COUPLER", "Panel Coupler", "Coupler", "CRP"),
}

HEAD_KEYS = {"no": "no", "deskripsi temuan": "desc", "dokumentasi temuan": "img_before",
             "rencana tindakan": "plan", "dokumentasi penyelesaian": "img_after", "status": "status",
             "remark": "remark", "keterangan": "remark"}


def _uid(*parts) -> str:
    return str(_uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s in ("#VALUE!", "#REF!", "#N/A") else s


# ------------------------------------------------------------------ klasifikasi
CRIT = [r"intertrip", r"interlock", r"\bcbf\b", r"lockout", r"differential", r"on ?load transfer",
        r"s[yi]h?nchro", r"50bf", r"masih bisa close", r"\btrip\w*\b.*\b(belum|tidak)\b",
        r"rangkaian x\d+ masih keliru"]
MINOR_STRONG = [r"label", r"name ?plate", r"namplate", r"nametag", r"typo", r"\bfont\b", r"baret", r"cleaning",
                r"tube marker", r"tubing marker", r"penamaan", r"damage pada baut"]
MINOR = [r"baut", r"\bduck\b", r"\bduct\b", r"skun", r"\bplat\b", r"cover", r"\bgap\b", r"bolong", r"lubang",
         r"layout", r"hard copy", r"stopper", r"stoper", r"termostat", r"thermostat", r"kompartement", r"lampu",
         r"tube", r"tubbing", r"tubing"]
MAJOR_FORCE = [r"grounding", r"\bgnd\b", r"\bmcb\b", r"wiring", r"terlepas", r"supply", r"countinity",
               r"continuity", r"modem", r"\bfan\b", r"\bbcu\b", r"\bhmi\b", r"signal", r"\bdi ?\d",
               r"rangkaian", r"relay"]

CATS = [
    ("Interlock", [r"interlock", r"intertrip", r"on ?load transfer", r"s[yi]h?nchro", r"masih bisa close"]),
    ("Label & Marking", [r"label", r"name ?plate", r"namplate", r"nametag", r"tube marker", r"tubing", r"tubbing",
                         r"cable tube", r"marker", r"\bfont\b", r"penamaan", r"typo", r"nomor terminal",
                         r"nama terminal"]),
    ("Power Supply", [r"\bmcb\b", r"supply", r"voltage"]),
    ("Wiring", [r"grounding", r"\bgnd\b", r"shield"]),
    ("Dokumen", [r"drawing", r"layout", r"\bga\b", r"skematik", r"schematic", r"hard copy", r"\bcld\b",
                 r"revisi", r"gambar"]),
    ("Komunikasi / IEC 61850", [r"gateway", r"\bgtw\b", r"modem", r"switch", r"server", r"\bgps\b", r"\bows\b",
                                r"t500"]),
    ("SCADA / HMI", [r"\bhmi\b", r"\bbcu\b", r"\bdi ?\d", r"signal", r"status", r"scada"]),
    ("Setting Relay", [r"trip", r"\bcbf\b", r"differential", r"opto", r"50bf", r"\bf\d{2,3}", r"sbef", r"lockout",
                       r"buspro", r"relay", r"\bgfr\b"]),
    ("Mekanikal", [r"baut", r"\bplat\b", r"pintu", r"engsel", r"\bduck\b", r"\bduct\b", r"baret", r"bolong",
                   r"lubang", r"\bgap\b", r"cover", r"\bfan\b", r"cleaning", r"stopp?er", r"emergency", r"mimic",
                   r"termostat", r"damage"]),
    ("Wiring", [r"kabel", r"wiring", r"terminal", r"testblo?ck", r"test block", r"rangkaian", r"continuity",
                r"countinity", r"skun", r"\bx\d"]),
]


def _any(pats, s):
    return any(re.search(p, s) for p in pats)


def classify(text: str, extra: str = ""):
    """Tebak (severity, kategori) dari deskripsi temuan; `extra` (rencana tindakan) hanya cadangan."""
    s = " " + re.sub(r"\s+", " ", text.lower()) + " "
    if _any(CRIT, s):
        sev = "Critical"
    elif _any(MINOR_STRONG, s) or (_any(MINOR, s) and not _any(MAJOR_FORCE, s)):
        sev = "Minor"
    else:
        sev = "Major"
    cat = next((c for c, kws in CATS if _any(kws, s)), None)
    if cat is None and extra:
        e = " " + extra.lower() + " "
        cat = next((c for c, kws in CATS if _any(kws, e)), None)
    return sev, cat or "Lainnya"


# ------------------------------------------------------------------ foto dalam sel
def _cell_images(z: zipfile.ZipFile, sheet_path: str) -> dict[str, list[tuple[str, bytes]]]:
    """Map 'C8' -> [(nama_file, bytes)] untuk gambar rich-value di sheet."""
    names = set(z.namelist())
    if "xl/metadata.xml" not in names or "xl/richData/rdrichvalue.xml" not in names:
        return {}
    ns_main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ns_rd = "{http://schemas.microsoft.com/office/spreadsheetml/2017/richdata}"
    ns_rel = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    ns_r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    meta = ET.fromstring(z.read("xl/metadata.xml"))
    fut = []
    fm = meta.find(f"{ns_main}futureMetadata")
    if fm is not None:
        for bk in fm.findall(f"{ns_main}bk"):
            rvb = bk.find(f".//{ns_rd[:-1]}" + "}rvb") if False else None
            for el in bk.iter():
                if el.tag.endswith("}rvb"):
                    rvb = el
            fut.append(int(rvb.get("i")) if rvb is not None else None)
    vm_list = []
    vmeta = meta.find(f"{ns_main}valueMetadata")
    if vmeta is not None:
        for bk in vmeta.findall(f"{ns_main}bk"):
            rc = bk.find(f"{ns_main}rc")
            vm_list.append(int(rc.get("v")) if rc is not None else None)
    rv = ET.fromstring(z.read("xl/richData/rdrichvalue.xml"))
    rv_rel_idx = []
    for r in rv.findall(f"{ns_rd}rv"):
        vs = r.findall(f"{ns_rd}v")
        rv_rel_idx.append(int(vs[0].text) if vs else None)
    rels_xml = ET.fromstring(z.read("xl/richData/richValueRel.xml"))
    rel_ids = [el.get(f"{ns_r}id") for el in rels_xml]
    targets = {}
    rp = "xl/richData/_rels/richValueRel.xml.rels"
    if rp in names:
        for el in ET.fromstring(z.read(rp)).findall(f"{ns_rel}Relationship"):
            targets[el.get("Id")] = posixpath.normpath(posixpath.join("xl/richData", el.get("Target")))
    out = {}
    sx = z.read(sheet_path).decode("utf-8")
    for m in re.finditer(r'<c r="([A-Z]+\d+)"[^>]*?\svm="(\d+)"', sx):
        ref, vm = m.group(1), int(m.group(2))
        try:
            fut_idx = vm_list[vm - 1]
            rv_idx = fut[fut_idx]
            rel_idx = rv_rel_idx[rv_idx]
            path = targets[rel_ids[rel_idx]]
            out.setdefault(ref, []).append((posixpath.basename(path), z.read(path)))
        except (IndexError, KeyError, TypeError):
            continue
    return out


def _sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    ns_main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ns_r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    ns_rel = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {el.get("Id"): el.get("Target") for el in
            ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall(f"{ns_rel}Relationship")}
    out = {}
    for sh in wb.find(f"{ns_main}sheets"):
        t = rels.get(sh.get(f"{ns_r}id"), "")
        t = t.lstrip("/")
        out[sh.get("name")] = t if t.startswith("xl/") else posixpath.join("xl", t)
    return out


def _resize(data: bytes, max_px=1280) -> bytes:
    """Foto dari Excel FAT → JPEG terkompresi (lihat app/imaging.py)."""
    try:
        from .imaging import compress
        return compress(data, max_px=max_px) or data
    except Exception:
        return data
        if img.width() > max_px or img.height() > max_px:
            img = img.scaled(max_px, max_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if img.hasAlphaChannel():
            img = img.convertToFormat(QImage.Format_RGB32)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "JPG", 82)
        return bytes(ba)
    except Exception:
        return data


# ------------------------------------------------------------------ parse
def parse_workbook(path: str):
    """Kembalikan list sheet: {sheet, title, key, rows:[{no,row,desc,plan,status,remark,after_text,
    before:[(fn,bytes)], after:[...], other:[...]}]}"""
    z = zipfile.ZipFile(path)
    spaths = _sheet_paths(z)
    wb = load_workbook(path, data_only=True)
    out = []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        hdr_row, cols = None, {}
        for r in range(1, min(ws.max_row, 20) + 1):
            vals = {c: _clean(ws.cell(r, c).value).lower() for c in range(1, ws.max_column + 1)}
            if any(v == "deskripsi temuan" for v in vals.values()):
                hdr_row = r
                for c, v in vals.items():
                    if v in HEAD_KEYS:
                        cols[HEAD_KEYS[v]] = c
                break
        if not hdr_row or "desc" not in cols:
            continue
        title = _clean(ws.cell(1, 1).value) or ws.title
        imgs = _cell_images(z, spaths.get(ws.title, "")) if ws.title in spaths else {}
        from openpyxl.utils import get_column_letter as L
        rows = []
        prev_no = 0
        for r in range(hdr_row + 1, ws.max_row + 1):
            desc = _clean(ws.cell(r, cols["desc"]).value)
            if not desc:
                continue
            no = ws.cell(r, cols["no"]).value if "no" in cols else None
            try:
                no = int(no)
            except (TypeError, ValueError):
                no = prev_no + 1
            prev_no = no

            def g(k):
                return _clean(ws.cell(r, cols[k]).value) if k in cols else ""
            item = dict(no=no, row=r, desc=desc, plan=g("plan"), status=g("status"), remark=g("remark"),
                        after_text=g("img_after"), before=[], after=[], other=[])
            for c in range(1, ws.max_column + 1):
                ref = f"{L(c)}{r}"
                for fn, data in imgs.get(ref, []):
                    if c == cols.get("img_before"):
                        item["before"].append((fn, data))
                    elif c == cols.get("img_after"):
                        item["after"].append((fn, data))
                    else:
                        item["other"].append((fn, data))
            rows.append(item)
        key = re.sub(r"[^a-z0-9]", "", ws.title.lower().replace("punchlist", ""))
        out.append(dict(sheet=ws.title, title=title, key=key, rows=rows))
    return out


# ------------------------------------------------------------------ import
def _add_photos(db, key, sh, it, iid, exists, st):
    for kind, lst in (("before", it["before"]), ("after", it["after"]), ("other", it["other"])):
        for k, (fn, data) in enumerate(lst):
            auid = _uid(key, "att", sh["key"], it["row"], kind, k)
            if exists("attachment", auid):
                continue
            db._insert("attachment", dict(
                uuid=auid, issue_id=iid, kind=kind, filename=fn, data=_resize(data),
                caption={"before": "Dokumentasi temuan (FAT)", "after": "Dokumentasi penyelesaian",
                         "other": "Lampiran"}[kind]))
            st["photos"] += 1


def import_fat_punchlist(db: Database, path: str, site_name: str | None = None, project_id: int | None = None,
                         report_date: str | None = None, progress=None) -> dict:
    progress = progress or (lambda m: None)
    fname = os.path.basename(path)
    base = os.path.splitext(fname)[0]
    m = re.search(r"(\d{2})(\d{2})(\d{4})", base)
    if not report_date and m:
        try:
            report_date = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            report_date = None
    report_date = report_date or dt.date.today().isoformat()
    if not site_name:
        mm = re.search(r"(GI[ _][A-Za-z0-9 _]+?)(?:_\d{6,8}|$)", base, re.I)
        site_name = (mm.group(1).replace("_", " ").strip() if mm else "Site").upper().replace("GI ", "GI ")
    progress("Membaca Excel & foto…")
    sheets = parse_workbook(path)
    key = f"fat|{site_name.lower()}"
    st = {"panels": 0, "issues": 0, "photos": 0, "skipped": 0}

    def exists(table, uid):
        return db.q1(f"SELECT id FROM {table} WHERE uuid=?", (uid,))

    # project
    if project_id is None:
        puid = _uid(key, "project")
        r = exists("project", puid)
        if r:
            project_id = r["id"]
            db._update("project", project_id, {"deleted": 0})
        else:
            code = re.sub(r"[^A-Z0-9]", "", site_name.upper().replace("GI", "", 1))[:8] or "FAT"
            letters, digits = re.sub(r"\d", "", code), re.sub(r"\D", "", code)
            prefix = (letters[:2] + digits[:2]) if digits else letters[:3]
            project_id = db._insert("project", dict(
                uuid=puid, code=f"{code}-FAT", name=f"FAT SAS {site_name}", issue_prefix=prefix or "PL",
                description=f"Diimpor dari {fname} (status per {report_date})."))
            db.log(project_id, "project", project_id, "import", f"Project dibuat dari {fname}")
    suid = _uid(key, "site")
    r = exists("site", suid)
    site_id = r["id"] if r else db._insert("site", dict(uuid=suid, project_id=project_id, name=site_name, sort=1))
    cats = db.get_list_setting("categories")
    if "Label & Marking" not in cats:
        cats.insert(cats.index("Dokumen") if "Dokumen" in cats else len(cats), "Label & Marking")
        import json
        db.set_setting("categories", json.dumps(cats))
    for sh in sheets:
        hint = PANEL_HINTS.get(sh["key"], ("PANEL-" + sh["key"].upper(), sh["title"], sh["key"].title(), ""))
        panel_id = None
        if hint:
            tag, name, bay, ptype = hint
            pnuid = _uid(key, "panel", sh["key"])
            r = exists("panel", pnuid)
            if r:
                panel_id = r["id"]
            else:
                panel_id = db._insert("panel", dict(uuid=pnuid, site_id=site_id, tag=tag, name=name, bay=bay,
                                                     panel_type=ptype, remarks=sh["title"], sort=st["panels"] + 1))
                st["panels"] += 1
        progress(f"Import {sh['sheet']}…")
        for it in sh["rows"]:
            iuid = _uid(key, "issue", sh["key"], it["row"])
            ex = exists("issue", iuid)
            if ex:
                # punch sudah ada (mis. hasil sinkron dari cloud tanpa foto): tetap lengkapi foto yang belum ada
                st["skipped"] += 1
                _add_photos(db, key, sh, it, ex["id"], exists, st)
                continue
            status = STATUS_MAP.get(it["status"].strip().lower(), "Open")
            sev, cat = classify(it["desc"], it["plan"])
            desc = [f"Sumber: {fname} · {sh['sheet']} No. {it['no']}"]
            if it["remark"]:
                desc.append(f"Remark: {it['remark']}")
            action = it["plan"]
            if it["after_text"]:
                action = (action + "\n" if action else "") + f"Dokumentasi: {it['after_text']}"
            title = re.sub(r"\s+", " ", it["desc"]).strip()
            iid = db._insert("issue", dict(
                uuid=iuid, project_id=project_id, site_id=site_id, panel_id=panel_id,
                code=db.next_issue_code(project_id), title=title, description="\n".join(desc), category=cat,
                severity=sev, status=status, pic="", raised_by="FAT", raised_date=report_date,
                closed_date=report_date if status == "Closed" else None,
                verified_by="", action=action))
            st["issues"] += 1
            _add_photos(db, key, sh, it, iid, exists, st)
    db.log(project_id, "issue", None, "import",
           f"Import {fname}: {st['issues']} punch, {st['photos']} foto, {st['panels']} panel baru")
    st["project_id"] = project_id
    return st
