"""Edit nama/kriteria item (mis. nama sinyal DI/DO) saat tim sedang mengisi hasil di perangkat lain.

Skenario yang dijaga:
1. Laptop B mengisi hasil (belum sinkron), laptop A mengganti nama item → setelah keduanya sinkron,
   nama baru DAN hasil B sama-sama ada (tidak ada yang tertimpa).
2. A punya salinan lama (belum pull hasil B yang sudah di cloud) lalu ganti nama → hasil B di cloud utuh.
3. Edit nama tidak mengubah updated_at di cloud (LWW hasil cek tidak terganggu).
4. UI: tanpa login cloud → edit lokal biasa; login cloud → jalur aman (PATCH).
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
import mock_supabase as M  # noqa: E402
from app.cloud import SupabaseClient, SyncEngine, rename_check  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("OK   " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


tmp = tempfile.mkdtemp()
srv, URL = M.start()


def client(email, pw):
    c = SupabaseClient(URL, "sb_publishable_test")
    c.sign_in(email, pw)
    return c


A, B = Database(f"{tmp}/A.db"), Database(f"{tmp}/B.db")
ca, cb = client("a@test.id", "pass-a"), client("b@test.id", "pass-b")
pid = create_demo(A)
pn = A.panels(pid)[0]["id"]
SEC = "K. SAS · DI/DO -A30 MiCOM C264 (BCU)"
i1 = A.add_check_item(pn, SEC, "P/DI1 · CB(-Q0) CLOSED · sh.061", "Status DI masuk BCU/HMI sesuai drawing")
i2 = A.add_check_item(pn, SEC, "P/DI2 · CB(-Q0) OPEN · sh.061", "Status DI masuk BCU/HMI sesuai drawing")
SyncEngine(A, ca).run()
SyncEngine(B, cb).run()
u1, u2 = A.check(i1)["uuid"], A.check(i2)["uuid"]
b1 = B.q1("SELECT id FROM panel_check WHERE uuid=?", (u1,))["id"]
b2 = B.q1("SELECT id FROM panel_check WHERE uuid=?", (u2,))["id"]

# ---- 1. B isi hasil (belum sinkron), A ganti nama
B.set_check(b1, result="OK", remark="DI masuk di HMI")
srv_before = dict(M.TABLES["panel_checks"][u1])
rename_check(A, ca, i1, description="P/DI1 · CB(-Q0) CLOSED POSITION · sh.061", criteria="Status masuk HMI SAS 1 & 2")
srv_after = M.TABLES["panel_checks"][u1]
check(srv_after["description"].endswith("CLOSED POSITION · sh.061") and srv_after["updated_at"] == srv_before["updated_at"],
      "cloud: nama berubah, updated_at tetap")
check(A.check(i1)["description"].endswith("CLOSED POSITION · sh.061") and not A.check(i1)["dirty"],
      "laptop A: nama lokal berubah tanpa jadi baris kotor")
SyncEngine(B, cb).run()
rb = B.check(b1)
check(rb["description"].endswith("CLOSED POSITION · sh.061") and rb["result"] == "OK" and rb["remark"] == "DI masuk di HMI",
      "laptop B: nama baru diterima, hasil yang belum terkirim tetap")
s1 = M.TABLES["panel_checks"][u1]
check(s1["result"] == "OK" and s1["description"].endswith("CLOSED POSITION · sh.061") and s1["criteria"].startswith("Status masuk"),
      "cloud: nama baru + hasil B")
SyncEngine(A, ca).run()
ra = A.check(i1)
check(ra["result"] == "OK" and ra["remark"] == "DI masuk di HMI" and ra["description"].endswith("POSITION · sh.061"),
      "laptop A: menerima hasil B, nama tetap yang baru")

# ---- 2. B isi hasil & sinkron; A (belum pull) ganti nama → hasil di cloud utuh
B.set_check(b2, result="NG", remark="tidak muncul")
SyncEngine(B, cb).run()
check(A.check(i2)["result"] == "", "laptop A masih salinan lama (belum pull)")
rename_check(A, ca, i2, description="P/DI2 · CB(-Q0) OPEN POSITION · sh.061")
s2 = M.TABLES["panel_checks"][u2]
check(s2["result"] == "NG" and s2["remark"] == "tidak muncul" and s2["description"].endswith("OPEN POSITION · sh.061"),
      "cloud: hasil B tidak tertimpa oleh edit nama dari salinan lama")
SyncEngine(A, ca).run()
SyncEngine(B, cb).run()
check(A.check(i2)["result"] == "NG" and B.check(b2)["description"].endswith("OPEN POSITION · sh.061"),
      "kedua laptop konsisten setelah sinkron")
check(A.pending_changes() == 0 and B.pending_changes() == 0, "tidak ada perubahan tertunda")

# ---- 3. viewer tidak bisa edit nama
M.USERS["v@test.id"] = "pass-v"
M.MEMBERS["v@test.id"] = "viewer"
try:
    rename_check(A, client("v@test.id", "pass-v"), i2, description="X")
    check(False, "viewer ditolak")
except Exception:
    check(M.TABLES["panel_checks"][u2]["description"].endswith("OPEN POSITION · sh.061"), "viewer ditolak server")
A.conn.execute("UPDATE panel_check SET description=? WHERE id=?", (M.TABLES["panel_checks"][u2]["description"], i2))
A.conn.commit()

# ---- 4. UI: CheckRow._edit tanpa / dengan login cloud
from app.ui import page_checklist as PC  # noqa: E402


class _Cfg:
    def __init__(self, logged):
        self.logged_in, self.url, self.key = logged, URL, "sb_publishable_test"

    def get(self, k, d=""):
        return ca.refresh_token if k == "refresh_token" else d

    def set(self, k, v):
        pass


class _Sync:
    def __init__(self, logged):
        self.cfg = _Cfg(logged)

    def busy(self):
        return False


class _Main:
    db = A
    project_id = pid

    def refresh_all(self, **k):
        pass


class _View:
    main = _Main()
    photo_counts = {}
    page = None
    panel_id = pn

    def sections(self):
        return [SEC]

    def load(self, *_):
        pass

    def stats_changed(self, *a, **k):
        pass


PC.CheckItemDialog.exec = lambda self: (self.desc.setText(self.desc.text().replace("sh.061", "sh.061 (rev)")), True)[1]
_View.main.sync = _Sync(False)
PC.CheckRow(_View(), A.check(i1), 1, [])._edit()
check(A.check(i1)["description"].endswith("(rev)") and A.check(i1)["dirty"] and
      not M.TABLES["panel_checks"][u1]["description"].endswith("(rev)"), "tanpa login cloud: edit lokal biasa")
A.update_check_item(i1, description=M.TABLES["panel_checks"][u1]["description"])
SyncEngine(A, ca).run()
_View.main.sync = _Sync(True)
PC.CheckRow(_View(), A.check(i2), 2, [])._edit()
check(M.TABLES["panel_checks"][u2]["description"].endswith("(rev)") and M.TABLES["panel_checks"][u2]["result"] == "NG",
      "login cloud: edit lewat jalur aman, hasil di cloud tetap")

srv.shutdown()
print("ALL OK" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
