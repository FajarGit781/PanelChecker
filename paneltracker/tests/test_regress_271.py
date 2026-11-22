"""Regresi v2.7.1: label kosong checklist dihapus Qt (RuntimeError), QR antar laptop, label QR rapi."""
import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # paneltracker/
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
app = QApplication([])
from app.ui.theme import setup_app; setup_app(app)
import app.ui.widgets as W
ERR = []
import traceback
sys.excepthook = lambda t, v, tb: (ERR.append(f"{t.__name__}: {v}"), traceback.print_exception(t, v, tb))
from app import i18n
from app.ui.main_window import MainWindow
from app.demo import create_demo
from app.reports import qr_payload
for f in ("/tmp/rg.db", "/tmp/rg.db-wal", "/tmp/rg.db-shm"):
    if os.path.exists(f): os.remove(f)
w = MainWindow("/tmp/rg.db", remember=False, settings=QSettings("/tmp/rg.ini", QSettings.IniFormat)); w.show()
pid = create_demo(w.db); w.load_projects(pid)
sid = w.db.sites(pid)[0]["id"]
bare = [w.db.add_panel(sid, f"=E00+X{i}", name="COMMON IED I/O\nPANEL") for i in (7, 8)]   # tanpa checklist (seperti import FAT)
full = [o["panel"]["id"] for o in w.db.panel_overview(pid)][:2]
pump = lambda: [app.processEvents() for _ in range(3)]
w.refresh_all(); w.nav_to(1); [app.processEvents() for _ in range(3)]
for pnid in [bare[0], bare[1], bare[0], full[0], bare[1], full[1], bare[1]]:
    w.go_panel(pnid); pump()
    assert w.p_check.detail.panel_id == pnid, (pnid, w.p_check.detail.panel_id)
    w.refresh_all(); pump()          # sinkron/refresh saat panel tanpa checklist terbuka
w.p_check.detail.load(None); pump(); w.p_check.detail.load(bare[0]); pump()
assert not ERR, ERR
print("checklist kosong berulang: OK")
# scan: QR baru (uuid), label lama (nomor lokal laptop lain), tag dengan baris baru
w.scan.setText(qr_payload(w.db.panel(full[1]))); w._scan(); pump()
assert w.p_check.detail.panel_id == full[1]
w.scan.setText(f"PT:{full[0]}:=E00+X7"); w._scan(); pump()
assert w.p_check.detail.panel_id == bare[0], "label lama harus pakai tag, bukan nomor lokal"
assert not ERR, ERR
print("scan QR: OK")
# stres: semua halaman × refresh × ganti project/site, sambil panel tanpa checklist terbuka
for rnd in range(3):
    for i in range(5):
        w.nav_to(i); pump(); w.refresh_all(); pump()
    w.go_panel(bare[rnd % 2]); pump()
    w.cb_site.setCurrentIndex((rnd + 1) % w.cb_site.count()); pump()
    w._sync_done({"pushed": 0, "pulled": 3, "photos_up": 0, "photos_down": 0, "skipped": 0, "seconds": 0}); pump()
assert not ERR, ERR
print("stres halaman: OK")
print("REGRESS OK")
os._exit(0)
