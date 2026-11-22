"""Cetak check sheet dengan filter: panel (tipe/bay/status/cari), seksi (mis. SAS), item (belum/NG), form kosong."""
import os, re, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, Qt
app = QApplication([])
from app.ui.theme import setup_app; setup_app(app)
from app.ui.main_window import MainWindow
from app.ui.report_dialogs import CheckSheetDialog
from app.demo import create_demo
from app.reports import ReportBuilder

try:
    import pymupdf
except ImportError:          # teks PDF hanya dicek bila pymupdf tersedia
    pymupdf = None

tmp = tempfile.mkdtemp()
w = MainWindow(os.path.join(tmp, "c.db"), remember=False, settings=QSettings(os.path.join(tmp, "c.ini"), QSettings.IniFormat))
pid = create_demo(w.db); w.load_projects(pid)
db = w.db
ov = db.panel_overview(pid)
ALL = [o["panel"]["id"] for o in ov]
# dua panel diberi seksi SAS (seperti checksheet integrasi SAS)
sas_pan = ALL[:2]
for pnid in sas_pan:
    for d in ("Device terintegrasi ke SAS", "IP address sudah dikonfigurasi", "File CID sudah diupload"):
        db.add_check_item(pnid, "I. SAS · -A30 MiCOM C264 (BCU)", d, "Terupload")


def pdf_text(fp):
    if not pymupdf:
        return None, None
    doc = pymupdf.open(fp)
    return len(doc), "\n".join(pg.get_text() for pg in doc)


def visible_ids(d):
    return [d.pl.item(i).data(Qt.UserRole) for i in range(d.pl.count()) if not d.pl.item(i).isHidden()]


# 1. default: semua panel, semua seksi, semua item
d = CheckSheetDialog(w)
o = d.options()
assert o["panel_ids"] == ALL and o["sections"] is None and o["items"] == "all" and not o["blank"]
assert "panel" in d.count.text() and d.ok.isEnabled()
print("default: OK", len(ALL), "panel")

# 2. filter tipe / status / cari → hanya panel yang tampil & dicentang yang dicetak
types = sorted({o_["panel"]["panel_type"] for o_ in ov if o_["panel"]["panel_type"]})
d.ptype.setCurrentIndex(d.ptype.findData(types[0]))
want = [o_["panel"]["id"] for o_ in ov if o_["panel"]["panel_type"] == types[0]]
assert visible_ids(d) == want and d.options()["panel_ids"] == want, (types[0], want)
d.ptype.setCurrentIndex(0)
tag = " ".join(db.panel(ALL[3])["tag"].split())
d.q.setText(tag)
assert ALL[3] in d.options()["panel_ids"] and len(d.options()["panel_ids"]) <= 2
d.q.clear()
st = ov[0]["status"]
d.pstat.setCurrentIndex(d.pstat.findData(st))
assert d.options()["panel_ids"] == [o_["panel"]["id"] for o_ in ov if o_["status"] == st]
d.pstat.setCurrentIndex(0)
d._mark_visible(False)
assert d.options()["panel_ids"] == [] and not d.ok.isEnabled(), "tanpa panel → tombol nonaktif"
d._q_all()
print("filter panel: OK")

# 3. hanya seksi SAS → panel tanpa SAS dilewati
d._only_sas()
o = d.options()
assert o["sections"] == {"I. SAS · -A30 MiCOM C264 (BCU)"} and "SAS" in o["note"]
assert "dilewati" in d.count.text()
fp = os.path.join(tmp, "sas.pdf")
n = ReportBuilder(db, pid).check_sheets(fp, o["panel_ids"], sections=o["sections"], items=o["items"], note=o["note"])
assert n == 2, n
pages, txt = pdf_text(fp)
if txt is not None:
    assert pages == 2 and "Device terintegrasi ke SAS" in txt and "A. Visual" not in txt, pages
print("hanya SAS: OK", n, "panel")

# 4. item NG saja
d._q_all()
d.mode.buttons()[2].setChecked(True)
o = d.options()
assert o["items"] == "ng"
ng_pan = [p for p in ALL if any(c["result"] == "NG" for c in db.panel_checks(p))]
fp = os.path.join(tmp, "ng.pdf")
n = ReportBuilder(db, pid).check_sheets(fp, o["panel_ids"], sections=o["sections"], items="ng")
assert n == len(ng_pan) and n > 0, (n, len(ng_pan))
pages, txt = pdf_text(fp)
if txt is not None:
    res = re.findall(r"^(OK|NG|N/A)$", txt, re.M)
    assert res and set(res) == {"NG"}, set(res)
print("NG saja: OK", n, "panel")

# 5. form kosong: hasil/nilai tidak dicetak, ada isian tanggal & penguji
d.mode.buttons()[0].setChecked(True)
d.blank.setChecked(True)
o = d.options()
assert o["blank"] and not o["with_punch"] and not d.punch.isEnabled()
fp = os.path.join(tmp, "blank.pdf")
n = ReportBuilder(db, pid).check_sheets(fp, ALL[:3], blank=True, with_punch=False, note=o["note"])
pages, txt = pdf_text(fp)
if txt is not None:
    assert "Tanggal uji" in txt and "Penguji" in txt and "OK · NG · N/A" in txt
    assert not re.search(r"^(OK|NG|N/A)$", txt, re.M), "form kosong tidak boleh memuat hasil"
    assert "Punch List Panel" not in txt
print("form kosong: OK")

# 6. dari menu panel: hanya panel itu yang dicentang; alur penuh sampai PDF
d1 = CheckSheetDialog(w, preset_panels=[ALL[4]])
assert d1.options()["panel_ids"] == [ALL[4]]
fp = os.path.join(tmp, "flow.pdf")
w._report_path = lambda kind: fp
w.open_file = lambda *a, **k: None
CheckSheetDialog.exec = lambda self: (self._only_sas(), 1)[1]
w.report_check_sheet(sas_pan[:1])
assert os.path.getsize(fp) > 1000
pages, txt = pdf_text(fp)
if txt is not None:
    assert pages == 1 and "Seksi: integrasi SAS" in txt
# kompatibel: pemanggilan lama tanpa opsi tetap mencetak semua item
fp = os.path.join(tmp, "lama.pdf")
assert ReportBuilder(db, pid).check_sheets(fp, ALL[:2]) == 2
print("alur menu & kompatibilitas: OK")
print("SEMUA OK")
# Tutup rapi: window ditutup lewat closeEvent (database ditutup), lalu proses diakhiri langsung. Tanpa ini PySide6
# 6.12 (mode offscreen) bisa segfault saat interpreter membongkar dialog yang dibuat tanpa exec() di tes.
w.close()
app.processEvents()
sys.stdout.flush()
os._exit(0)
