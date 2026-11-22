"""Import / export Excel (openpyxl) — v2."""
from __future__ import annotations

import datetime as dt
import os

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .db import SEV_LABEL, Database, parse_date, today

HEAD_FILL = PatternFill("solid", fgColor="0E1A2B")
HEAD_FONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="D5DBE3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
RES_FILL = {"OK": ("DCFCE7", "166534"), "NG": ("FEE2E2", "991B1B"), "NA": ("E2E8F0", "334155")}
SEV_FILL = {"Critical": "DC2626", "Major": "EA580C", "Minor": "CA8A04"}
STATUS_FILL = {"Lulus": "DCFCE7", "Diterima": "CCFBF1", "Ada temuan": "FEE2E2", "Sedang dicek": "DBEAFE"}
LATE = PatternFill("solid", fgColor="FEE2E2")

PANEL_COLS = ["Site", "Bay", "Tag", "Nama", "Tipe", "Vendor", "Serial No", "Catatan", "Template"]
ALIASES = {
    "site": "Site", "gi": "Site", "gardu": "Site", "site / gi": "Site", "gi / site": "Site",
    "bay": "Bay",
    "tag": "Tag", "tag panel": "Tag", "panel tag": "Tag", "kode panel": "Tag", "panel": "Tag",
    "nama": "Nama", "nama panel": "Nama", "deskripsi": "Nama", "description": "Nama", "name": "Nama",
    "tipe": "Tipe", "type": "Tipe", "tipe panel": "Tipe",
    "vendor": "Vendor", "pabrikan": "Vendor", "manufacturer": "Vendor",
    "serial no": "Serial No", "sn": "Serial No", "serial number": "Serial No", "s/n": "Serial No",
    "catatan": "Catatan", "remarks": "Catatan", "keterangan": "Catatan",
    "template": "Template", "template checklist": "Template", "checklist": "Template",
}


def _head(ws, row, headers, widths=None):
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        if widths and c - 1 < len(widths):
            ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    ws.row_dimensions[row].height = 22


def _cell(ws, r, c, v, date=False, wrap=False):
    cell = ws.cell(row=r, column=c, value=v)
    cell.border = BORDER
    cell.alignment = Alignment(vertical="top", wrap_text=wrap)
    if date:
        cell.number_format = "DD-MM-YYYY"
    return cell


def guess_template(db: Database, panel_type: str, name: str = ""):
    tpls = db.templates()
    if not tpls:
        return None
    if name:
        for t in tpls:
            if t["name"].strip().lower() == name.strip().lower():
                return t["id"]
    from .i18n import lang
    rtu = any(k in (panel_type or "").lower() for k in ("rtu", "gateway", "station"))
    en = lang() == "en"
    key = "rtu" if rtu else ("protection" if en else "proteksi")
    for t in sorted(tpls, key=lambda t: t["name"].rstrip().endswith("EN") != en):
        if key in t["name"].lower():
            return t["id"]
    return tpls[0]["id"]


# ---------------------------------------------------------------- panel import
def write_panel_template(db: Database, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Panel"
    _head(ws, 1, PANEL_COLS, [16, 14, 14, 32, 14, 16, 14, 24, 38])
    ex = [["GI Contoh", "Line 1", "CRP-L1", "Control & Relay Panel Line 1", "CRP", "Vendor", "SN001", "", ""],
          ["GI Contoh", "Common", "GW-01", "Gateway & Station Panel", "RTU / Gateway", "Vendor", "SN002", "", ""]]
    for r, row in enumerate(ex, start=2):
        for c, v in enumerate(row, start=1):
            _cell(ws, r, c, v)
    names = [t["name"] for t in db.templates()]
    if names:
        lst = wb.create_sheet("_list")
        for i, n in enumerate(names, start=1):
            lst.cell(row=i, column=1, value=n)
        lst.sheet_state = "hidden"
        dv = DataValidation(type="list", formula1=f"=_list!$A$1:$A${len(names)}", allow_blank=True)
        ws.add_data_validation(dv)
        dv.add("I2:I2000")
    ws.freeze_panes = "D2"
    info = wb.create_sheet("Petunjuk")
    lines = [
        "PETUNJUK IMPORT PANEL",
        "",
        "1. Isi sheet 'Panel', satu baris per panel. Baris contoh boleh dihapus/ditimpa.",
        "2. Kolom wajib: Site dan Tag. Site yang belum ada dibuat otomatis.",
        "3. Kolom Template (opsional): pilih template checklist. Kalau kosong, dipilih otomatis dari Tipe "
        "(RTU/Gateway → template RTU, lainnya → Panel Proteksi & Kontrol).",
        "4. Tag yang sudah ada di site yang sama akan di-UPDATE (tidak dobel, hasil cek tidak hilang).",
    ]
    for i, l_ in enumerate(lines, start=1):
        info.cell(row=i, column=1, value=l_).font = Font(bold=(i == 1), size=12 if i == 1 else 11)
    info.column_dimensions["A"].width = 120
    wb.save(path)


def import_panels(db: Database, project_id, path) -> dict:
    wb = load_workbook(path, data_only=True)
    ws = wb["Panel"] if "Panel" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = None
    for i, r in enumerate(rows[:15]):
        norm = [str(c).strip().lower() if c is not None else "" for c in r]
        if any(ALIASES.get(n) == "Tag" for n in norm) and any(ALIASES.get(n) == "Site" for n in norm):
            hdr = i
            break
    if hdr is None:
        raise ValueError("Header tidak ditemukan. Pastikan ada kolom 'Site' dan 'Tag' (pakai template import).")
    colmap = {}
    for j, h in enumerate(rows[hdr]):
        key = ALIASES.get(str(h).strip().lower()) if h is not None else None
        if key and key not in colmap:
            colmap[key] = j
    added = updated = skipped = with_tpl = 0
    for r in rows[hdr + 1:]:
        def g(k):
            j = colmap.get(k)
            v = r[j] if j is not None and j < len(r) else None
            if isinstance(v, float) and v.is_integer():
                v = int(v)   # angka dari Excel: 101.0 → "101"
            return "" if v is None else str(v).strip()
        site, tag = g("Site"), g("Tag")
        if site.lower() == "gi contoh":   # baris contoh dari template, jangan ikut diimpor
            skipped += 1
            continue
        if not site or not tag:
            if any(c not in (None, "") for c in r):
                skipped += 1
            continue
        sid = db.get_or_create_site(project_id, site)
        vals = dict(bay=g("Bay"), name=g("Nama"), panel_type=g("Tipe"), vendor=g("Vendor"), serial_no=g("Serial No"),
                    remarks=g("Catatan"))
        ex = db.q1("SELECT id FROM panel WHERE site_id=? AND deleted=0 AND lower(tag)=lower(?)", (sid, tag))
        if ex:
            db._update("panel", ex["id"], vals)
            updated += 1
        else:
            tid = guess_template(db, vals["panel_type"], g("Template"))
            db.add_panel(sid, tag, template_id=tid, **vals)
            added += 1
            with_tpl += 1 if tid else 0
    db.log(project_id, "panel", None, "import", f"Import Excel: {added} panel baru, {updated} di-update")
    return {"added": added, "updated": updated, "skipped": skipped, "tpl": with_tpl}


# ---------------------------------------------------------------- templates
def export_template(db: Database, tid, path):
    t = db.template(tid)
    wb = Workbook()
    ws = wb.active
    ws.title = "Checklist"
    ws["A1"] = t["name"]
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = t["description"]
    _head(ws, 4, ["Section", "Item pengecekan", "Kriteria terima", "Satuan"], [28, 60, 26, 10])
    for i, it in enumerate(db.template_items(tid), start=5):
        for c, v in enumerate([it["section"], it["description"], it["criteria"], it["unit"]], start=1):
            _cell(ws, i, c, v, wrap=c == 2)
    wb.save(path)


def import_template(db: Database, path, name=None):
    wb = load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = None
    for i, r in enumerate(rows[:15]):
        norm = [str(c).strip().lower() if c else "" for c in r]
        if "section" in norm and any(n.startswith("item") for n in norm):
            hdr = i
            break
    if hdr is None:
        raise ValueError("Header 'Section' dan 'Item pengecekan' tidak ditemukan.")
    norm = [str(c).strip().lower() if c else "" for c in rows[hdr]]
    ci = {"sec": norm.index("section"), "item": next(k for k, n in enumerate(norm) if n.startswith("item"))}
    ci["crit"] = next((k for k, n in enumerate(norm) if n.startswith("kriteria") or n.startswith("criteria")), None)
    ci["unit"] = next((k for k, n in enumerate(norm) if n in ("satuan", "unit")), None)
    items = []
    for r in rows[hdr + 1:]:
        def g(k):
            j = ci[k]
            return "" if j is None or j >= len(r) or r[j] is None else str(r[j]).strip()
        if g("item"):
            items.append((g("sec") or "Umum", g("item"), g("crit"), g("unit")))
    if not items:
        raise ValueError("Tidak ada item di file.")
    nm = name or (str(rows[0][0]).strip() if hdr > 0 and rows[0] and rows[0][0] else
                  os.path.splitext(os.path.basename(path))[0])
    existing = {t["name"] for t in db.templates()}
    base, k = nm, 2
    while nm in existing:
        nm = f"{base} ({k})"
        k += 1
    return db.add_template(nm, "Diimpor dari Excel", items), len(items)


# ---------------------------------------------------------------- export all
def export_project(db: Database, project_id, path, site_id=None):
    wb = Workbook()
    p = db.project(project_id)
    t = today()
    ov = db.panel_overview(project_id, site_id)

    ws = wb.active
    ws.title = "Ringkasan Panel"
    ws["A1"] = f"{p['code']} — {p['name']}"
    ws["A1"].font = Font(bold=True, size=14, color="0E1A2B")
    ws["A2"] = f"Diekspor {dt.datetime.now():%d-%m-%Y %H:%M} oleh {db.user}"
    ws["A2"].font = Font(italic=True, color="64748B")
    hdr = ["Site", "Bay", "Tag", "Nama", "Tipe", "Status", "Item", "Diuji", "% diuji", "OK", "NG", "N/A",
           "Punch open", "Punch A open", "Punch total", "Diterima oleh", "Tgl diterima"]
    _head(ws, 4, hdr, [14, 12, 14, 30, 12, 14, 7, 7, 8, 6, 6, 6, 10, 11, 10, 16, 12])
    for r, o in enumerate(ov, start=5):
        pn, s, pu = o["panel"], o["stats"], o["punch"]
        vals = [pn["site_name"], pn["bay"], pn["tag"], pn["name"], pn["panel_type"], o["status"], s["total"],
                s["checked"], round(s["pct"], 1), s["OK"], s["NG"], s["NA"], pu.get("open", 0),
                pu.get("Critical", 0), pu.get("total", 0), pn["accepted_by"], parse_date(pn["accepted_at"])]
        for c, v in enumerate(vals, start=1):
            _cell(ws, r, c, v, date=c == 17)
        if o["status"] in STATUS_FILL:
            ws.cell(row=r, column=6).fill = PatternFill("solid", fgColor=STATUS_FILL[o["status"]])
        if s["NG"]:
            ws.cell(row=r, column=11).font = Font(bold=True, color="DC2626")
    ws.auto_filter.ref = f"A4:Q{max(4, 4 + len(ov))}"
    ws.freeze_panes = "D5"

    wc = wb.create_sheet("Hasil Cek")
    _head(wc, 1, ["Site", "Bay", "Tag", "No", "Section", "Item pengecekan", "Kriteria", "Satuan", "Hasil", "Nilai",
                  "Catatan", "Dicek oleh", "Tgl cek"], [14, 12, 14, 5, 24, 46, 20, 8, 8, 12, 30, 14, 12])
    r = 2
    for o in ov:
        pn = o["panel"]
        for k, c in enumerate(db.panel_checks(pn["id"]), start=1):
            vals = [pn["site_name"], pn["bay"], pn["tag"], k, c["section"], c["description"], c["criteria"], c["unit"],
                    c["result"] or "", c["value"], c["remark"], c["checked_by"], parse_date(c["checked_at"])]
            for col, v in enumerate(vals, start=1):
                _cell(wc, r, col, v, date=col == 13, wrap=col in (6, 11))
            if c["result"] in RES_FILL:
                bg, fg = RES_FILL[c["result"]]
                cell = wc.cell(row=r, column=9)
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(bold=True, color=fg)
                cell.alignment = Alignment(horizontal="center", vertical="top")
            r += 1
    wc.auto_filter.ref = f"A1:M{max(1, r - 1)}"
    wc.freeze_panes = "D2"

    wi = wb.create_sheet("Punch List")
    hdr = ["Kode", "Kategori A/B/C", "Site", "Panel", "Item cek terkait", "Judul", "Deskripsi", "Kategori",
           "Status", "PIC", "Ditemukan oleh", "Tgl temuan", "Target", "Tgl close", "Verifikasi", "Tindakan perbaikan"]
    _head(wi, 1, hdr, [10, 14, 14, 12, 34, 36, 44, 18, 14, 16, 14, 12, 12, 12, 14, 36])
    for r, s in enumerate(db.issues(project_id, site_id=site_id), start=2):
        vals = [s["code"], SEV_LABEL.get(s["severity"], s["severity"]), s["site_name"], s["panel_tag"] or "(umum)",
                s["check_desc"] or "", s["title"], s["description"], s["category"], s["status"], s["pic"],
                s["raised_by"], parse_date(s["raised_date"]), parse_date(s["due_date"]), parse_date(s["closed_date"]),
                s["verified_by"], s["action"]]
        for c, v in enumerate(vals, start=1):
            _cell(wi, r, c, v, date=c in (12, 13, 14), wrap=c in (5, 6, 7, 16))
        sc = wi.cell(row=r, column=2)
        if s["severity"] in SEV_FILL:
            sc.fill = PatternFill("solid", fgColor=SEV_FILL[s["severity"]])
            sc.font = Font(bold=True, color="FFFFFF")
        if s["status"] != "Closed" and s["due_date"] and s["due_date"] < t:
            wi.cell(row=r, column=13).fill = LATE
    wi.auto_filter.ref = f"A1:P{max(1, wi.max_row)}"
    wi.freeze_panes = "B2"
    wb.save(path)
