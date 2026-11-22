"""v2.7.2: label QR berisi link viewer web (tanpa login) dan tetap bisa di-scan di aplikasi desktop."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
app = QApplication([])
from app.ui.theme import setup_app; setup_app(app)
from app.ui.main_window import MainWindow
from app.ui.dialogs import SettingsDialog
from app.demo import create_demo
from app.reports import qr_payload, ReportBuilder
from app.db import SHARED_SETTINGS
import app.ui.widgets as W

tmp = tempfile.mkdtemp()
dbp = os.path.join(tmp, "v.db")
w = MainWindow(dbp, remember=False, settings=QSettings(os.path.join(tmp, "v.ini"), QSettings.IniFormat)); w.show()
pid = create_demo(w.db); w.load_projects(pid)
pump = lambda: [app.processEvents() for _ in range(3)]
pans = [o["panel"]["id"] for o in w.db.panel_overview(pid)][:3]
p0 = w.db.panel(pans[0])

# 1. tanpa alamat viewer: format lama tidak berubah
assert qr_payload(p0) == f"PT:{p0['uuid']}:{' '.join(p0['tag'].split())}"
assert qr_payload(p0, "http://tidak-aman.example/") .startswith("PT:"), "http tidak boleh dipakai"

# 2. Pengaturan: http ditolak, https disimpan & ikut pengaturan tim (sinkron)
assert "viewer_url" in SHARED_SETTINGS
W.warn = lambda *a, **k: None
import app.ui.dialogs as D; D.warn = lambda *a, **k: None
dlg = SettingsDialog(w, w.db)
dlg.viewer_url.setText("http://x.example/"); dlg.accept()
assert w.db.get_setting("viewer_url") == "", "http harus ditolak"
dlg.viewer_url.setText("https://viewer.example.app/"); dlg.accept()
assert w.db.get_setting("viewer_url") == "https://viewer.example.app/"
assert any(r["key"] == "viewer_url" for r in w.db.shared_settings_dirty()), "harus ikut dikirim ke cloud"
print("pengaturan: OK")

# 3. isi QR jadi link; query string yang sudah ada dihormati
url = qr_payload(p0, w.db.get_setting("viewer_url"))
assert url == f"https://viewer.example.app/?p={p0['uuid']}", url
assert qr_payload(p0, "https://h.example/v?x=1") == f"https://h.example/v?x=1&p={p0['uuid']}"

# 4. scanner USB di desktop mengenali link (huruf besar juga), label PT lama tetap jalan
w.refresh_all(); w.nav_to(1); pump()
w.scan.setText(url); w._scan(); pump()
assert w.p_check.detail.panel_id == pans[0]
w.scan.setText(url.upper().replace("HTTPS://VIEWER.EXAMPLE.APP/?P=", "https://viewer.example.app/?p=")); w._scan(); pump()
assert w.p_check.detail.panel_id == pans[0]
w.scan.setText(qr_payload(w.db.panel(pans[1]))); w._scan(); pump()
assert w.p_check.detail.panel_id == pans[1]
assert w.db.find_panel(pid, "https://viewer.example.app/?p=00000000-0000-4000-8000-000000000000") is None
assert w.db.find_panel(pid, "https://viewer.example.app/") is None
print("scan link: OK")

# 5. PDF label QR & lembar uji tetap terbentuk, dan QR di dalamnya berisi link
import reportlab.graphics.barcode.qr as Q
seen = []
orig = Q.QrCodeWidget.__init__
def spy(self, value="", *a, **k):
    seen.append(value); orig(self, value, *a, **k)
Q.QrCodeWidget.__init__ = spy
rb = ReportBuilder(w.db, pid)
fp = os.path.join(tmp, "label.pdf"); rb.qr_labels(fp, pans)
assert os.path.getsize(fp) > 1000
assert seen and all(s.startswith("https://viewer.example.app/?p=") for s in seen), seen[:3]
print("PDF label: OK", len(seen), "QR")

# 6. printer label (Xprinter dll.): 1 label per halaman seukuran label, pilihan diingat per laptop
import app.ui.report_dialogs as RD
from app.ui.report_dialogs import QrLabelDialog
WARNED = []
RD.warn = lambda *a, **k: WARNED.append(a[1] if len(a) > 1 else "")
dlg = QrLabelDialog(w, 3)
assert dlg.rb_roll.isChecked(), "default: printer label"
dlg.preset.setCurrentIndex(3)                     # 60 x 40
assert (dlg.w.value(), dlg.h.value()) == (60, 40)
dlg.w.setValue(57); assert dlg.preset.currentData() is None, "ukuran custom → 'Ukuran lain…'"
dlg.w.setValue(60); dlg.accept()
dlg2 = QrLabelDialog(w, 3)
assert (dlg2.w.value(), dlg2.h.value()) == (60, 40) and dlg2.rb_roll.isChecked(), "pilihan harus diingat"
dlg2.margin.setValue(6); dlg2.w.setValue(20); dlg2.h.setValue(20); dlg2.accept()
assert dlg2.result() != 1 and WARNED, "label terlalu kecil harus ditolak"
assert float(w.settings.value("label/w")) == 60, "pilihan yang ditolak tidak boleh tersimpan"
fp2 = os.path.join(tmp, "roll.pdf")
w._report_path = lambda kind: (seen.clear(), fp2)[1]
QrLabelDialog.exec = lambda self: 1
w.open_file = lambda *a, **k: None    # jangan tampilkan dialog "Report selesai"
w.report_qr(pans)
from reportlab.lib.units import mm
import re
raw = open(fp2, "rb").read()
boxes = re.findall(rb"/MediaBox \[\s*0 0 ([\d.]+) ([\d.]+)", raw)
assert len(boxes) == len(pans), boxes
assert all(abs(float(a) - 60 * mm) < 0.1 and abs(float(b) - 40 * mm) < 0.1 for a, b in boxes), boxes
assert len(seen) == len(pans) and all(x.startswith("https://viewer.example.app/?p=") for x in seen)
print("label printer 1/halaman: OK", len(boxes), "halaman 60x40 mm")
print("SEMUA OK")
# Tutup rapi: window ditutup lewat closeEvent (database ditutup), lalu proses diakhiri langsung. Tanpa ini PySide6
# 6.12 (mode offscreen) bisa segfault saat interpreter membongkar dialog yang dibuat tanpa exec() di tes.
w.close()
app.processEvents()
sys.stdout.flush()
os._exit(0)
