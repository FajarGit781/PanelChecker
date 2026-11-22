"""Simulasi 2 laptop (A & B) sinkron lewat server tiruan."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # paneltracker/
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication([])
import mock_supabase as M  # noqa: E402
from app.cloud import AuthError, CloudError, SupabaseClient, SyncEngine  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402

for f in ("/tmp/A.db", "/tmp/B.db"):
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(f + ext):
            os.remove(f + ext)
srv, URL = M.start()


def client(email, pw):
    c = SupabaseClient(URL, "sb_publishable_test")
    c.sign_in(email, pw)
    return c


def sync(db, c):
    return SyncEngine(db, c).run()


A, B = Database("/tmp/A.db"), Database("/tmp/B.db")
ca, cb = client("a@test.id", "pass-a"), client("b@test.id", "pass-b")

# login salah
try:
    client("a@test.id", "salah")
    print("FAIL: login salah lolos")
except AuthError as e:
    print("login salah ditolak:", e)
print("membership A:", ca.membership(), "| stranger:", client("stranger@test.id", "pass-x").membership())

# A: buat demo lalu sinkron
pid = create_demo(A)
print("A pending sebelum sync:", A.pending_changes())
s = sync(A, ca)
print("A sync #1:", s, "| pending sesudah:", A.pending_changes())
print("server:", {t: len(v) for t, v in M.TABLES.items()}, "| foto di storage:", len(M.STORAGE))

# B: kosong, sinkron → dapat semuanya
s = sync(B, cb)
print("B sync #1:", s)
pb = B.projects()
print("B projects:", [p["code"] for p in pb], "| templates:", [t["name"][:18] for t in B.templates()])
pidB = pb[0]["id"]
oa, ob = A.overall(pid), B.overall(pidB)
print("overall sama?", oa == ob)
ph = B.q1("SELECT COUNT(*) c FROM attachment WHERE data IS NOT NULL")["c"]
print("foto di B:", ph, "== A:", A.q1("SELECT COUNT(*) c FROM attachment WHERE kind<>'logo'")["c"])
print("B pending setelah pull:", B.pending_changes())

# B (vendor): tutup sebuah punch + ubah satu hasil cek; A sinkron
iB = [i for i in B.issues(pidB) if i["status"] == "Open"][0]
B.update_issue(iB["id"], status="Closed", action="Diperbaiki vendor")
chkB = B.q1("SELECT id, uuid FROM panel_check WHERE result='' AND deleted=0 LIMIT 1")
B.set_check(chkB["id"], result="OK", value="ok-B")
print("B push:", sync(B, cb))
print("A pull:", sync(A, ca))
iA = A.q1("SELECT status, action FROM issue WHERE uuid=?", (iB["uuid"],))
cA = A.q1("SELECT result, value FROM panel_check WHERE uuid=?", (chkB["uuid"],))
print("A melihat punch closed:", dict(iA), "| cek:", dict(cA))

# Konflik: A & B mengubah item yang sama offline; yang terakhir menang
import time  # noqa: E402
c_uuid = chkB["uuid"]
idA = A.q1("SELECT id FROM panel_check WHERE uuid=?", (c_uuid,))["id"]
idB = chkB["id"]
A.set_check(idA, remark="catatan A")
time.sleep(0.01)
B.set_check(idB, remark="catatan B (lebih baru)")
sync(B, cb)
sync(A, ca)   # A push versi lama → server tolak; A pull → dapat versi B
sync(B, cb)
ra = A.q1("SELECT remark FROM panel_check WHERE uuid=?", (c_uuid,))["remark"]
rb = B.q1("SELECT remark FROM panel_check WHERE uuid=?", (c_uuid,))["remark"]
print("konflik → A:", ra, "| B:", rb, "| server:", M.TABLES["panel_checks"][c_uuid]["remark"])

# Bentrok kode punch: A & B sama-sama buat punch baru offline
pnA = A.panels(pid)[0]["id"]
pnB = B.q1("SELECT id FROM panel WHERE uuid=?", (A.panel(pnA)["uuid"],))["id"]
xa = A.add_issue(pid, panel_id=pnA, title="Temuan dari A")
xb = B.add_issue(pidB, panel_id=pnB, title="Temuan dari B")
print("kode offline:", A.issue(xa)["code"], B.issue(xb)["code"])
sync(A, ca)
sync(B, cb)
sync(A, ca)
codesA = sorted(i["code"] for i in A.issues(pid))
codesB = sorted(i["code"] for i in B.issues(pidB))
print("kode unik di A:", len(codesA) == len(set(codesA)), "| A==B:", codesA == codesB, "| B baru:",
      B.issue(xb)["code"])

# Hapus (soft) di A → hilang di B
pdel = A.panels(pid)[-1]
A.delete_panel(pdel["id"])
sync(A, ca)
sync(B, cb)
print("panel terhapus di B:", B.q1("SELECT deleted FROM panel WHERE uuid=?", (pdel["uuid"],))["deleted"] == 1,
      "| jumlah panel A/B:", len(A.panels(pid)), len(B.panels(pidB)))

# Template edit di B → A
tB = B.templates()[0]
items = [(i["section"], i["description"], i["criteria"], i["unit"]) for i in B.template_items(tB["id"])]
B.save_template(tB["id"], tB["name"], "edit B", items + [("Z. Tambahan", "Item baru dari B", "OK", "")])
sync(B, cb)
sync(A, ca)
tA = A.q1("SELECT id, description FROM check_template WHERE uuid=?", (tB["uuid"],))
print("template di A:", tA["description"], len(A.template_items(tA["id"])), "item")

# Non-member tidak bisa push
cx = client("stranger@test.id", "pass-x")
C = Database("/tmp/A.db")
try:
    C.update_project(pid, name="hack")
    sync(C, cx)
    print("FAIL: non-member bisa push")
except CloudError as e:
    print("non-member ditolak:", str(e)[:60])
print("server tables:", {t: len(v) for t, v in M.TABLES.items()})
print("SYNC TEST OK")
