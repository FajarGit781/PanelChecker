import sys, os, shutil, subprocess
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # paneltracker/
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QGuiApplication
_a = QGuiApplication([])
import mock_supabase as M
from app.db import Database
from app.cloud import SupabaseClient, SyncEngine
from app.import_fat import import_fat_punchlist
from app.reports import ReportBuilder
D = "/tmp/photofix"; shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
FAT = os.environ.get("PT_FAT_XLSX", os.path.join(_ROOT, "tests", "data", "Punchlist_GI_GAIA_2_13112026.xlsx"))
if not os.path.exists(FAT):
    print(f"SKIP: file FAT tidak ada ({FAT}); set PT_FAT_XLSX untuk menjalankan"); sys.exit(0)
srv, URL = M.start()
def sync(db):
    c = SupabaseClient(URL, "k"); c.sign_in("a@test.id", "pass-a"); return SyncEngine(db, c).run()
# server berisi punch TANPA foto (seperti kondisi Supabase sekarang)
s = Database(f"{D}/seed.db"); import_fat_punchlist(s, FAT, site_name="GI GAIA 2")
s.conn.execute("DELETE FROM attachment"); s.conn.commit(); print("seed push:", sync(s))
# laptop user: DB baru → sinkron → punch ada, foto tidak ada
u = Database(f"{D}/user.db"); print("user pull:", sync(u))
pid = u.projects()[0]["id"]
print("user punch/foto:", len(u.issues(pid)), u.q1("SELECT COUNT(*) c FROM attachment WHERE deleted=0")["c"])
# perbaikan: import ulang file FAT → foto dilengkapi, punch tidak dobel
r = import_fat_punchlist(u, FAT, site_name="GI GAIA 2"); print("re-import:", r)
print("user punch/foto:", len(u.issues(pid)), u.q1("SELECT COUNT(*) c FROM attachment WHERE deleted=0")["c"])
print("user push:", sync(u), "storage:", len(M.STORAGE))
# laptop lain: DB baru → sinkron → foto terunduh → report ada foto
v = Database(f"{D}/other.db"); print("other pull:", sync(v))
vp = v.projects()[0]["id"]
ReportBuilder(v, vp).punchlist_report(f"{D}/pl.pdf")
n_img = len(subprocess.run(["pdfimages", "-list", f"{D}/pl.pdf"], capture_output=True, text=True).stdout.splitlines()) - 2
print("laptop lain punch:", len(v.issues(vp)), "| foto di DB:", v.q1("SELECT COUNT(*) c FROM attachment WHERE deleted=0 AND data IS NOT NULL")["c"], "| gambar di PDF:", n_img)
srv.shutdown()
