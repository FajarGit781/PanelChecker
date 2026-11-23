"""v2.9: uji injeksi CT/VT di laptop — blok di halaman Checking, actual → OK/NG otomatis, setup/titik uji,
baca foto HMI (OCR bawaan OS), report PDF terpisah, Lembar Uji tidak memuat blok injeksi, sinkron ke laptop lain."""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from app.ui.theme import setup_app  # noqa: E402
setup_app(app)
import mock_supabase as M  # noqa: E402
import app.ui.widgets as W  # noqa: E402
from app import injection as INJ, ocr  # noqa: E402
from app.cloud import SupabaseClient, SyncEngine  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402
from app.reports import ReportBuilder  # noqa: E402
from app.ui import injection_ui as IU  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("OK   " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


tmp = tempfile.mkdtemp()
st = QSettings(os.path.join(tmp, "m.ini"), QSettings.IniFormat)
w = MainWindow(os.path.join(tmp, "m.db"), remember=False, settings=st); w.show()
pid = create_demo(w.db); w.load_projects(pid)
db = w.db
pn = [o["panel"]["id"] for o in db.panel_overview(pid)][0]
pump = lambda: [app.processEvents() for _ in range(4)]
W.ask = lambda *a, **k: True
IU.ask = lambda *a, **k: True
DEV = "-A30 MiCOM C264 (BCU)"

# ---- prefill rasio dari item Rasio CT/VT
ct = db.add_check_item(pn, "J. SAS · Rasio CT/VT", f"{DEV} · CT ratio", "Sesuai drawing", "rasio")
vt = db.add_check_item(pn, "J. SAS · Rasio CT/VT", f"{DEV} · VT ratio", "Sesuai drawing", "rasio")
db.set_check(ct, value="1600/1 A")
db.set_check(vt, value="150000/110 V")
rows = db.panel_checks(pn)
s = IU.prefill_from_ratio_items(rows, DEV)
check(s["ct_p"] == 1600 and s["ct_s"] == 1 and s["vt_p"] == 150 and s["vt_s"] == 110, f"prefill rasio dari item Rasio CT/VT: {s}")
db.set_check(vt, value="150/0.11 kV")
check(IU.prefill_from_ratio_items(db.panel_checks(pn), DEV)["vt_s"] == 110, "VT '150/0.11 kV' → 110 V")
check(IU.ratio_devices(db.panel_checks(pn)) == [DEV], "device dari item rasio")
check(IU.parse_list("10, 50, 100") == [10, 50, 100] and IU.parse_list("12,5; 50") == [12.5, 50] and IU.parse_list("x") is None,
      "daftar % injeksi")

# ---- buat blok (logika create_block tanpa dialog)
S = dict(INJ.DEFAULT_SETUP)
n_before = len(db.panel_checks(pn))
max_sort = max(r["sort"] for r in db.panel_checks(pn))
secs = [r["section"] for r in db.panel_checks(pn)]
items = INJ.block_items(DEV, INJ.next_letter(secs), S, [(10, 100, 0, 50), (50, 100, 30, 50)])
dirty_before = {r["id"] for r in db.q("SELECT id FROM panel_check WHERE panel_id=? AND dirty=1", (pn,))}
db.conn.execute("UPDATE panel_check SET dirty=0 WHERE panel_id=?", (pn,)); db.conn.commit()
IU.add_items(db, pn, items)
after = db.panel_checks(pn)
check(len(after) == n_before + 21, "21 item baru (setup + 2×10)")
check(db.q1("SELECT COUNT(*) n FROM panel_check WHERE panel_id=? AND dirty=1", (pn,))["n"] == 21,
      "hanya item baru yang dirty (sort item lain tidak digeser → hasil tim tidak ikut ter-push ulang)")
new = [r for r in after if INJ.is_injection_section(r["section"])]
check(min(r["sort"] for r in new) == max_sort + 1, "blok di akhir checklist")
setup_row = next(r for r in new if r["unit"] == "setup")
check(setup_row["result"] == "OK", "item setup bertanda OK")
SEC = new[0]["section"]

# ---- tampilan
w.nav_to(1); pump()
w.go_panel(pn); pump()
view = w.p_check.detail
check(len(view.inj_blocks) == 1, "satu blok injeksi tampil")
blk = view.inj_blocks[0]
check(not any(INJ.is_injection_section(r.section) for r in view.rows), "item injeksi tidak tampil dobel sebagai baris biasa")
check(len(blk.edits) == 20, "20 kolom Actual")
check(blk.stats() == (0, 0, 20), "statistik awal 0/20")


def row(n, key):
    return next(r for r in db.panel_checks(pn) if r["section"] == SEC and r["description"].startswith(f"T{n} ·")
                and r["description"].endswith("· " + key))


def type_(n, key, text):
    cid = row(n, key)["id"]
    e = view.inj_blocks[0].edits[cid]
    e.setText(text)
    e.editingFinished.emit()
    pump()


type_(1, "IA", "201.5")
check(row(1, "IA")["result"] == "OK" and row(1, "IA")["value"] == "201.5", "IA 201,5 (expected 200 ±2) → OK")
type_(1, "IB", "202,5")
check(row(1, "IB")["result"] == "NG", "IB 202,5 → NG")
check(row(1, "IB")["checked_by"], "checked_by terisi")
type_(1, "IB", "")
check(row(1, "IB")["result"] == "" and not row(1, "IB")["checked_by"], "actual dikosongkan → hasil kosong")
type_(2, "Q", "126.9")
check(row(2, "Q")["result"] == "NG", "Q 126,9 MVAR (expected 129,9 ±2,6) → NG")
blk = view.inj_blocks[0]
check(blk.stats() == (2, 1, 20), f"statistik 2/20 · 1 NG: {blk.stats()}")
pt2 = next(p for p in INJ.group(blk.rows)["points"] if p["n"] == 2)
n = blk.apply_values(pt2, {"P": 225.1, "PF": 0.871, "f": 50.0, "Q": 129.5})
check(n == 4 and row(2, "P")["result"] == "OK" and row(2, "Q")["result"] == "OK" and row(2, "PF")["value"] == "0.871",
      "nilai dari foto dimasukkan + dinilai (Q diganti 129,5 → OK)")

# ---- filter halaman
view.q.setText("Injeksi"); pump()
check(view.inj_blocks[0].isVisible(), "pencarian 'Injeksi' menampilkan blok")
view.q.setText("tidak-ada-yang-cocok-xyz"); pump()
check(not view.inj_blocks[0].isVisible(), "pencarian lain menyembunyikan blok")
view.q.setText(""); pump()

# ---- tambah titik uji (dialog di-stub)
class FakePoint:
    def __init__(self, *a, **k): pass
    def exec(self): return True
    def values(self): return (100, 100, 30, 50)


IU.PointDialog = FakePoint
view.inj_blocks[0].add_point(); pump()
g = INJ.group([r for r in db.panel_checks(pn) if r["section"] == SEC])
check([p["n"] for p in g["points"]] == [1, 2, 3] and abs(INJ.parse_point(g["points"][2]["rows"]["IA"]["description"])["pi"] - 100) < 1e-9,
      "titik T3 100% ditambahkan")
check(g["points"][2]["rows"]["IA"]["criteria"] == "2000.0 ± 20.0", "kriteria T3 IA = 2000 ±20")

# ---- hapus titik: yang sudah ada hasil ditolak, yang kosong boleh
warned = []
IU.warn = lambda *a, **k: warned.append(a[1])
view.inj_blocks[0]._delete_point(g["points"][0]); pump()
check(warned and len([r for r in db.panel_checks(pn) if r["section"] == SEC]) == 31, "T1 berisi hasil → tidak dihapus")
view.inj_blocks[0]._delete_point(g["points"][2]); pump()
check(len([r for r in db.panel_checks(pn) if r["section"] == SEC]) == 21, "T3 kosong → dihapus (soft delete)")

# ---- ubah setup (offline) → kriteria & hasil dihitung ulang
class FakeSetup:
    def __init__(self, *a, **k):
        self.form = type("F", (), {"value": staticmethod(lambda: dict(S, ct_p=2010))})()
    def exec(self): return True


IU.SetupDialog = FakeSetup
view.inj_blocks[0].edit_setup(); pump()
check(INJ.parse_setup(row(1, "IA")["criteria"].replace("±", "±") and next(
    r for r in db.panel_checks(pn) if r["section"] == SEC and r["unit"] == "setup")["criteria"])["ct_p"] == 2010, "setup CT 2010/1 tersimpan")
check(row(1, "IA")["criteria"] == "201.0 ± 2.0", f"kriteria IA dihitung ulang: {row(1, 'IA')['criteria']}")
check(row(1, "IA")["result"] == "OK", "IA 201,5 tetap OK dengan rasio baru")

# ---- foto evidence titik uji + baca foto HMI (OCR bawaan OS)
from PySide6.QtCore import QBuffer, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
img = QImage(900, 560, QImage.Format_RGB32)
img.fill(QColor("#0B1A12"))
p_ = QPainter(img)
p_.setPen(QColor("#8EF0B0"))
f_ = QFont("Menlo"); f_.setPixelSize(40); p_.setFont(f_)
for i, t in enumerate(["BCU =E01 MEASUREMENT", "IA 1005.1 A  IB 1004.8 A  IC 1005.3 A", "VAB 150.02 kV",
                       "P 226.2 MW", "Q 130.4 MVAR", "PF 0.866", "f 50.00 Hz"]):
    p_.drawText(40, 70 + i * 66, t)
p_.end()
buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG"); data = bytes(buf.data())
if ocr.available():
    txt = ocr.recognize(data)
    found = INJ.parse_hmi(txt)
    check({k: round(v["value"], 3) for k, v in found.items() if k in ("IA", "IB", "IC", "P", "Q", "PF", "f")} ==
          {"IA": 1005.1, "IB": 1004.8, "IC": 1005.3, "P": 226.2, "Q": 130.4, "PF": 0.866, "f": 50.0},
          f"OCR layar HMI terbaca: {found}")

    class FakeReview:
        def __init__(self, parent, image_data, found_, exp, cur, raw):
            FakeReview.found = found_
        def exec(self): return True
        def values(self): return {k: v["value"] for k, v in FakeReview.found.items()}
    IU.OcrReviewDialog = FakeReview
    blk = view.inj_blocks[0]
    pt2 = next(p for p in INJ.group(blk.rows)["points"] if p["n"] == 2)
    blk._ocr_run(pt2, data, "hmi_t2.png"); pump()
    check(row(2, "IA")["value"] == "1005.1" and row(2, "IA")["result"] == "OK", "baca foto → IA T2 terisi + OK")
    check(len(db.check_photos(row(2, "IA")["id"])) == 1, "foto HMI tersimpan sebagai evidence titik T2")
else:
    print("SKIP OCR (mesin OCR OS tidak tersedia)")

# ---- report
rb = ReportBuilder(db, pid)
check(rb.injection_report(os.path.join(tmp, "inj.pdf"), [pn]) == 1 and os.path.getsize(os.path.join(tmp, "inj.pdf")) > 3000,
      "report uji injeksi dibuat")
check(ReportBuilder(db, pid).injection_report(os.path.join(tmp, "inj_none.pdf"), [p for p in [o["panel"]["id"] for o in db.panel_overview(pid)] if p != pn][:2]) == 0,
      "panel tanpa uji injeksi tidak dicetak")
cs = ReportBuilder.check_item_filter([c for c in db.panel_checks(pn)], None, "all")
from app.sas_matrix import is_measurement  # noqa: E402
check(not is_measurement("setup") and is_measurement("A"), "item setup bukan measurement (tanpa tombol foto)")
src = open(os.path.join(os.path.dirname(_HERE), "app", "reports.py"), encoding="utf-8").read()
check("not INJ.is_injection_section" in src, "Lembar Uji tidak memuat blok injeksi")
from app.i18n import set_lang  # noqa: E402
try:
    set_lang("en")
    check(ReportBuilder(db, pid).injection_report(os.path.join(tmp, "inj_en.pdf"), [pn]) == 1, "report bahasa Inggris")
finally:
    set_lang("id")

# ---- sinkron ke laptop lain lewat server tiruan
srv, URL = M.start()
c1 = SupabaseClient(URL, "sb_publishable_test"); c1.sign_in("a@test.id", "pass-a")
c2 = SupabaseClient(URL, "sb_publishable_test"); c2.sign_in("b@test.id", "pass-b")
SyncEngine(db, c1).run()
B = Database(os.path.join(tmp, "B.db"))
SyncEngine(B, c2).run()
pb = B.q1("SELECT id FROM panel WHERE uuid=?", (db.panel(pn)["uuid"],))["id"]
gb = INJ.group([r for r in B.panel_checks(pb) if r["section"] == SEC])
check(gb["setup"] is not None and INJ.parse_setup(gb["setup"]["criteria"])["ct_p"] == 2010 and len(gb["points"]) == 2,
      "laptop lain menerima setup + 2 titik uji")
check(next(r for r in B.panel_checks(pb) if r["section"] == SEC and r["description"].endswith("T2 · I 50% · V 100% · φ 30° · 50 Hz · Q") or
           (r["section"] == SEC and r["description"].startswith("T2") and r["description"].endswith("· Q")))["result"] == "OK",
      "hasil Q T2 ikut tersinkron")

import shutil as _sh; _sh.copy(os.path.join(tmp, "inj.pdf"), os.environ.get("PT_SHOT_DIR", tmp)) if os.environ.get("PT_SHOT_DIR") else None
if os.environ.get("PT_SHOT_DIR"):
    w.go_panel(pn); pump(); w.resize(1400, 900); pump()
    view.sa.verticalScrollBar().setValue(view.sa.verticalScrollBar().maximum()); pump()
    w.grab().save(os.path.join(os.environ["PT_SHOT_DIR"], "inj_ui.png"))
print("ALL OK" if ok else "ADA YANG GAGAL")
w.close(); app.processEvents(); sys.stdout.flush(); os._exit(0 if ok else 1)
