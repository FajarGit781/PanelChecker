"""v2.8: foto evidence per item uji DI/DO + Report Uji DI/DO terpisah.

- foto evidence (attachment.check_id) sinkron lewat server tiruan → laptop lain dapat tautan item + foto
- laptop yang dulu menarik foto tanpa check_uuid (versi lama) ditautkan ulang setelah upgrade
- check sheet biasa tidak memuat item DI/DO; dido_report memuat item DI/DO + foto
- matriks SAS tidak memuat blok Rasio CT/VT & DI/DO sebagai device
- UI: tombol evidence di baris DI/DO & measurement test, dialog evidence menambah foto dari clipboard
- foto dikompres (≤1280 px, ≤150 KB) saat disimpan & sebelum upload; lembar uji memuat foto pengukuran
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

# ---------------------------------------------------------------- measurement test & kompresi
from app import imaging  # noqa: E402
check(SM.is_measurement("VDC") and SM.is_measurement("rasio") and not SM.is_measurement("IP")
      and not SM.is_measurement("rev CID") and not SM.is_measurement(""), "is_measurement")
meas = next(r for r in A.panel_checks(pn) if r["unit"] == "VDC")
r_meas = CheckRow(_View(), meas, 4, [])
check(r_meas.ebtn is not None and "foto evidence" in r_meas.ebtn.toolTip(), "tombol evidence di item pengukuran (VDC)")
A.set_check(meas["id"], result="")
check("pengukuran" in CheckRow(_View(), A.check(meas["id"]), 4, []).ebtn.toolTip(), "tooltip evidence pengukuran")
ip_rows = [r for r in A.panel_checks(pn) if not SM.needs_evidence(r["section"], r["unit"])]
check(ip_rows and CheckRow(_View(), ip_rows[0], 5, []).ebtn is None, "item biasa tanpa tombol evidence")

# foto HP 4000x3000 penuh detail → ≤150 KB, ≤1280 px
import random  # noqa: E402
from PySide6.QtGui import QPainter  # noqa: E402
big = QImage(4000, 3000, QImage.Format_RGB32)
pa = QPainter(big)
rnd = random.Random(1)
for _ in range(4000):
    pa.fillRect(rnd.randrange(4000), rnd.randrange(3000), rnd.randrange(5, 200), rnd.randrange(5, 200),
                QColor(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
pa.end()
raw = imaging._jpeg(big, 95)
small = imaging.compress(raw)
chk = QImage.fromData(small)
check(len(small) <= imaging.TARGET and max(chk.width(), chk.height()) <= 1280,
      f"kompresi {len(raw) // 1024} KB → {len(small) // 1024} KB, {chk.width()}x{chk.height()}")
check(imaging.shrink_if_large(jpeg("red")) == jpeg("red"), "foto kecil tidak dikompres ulang")
# foto lama besar di DB → dikompres sebelum upload
mid = A.add_check_photo(meas["id"], "meter.jpg", raw)
SyncEngine(A, ca).run()
up = [v for k, v in M.STORAGE.items() if A.q1("SELECT uuid FROM attachment WHERE id=?", (mid,))["uuid"] in k]
check(up and len(up[0]) <= imaging.TARGET and len(A.attachment_data(mid)) <= imaging.TARGET,
      "foto besar dikompres sebelum upload (storage & lokal)")
# lembar uji: lampiran foto pengukuran
p1 = f"{tmp}/cs_ph.pdf"; p0 = f"{tmp}/cs_noph.pdf"
ReportBuilder(A, pid).check_sheets(p1, [pn])
ReportBuilder(A, pid).check_sheets(p0, [pn], with_photos=False)
check(os.path.getsize(p1) > os.path.getsize(p0) + 5000, "lembar uji memuat foto evidence pengukuran")

srv.shutdown()
print("ALL OK" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
