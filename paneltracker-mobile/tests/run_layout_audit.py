"""Audit tata letak semua layar HP di layar sempit (Safari iPhone 375 px / Chrome Android 360 px) dengan nama panel
asli GI GAIA 2 (tag & nama panjang, multi-baris). Gagal bila ada elemen yang keluar layar atau halaman bisa bergeser
ke samping. Build tes dulu: PT_TEST=1 npx vite build --outDir <DIST>; lalu python tests/run_layout_audit.py <DIST> [OUT]
"""
import functools
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
REAL = [
    ("ET09+R1 & ET09+W1", "Panel Control & Protection Trafo #9", "TRANSFORMER-9"),
    ("=ES02+WR1", "BUS SECTION 2A2B\nBAY CONTROL &\nPROTECTION PANEL", "BUS SECTION 2A2B\nBAY CONTROL &\nPROTECTION PANEL"),
    ("=EC01+WR1", "BUS COUPLER\n1A2A BAY CONTROL &\nPROTECTION PANEL", "BUS COUPLER\n1A2A BAY CONTROL &\nPROTECTION PANEL"),
    ("=EC02+WR1", "BUS COUPLER 1B2B\nBAY CONTROL &\nPROTECTION PANEL", "BUS COUPLER 1B2B\nBAY CONTROL &\nPROTECTION PANEL"),
    ("=E00+R1", "BUSBAR PROTECTION\nPANEL SYSTEM 1A2A", "BUSBAR PROTECTION\nPANEL SYSTEM 1A2A"),
    ("=EU01+WR1", "UGC 1 BAY\nCONTROL &\nPROTECTION PANEL", "UGC 1 BAY\nCONTROL &\nPROTECTION PANEL"),
    ("=ET07+R1", "TRANSFORMER-7 BAY PROTECTION PANEL", "TRANSFORMER-7 BAY PROTECTION PANEL"),
]

M.USERS.update({"fajar@paneltracker.local": "Gardu-Induk-2026x", "seed@x.id": "Kuat-Sekali-123a"})
M.MEMBERS.update({"fajar@paneltracker.local": "engineer", "seed@x.id": "engineer"})
srv, URL = M.start()
tmp = tempfile.mkdtemp()
lap = Database(os.path.join(tmp, "laptop.db"))
pid = create_demo(lap)
lap.update_project(pid, code="GAIA2-FAT", name="GI GAIA 2 150kV SAS - Factory Acceptance Test")
pans = lap.panels(pid)
for p, (tag, name, bay) in zip(pans, REAL):
    lap.update_panel(p["id"], tag=tag, name=name, bay=bay)
P0 = pans[3]["id"]   # =EC02+WR1
secs = [r["section"] for r in lap.panel_checks(P0)]
add_items(lap, P0, INJ.block_items("-A30 MiCOM C264 (BCU)", INJ.next_letter(secs), INJ.DEFAULT_SETUP, [(10, 100, 0, 50)]))
c = SupabaseClient(URL, "k"); c.sign_in("seed@x.id", "Kuat-Sekali-123a"); SyncEngine(lap, c).run()


class Q(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


web = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=DIST))
threading.Thread(target=web.serve_forever, daemon=True).start()
APP = f"http://127.0.0.1:{web.server_address[1]}/index.html?server={URL}"

# elemen yang memang boleh digulir menyamping di dalam kotaknya sendiri
SCROLLERS = ".chips, .mx-scroll, .seg"
AUDIT = """(scrollers) => {
  const W = document.documentElement.clientWidth, out = [];
  const de = document.documentElement, sc = document.querySelector('.content');
  if (de.scrollWidth > W + 1) out.push('halaman bisa digeser: scrollWidth ' + de.scrollWidth + ' > ' + W);
  if (sc && sc.scrollWidth > sc.clientWidth + 1) out.push('.content melebar: ' + sc.scrollWidth + ' > ' + sc.clientWidth);
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest(scrollers)) continue;
    const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    if (r.right > W + 1 || r.left < -1) out.push(el.tagName.toLowerCase() + '.' + (el.className || '') + ' [' + Math.round(r.left) + '..' + Math.round(r.right) + ']');
  }
  return [...new Set(out)].slice(0, 12);
}"""
from playwright.sync_api import sync_playwright  # noqa: E402
bad = {}
with sync_playwright() as p:
    for label, launch, ctxargs in (
        ("iphone", p.webkit, {**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 812}}),
        ("android", p.chromium, {"viewport": {"width": 360, "height": 780}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}),
    ):
        b = launch.launch()
        pg = b.new_context(**ctxargs).new_page()
        pg.on("dialog", lambda d: d.accept())

        def shot(n):
            time.sleep(0.5)
            pg.screenshot(path=f"{OUT}/{label}_{n}.png")
            r = pg.evaluate(AUDIT, SCROLLERS)
            if r:
                bad[f"{label}/{n}"] = r

        pg.goto(APP); pg.wait_for_selector("text=Masuk ke tim"); shot("01_login")
        pg.fill("#u", "Fajar"); pg.fill("#p", "Gardu-Induk-2026x"); pg.click("button.btn.primary")
        pg.wait_for_selector(".gauges", timeout=20000); time.sleep(1); shot("02_home")
        pg.click(".nav button:has-text('Panel')"); pg.wait_for_selector(".cubicle"); shot("03_panels")
        pg.evaluate("document.querySelector('.content').scrollTop = 700"); shot("03b_panels_scroll")
        pg.fill("input[type=search]", "EC02"); time.sleep(0.3)
        pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".step"); shot("04_panel_detail")
        pg.wait_for_selector(".inj"); pg.locator(".inj").scroll_into_view_if_needed(); shot("05_injection")
        pg.click("button:has-text('Uji injeksi CT/VT')"); pg.wait_for_selector(".sheet-modal .inj-form"); shot("06_create_sheet")
        pg.click(".sheet-modal .inj-mode button:has-text('P')"); shot("06b_create_target")
        pg.click(".sheet-modal button:has-text('Batal')")
        pg.click(".nav button:has-text('Punch')"); pg.wait_for_selector(".ptag"); shot("07_punches")
        pg.click(".ptag >> nth=0"); pg.wait_for_selector(".flow"); time.sleep(0.8); shot("08_punch_detail")
        pg.click(".nav button:has-text('Akun')"); pg.wait_for_selector("text=Keamanan"); shot("09_account")
        pg.click(".nav button:has-text('Ringkasan')"); pg.wait_for_selector(".gauges")
        pg.click(".icon-btn[aria-label*='project']"); time.sleep(0.4); shot("10_project_sheet")
        b.close()
srv.shutdown(); web.shutdown()
for k, v in bad.items():
    print("FAIL", k)
    for x in v:
        print("     ", x)
print("shots:", OUT)
print("ALL OK" if not bad else "ADA YANG GAGAL")
sys.exit(0 if not bad else 1)
