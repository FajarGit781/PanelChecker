"""Matriks integrasi SAS di aplikasi laptop: device × Integrasi/IP/SNTP/CID/Setting, klik sel, IP langsung, validasi."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
app = QApplication([])
from app.ui.theme import setup_app; setup_app(app)
from app.ui.main_window import MainWindow
from app.demo import create_demo
from app import sas_matrix as SM
import app.ui.widgets as W

# ---- logika (sama dengan aplikasi HP)
assert [SM.next_result(x) for x in ("", "OK", "NG", "NA")] == ["OK", "NG", "NA", ""]
assert SM.subnet_prefix("Subnet 172.16.9.x") == "172.16.9."
used = {"172.16.9.12": "=ET09+R1 · -P501"}
assert SM.ip_warning("172.16.9.11", "Subnet 172.16.9.x", used) == ""
assert "luar subnet" in SM.ip_warning("172.16.90.1", "Subnet 172.16.9.x", used)
assert "tidak valid" in SM.ip_warning("172.16.9.300", "Subnet 172.16.9.x", used)
assert "Sudah dipakai" in SM.ip_warning("172.16.9.12", "Subnet 172.16.9.x", used)
print("logika: OK")

tmp = tempfile.mkdtemp()
st = QSettings(os.path.join(tmp, "m.ini"), QSettings.IniFormat)
w = MainWindow(os.path.join(tmp, "m.db"), remember=False, settings=st); w.show()
pid = create_demo(w.db); w.load_projects(pid)
db = w.db
pans = [o["panel"]["id"] for o in db.panel_overview(pid)][:2]
DEVS = ("-F87T MiCOM P643", "-A30 MiCOM C264 (BCU)")
ITEMS = (("Device terintegrasi ke SAS (online di HMI SAS 1 & 2)", "Online"), ("IP address sudah dikonfigurasi", "Subnet 172.16.1.x"),
         ("SNTP sudah dikonfigurasi & waktu sinkron", "Sync OK"), ("File CID sudah diupload", "Terupload"),
         ("Setting sudah diupload", "Terupload"))
for pn in pans:
    for k, dv in enumerate(DEVS):
        for d, c in ITEMS:
            db.add_check_item(pn, f"{'IJ'[k]}. SAS · {dv}", d, c)
pump = lambda: [app.processEvents() for _ in range(3)]
W.ask = lambda *a, **k: True
w.nav_to(1); pump()
w.go_panel(pans[0]); pump()
view = w.p_check.detail
m = view.matrix
assert m is not None and view.b_matrix.isVisible() and view.b_matrix.isChecked(), "matriks muncul untuk panel ber-SAS"
assert [d["name"] for d in m.devices] == list(DEVS)
assert len(m.cells) == 10
mapped = m.mapped_rows()
assert all(r.isHidden() for r in view.rows if r.cid in mapped), "item SAS tidak tampil dobel di daftar"
assert any(not r.isHidden() for r in view.rows if r.cid not in mapped), "seksi lain tetap tampil"
print("tampilan: OK")

cell = lambda dev, key: next(x for x in m.cells if x[0] == key and dev in x[1].row["section"])
# klik SNTP P643 dua kali → NG (tanpa membuka form punch otomatis)
k, r, b = cell("P643", "sntp")
b.click(); pump(); b.click(); pump()
assert db.check(r.cid)["result"] == "NG" and r.res.value == "NG" and b.text() == "✗"
_, _, _, pb = next(x for x in m.dev_widgets if x[0]["name"] == DEVS[0])
assert not pb.isHidden(), "tombol + Punch muncul untuk sel NG"
# IP valid → otomatis OK
_, rip, wip = cell("P643", "ip")
wip.edit.setText("172.16.1.11"); wip.edit.editingFinished.emit(); pump()
assert db.check(rip.cid)["value"] == "172.16.1.11" and db.check(rip.cid)["result"] == "OK"
# IP dobel (device lain di panel ini) → peringatan, tidak otomatis OK
_, rip2, wip2 = cell("C264", "ip")
wip2.edit.setText("172.16.1.11"); wip2.edit.editingFinished.emit(); pump()
assert db.check(rip2.cid)["result"] == "" and "Sudah dipakai" in wip2.warnlbl.text() and not wip2.warnlbl.isHidden()
# IP di luar subnet → peringatan
wip2.edit.setText("172.16.5.1"); wip2.edit.editingFinished.emit(); pump()
assert db.check(rip2.cid)["result"] == "" and "luar subnet" in wip2.warnlbl.text()
# Semua OK di device C264
_, _, ok_btn, _ = next(x for x in m.dev_widgets if x[0]["name"] == DEVS[1])
ok_btn.click(); pump()
assert all(db.check(r_.cid)["result"] == "OK" for r_ in m.devices[1]["cells"].values())
print("klik sel, IP & Semua OK: OK")

# IP dobel lintas panel: panel 2 memakai IP panel 1
w.go_panel(pans[1]); pump()
m2 = view.matrix
_, rq, wq = next(x for x in m2.cells if x[0] == "ip" and "P643" in x[1].row["section"])
wq.edit.setText("172.16.1.11"); wq.edit.editingFinished.emit(); pump()
assert db.check(rq.cid)["result"] == "" and "Sudah dipakai" in wq.warnlbl.text() and "·" in wq.warnlbl.text()
print("IP dobel antar panel: OK")

# toggle ke daftar: item SAS tampil lagi, pilihan diingat
view.b_matrix.setChecked(False); pump()
assert view.matrix.isHidden() and all(not r.isHidden() for r in view.rows if r.cid in view.matrix.mapped_rows())
assert st.value("ui/sas_matrix") == "0"
view.b_matrix.setChecked(True); pump()
# panel tanpa SAS: tombol matriks disembunyikan
other = [o["panel"]["id"] for o in db.panel_overview(pid)][2]
w.go_panel(other); pump()
assert view.matrix is None and not view.b_matrix.isVisible()
print("toggle & panel tanpa SAS: OK")
print("SEMUA OK")
w.close(); app.processEvents(); sys.stdout.flush(); os._exit(0)
