import sys, os, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # paneltracker/
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from app.ui.theme import STYLE
app = QApplication([]); from app.ui.theme import setup_app; setup_app(app)
msgs = []
for n in ("question", "information", "warning"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: (msgs.append(a[1] if len(a) > 1 else ""), QMessageBox.Yes)[1]))
import mock_supabase as M
M.USERS.update({"a@test.id": "Kuat-Sekali-123a", "b@test.id": "Kuat-Sekali-123b"})
srv, URL = M.start()
st = QSettings("/tmp/ui3.ini", QSettings.IniFormat)
st.setValue("cloud/url", URL); st.setValue("cloud/key", "sb_publishable_test"); st.sync()
from app.ui.main_window import MainWindow
from app.ui.cloud_ui import CloudDialog
from app.demo import create_demo
w = MainWindow("/tmp/ui3a.db", remember=False, settings=st); w.resize(1440, 880); w.show()
pid = create_demo(w.db); w.load_projects(pid); app.processEvents()
w.grab().save("/tmp/s2/sync_before.png")
d = CloudDialog(w, w.sync); d.show(); app.processEvents(); d.grab().save("/tmp/s2/cloud_login.png")
d.email.setText("a@test.id"); d.pw.setText("Kuat-Sekali-123a")
d.login()   # login → langsung sinkron di thread
t0 = time.time()
while (w.sync.busy or w.sync.worker) and time.time() - t0 < 30:
    app.processEvents(); time.sleep(0.05)
for _ in range(20): app.processEvents()
print("msgs:", msgs)
print("status:", w.sync.cfg.get("last_status"), "| err:", w.sync.cfg.get("last_error"), "| pending:", w.db.pending_changes())
print("server:", {t: len(v) for t, v in M.TABLES.items()}, "photos:", len(M.STORAGE))
w.grab().save("/tmp/s2/sync_after.png")
d2 = CloudDialog(w, w.sync); d2.show(); app.processEvents(); d2.grab().save("/tmp/s2/cloud_status.png")
# laptop kedua (DB kosong) login sebagai B, sinkron
w2 = MainWindow("/tmp/ui3b.db", remember=False, settings=QSettings("/tmp/ui3b.ini", QSettings.IniFormat))
w2.sync.cfg.set("url", URL); w2.sync.cfg.set("key", "x")
d3 = CloudDialog(w2, w2.sync); d3.email.setText("b@test.id"); d3.pw.setText("Kuat-Sekali-123b"); d3.login()
t0 = time.time()
while (w2.sync.busy or w2.sync.worker) and time.time() - t0 < 30:
    app.processEvents(); time.sleep(0.05)
for _ in range(20): app.processEvents()
print("laptop B projects:", [p["code"] for p in w2.db.projects()], "| combo:", w2.cb_project.currentText(),
      "| panels:", len(w2.db.panels(w2.project_id)) if w2.project_id else 0)
w2.resize(1440, 880); w2.show(); w2.nav_to(2); app.processEvents(); w2.grab().save("/tmp/s2/laptopB_punch.png")
print("UI SYNC OK")
