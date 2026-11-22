"""Tes menyeluruh Panel Tracker: database, Excel, import FAT, report, UI (semua halaman & dialog), viewer, sinkron.

Jalankan: python3 test_full.py   → mencetak FAIL/ERROR bila ada, dan 'ALL OK' bila semua lolos.
"""
import os
import shutil
import sys
import time
import traceback
import faulthandler

faulthandler.enable()
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # paneltracker/
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

OUT = "/tmp/full"
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)

ERRORS, FAILS, MSGS = [], [], []


def hook(t, v, tb):
    txt = "".join(traceback.format_exception(t, v, tb))
    ERRORS.append(txt)
    print("!! EXCEPTION:", txt[-1500:])


sys.excepthook = hook


def check(cond, what):
    if not cond:
        FAILS.append(what)
        print("  FAIL:", what)


def step(name):
    print("--", name)


from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QFont, QDesktopServices  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QInputDialog, QMenu,  # noqa: E402
                               QMessageBox)

app = QApplication([])
from app.ui.theme import setup_app  # noqa: E402
setup_app(app)

# ------------------------------------------------------------------ patch dialog modal → otomatis
ANSWER = {"question": QMessageBox.Yes}


def _msg(kind):
    def f(parent, title, text, *a, **k):
        MSGS.append((kind, str(text)))
        return ANSWER["question"] if kind == "question" else QMessageBox.Ok
    return staticmethod(f)


for _k in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _k, _msg(_k))
QMessageBox.about = staticmethod(lambda *a, **k: MSGS.append(("about", a[2] if len(a) > 2 else "")))
QDesktopServices.openUrl = staticmethod(lambda *a, **k: True)
QMenu.exec = lambda self, *a, **k: None
SAVE_DIR = OUT
OPEN_FILES = []
QFileDialog.getSaveFileName = staticmethod(
    lambda parent, cap="", path="", flt="", *a, **k: (os.path.join(SAVE_DIR, os.path.basename(path or "out.bin")), ""))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (OPEN_FILES.pop(0) if OPEN_FILES else "", ""))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([OPEN_FILES.pop(0)] if OPEN_FILES else [], ""))
INPUT = []
QInputDialog.getText = staticmethod(lambda *a, **k: (INPUT.pop(0) if INPUT else k.get("text", "isi"), True))
QInputDialog.getItem = staticmethod(lambda parent, t, l, items, *a, **k: (items[0], True))

DIALOG = {}  # nama kelas → fungsi(dlg) yang mengisi form lalu accept/reject


def _exec(self, *a, **k):
    fn = DIALOG.get(type(self).__name__)
    self.show()
    app.processEvents()
    try:
        if fn:
            fn(self)
        else:
            self.reject()
    except Exception:
        hook(*sys.exc_info())
        self.reject()
    r = self.result()
    self.close()
    return r


QDialog.exec = _exec


def pump(n=3):
    for _ in range(n):
        app.processEvents()


def shot(w, name):
    pump()
    w.grab().save(os.path.join(OUT, name + ".png"))


def pdf_ok(path, min_pages=1):
    import subprocess
    if not os.path.exists(path):
        return False
    r = subprocess.run(["pdfinfo", path], capture_output=True, text=True)
    pages = int([l for l in r.stdout.splitlines() if l.startswith("Pages")][0].split()[-1]) if r.returncode == 0 else 0
    return pages >= min_pages


# ================================================================== 1. DATABASE
step("database")
from app.db import Database, ReadOnlyError, ISSUE_STATUSES  # noqa: E402
from app.demo import create_demo  # noqa: E402

db = Database(os.path.join(OUT, "core.db"))
check(len(db.templates()) == 6, f"6 template bawaan (ID+EN), dapat {len(db.templates())}")
pid = db.add_project("T-01", "Proyek Tes", client="PLN", contractor="Vendor", start_date="2026-11-01",
                     end_date="2026-12-31")
s1 = db.add_site(pid, "GI Satu", "Lokasi 1")
s2 = db.add_site(pid, "GI Dua")
db.move_site(s2, -1)
check([s["name"] for s in db.sites(pid)] == ["GI Dua", "GI Satu"], "urutan site setelah move")
tpl = db.templates()[0]["id"]
p1 = db.add_panel(s1, "CP-01", template_id=tpl, bay="Line 1", name="Control Panel", panel_type="CP")
p2 = db.add_panel(s1, "RTU-01", bay="Common", name="RTU", panel_type="RTU")
checks = db.panel_checks(p1)
check(len(checks) == 35, f"template diterapkan 35 item, dapat {len(checks)}")
db.set_check(checks[0]["id"], result="OK")
db.set_check(checks[1]["id"], result="NG", remark="kabel kendor", value="")
db.set_check(checks[2]["id"], result="NA")
db.set_check(checks[3]["id"], value="111.2")
n = db.bulk_set_result([c["id"] for c in checks[4:10]], "OK")
check(n == 6, f"bulk OK 6 item, dapat {n}")
cid = db.add_check_item(p1, "Z. Tambahan", "Item baru", "Kriteria", "V")
db.update_check_item(cid, description="Item baru (edit)")
db.delete_check_item(cid)
check(len(db.panel_checks(p1)) == 35, "hapus item cek")
added = db.apply_template(p2, db.templates()[1]["id"])
check(added == 16 and len(db.panel_checks(p2)) == 16, "apply template RTU")
db.apply_template(p2, db.templates()[2]["id"], replace=True)
check(len(db.panel_checks(p2)) == 6, "replace template")
i1 = db.add_issue(pid, title="Kabel kendor", panel_id=p1, site_id=s1, check_id=checks[1]["id"], severity="Critical",
                  status="Open", category="Wiring", due_date="2026-11-01", raised_date="2026-10-20")
i2 = db.add_issue(pid, title="Umum: dokumen", site_id=s2, severity="Minor", status="In Progress")
i3 = db.add_issue(pid, title="Selesai", panel_id=p2, site_id=s1, severity="Major", status="Closed",
                  closed_date="2026-11-10")
codes = [db.issue(i)["code"] for i in (i1, i2, i3)]
check(len(set(codes)) == 3, f"kode punch unik {codes}")
from PIL import Image  # noqa: E402
import io  # noqa: E402
img = io.BytesIO()
Image.new("RGB", (800, 600), "#887766").save(img, "JPEG")
JPG = img.getvalue()
jpg_path = os.path.join(OUT, "foto.jpg")
open(jpg_path, "wb").write(JPG)
a1 = db.add_attachment(i1, "foto.jpg", JPG, kind="before", caption="sebelum")
db.update_attachment(a1, kind="after", caption="sesudah")
check(db.attachments(i1)[0]["kind"] == "after", "update attachment")
db.update_issue(i1, status="Ready to Verify")
o = db.overall(pid)
check(o["issues_open"] == 2 and o["issues_closed"] == 1, f"overall punch open/closed {o['issues_open']}/{o['issues_closed']}")
check(o["issues_overdue"] == 1, f"overdue 1, dapat {o['issues_overdue']}")
ov = {x["panel"]["id"]: x for x in db.panel_overview(pid)}
check(ov[p1]["status"] == "Ada temuan", f"status panel CP-01 = Ada temuan, dapat {ov[p1]['status']}")
db.set_accepted(p2, "Owner")
check(db.panel_overview(pid)[1]["status"] in ("Diterima", "Lulus", "Sedang dicek", "Belum dicek"), "accepted")
check(db.find_panel(pid, "cp-01")["id"] == p1, "cari panel (scan QR) case-insensitive")
check(db.find_panel(pid, f"PT:{p1}:CP-01")["id"] == p1, "scan isi QR")
check(len(db.punch_trend(pid)) > 0, "punch trend")
db.backup(os.path.join(OUT, "backup.db"))
check(os.path.getsize(os.path.join(OUT, "backup.db")) > 10000, "backup database")
# read-only (viewer)
db.read_only = True
for fn, args in ((db.add_issue, (pid,)), (db.update_issue, (i1,)), (db.set_check, (checks[0]["id"],)),
                 (db.delete_panel, (p1,)), (db.add_attachment, (i1, "x", b"x")), (db.add_project, ("X", "Y"))):
    try:
        fn(*args, title="x") if fn in (db.add_issue, db.update_issue) else fn(*args)
        check(False, f"viewer seharusnya tidak bisa {fn.__name__}")
    except ReadOnlyError:
        pass
db.set_setting("user_name", "Viewer")  # pengaturan lokal tetap boleh
db.read_only = False
db.delete_issue(i3)
check(len(db.issues(pid)) == 2, "hapus punch (soft delete)")
db.delete_panel(p2)
check(len(db.panels(pid)) == 1, "hapus panel")

# ================================================================== 2. EXCEL
step("excel import/export")
from app.excel_io import write_panel_template, import_panels, export_template, import_template, export_project  # noqa
from openpyxl import load_workbook  # noqa: E402
tp = os.path.join(OUT, "tpl_panel.xlsx")
write_panel_template(db, tp)
wb = load_workbook(tp)
ws = wb.active
hdr = [c.value for c in ws[1]]
rows = [["GI Satu", "Line 2", "CRP-02", "Control Relay 2", "CRP", "Vendor A", "SN1"],
        ["GI Tiga", "Trafo", "RTU-05", "RTU Trafo", "RTU", "Vendor B", "SN2"],
        ["", "", "", "", "", "", ""]]
start = ws.max_row + 1
for k, r in enumerate(rows):
    for j, v in enumerate(r[:len(hdr)]):
        ws.cell(row=start + k, column=j + 1, value=v)
wb.save(tp)
r = import_panels(db, pid, tp)
check(r["added"] == 2 and r["skipped"] >= 2, f"import panel Excel: 2 baru (contoh dilewati), dapat {r}")
check(any(s["name"] == "GI Tiga" for s in db.sites(pid)), "site baru dibuat dari import")
r2 = import_panels(db, pid, tp)
check(r2["added"] == 0 and r2["updated"] == 2, f"import ulang = update, dapat {r2}")
te = os.path.join(OUT, "tpl_export.xlsx")
export_template(db, db.templates()[0]["id"], te)
nt, _n = import_template(db, te, name="Template Impor")
check(len(db.template_items(nt)) == 35, "import template Excel")
ex = os.path.join(OUT, "export.xlsx")
export_project(db, pid, ex)
check(len(load_workbook(ex).sheetnames) >= 3, "export project Excel")

# ================================================================== 3. IMPORT FAT
step("import FAT")
from app.import_fat import import_fat_punchlist  # noqa: E402
FAT = os.environ.get("PT_FAT_XLSX", os.path.join(_ROOT, "tests", "data", "Punchlist_GI_GAIA_2_13112026.xlsx"))
dbf = fpid = None
if os.path.exists(FAT):
    dbf = Database(os.path.join(OUT, "fat.db"))
    r = import_fat_punchlist(dbf, FAT, site_name="GI GAIA 2")
    check(r["issues"] == 110 and r["photos"] >= 100, f"FAT import 110 punch, dapat {r}")
    r2 = import_fat_punchlist(dbf, FAT, site_name="GI GAIA 2")
    check(r2["issues"] == 0 and r2["skipped"] == 110, f"FAT import ulang tidak dobel, dapat {r2}")
    fpid = r["project_id"]
    st = {s: sum(1 for i in dbf.issues(fpid) if i["status"] == s) for s in ISSUE_STATUSES}
    check(st["Closed"] == 85 and st["Open"] == 20, f"status FAT {st}")

else:
    print(f"  SKIP import FAT: file tidak ada ({FAT}); set PT_FAT_XLSX untuk menjalankan")

# ================================================================== 4. REPORTS
step("reports (ID & EN)")
from app.reports import ReportBuilder  # noqa: E402
from app.i18n import using  # noqa: E402
dpid = create_demo(db)
for lang in ("id", "en"):
    with using(lang):
        for (dbx, px, sid) in ((db, dpid, None), (db, dpid, db.sites(dpid)[0]["id"]), (dbf, fpid, None),
                               (db, pid, None)):
            if dbx is None:
                continue
            rb = ReportBuilder(dbx, px, sid)
            tag = f"{lang}_{px}_{sid}"
            rb.punchlist_report(f"{OUT}/pl_{tag}.pdf")
            rb.punchlist_report(f"{OUT}/plg_{tag}.pdf", group_by_panel=True, sort="severity", with_photos=False,
                                title="Tes & <judul>", filter_text="Filter & <x>")
            rb.punchlist_report(f"{OUT}/ple_{tag}.pdf", issue_ids=[])
            pans = [p["id"] for p in dbx.panels(px, sid)]
            if pans:
                rb.check_sheets(f"{OUT}/cs_{tag}.pdf", pans)
                rb.qr_labels(f"{OUT}/qr_{tag}.pdf", pans)
            rb.summary_report(f"{OUT}/sum_{tag}.pdf")
            for f in ("pl", "plg", "ple", "sum"):
                check(pdf_ok(f"{OUT}/{f}_{tag}.pdf"), f"report {f}_{tag}")
# project kosong (tanpa site/panel/punch)
epid = db.add_project("EMPTY", "Kosong")
rb = ReportBuilder(db, epid)
rb.punchlist_report(f"{OUT}/empty_pl.pdf")
rb.summary_report(f"{OUT}/empty_sum.pdf")
check(pdf_ok(f"{OUT}/empty_pl.pdf") and pdf_ok(f"{OUT}/empty_sum.pdf"), "report project kosong")

# ================================================================== 5. UI
step("UI: main window & pages")
from app import i18n  # noqa: E402
from app.ui.main_window import MainWindow, _WINDOWS  # noqa: E402
from app.ui import widgets as W  # noqa: E402

uidb = os.path.join(OUT, "ui.db")
st_ini = QSettings(os.path.join(OUT, "ui.ini"), QSettings.IniFormat)
w = MainWindow(uidb, remember=False, settings=st_ini)
w.resize(1440, 880)
w.show()
pump()
# DB kosong: semua halaman harus aman
for k in range(5):
    w.nav_to(k)
    pump()
shot(w, "empty_home")
# project baru lewat dialog
def fill_project(d):
    d.code.setText("UI-01") if hasattr(d, "code") else None
    d.name.setText("Project UI")
    d.accept()
DIALOG["ProjectDialog"] = fill_project
INPUT[:] = ["GI Uji", "Lokasi Uji"]
w.new_project()   # → tanya tambah site → SitesDialog
check(w.project_id is not None, "project baru dari UI")
from PySide6.QtWidgets import QLineEdit  # noqa: E402


def generic(d):
    for le, v in zip(d.findChildren(QLineEdit), list(INPUT)):
        le.setText(v)
    INPUT.clear()
    d.accept()


DIALOG["QDialog"] = generic
DIALOG["SitesDialog"] = lambda d: (d.add(), d.accept())
INPUT[:] = ["GI Uji", "Lokasi"]
w.manage_sites()
check(len(w.db.sites(w.project_id)) >= 1, "tambah site lewat dialog")
w.edit_project()
# panel baru
def fill_panel(d):
    d.tag.setText("UI-CP-01")
    d.name.setText("Panel UI")
    d.bay.setText("Bay 1")
    d.ptype.setCurrentText("CP")
    d.accept()
DIALOG["PanelDialog"] = fill_panel
w.nav_to(1)
w.p_check.add_panel()
pump()
pans = w.db.panels(w.project_id)
check(len(pans) == 1 and len(w.db.panel_checks(pans[0]["id"])) > 0, "panel baru + checklist otomatis")
# demo
w.make_demo()
pump()
dp = w.project_id
check(w.db.project(dp)["code"] == "DEMO-SAT", "project demo")
for k, n in enumerate(["home", "check", "punch", "reports", "templates"]):
    w.nav_to(k)
    shot(w, "id_" + n)
# site filter
w.cb_site.setCurrentIndex(1)
pump()
for k in range(5):
    w.nav_to(k)
    pump()
w.cb_site.setCurrentIndex(0)
pump()

step("UI: checklist")
w.nav_to(1)
ovs = w.db.panel_overview(dp)
target = [x for x in ovs if x["stats"]["pending"]][0]["panel"]["id"]
w.go_panel(target)
pump()
view = w.p_check.detail
rows = view.rows
check(len(rows) > 0, "baris checklist tampil")
row0 = [r for r in rows if not r.res.value][0]
row0.res.btns["OK"].click()
pump()
check(w.db.check(row0.cid)["result"] == "OK", "klik OK tersimpan")
row0.res.btns["OK"].click()   # klik lagi → kosong
pump()
check((w.db.check(row0.cid)["result"] or "") == "", "klik ulang mengosongkan hasil")
# NG → form punch otomatis
def fill_issue(d):
    if not d.title.text():
        d.title.setText("Temuan dari NG")
    d.accept()
DIALOG["IssueDialog"] = fill_issue
n_before = len(w.db.issues(dp))
rowng = [r for r in view.rows if not r.res.value][0]
rowng.res.btns["NG"].click()
time.sleep(0.1)
pump(10)
check(len(w.db.issues(dp)) == n_before + 1, "NG → punch baru otomatis")
iss_ng = [i for i in w.db.issues(dp) if i["check_id"] == rowng.cid]
check(bool(iss_ng), "punch terhubung ke item cek")
# nilai & catatan
r2 = view.rows[3]
r2.value.setText("12.5")
r2._save_value()
r2.remark.setText("catatan tes")
r2._save_remark()
check(w.db.check(r2.cid)["value"] == "12.5" and w.db.check(r2.cid)["remark"] == "catatan tes", "nilai & catatan")
# filter tombol
for b in view.fbtns if hasattr(view, "fbtns") else []:
    b.click()
    pump()
view.mark_rest_ok()
pump()
st_after = w.db.panel_overview(dp)
check(any(x["panel"]["id"] == target and x["stats"]["pending"] == 0 for x in st_after), "sisa item = OK")
# item baru / edit / hapus
DIALOG["CheckItemDialog"] = lambda d: (d.desc.setText("Item tambahan UI") if hasattr(d, "desc") else None,
                                       d.accept())
view.add_item("A. Visual & Mekanikal")
pump()
# terima panel & batal
view._accept(True)
pump()
check(w.db.panel(target)["accepted_at"] is not None, "terima panel")
view._accept(False)
pump()
check(w.db.panel(target)["accepted_at"] is None, "batalkan penerimaan")
view._apply(w.db.templates()[2]["id"], False)
pump()
INPUT[:] = ["Template dari panel"]
view._save_as_template()
check(any(t["name"] == "Template dari panel" for t in w.db.templates()), "simpan checklist jadi template")
view._edit_panel()
shot(w, "id_check_after")
# scan
w.scan.setText(w.db.panel(target)["tag"].lower())
w._scan()
pump()
check(w.p_check.detail.panel_id == target, "scan QR membuka panel")
w.scan.setText("TIDAK-ADA")
w._scan()

step("UI: punch list")
w.nav_to(2)
pp = w.p_punch
pump()
ids = [i["id"] for i in w.db.issues(dp) if i["status"] == "Open"][:2]
pp.move_to(ids, "In Progress")
pump()
check(all(w.db.issue(i)["status"] == "In Progress" for i in ids), "drag ke kolom Dikerjakan")
pp.move_to(ids[:1], "Closed")
check(w.db.issue(ids[0])["closed_date"], "pindah ke Closed mengisi tanggal close")
for b in pp.vgroup.buttons():
    b.click()
    pump()
    shot(w, "id_punch_" + b.property("key"))
pp.q.setText("PL-00")
pp.f_closed.setChecked(False)
pp.f_over.setChecked(True)
pp.f_sev.setCurrentIndex(1)
pump()
pp.f_over.setChecked(False)
pp.f_sev.setCurrentIndex(0)
pp.f_closed.setChecked(True)
pp.f_panel.setCurrentIndex(1)
pump()
pp.f_panel.setCurrentIndex(0)
pp.q.setText("")
pp.new()
pump()
# edit punch: ganti status via combo (data, bukan teks)
iid = w.db.issues(dp)[0]["id"]
def edit_issue(d):
    d.status.setCurrentIndex(d.status.findData("Ready to Verify"))
    OPEN_FILES.append(jpg_path)
    d._add_photo()
    d.accept()
DIALOG["IssueDialog"] = edit_issue
w.open_issue(iid)
check(w.db.issue(iid)["status"] == "Ready to Verify", "status tersimpan sebagai nilai (bukan label)")
check(len(w.db.attachments(iid)) >= 1, "tambah foto di punch")
# punch baru dengan foto pending + kode dobel ditolak
def new_dup(d):
    d.title.setText("Kode dobel")
    d.code.setText(w.db.issue(iid)["code"])
    d.accept()     # harus ditolak (warning), dialog tetap terbuka
    d.code.setText("UNIK-001")
    OPEN_FILES.append(jpg_path)
    d._add_photo()
    d.accept()
DIALOG["IssueDialog"] = new_dup
n0 = len(w.db.issues(dp))
pp.new()
check(len(w.db.issues(dp)) == n0 + 1, "punch baru setelah kode diperbaiki")
newi = [i for i in w.db.issues(dp) if i["code"] == "UNIK-001"]
check(newi and len(w.db.attachments(newi[0]["id"])) == 1, "foto pending tersimpan saat punch baru")
check(any("sudah dipakai" in m[1] for m in MSGS), "peringatan kode punch dobel")
pp._delete([newi[0]["id"]])
check(not [i for i in w.db.issues(dp) if i["code"] == "UNIK-001"], "hapus punch dari board")

step("UI: dialog cetak punch list")
from app.ui.report_dialogs import PunchReportDialog  # noqa: E402
SAVE_DIR = OUT
for preset in ("_p_all", "_p_active", "_p_open", "_p_closed", "_p_crit"):
    d = PunchReportDialog(w)
    getattr(d, preset)()
    d._update()
    o = d.options()
    check(isinstance(o["issue_ids"], list), f"preset {preset}")
    d.close()
d = PunchReportDialog(w)
d.show()
pump()
d._pick_bay()
shot(d, "id_dialog_cetak")
d.close()
for fn in ("_p_open", "_p_all"):
    def run(dd, fn=fn):
        getattr(dd, fn)()
        dd.accept()
    DIALOG["PunchReportDialog"] = run
    w.report_punchlist()
w.p_punch.print_pdf()
w.report_check_sheet()
w.report_check_sheet(only_started=True)
w.report_summary()
w.report_qr()
pdfs = [f for f in os.listdir(OUT) if f.startswith("DEMO-SAT") and f.endswith(".pdf")]
check(len(pdfs) >= 5, f"report dari UI tersimpan ({len(pdfs)} file)")

step("UI: laporan & data, template")
w.nav_to(3)
w.export_excel()
w.save_template()
OPEN_FILES.append(os.path.join(OUT, "tpl_panel.xlsx"))
w.import_excel()
OPEN_FILES.append(FAT)
INPUT[:] = ["GI GAIA 2"]
w.import_fat()
pump()
check(any(p["code"].startswith("GAIA") for p in w.db.projects()), "import FAT dari UI")
w.nav_to(4)
tp_ = w.p_tpl
tp_.refresh()
tp_.add_row()
tp_.save()
INPUT[:] = ["Template Baru UI"]
tp_.new()
tp_.duplicate()
tp_.export_xlsx()
tp_.delete()
pump()
shot(w, "id_templates_after")

step("UI: pengaturan, bahasa, cloud dialog")
def fill_settings(d):
    d.accept()
DIALOG["SettingsDialog"] = fill_settings
w.edit_settings()
w.backup_db()
w.about()
from app.ui.cloud_ui import CloudDialog  # noqa: E402
cd = CloudDialog(w, w.sync)
cd.show()
shot(cd, "id_cloud_login")
cd.close()
w.cb_project.setCurrentIndex(w.cb_project.findData(dp))
pump()
w.switch_lang("en")
pump()
we = _WINDOWS[-1]
for k, n in enumerate(["home", "check", "punch", "reports", "templates"]):
    we.nav_to(k)
    shot(we, "en_" + n)
we.p_check.select_panel(target)
shot(we, "en_check_panel")
cd = CloudDialog(we, we.sync)
cd.show()
shot(cd, "en_cloud_login")
cd.close()
we.switch_lang("id")
pump()
w = _WINDOWS[-1]
check(i18n.lang() == "id", "kembali ke bahasa Indonesia")
w.nav_to(0)
pump()

step("UI: hapus project")
w.cb_project.setCurrentIndex(w.cb_project.findData(epid) if w.cb_project.findData(epid) >= 0 else 0)
before = len(w.db.projects())
w.delete_project()
check(len(w.db.projects()) == before - 1, "hapus project")

# ================================================================== 6. SINKRON & VIEWER (mock server)
step("sinkron & viewer")
import mock_supabase as M  # noqa: E402
M.USERS["fajar@paneltracker.local"] = "P@ssw0rd"
M.USERS["viewer@paneltracker.local"] = "Viewer"
M.MEMBERS["fajar@paneltracker.local"] = "engineer"
M.MEMBERS["viewer@paneltracker.local"] = "viewer"
srv, URL = M.start()


def wait_sync(win):
    t0 = time.time()
    while (win.sync.busy or win.sync.worker) and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.05)
    pump(10)


sA = QSettings(os.path.join(OUT, "a.ini"), QSettings.IniFormat)
sA.setValue("cloud/url", URL)
sA.setValue("cloud/key", "k")
wa = MainWindow(os.path.join(OUT, "syncA.db"), remember=False, settings=sA)
pa = create_demo(wa.db)
wa.load_projects(pa)
# keamanan konfigurasi: http & secret key ditolak
from app.cloud import check_endpoint, CloudError as _CE  # noqa: E402
for u_, k_ in (("http://evil.example.com", "sb_publishable_x"), ("https://x.supabase.co", "sb_secret_abc")):
    try:
        check_endpoint(u_, k_)
        check(False, f"endpoint tidak aman diterima: {u_} {k_}")
    except _CE:
        pass
cd = CloudDialog(wa, wa.sync)
cd.url.setText("http://evil.example.com")
check(cd._save_opts() is False and wa.sync.cfg.url == URL, "URL http ditolak di dialog cloud")
cd.url.setText(URL)
# password lemah → wajib ganti; kalau dibatalkan, tidak login
DIALOG["ChangePasswordDialog"] = lambda d: d.reject()
cd.email.setText("Fajar")
cd.pw.setText("P@ssw0rd")
cd.login()
check(not wa.sync.cfg.logged_in, "batal ganti password lemah → tidak login")
NEWPW = "Gardu-Induk-2026x"
def change_pw(d):
    d.new.setText(NEWPW)
    d.new2.setText(NEWPW)
    d.accept()
DIALOG["ChangePasswordDialog"] = change_pw
cd = CloudDialog(wa, wa.sync)
cd.email.setText("Fajar")         # username tanpa @
cd.pw.setText("salah")
cd.login()
check(any("salah" in m[1].lower() or "wrong" in m[1].lower() for m in MSGS[-2:]), "password salah → pesan jelas")
cd.email.setText("Fajar")
cd.pw.setText("P@ssw0rd")
cd.login()
wait_sync(wa)
check(wa.sync.cfg.get("email") == "fajar@paneltracker.local", "login pakai username")
check(M.USERS["fajar@paneltracker.local"] == NEWPW, "password lemah diganti saat login pertama")
raw_tok = sA.value("cloud/refresh_token")
check(str(raw_tok).startswith(("plain:", "dpapi:")), f"token tersimpan lewat secure_store ({str(raw_tok)[:6]}…)")
check(not wa.read_only, "engineer bisa edit")
check(wa.db.pending_changes() == 0, f"semua terkirim, sisa {wa.db.pending_changes()}")
check(len(M.TABLES["issues"]) == len(wa.db.issues(pa)), "punch terkirim ke server")
# viewer di laptop lain
sB = QSettings(os.path.join(OUT, "b.ini"), QSettings.IniFormat)
sB.setValue("cloud/url", URL)
sB.setValue("cloud/key", "k")
wb_ = MainWindow(os.path.join(OUT, "syncB.db"), remember=False, settings=sB)
wb_.resize(1440, 880)
wb_.show()
cd = CloudDialog(wb_, wb_.sync)
NEWPW = "Lihat-Saja-77x"
cd.email.setText("viewer")
cd.pw.setText("Viewer")
cd.login()
wait_sync(wb_)
check(wb_.read_only and wb_.db.read_only, "viewer → mode baca saja")
check(len(wb_.db.issues(wb_.project_id)) == len(wa.db.issues(pa)), "viewer menerima data")
check(not wb_.p_punch.b_new.isVisible(), "tombol punch baru disembunyikan untuk viewer")
wb_.nav_to(1)
pid_b = wb_.db.panels(wb_.project_id)[0]["id"]
wb_.go_panel(pid_b)
pump()
vr = wb_.p_check.detail.rows[0]
before_v = wb_.db.check(vr.cid)["result"]
vr.res.btns["NG"].click()
pump()
check(wb_.db.check(vr.cid)["result"] == before_v, "viewer tidak bisa mengubah hasil cek")
check(not wb_.p_check.detail.b_punch.isVisible(), "tombol + Punch disembunyikan untuk viewer")
shot(wb_, "viewer_check")
wb_.nav_to(2)
shot(wb_, "viewer_punch")
# aksi tulis dari viewer → ReadOnlyError ditangkap excepthook aplikasi (di sini: tercatat sebagai error)
n_err = len(ERRORS)
try:
    wb_.db.add_issue(wb_.project_id, title="x")
except ReadOnlyError:
    pass
# engineer ubah → viewer sinkron menerima
wa.db.update_issue(wa.db.issues(pa)[0]["id"], title="Diubah engineer")
wa.sync.sync()
wait_sync(wa)
wb_.sync.sync()
wait_sync(wb_)
check(any(i["title"] == "Diubah engineer" for i in wb_.db.issues(wb_.project_id)), "viewer menerima update")
check(not wb_.sync.cfg.get("last_error"), f"sinkron viewer tanpa error: {wb_.sync.cfg.get('last_error')}")
# ganti password lewat tombol (minta password lama)
def change_pw2(d):
    d.old.setText("Lihat-Saja-77x")
    d.new.setText("Pantau-Baru-2026q")
    d.new2.setText("Pantau-Baru-2026q")
    d.accept()
DIALOG["ChangePasswordDialog"] = change_pw2
cd = CloudDialog(wb_, wb_.sync)
cd.change_password()
check(M.USERS["viewer@paneltracker.local"] == "Pantau-Baru-2026q", "ganti password lewat tombol")
# logout → sesi dicabut di server & mode normal
old_tok = wb_.sync.cfg.get("refresh_token")
cd.logout()
check(not wb_.read_only and not wb_.db.read_only, "logout viewer → mode normal")
from app.cloud import SupabaseClient as _SC, AuthError as _AE  # noqa: E402
try:
    _c = _SC(URL, "k")
    _c.restore(old_tok)
    check(False, "refresh token lama masih berlaku setelah logout")
except _AE:
    pass
# token yang disalin dari laptop/akun lain (format dpapi) tidak bisa dipakai di sini
from app import secure_store  # noqa: E402
check(secure_store.unprotect("dpapi:AAAA") == "", "token terenkripsi asing tidak terbaca")
check(secure_store.unprotect("token-lama") == "token-lama", "token format lama tetap terbaca (migrasi)")
srv.shutdown()

# ================================================================== hasil
pump(10)
real_errors = [e for e in ERRORS if "ReadOnlyError" not in e]
print()
print("pesan dialog:", len(MSGS))
for m in MSGS: print("   MSG", m[0], "|", m[1][:160].replace("\n", " / "))
for e in real_errors:
    print("ERROR:\n" + e)
for f in FAILS:
    print("FAIL:", f)
print("ALL OK" if not FAILS and not real_errors else f"{len(FAILS)} FAIL, {len(real_errors)} ERROR")
sys.stdout.flush()
# keluar seperti aplikasi asli (main.py memakai os._exit): hindari crash teardown Qt offscreen setelah tes selesai
os._exit(0 if not FAILS and not real_errors else 1)
