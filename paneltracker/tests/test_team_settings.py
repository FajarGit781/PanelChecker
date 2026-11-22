"""Pengaturan tim (kop, logo, tanda tangan, daftar pilihan, target default) ikut sinkron antar laptop."""
import os, sys, sqlite3, json
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # paneltracker/
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
import mock_supabase as M
from app.db import Database, OLD_STAMP
from app.cloud import SupabaseClient, SyncEngine

srv, URL = M.start()
M.USERS.update({"v@test.id": "pass-v"}); M.MEMBERS["v@test.id"] = "viewer"


def fresh(p):
    for s in ("", "-wal", "-shm"):
        if os.path.exists(p + s):
            os.remove(p + s)
    return Database(p)


def eng(db, who="a@test.id", pw="pass-a", push=True):
    c = SupabaseClient(URL, "k"); c.sign_in(who, pw)
    return SyncEngine(db, c, push=push).run()


# --- 1. laptop lama (sebelum v2.7) yang sudah mengisi kop: kolom baru ditambah & nilai custom ditandai kirim
p = "/tmp/ts_old.db"
old = fresh(p); old.close()
con = sqlite3.connect(p)
con.execute("CREATE TABLE s2 (key TEXT PRIMARY KEY, value TEXT)")   # bentuk tabel settings v2.6
con.execute("INSERT INTO s2 SELECT key, value FROM settings"); con.execute("DROP TABLE settings")
con.execute("ALTER TABLE s2 RENAME TO settings")
con.execute("UPDATE settings SET value='PT Lama Jaya' WHERE key='company_name'")
con.execute("DELETE FROM settings WHERE key='logo'")
con.commit(); con.close()
old = Database(p)
dirty = {r["key"]: r["updated_at"] for r in old.shared_settings_dirty()}
assert dirty == {"company_name": OLD_STAMP}, dirty
print("migrasi laptop lama:", dirty)

# --- 2. laptop A mengisi pengaturan lalu sinkron
A = fresh("/tmp/ts_a.db")
A.set_setting("company_name", "PT Gardu Andalan")
A.set_setting("company_address", "Jl. Relay No. 1, Batam")
A.set_setting("sign_prepared", "Fajar")
A.set_setting("due_days_Critical", "2")
A.set_setting("categories", json.dumps(["Wiring", "Proteksi"]))
logo = open(os.path.join(_ROOT, "assets", "icon.png"), "rb").read()
A.set_logo(logo, "logo.png")
assert A.pending_changes() >= 6
st = eng(A); print("A push:", st)
assert not A.shared_settings_dirty()
srv_rows = {r["key"]: r for r in M.TABLES["team_settings"].values()}
assert srv_rows["company_name"]["value"] == "PT Gardu Andalan" and len(srv_rows["logo"]["value"]) > 100
# simpan ulang tanpa perubahan → tidak ada yang dikirim lagi
A.set_setting("company_name", "PT Gardu Andalan"); A.set_logo(logo, "logo.png")
assert not A.shared_settings_dirty(), "simpan tanpa perubahan tidak boleh menandai kirim"

# --- 3. laptop B baru: langsung dapat semua pengaturan
B = fresh("/tmp/ts_b.db")
eng(B, "b@test.id", "pass-b")
assert B.get_setting("company_name") == "PT Gardu Andalan"
assert B.get_setting("company_address") == "Jl. Relay No. 1, Batam"
assert B.get_setting("sign_prepared") == "Fajar" and B.get_setting("due_days_Critical") == "2"
assert B.get_list_setting("categories") == ["Wiring", "Proteksi"]
assert B.get_logo() == logo, "logo harus sama persis"
assert not B.shared_settings_dirty(), "data dari cloud tidak boleh dikirim balik"
print("B terima:", B.get_setting("company_name"), "| logo", len(B.get_logo()), "byte")

# --- 4. laptop lama sinkron: nilai cloud (lebih baru) menang atas nilai lama
eng(old, "b@test.id", "pass-b")
assert old.get_setting("company_name") == "PT Gardu Andalan", old.get_setting("company_name")
print("laptop lama ikut tim:", old.get_setting("company_name"))

# --- 5. B mengubah, A menerima; logo dihapus ikut terhapus
B.set_setting("company_address", "Jl. Proteksi No. 2"); B.set_logo(None)
eng(B, "b@test.id", "pass-b"); eng(A)
assert A.get_setting("company_address") == "Jl. Proteksi No. 2" and A.get_logo() is None
print("perubahan B sampai di A; logo terhapus")

# --- 6. konflik: dua laptop mengubah saat offline → yang terakhir menang
A.set_setting("company_name", "PT Versi A")
B.set_setting("company_name", "PT Versi B")   # lebih baru
eng(A); eng(B, "b@test.id", "pass-b"); eng(A)
assert A.get_setting("company_name") == B.get_setting("company_name") == "PT Versi B"
print("konflik: yang terakhir menang →", A.get_setting("company_name"))

# --- 7. viewer: menerima, tidak mengirim
V = fresh("/tmp/ts_v.db")
eng(V, "v@test.id", "pass-v", push=False)
assert V.get_setting("company_name") == "PT Versi B"
V.set_setting("company_name", "PT Coba Viewer")
eng(V, "v@test.id", "pass-v", push=False)
assert {r["key"]: r for r in M.TABLES["team_settings"].values()}["company_name"]["value"] == "PT Versi B"
print("viewer: terima saja, tidak mengubah cloud")

# --- 8. pengaturan lokal (nama user, cursor) tidak pernah dikirim
assert "user_name" not in {r["key"] for r in M.TABLES["team_settings"].values()}
print("TEAM SETTINGS OK")
