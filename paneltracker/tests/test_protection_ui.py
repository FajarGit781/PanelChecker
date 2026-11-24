"""v2.10: uji proteksi relay di laptop — blok di halaman Checking, setting → expected, actual → OK/NG, uji fungsional,
toleransi, hapus blok kosong, report PDF terpisah, Lembar Uji tidak memuatnya, sinkron ke laptop lain."""
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
from app import relaytest as R  # noqa: E402
from app.cloud import SupabaseClient, SyncEngine  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402
from app.reports import ReportBuilder  # noqa: E402
from app.ui import protection_ui as PU  # noqa: E402
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
PU.ask = lambda *a, **k: True
DEV = "-F87T MiCOM P643"
db.add_check_item(pn, "J. SAS · Rasio CT/VT", f"{DEV} · CT ratio", "Sesuai drawing", "rasio")
check(PU.ratio_devices(db.panel_checks(pn)) == [DEV], "relay dari item rasio")

# ---- buat blok (dialog di-stub lewat add_items)
secs = [r["section"] for r in db.panel_checks(pn)]
PU.add_items(db, pn, R.block_items(DEV, R.next_letter(secs), ["51", "87T", "TRIP", "90"]))
SEC = R.section_name(R.next_letter(secs), DEV)
rows = [r for r in db.panel_checks(pn) if r["section"] == SEC]
check(len(rows) == 1 + 5 + 5 + 1 + 4 and next(r for r in rows if r["unit"] == "psetup")["result"] == "OK", "blok dibuat, toleransi OK")
w.nav_to(1); pump(); w.go_panel(pn); pump()
view = w.p_check.detail
blk = next(b for b in view.inj_blocks if b.section == SEC)
check(isinstance(blk, PU.ProtectionBlock) and blk.stats() == (0, 0, 15), f"blok proteksi tampil: {blk.stats()}")
check(not any(R.is_protection_section(r.section) for r in view.rows), "item proteksi tidak tampil dobel")
check(blk.used() == 0, "blok kosong")


def g():
    return R.group([r for r in db.panel_checks(pn) if r["section"] == SEC])


# ---- setting 51 (dialog di-stub)
class FakeSetting:
    params_ = {"kurva": "IEC SI", "Is": "1", "TMS": "0.1"}
    def __init__(self, *a, **k): pass
    def exec(self): return True
    def params(self): return dict(FakeSetting.params_)


PU.SettingDialog = FakeSetting
blk.edit_setting(g()["funcs"][0], g()["tol"]); pump()
f51 = g()["funcs"][0]
pts = dict(f51["points"])
check(R.parse_params(f51["fset"]["criteria"]) == FakeSetting.params_, "setting 51 tersimpan")
check(pts["2×Is"]["criteria"] == "1.003 ± 0.050" and pts["10×Is"]["criteria"] == "0.297 ± 0.040", "kriteria expected dihitung")
blk = next(b for b in view.inj_blocks if b.section == SEC)
blk._save(pts["2×Is"]["id"], 1.00287, 0.05014, "1.04"); pump()
blk._save(pts["5×Is"]["id"], 0.42780, 0.04, "0.6"); pump()
pts = dict(g()["funcs"][0]["points"])
check(pts["2×Is"]["result"] == "OK" and pts["5×Is"]["result"] == "NG", "actual → OK/NG")
blk = next(b for b in view.inj_blocks if b.section == SEC)
blk._set_result(dict(g()["funcs"][2]["points"])[R.FUNCS["TRIP"][0]]["id"], "OK"); pump()
check(dict(g()["funcs"][2]["points"])[R.FUNCS["TRIP"][0]]["result"] == "OK", "uji fungsional TRIP OK")

# ---- ubah toleransi → kriteria & hasil dihitung ulang (10 % / 50 ms)
class FakeTol:
    def __init__(self, *a, **k): pass
    def exec(self): return True
    def value(self): return dict(t_pct=50.0, t_ms=50.0, p_pct=5.0)


PU.TolDialog = FakeTol
blk = next(b for b in view.inj_blocks if b.section == SEC)
blk.edit_tol(g()); pump()
pts = dict(g()["funcs"][0]["points"])
check(g()["tol"]["t_pct"] == 50 and pts["5×Is"]["criteria"] == "0.428 ± 0.214" and pts["5×Is"]["result"] == "OK",
      f"toleransi baru → 5×Is jadi OK: {pts['5×Is']['criteria']}")

# ---- hapus blok: berisi hasil ditolak; blok kosong boleh
warned = []
PU.warn = lambda *a, **k: warned.append(a[1])
blk = next(b for b in view.inj_blocks if b.section == SEC)
blk.delete_block(); pump()
check(warned and len([r for r in db.panel_checks(pn) if r["section"] == SEC]) == 16, "blok berisi hasil tidak dihapus")
secs2 = [r["section"] for r in db.panel_checks(pn)]
SEC2 = R.section_name(R.next_letter(secs2), "-N90 RTF")
PU.add_items(db, pn, R.block_items("-N90 RTF", R.next_letter(secs2), R.preset_for("-N90 RTF")))
view.load(pn); pump()
b2 = next(b for b in view.inj_blocks if b.section == SEC2)
b2.delete_block(); pump()
check(not [r for r in db.panel_checks(pn) if r["section"] == SEC2], "blok kosong dihapus")

# ---- report & lembar uji
rb = ReportBuilder(db, pid)
check(rb.protection_report(os.path.join(tmp, "prot.pdf"), [pn]) == 1 and os.path.getsize(os.path.join(tmp, "prot.pdf")) > 3000,
      "report uji proteksi dibuat")
src = open(os.path.join(os.path.dirname(_HERE), "app", "reports.py"), encoding="utf-8").read()
check("not RT.is_protection_section" in src, "Lembar Uji tidak memuat blok proteksi")
from app.sas_matrix import is_measurement  # noqa: E402
check(not is_measurement("fset") and not is_measurement("psetup"), "item setting bukan measurement")
from app.i18n import set_lang  # noqa: E402
try:
    set_lang("en")
    check(ReportBuilder(db, pid).protection_report(os.path.join(tmp, "prot_en.pdf"), [pn]) == 1, "report bahasa Inggris")
finally:
    set_lang("id")
if os.environ.get("PT_SHOT_DIR"):
    import shutil
    shutil.copy(os.path.join(tmp, "prot.pdf"), os.environ["PT_SHOT_DIR"])
    view.load(pn); pump(); w.resize(1400, 900); pump()
    b = next(b for b in view.inj_blocks if b.section == SEC)
    view.sa.ensureWidgetVisible(b); pump()
    w.grab().save(os.path.join(os.environ["PT_SHOT_DIR"], "prot_ui.png"))

# ---- sinkron ke laptop lain
srv, URL = M.start()
c1 = SupabaseClient(URL, "sb_publishable_test"); c1.sign_in("a@test.id", "pass-a")
c2 = SupabaseClient(URL, "sb_publishable_test"); c2.sign_in("b@test.id", "pass-b")
SyncEngine(db, c1).run()
B = Database(os.path.join(tmp, "B.db"))
SyncEngine(B, c2).run()
pb = B.q1("SELECT id FROM panel WHERE uuid=?", (db.panel(pn)["uuid"],))["id"]
gb = R.group([r for r in B.panel_checks(pb) if r["section"] == SEC])
check(gb["tol"]["t_pct"] == 50 and R.parse_params(gb["funcs"][0]["fset"]["criteria"])["Is"] == "1"
      and dict(gb["funcs"][0]["points"])["2×Is"]["value"] == "1.04", "laptop lain menerima setting, toleransi & hasil")
print("ALL OK" if ok else "ADA YANG GAGAL")
w.close(); app.processEvents(); sys.stdout.flush(); os._exit(0 if ok else 1)
