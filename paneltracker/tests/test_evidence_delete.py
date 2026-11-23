"""Hapus foto evidence item DI/DO: soft delete, ikut sinkron, hasil cek tidak berubah."""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
import mock_supabase as M  # noqa: E402
from app.cloud import SupabaseClient, SyncEngine  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402
from app.ui import dialogs as D  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("OK   " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


tmp = tempfile.mkdtemp()
srv, URL = M.start()
c = SupabaseClient(URL, "sb_publishable_test")
c.sign_in("a@test.id", "pass-a")
A = Database(f"{tmp}/A.db")
pid = create_demo(A)
pn = A.panels(pid)[0]["id"]
cid = A.add_check_item(pn, "K. SAS · DI/DO -A30 MiCOM C264 (BCU)", "P/DI1 · CB CLOSED · sh.061", "Status DI")
A.set_check(cid, result="OK", remark="masuk")
from PySide6.QtGui import QImage, QColor  # noqa: E402
img = QImage(64, 48, QImage.Format_RGB32); img.fill(QColor("red"))
jpg = D._image_to_jpeg(img)
for i in range(3):
    A.add_check_photo(cid, f"e{i}.jpg", jpg)
SyncEngine(A, c).run()
check(sum(1 for r in M.TABLES["attachments"].values() if not r.get("deleted")) >= 3, "3 foto di cloud")

D.ask = lambda *a, **k: True
dlg = D.EvidenceDialog(None, A, cid, "BCU")
check(dlg.photos.count() == 3, "dialog menampilkan 3 foto")
dlg.photos.item(0).setSelected(True); dlg.photos.item(1).setSelected(True)
dlg._delete()
check(dlg.photos.count() == 1 and len(A.check_photos(cid)) == 1, "hapus 2 foto terpilih")
check(dlg.photos.contextMenuPolicy() == Qt.CustomContextMenu, "klik kanan tersedia")
SyncEngine(A, c).run()
live = [r for r in M.TABLES["attachments"].values() if r.get("check_uuid") == A.check(cid)["uuid"] and not r.get("deleted")]
check(len(live) == 1, "cloud: tinggal 1 foto (soft delete tersinkron)")
r = A.check(cid)
check(r["result"] == "OK" and r["remark"] == "masuk", "hasil cek tetap")
A.read_only = True
dro = D.EvidenceDialog(None, A, cid, "BCU")
check(dro.photos.contextMenuPolicy() != Qt.CustomContextMenu, "viewer: tanpa hapus")
srv.shutdown()
print("ALL OK" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
