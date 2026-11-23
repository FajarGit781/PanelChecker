"""Uji UI uji injeksi CT/VT di HP (Chrome, viewport Android) terhadap server tiruan.

Build tes dulu:  PT_TEST=1 npx vite build --outDir <DIST>   lalu:  python tests/run_injection_ui.py <DIST> [OUT_SHOTS]
- laptop membuat blok injeksi → HP menampilkan tabel expected, isi actual → OK/NG otomatis
- HP membuat blok baru (3 titik), "Sisa item OK" tidak menyentuh item injeksi
- baca foto layar HMI (OCR Tesseract di browser) → review → nilai masuk Actual + foto evidence
- sinkron balik ke laptop: nilai & hasil sama
"""
import functools
import json
import os
import sys
import tempfile
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "paneltracker")
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication  # noqa: E402
_a = QApplication([])
import mock_supabase as M  # noqa: E402
from app import injection as INJ  # noqa: E402
from app.cloud import SupabaseClient, SyncEngine  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402
from app.ui.injection_ui import add_items  # noqa: E402
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

DIST = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp()
os.makedirs(OUT, exist_ok=True)
ok = True


def check(cond, msg):
    global ok
    print(("OK   " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


M.USERS.update({"fajar@paneltracker.local": "Gardu-Induk-2026x", "seed@x.id": "Kuat-Sekali-123a"})
M.MEMBERS.update({"fajar@paneltracker.local": "engineer", "seed@x.id": "engineer"})
srv, URL = M.start()
tmp = tempfile.mkdtemp()
lap = Database(os.path.join(tmp, "laptop.db"))
pid = create_demo(lap)
pans = {p["tag"]: p["id"] for p in lap.panels(pid)}
P1, P2 = pans["A-CRP-01"], pans["A-CRP-02"]
DEV = "-A30 MiCOM C264 (BCU)"
secs = [r["section"] for r in lap.panel_checks(P1)]
add_items(lap, P1, INJ.block_items(DEV, INJ.next_letter(secs), INJ.DEFAULT_SETUP, [(10, 100, 0, 50), (50, 100, 30, 50)]))
SEC = INJ.section_name(INJ.next_letter(secs), DEV)
c = SupabaseClient(URL, "k"); c.sign_in("seed@x.id", "Kuat-Sekali-123a"); print("seed:", SyncEngine(lap, c).run())

# gambar layar HMI untuk diuji OCR (nilai titik T2: 50 % · φ 30°)
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
img = QImage(1000, 640, QImage.Format_RGB32); img.fill(QColor("#0B1A12"))
pp = QPainter(img); pp.setPen(QColor("#8EF0B0")); f = QFont("Menlo"); f.setPixelSize(42); pp.setFont(f)
for i, t in enumerate(["BCU =E01 MEASUREMENT", "IA 1001.0 A", "IB 998.6 A", "IC 1000.2 A", "P 225.1 MW", "Q 126.9 MVAR", "PF 0.871", "f 50.00 Hz"]):
    pp.drawText(50, 70 + i * 70, t)
pp.end()
HMI = os.path.join(tmp, "hmi.png"); img.save(HMI)


class Q(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


web = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=DIST))
threading.Thread(target=web.serve_forever, daemon=True).start()
APP = f"http://127.0.0.1:{web.server_address[1]}/index.html?server={URL}"

from playwright.sync_api import sync_playwright  # noqa: E402
ERR = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 412, "height": 892}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: ERR.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and ERR.append(m.text))
    pg.on("dialog", lambda d: d.accept())
    shot = lambda n: (time.sleep(0.4), pg.screenshot(path=f"{OUT}/{n}.png"))
    pg.goto(APP); pg.wait_for_selector("text=Masuk ke tim")
    pg.fill("#u", "Fajar"); pg.fill("#p", "Gardu-Induk-2026x"); pg.click("button.btn.primary")
    pg.wait_for_selector(".gauges", timeout=20000); time.sleep(1.5)
    pg.click(".nav button:has-text('Panel')"); pg.wait_for_selector(".cubicle")
    pg.fill("input[type=search]", "A-CRP-01"); time.sleep(0.3)
    pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".step")
    pg.wait_for_selector(".inj")
    check(pg.locator(".inj .inj-pt").count() == 2, "blok injeksi dari laptop tampil (2 titik uji)")
    check(pg.locator(".inj .inj-t input").count() == 20, "20 isian Actual")
    pg.locator(".inj").scroll_into_view_if_needed(); shot("inj_01_block")
    t1 = pg.locator(".inj .inj-pt").nth(0)
    t1.locator("tbody tr").nth(0).locator("input").fill("201.5"); t1.locator("tbody tr").nth(0).locator("input").press("Enter"); time.sleep(0.5)
    t1 = pg.locator(".inj .inj-pt").nth(0)
    check("OK" in t1.locator("tbody tr").nth(0).locator(".pill").inner_text(), "IA 201,5 → OK")
    t1.locator("tbody tr").nth(1).locator("input").fill("205"); t1.locator("tbody tr").nth(1).locator("input").press("Enter"); time.sleep(0.5)
    t1 = pg.locator(".inj .inj-pt").nth(0)
    check("NG" in t1.locator("tbody tr").nth(1).locator(".pill").inner_text(), "IB 205 → NG")
    check(t1.locator("tbody tr").nth(1).locator(".add-punch").count() == 1, "NG → tombol + Punch")
    check("+2.50 %" in t1.locator("tbody tr").nth(1).inner_text(), "error % tampil")
    shot("inj_02_values")

    # ---- baca foto HMI (OCR di browser)
    t2 = pg.locator(".inj .inj-pt").nth(1)
    t2.locator(".inj-ocr input[type=file]:not([capture])").set_input_files(HMI)
    pg.wait_for_selector(".sheet-modal .inj-rv", timeout=120000)
    shot("inj_03_review")
    rv = pg.inner_text(".sheet-modal")
    check("1001.0" in rv and "126.900" in rv and "0.871" in rv, "review menampilkan nilai terbaca")
    pg.click(".sheet-modal button.primary"); time.sleep(1)
    t2 = pg.locator(".inj .inj-pt").nth(1)
    vals = [t2.locator("tbody tr").nth(i).locator("input").input_value() for i in range(10)]
    check(vals[0] == "1001" and vals[6] == "225.1" and vals[7] == "126.9" and vals[8] == "0.871" and vals[9] == "50",
          f"nilai foto masuk Actual (VAB/VBC/VCA tidak ada di foto → tetap kosong): {vals}")
    check("NG" in t2.locator("tbody tr").nth(7).locator(".pill").inner_text(), "Q 126,9 (expected 129,9) → NG")
    check(t2.locator(".evidence .ev-item").count() == 1, "foto HMI tersimpan sebagai evidence T2")
    shot("inj_04_after_ocr")

    # ---- HP membuat blok baru di panel lain
    pg.click(".back-btn"); pg.wait_for_selector(".cubicle")
    pg.fill("input[type=search]", "A-CRP-02"); time.sleep(0.3)
    pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".step")
    pg.click("button:has-text('Uji injeksi CT/VT')"); pg.wait_for_selector(".sheet-modal .inj-form")
    shot("inj_05_create")
    pg.locator(".sheet-modal .fld input").nth(1).fill("1600")          # CT primer
    pg.click(".sheet-modal button.primary:has-text('Buat')"); time.sleep(0.8)
    check(pg.locator(".inj .inj-pt").count() == 3, "blok baru 3 titik (10, 50, 100 %)")
    ia = pg.locator(".inj .inj-pt").nth(0).locator("td.ex").nth(0).inner_text()
    check(ia.startswith("160.0"), f"expected IA 10 % dari CT 1600/1 = 160 A: {ia}")
    if pg.locator("button:has-text('Sisa item OK')").count():
        pg.click("button:has-text('Sisa item OK')"); time.sleep(0.6)
    check(pg.locator(".inj td.st .pill:not(.OK):not(.NG)").count() == 30, "'Sisa item OK' tidak menyentuh item injeksi")
    pg.locator(".inj").scroll_into_view_if_needed(); shot("inj_06_new_block")

    # ---- bahasa Inggris
    pg.click(".nav button:has-text('Akun')"); pg.click(".line:has-text('English')"); pg.wait_for_selector(".gauges"); time.sleep(0.5)
    pg.click(".nav button:has-text('Panel')"); pg.fill("input[type=search]", "A-CRP-01"); time.sleep(0.3)
    pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".inj"); pg.locator(".inj").scroll_into_view_if_needed()
    check("quantity" in pg.inner_text(".inj").lower() and "fill actual" in pg.inner_text(".inj").lower(), "UI bahasa Inggris")
    shot("inj_07_en")
    time.sleep(3)   # sinkron otomatis
    pg.evaluate("() => 0")
    b.close()

# ---- laptop menerima hasil dari HP
c2 = SupabaseClient(URL, "k"); c2.sign_in("seed@x.id", "Kuat-Sekali-123a")
print("laptop pull:", SyncEngine(lap, c2).run())
g = INJ.group([r for r in lap.panel_checks(P1) if r["section"] == SEC])
r1 = g["points"][0]["rows"]
check(r1["IA"]["value"] == "201.5" and r1["IA"]["result"] == "OK" and r1["IB"]["result"] == "NG", "laptop: hasil T1 dari HP")
r2 = g["points"][1]["rows"]
check(r2["Q"]["value"] == "126.9" and r2["Q"]["result"] == "NG", "laptop: nilai baca foto T2 dari HP")
check(len(lap.check_photos(r2["IA"]["id"])) == 1, "laptop: foto HMI evidence T2")
blk2 = [r for r in lap.panel_checks(P2) if INJ.is_injection_section(r["section"])]
check(len(blk2) == 31 and INJ.parse_setup(next(r for r in blk2 if r["unit"] == "setup")["criteria"])["ct_p"] == 1600,
      "laptop: blok baru dari HP (setup CT 1600/1 + 30 item)")
ERR = [e for e in ERR if "400 (Bad Request)" not in e]
check(not ERR, f"tanpa error JS: {ERR}")
srv.shutdown(); web.shutdown()
print("shots:", OUT)
print("ALL OK" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
