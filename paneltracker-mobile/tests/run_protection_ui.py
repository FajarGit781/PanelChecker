"""Uji UI uji proteksi relay di HP (Safari iPhone 375 px & Chrome Android) terhadap server tiruan.
Build tes dulu: PT_TEST=1 npx vite build --outDir <DIST>; lalu python tests/run_protection_ui.py <DIST> [OUT]"""
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
from app import relaytest as R  # noqa: E402
from app.cloud import SupabaseClient, SyncEngine  # noqa: E402
from app.db import Database  # noqa: E402
from app.demo import create_demo  # noqa: E402
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

DIST = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp()
os.makedirs(OUT, exist_ok=True)
ok = True


def check(cond, msg):
    global ok
    print(("OK   " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


OVERFLOW = """() => { const W = document.documentElement.clientWidth, out = [];
  if (document.documentElement.scrollWidth > W + 1) out.push('page ' + document.documentElement.scrollWidth);
  for (const el of document.querySelectorAll('.prot *, .sheet-modal *')) { if (el.closest('.chips,.seg')) continue;
    const r = el.getBoundingClientRect(); if (r.width && (r.right > W + 1 || r.left < -1)) out.push(el.tagName + '.' + el.className); }
  for (const b of document.querySelectorAll('.sheet-modal button.primary')) { const r = b.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, Math.min(r.top + r.height / 2, innerHeight - 2));
    if (!hit || !(b === hit || b.contains(hit))) out.push('tombol Simpan tertutup oleh ' + (hit ? hit.tagName + '.' + hit.className : 'luar layar'));
    if (r.bottom > innerHeight + 1) out.push('tombol Simpan di luar layar'); }
  return [...new Set(out)].slice(0, 8); }"""

for label in ("iphone", "android"):
    M.TABLES.update({k: {} for k in M.TABLES}); M.STORAGE.clear()
    M.USERS.update({"fajar@paneltracker.local": "Gardu-Induk-2026x", "seed@x.id": "Kuat-Sekali-123a"})
    M.MEMBERS.update({"fajar@paneltracker.local": "engineer", "seed@x.id": "engineer"})
    srv, URL = M.start()
    tmp = tempfile.mkdtemp()
    lap = Database(os.path.join(tmp, "laptop.db"))
    pid = create_demo(lap)
    pans = {p["tag"]: p["id"] for p in lap.panels(pid)}
    P1, P2 = pans["A-CRP-01"], pans["A-CRP-02"]
    DEV = "-F87T MiCOM P643"
    for pn, dv in ((P1, DEV), (P2, "-N90 RTF")):
        lap.add_check_item(pn, "J. SAS · Rasio CT/VT", f"{dv} · CT ratio", "Sesuai drawing", "rasio")
    secs = [r["section"] for r in lap.panel_checks(P1)]
    mx = max(r["sort"] for r in lap.panel_checks(P1))
    for i, (sec, desc, crit, unit) in enumerate(R.block_items(DEV, R.next_letter(secs), ["51", "87T", "TRIP"]), 1):
        lap._insert("panel_check", dict(panel_id=P1, section=sec, description=desc, criteria=crit, unit=unit, sort=mx + i))
    SEC = R.section_name(R.next_letter(secs), DEV)
    c = SupabaseClient(URL, "k"); c.sign_in("seed@x.id", "Kuat-Sekali-123a"); SyncEngine(lap, c).run()

    class Q(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    web = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=DIST))
    threading.Thread(target=web.serve_forever, daemon=True).start()
    APP = f"http://127.0.0.1:{web.server_address[1]}/index.html?server={URL}"
    from playwright.sync_api import sync_playwright
    ERR, OVER = [], {}
    print(f"== {label}")
    with sync_playwright() as p:
        if label == "iphone":
            b = p.webkit.launch(); ctx = b.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 667}})   # layar pendek (iPhone SE): form panjang harus tetap bisa disimpan
        else:
            b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 360, "height": 780}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: ERR.append(str(e)))
        pg.on("dialog", lambda d: d.accept())

        def shot(n):
            time.sleep(0.4); pg.screenshot(path=f"{OUT}/{label}_{n}.png")
            r = pg.evaluate(OVERFLOW)
            if r: OVER[n] = r

        pg.goto(APP); pg.wait_for_selector("text=Masuk ke tim")
        pg.fill("#u", "Fajar"); pg.fill("#p", "Gardu-Induk-2026x"); pg.click("button.btn.primary")
        pg.wait_for_selector(".gauges", timeout=20000); time.sleep(1)
        pg.click(".nav button:has-text('Panel')"); pg.wait_for_selector(".cubicle")
        pg.fill("input[type=search]", "A-CRP-01"); time.sleep(0.3); pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".prot")
        cards = pg.locator(".prot .inj-pt")
        check(cards.count() == 3, "blok proteksi dari laptop: 3 fungsi")
        check("Setting belum diisi" in cards.nth(0).inner_text(), "fungsi 51 tanpa setting: expected belum ada")
        pg.locator(".prot").scroll_into_view_if_needed(); shot("p01_block")
        # uji fungsional (check) → OK
        cards.nth(2).locator(".push button.OK").click(); time.sleep(0.5)
        check("Lulus" in pg.locator(".prot .inj-pt").nth(2).inner_text(), "uji fungsional TRIP → OK")
        # setting OCR 51
        pg.locator(".prot .inj-pt").nth(0).locator("button:has-text('Setting')").click(); pg.wait_for_selector(".sheet-modal select")
        inp = pg.locator(".sheet-modal .fld input")
        inp.nth(0).fill("1"); inp.nth(1).fill("0.1"); time.sleep(0.3)
        check("1.003" in pg.inner_text(".sheet-modal .inj-prev"), "preview expected 2×Is = 1.003 s")
        shot("p02_setting")
        pg.click(".sheet-modal button.primary"); time.sleep(1)
        c0 = pg.locator(".prot .inj-pt").nth(0)
        check("1.003" in c0.inner_text() and "injeksi 2.000 A" in c0.inner_text(), "expected + panduan injeksi tampil")
        rows = c0.locator(".inj-t tbody tr")
        rows.nth(1).locator("input").fill("1.04"); rows.nth(1).locator("input").press("Enter"); time.sleep(0.5)
        rows = pg.locator(".prot .inj-pt").nth(0).locator(".inj-t tbody tr")
        check("OK" in rows.nth(1).locator(".pill").inner_text(), "2×Is actual 1.04 s → OK")
        rows.nth(2).locator("input").fill("0.6"); rows.nth(2).locator("input").press("Enter"); time.sleep(0.5)
        rows = pg.locator(".prot .inj-pt").nth(0).locator(".inj-t tbody tr")
        check("NG" in rows.nth(2).locator(".pill").inner_text(), "5×Is actual 0.6 s (expected 0.428) → NG")
        check(rows.nth(2).locator(".add-punch").count() == 1, "NG → tombol + Punch")
        pg.locator(".prot .inj-pt").nth(0).scroll_into_view_if_needed(); shot("p03_values")
        # setting 87T
        pg.locator(".prot .inj-pt").nth(1).locator("button:has-text('Setting')").click(); pg.wait_for_selector(".sheet-modal .fld input")
        shot("p02b_setting_87T")
        for i, v in enumerate(["0.2", "30", "1", "80"]):
            pg.locator(".sheet-modal .fld input").nth(i).fill(v)
        pg.click(".sheet-modal button.primary"); time.sleep(1)
        check("2.900" in pg.locator(".prot .inj-pt").nth(1).inner_text(), "87T slope: Ibias 4 In → 2.900 In")
        # blok AVR baru di panel lain + hapus blok kosong
        pg.click(".back-btn"); pg.wait_for_selector(".cubicle")
        pg.fill("input[type=search]", "A-CRP-02"); time.sleep(0.3); pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".step")
        pg.click("button:has-text('Uji proteksi relay')"); pg.wait_for_selector(".sheet-modal .prot-funcs")
        check(pg.locator(".sheet-modal .prot-funcs input:checked").count() == 6, "preset AVR (RTF): 6 fungsi tercentang")
        shot("p04_create")
        pg.click(".sheet-modal button.primary"); time.sleep(0.8)
        check(pg.locator(".prot .inj-pt").count() == 6, "blok AVR dibuat")
        pg.locator(".prot .inj-pt").nth(0).locator("button:has-text('Setting')").click(); pg.wait_for_selector(".sheet-modal .fld input")
        for i, v in enumerate(["110", "1", "30"]):
            pg.locator(".sheet-modal .fld input").nth(i).fill(v)
        pg.click(".sheet-modal button.primary"); time.sleep(1)
        check("injeksi 111.65 V" in pg.locator(".prot .inj-pt").nth(0).inner_text(), "panduan AVR: injeksi 111.65 V")
        pg.locator(".prot .inj-pt").nth(0).scroll_into_view_if_needed(); shot("p05_avr")
        pg.click("button:has-text('Uji proteksi relay')"); pg.wait_for_selector(".sheet-modal .prot-funcs")
        pg.click(".sheet-modal button.primary"); time.sleep(0.8)
        check(pg.locator(".prot").count() == 2, "blok kedua dibuat")
        pg.locator(".prot").nth(1).locator("button:has-text('Hapus blok')").click(); time.sleep(0.8)
        check(pg.locator(".prot").count() == 1, "blok kosong dihapus")
        for _ in range(30):
            pend = [r for r in M.TABLES["panel_checks"].values() if r.get("section") == SEC and r.get("value") == "0.6"]
            if pend: break
            time.sleep(0.5)
        b.close()
    c2 = SupabaseClient(URL, "k"); c2.sign_in("seed@x.id", "Kuat-Sekali-123a"); SyncEngine(lap, c2).run()
    g = R.group([r for r in lap.panel_checks(P1) if r["section"] == SEC])
    f51 = g["funcs"][0]
    pts = dict(f51["points"])
    check(R.parse_params(f51["fset"]["criteria"]) == {"kurva": "IEC SI", "Is": "1", "TMS": "0.1"}, "laptop: setting 51 dari HP")
    check(pts["2×Is"]["value"] == "1.04" and pts["2×Is"]["result"] == "OK" and pts["5×Is"]["result"] == "NG", "laptop: hasil 51 dari HP")
    check(pts["5×Is"]["criteria"] == "0.428 ± 0.040", f"laptop: kriteria expected ikut berubah: {pts['5×Is']['criteria']}")
    check(dict(g["funcs"][2]["points"])[R.FUNCS["TRIP"][0]]["result"] == "OK", "laptop: uji fungsional TRIP OK")
    avr = [r for r in lap.panel_checks(P2) if R.is_protection_section(r["section"])]
    check(len(avr) == 1 + 4 + 5, f"laptop: blok AVR (setup + 90 + 5 cek), blok terhapus tidak ikut: {len(avr)}")
    check(not OVER, f"tidak ada elemen keluar layar: {OVER}")
    check(not ERR, f"tanpa error JS: {ERR}")
    srv.shutdown(); web.shutdown()
print("shots:", OUT)
print("ALL OK" if ok else "ADA YANG GAGAL")
sys.exit(0 if ok else 1)
