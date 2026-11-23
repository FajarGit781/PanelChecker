"""Uji interoperabilitas: aplikasi desktop (Python) ↔ aplikasi HP (TypeScript) lewat server tiruan."""
import os, sys, shutil, subprocess, json
_HERE = os.path.dirname(os.path.abspath(__file__))
_MOBILE = os.path.dirname(_HERE)  # paneltracker-mobile/
_ROOT = os.path.join(os.path.dirname(_MOBILE), "paneltracker")
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QGuiApplication
_a = QGuiApplication([])
import mock_supabase as M
M.USERS.update({"a@test.id": "Kuat-Sekali-123a", "v@test.id": "Lihat-Saja-77x"})
M.MEMBERS["v@test.id"] = "viewer"
from app.db import Database
from app.cloud import SupabaseClient, SyncEngine
from app.demo import create_demo
D = "/tmp/interop"; shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
srv, URL = M.start()
def dsync(db):
    c = SupabaseClient(URL, "k"); c.sign_in("a@test.id", "Kuat-Sekali-123a"); return SyncEngine(db, c).run()
lap = Database(f"{D}/laptop.db"); pid = create_demo(lap); print("desktop push:", dsync(lap))
def mobile(phase, **extra):
    env = dict(os.environ, MOCK_URL=URL, PHASE=phase, **extra)
    r = subprocess.run(["npx", "vitest", "run", "tests/interop.test.ts", "--reporter=dot"], cwd=_MOBILE,
                       env=env, capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    print(f"--- mobile {phase}: exit {r.returncode}")
    print("\n".join(l for l in out.splitlines() if l.startswith(("pull:", "push:", "viewer ok", "{")) or "FAIL" in l or "Error" in l or "expected" in l.lower())[:3000])
    return r.returncode, out
rc, out = mobile("unit"); assert rc == 0
rc, out = mobile("edit"); assert rc == 0
info = json.loads([l for l in out.splitlines() if l.startswith("{\"code\"")][0])
# desktop menarik perubahan HP
print("desktop pull:", dsync(lap))
iss = lap.q1("SELECT * FROM issue WHERE uuid=?", (info["issue"],))
assert iss and iss["title"] == "Temuan dari HP" and iss["code"] == info["code"], dict(iss) if iss else None
assert lap.q1("SELECT check_id FROM issue WHERE uuid=?", (info["issue"],))["check_id"] == lap.q1("SELECT id FROM panel_check WHERE uuid=?", (info["check"],))["id"]
chk = lap.q1("SELECT * FROM panel_check WHERE uuid=?", (info["check"],))
assert chk["result"] == "NG" and chk["remark"] == "dari HP", dict(chk)
old = lap.q1("SELECT * FROM issue WHERE uuid=?", (info["old"],))
assert old["status"] == "In Progress" and old["action"] == "dikerjakan dari HP", dict(old)
att = lap.q1("SELECT * FROM attachment WHERE issue_id=?", (iss["id"],))
assert att and att["data"] and bytes(att["data"])[:2] == b"\xff\xd8", "foto HP sampai ke laptop"
cid = lap.q1("SELECT id FROM panel_check WHERE uuid=?", (info["check"],))["id"]
ev = lap.check_photos(cid)
assert len(ev) == 1 and lap.attachment_data(ev[0]["id"])[:2] == b"\xff\xd8", "foto evidence HP sampai ke laptop"
assert not lap.attachments(iss["id"]) or all(a["kind"] != "evidence" for a in lap.attachments(iss["id"]))
# laptop menambah foto evidence di item lain → diterima viewer HP
from PySide6.QtGui import QImage, QColor
from app.ui.dialogs import _image_to_jpeg
_img = QImage(64, 48, QImage.Format_RGB32); _img.fill(QColor("orange"))
other = [c for c in lap.panel_checks(chk["panel_id"]) if c["id"] != cid][0]
lap.add_check_photo(other["id"], "laptop_ev.jpg", _image_to_jpeg(_img))
print("evidence laptop → cloud:", dsync(lap))
ov = {o["panel"]["tag"]: o for o in lap.panel_overview(pid)}
print("desktop lihat panel", info["panel"], ov[info["panel"]]["status"], ov[info["panel"]]["stats"]["NG"], "NG")
# laptop ubah → viewer HP menerima
lap.update_issue(lap.issues(pid)[0]["id"], title="Diubah di laptop"); dsync(lap)
rc, out = mobile("viewer"); assert rc == 0
# viewer tidak bisa menulis ke server
c = SupabaseClient(URL, "k"); c.sign_in("v@test.id", "Lihat-Saja-77x")
try:
    c.upsert("issues", [{"uuid": "x", "updated_at": "2030", "deleted": 0}]); print("!! viewer bisa menulis")
except Exception as e:
    print("viewer ditolak server:", str(e)[:60])
# edit nama item dari HP saat laptop punya hasil yang belum terkirim (dan sebaliknya, di sisi HP)
cb_row = [c for c in lap.panel_checks(chk["panel_id"]) if not c["result"]][0]
lap.set_check(cb_row["id"], result="OK", remark="hasil laptop belum sinkron")
rc, out = mobile("rename", CHECK_B=cb_row["uuid"]); assert rc == 0, out[-3000:]
print("desktop pull setelah rename HP:", dsync(lap))
rb = lap.check(cb_row["id"])
assert rb["description"] == "Nama baru dari HP" and rb["result"] == "OK" and rb["remark"] == "hasil laptop belum sinkron", dict(rb)
sv = M.TABLES["panel_checks"][cb_row["uuid"]]
assert sv["description"] == "Nama baru dari HP" and sv["result"] == "OK", sv
print("rename HP: nama baru + hasil laptop utuh")
srv.shutdown()
print("INTEROP OK")
