"""v2.8: foto evidence per item uji DI/DO + Report Uji DI/DO terpisah.

- foto evidence (attachment.check_id) sinkron lewat server tiruan → laptop lain dapat tautan item + foto
- laptop yang dulu menarik foto tanpa check_uuid (versi lama) ditautkan ulang setelah upgrade
- check sheet biasa tidak memuat item DI/DO; dido_report memuat item DI/DO + foto
- matriks SAS tidak memuat blok Rasio CT/VT & DI/DO sebagai device
- UI: tombol evidence hanya di baris DI/DO, dialog evidence menambah foto dari clipboard
"""
import io
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE)); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
import mock_supabase as M  # noqa: E402
from app import sas_matrix as SM  # noqa: E402
from app.cloud import SupabaseClient, SyncEngine  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402
from app.reports import ReportBuilder  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("OK   " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


def jpeg(color):
    from PySide6.QtGui import QColor, QImage
    from app.ui.dialogs import _image_to_jpeg
    img = QImage(320, 240, QImage.Format_RGB32)
    img.fill(QColor(color))
    return _image_to_jpeg(img)


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
SEC_DEV = "I. SAS · -A30 MiCOM C264 (BCU)"
SEC_DIDO = "K. SAS · DI/DO -A30 MiCOM C264 (BCU)"
A.add_check_item(pn, SEC_DEV, "Device terintegrasi ke SAS (online di HMI SAS 1 & 2)", "Online")
A.add_check_item(pn, "J. SAS · Rasio CT/VT", "-A30 MiCOM C264 (BCU) · CT ratio", "Sesuai drawing", "rasio")
di = A.add_check_item(pn, SEC_DIDO, "DI slot P (DI1–DI16) · sh.061–062", "Status DI masuk BCU/HMI sesuai drawing")
do = A.add_check_item(pn, SEC_DIDO, "DO CB (-Q0) · sh.047", "Perintah BCU/HMI → peralatan beroperasi")
A.set_check(di, result="OK")
A.set_check(do, result="OK")
a1 = A.add_check_photo(di, "di_p.jpg", jpeg("red"), caption="HMI event DI1-DI16")
A.add_check_photo(di, "di_p2.jpg", jpeg("blue"))
check(len(A.check_photos(di)) == 2 and A.check_photo_counts(pn) == {di: 2}, "foto evidence tersimpan per item")
check(not A.attachments(None), "foto evidence tidak muncul sebagai lampiran punch")

# ---------------------------------------------------------------- sinkron A → server → B
SyncEngine(A, ca).run()
srv_att = [r for r in M.TABLES["attachments"].values() if r.get("check_uuid")]
di_uuid = A.check(di)["uuid"]
check(len(srv_att) == 2 and all(r["check_uuid"] == di_uuid and not r.get("issue_uuid") for r in srv_att),
      "server: 2 lampiran dengan check_uuid, tanpa issue_uuid")
check(all(r["storage_path"].startswith(f"check/{di_uuid}/") for r in srv_att), "path storage check/<uuid>/")
SyncEngine(B, cb).run()
di_b = B.q1("SELECT id FROM panel_check WHERE uuid=?", (di_uuid,))["id"]
ph_b = B.check_photos(di_b)
check(len(ph_b) == 2 and all(B.attachment_data(r["id"]) for r in ph_b), "laptop B: 2 foto evidence + datanya")
check({r["caption"] for r in ph_b} == {"HMI event DI1-DI16", ""}, "caption ikut")

# ---------------------------------------------------------------- versi lama: baris tanpa check_id → ditautkan ulang
B.conn.execute("UPDATE attachment SET check_id=NULL WHERE check_id IS NOT NULL")
B.set_setting("att_check_uuid_v1", "")
B.conn.commit()
check(not B.check_photos(di_b), "simulasi versi lama: tautan hilang")
SyncEngine(B, cb).run()
check(len(B.check_photos(di_b)) == 2, "setelah upgrade: tautan foto evidence pulih")
SyncEngine(B, cb).run()
check(B.pending_changes() == 0, "tidak ada perubahan tertunda setelah sinkron ulang")

# ---------------------------------------------------------------- hapus di B → A
B.delete_attachment(ph_b[0]["id"])
SyncEngine(B, cb).run()
SyncEngine(A, ca).run()
check(len(A.check_photos(di)) == 1, "hapus foto evidence ikut tersinkron")

# ---------------------------------------------------------------- matriks SAS
devs = SM.sas_matrix(A.panel_checks(pn))
names = [d["name"] for d in devs]
check("-A30 MiCOM C264 (BCU)" in names and not any("DI/DO" in n or "Rasio" in n for n in names),
      f"matriks SAS hanya device: {names}")
check(SM.is_dido_section(SEC_DIDO) and not SM.is_dido_section(SEC_DEV), "is_dido_section")

# ---------------------------------------------------------------- report
seen = []
orig = ReportBuilder.__dict__["check_item_filter"]
ReportBuilder.check_item_filter = staticmethod(lambda rows, *a, **k: (seen.extend(rows), orig.__func__(rows, *a, **k))[1])
rb = ReportBuilder(A, pid)
rb.check_sheets(f"{tmp}/cs.pdf", [pn])
check(seen and not any(SM.is_dido_section(r["section"]) for r in seen), "check sheet tanpa item DI/DO")
seen.clear()
n = rb.dido_report(f"{tmp}/dido.pdf", [p["id"] for p in A.panels(pid)])
check(n == 1 and seen and all(SM.is_dido_section(r["section"]) for r in seen), "report DI/DO: 1 panel, hanya item DI/DO")
ReportBuilder.check_item_filter = orig
size_photo = os.path.getsize(f"{tmp}/dido.pdf")
rb.dido_report(f"{tmp}/dido_nophoto.pdf", [pn], with_photos=False)
check(size_photo > os.path.getsize(f"{tmp}/dido_nophoto.pdf") + 1000, "foto evidence tercetak di report")
from app.i18n import using  # noqa: E402
with using("en"):
    check(ReportBuilder(A, pid).dido_report(f"{tmp}/dido_en.pdf", [pn]) == 1, "report DI/DO bahasa Inggris")

# ---------------------------------------------------------------- UI
from PySide6.QtGui import QColor, QImage  # noqa: E402
from app.ui.dialogs import EvidenceDialog  # noqa: E402
img = QImage(200, 100, QImage.Format_RGB32)
img.fill(QColor("green"))
QApplication.clipboard().setImage(img)
d = EvidenceDialog(None, A, do, "TEST")
d._paste()
check(len(A.check_photos(do)) == 1 and d.photos.count() == 1, "dialog evidence: tempel screenshot dari clipboard")
d.close()


class _Main:
    db = A
    project_id = pid

    def refresh_all(self, **k):
        pass


class _View:
    main = _Main()
    photo_counts = A.check_photo_counts(pn)
    page = None

    def stats_changed(self, *a, **k):
        pass


from app.ui.page_checklist import CheckRow  # noqa: E402
rows = {r["id"]: r for r in A.panel_checks(pn)}
r_dev = CheckRow(_View(), next(r for r in rows.values() if r["section"] == SEC_DEV), 1, [])
r_di = CheckRow(_View(), rows[di], 2, [])
check(r_dev.ebtn is None and r_di.ebtn is not None and r_di.ebtn.text() == "1", "tombol evidence hanya di item DI/DO")
r_new = CheckRow(_View(), A.check(A.add_check_item(pn, SEC_DIDO, "DO DS BUS-1 (-Q1) · sh.050", "x")), 3, [])
r_new.apply_result("OK")
check("belum ada foto" in r_new.ebtn.toolTip(), "OK tanpa foto → tombol mengingatkan")

srv.shutdown()
print("ALL OK" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
