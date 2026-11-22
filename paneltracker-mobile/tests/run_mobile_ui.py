"""Uji UI aplikasi HP di Chrome (viewport Android) terhadap server tiruan berisi data demo dari desktop."""
import os, sys, shutil, threading, functools, time, json
_HERE = os.path.dirname(os.path.abspath(__file__))
_MOBILE = os.path.dirname(_HERE)  # paneltracker-mobile/
_ROOT = os.path.join(os.path.dirname(_MOBILE), "paneltracker")
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QGuiApplication
_a = QGuiApplication([])
import mock_supabase as M
M.USERS.update({"fajar@paneltracker.local": "P@ssw0rd", "viewer@paneltracker.local": "Lihat-Saja-77x"})
M.MEMBERS.update({"fajar@paneltracker.local": "engineer", "viewer@paneltracker.local": "viewer"})
from app.db import Database
from app.cloud import SupabaseClient, SyncEngine
from app.demo import create_demo
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
OUT = "/tmp/mshots"; shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
srv, URL = M.start()
M.USERS["seed@x.id"] = "Kuat-Sekali-123a"; M.MEMBERS["seed@x.id"] = "engineer"
lap = Database("/tmp/mui_laptop.db") if not os.path.exists("/tmp/mui_laptop.db") else None
if lap is None:
    os.remove("/tmp/mui_laptop.db"); lap = Database("/tmp/mui_laptop.db")
pid = create_demo(lap)
lap.set_setting("categories", json.dumps(["Wiring", "Proteksi Khusus", "Dokumen"]))   # pengaturan tim dari laptop
lap.set_setting("due_days_Major", "5")
c = SupabaseClient(URL, "k"); c.sign_in("seed@x.id", "Kuat-Sekali-123a"); print("seed:", SyncEngine(lap, c).run())
class Q(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
web = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory="/tmp/mdist"))
threading.Thread(target=web.serve_forever, daemon=True).start()
APP = f"http://127.0.0.1:{web.server_address[1]}/index.html?server={URL}"

from playwright.sync_api import sync_playwright
ERR = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    ctx = b.new_context(viewport={"width": 412, "height": 892}, color_scheme="dark", device_scale_factor=2, is_mobile=True, has_touch=True,
                        permissions=["camera"])
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: ERR.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and ERR.append(m.text))
    pg.on("dialog", lambda d: d.accept())
    AUDIT_JS = r"""() => {
      const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
        const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
      const L = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const mix = (fg, bg) => [0,1,2].map(i => fg[i] * fg[3] + bg[i] * (1 - fg[3]));
      const bgOf = el => { const stack = []; let e = el, img = false;
        while (e && e.nodeType === 1) { const cs = getComputedStyle(e);
          if (cs.backgroundImage && cs.backgroundImage !== 'none' && !cs.backgroundImage.startsWith('url')) img = true;
          const c = parse(cs.backgroundColor); if (c && c[3] > 0) { stack.push(c); if (c[3] >= 1) break; } e = e.parentElement; }
        let base = [223, 226, 223]; for (let i = stack.length - 1; i >= 0; i--) base = mix(stack[i], base); return [base, img]; };
      const out = [];
      for (const el of document.querySelectorAll('body *')) {
        if (!['INPUT','TEXTAREA','SELECT'].includes(el.tagName) &&
            ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
        const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight) continue;
        const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || +cs.opacity === 0) continue;
        let op = 1; for (let e = el; e; e = e.parentElement) op *= +getComputedStyle(e).opacity;
        const [bg, img] = bgOf(el); const fg0 = parse(cs.color); if (!fg0) continue;
        const fg = mix([fg0[0], fg0[1], fg0[2], fg0[3] * op], bg);
        const a = L(fg), b = L(bg); const cr = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        const px = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 600;
        const lim = (px >= 24 || (px >= 18.6 && bold)) ? 3 : 4.5;
        const dis = el.disabled || el.closest('[disabled]');
        if (cr < (dis ? 2.5 : lim)) out.push(`${el.tagName.toLowerCase()}.${el.className||''} "${(el.value||el.placeholder||el.textContent).trim().slice(0,30)}" ${cr.toFixed(2)}${img ? ' (gradient bg)' : ''}`);
      }
      return out; }"""
    CONTRAST = {}
    def shot(n):
        time.sleep(0.4); pg.screenshot(path=f"{OUT}/{n}.png")
        bad = pg.evaluate(AUDIT_JS)
        if bad: CONTRAST[n] = bad
    pg.goto(APP); pg.wait_for_selector("text=Masuk ke tim")
    shot("01_login")
    pg.fill("#u", "Fajar"); pg.fill("#p", "salah"); pg.click("button.btn.primary")
    pg.wait_for_selector(".msg.err"); assert "salah" in pg.inner_text(".msg.err"), pg.inner_text(".msg.err")
    pg.fill("#p", "P@ssw0rd"); pg.click("button.btn.primary")
    pg.wait_for_selector("text=Ganti password"); shot("02_forced_password")
    pg.fill("#n1", "Gardu-Induk-2026x"); pg.fill("#n2", "Gardu-Induk-2026x"); time.sleep(0.2); shot("02b_password_ok")
    pg.click("button:has-text('Simpan password')")
    pg.wait_for_selector(".gauges", timeout=20000); time.sleep(1.5)
    assert M.USERS["fajar@paneltracker.local"] == "Gardu-Induk-2026x"
    shot("03_home")
    pg.screenshot(path=f"{OUT}/03_home_full.png", full_page=False)
    pg.click(".icon-btn[aria-label*='project']"); time.sleep(0.4); shot("03b_picker")
    pg.click(".sheet-modal .line:has-text('GI Bravo')"); time.sleep(0.4)
    pg.click(".icon-btn[aria-label*='project']"); pg.click(".sheet-modal .line:has-text('Semua site')"); time.sleep(0.3)
    pg.click(".nav button:has-text('Panel')"); pg.wait_for_selector(".cubicle"); shot("04_panels")
    pg.click(".chip:has-text('Ada temuan')"); time.sleep(0.3); shot("04b_panels_filter")
    pg.click(".chip:has-text('Semua')"); pg.fill("input[type=search]", "B-CRP-02"); time.sleep(0.3)
    pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".step"); shot("05_panel_detail")
    pg.evaluate("document.querySelector('.content').scrollTop = 520"); time.sleep(0.3); shot("05b_panel_steps")
    pend = pg.locator(".step:not(.OK):not(.NG):not(.NA)")
    n0 = pend.count()
    if n0:
        pend.nth(0).locator(".push button.OK").click(); time.sleep(0.3)
        assert pg.locator(".step:not(.OK):not(.NG):not(.NA)").count() == n0 - 1
    pend = pg.locator(".step:not(.OK):not(.NG):not(.NA)")
    target = pend.nth(0) if pend.count() else pg.locator(".step.OK").nth(0)
    target.locator(".push button.NG").click()
    pg.wait_for_selector(".flow"); shot("06_punch_from_ng")
    assert pg.locator("option:has-text('Proteksi Khusus')").count() > 0, "kategori tim dari laptop harus muncul di HP"
    assert "tidak sesuai" in pg.input_value("textarea >> nth=0")
    if os.path.exists("/tmp/full/foto.jpg"):
        pg.set_input_files("input[type=file]:not([capture])", "/tmp/full/foto.jpg")
    time.sleep(0.8)
    pg.evaluate("document.querySelector('.content').scrollTop = 600"); time.sleep(0.3); shot("07_punch_photo")
    pg.click(".save-btn"); time.sleep(2)
    pg.click(".nav button:has-text('Punch')"); pg.wait_for_selector(".ptag"); shot("08_punches")
    pg.click(".ptag >> nth=0"); pg.wait_for_selector(".flow"); time.sleep(1.5); shot("09_punch_detail")
    pg.click(".flow button:has-text('Dikerjakan')"); pg.click(".save-btn"); time.sleep(2)
    pg.click(".nav .scan"); time.sleep(1.5); shot("10_scan")
    pg.fill(".scan-bottom input", "pt:12:a-cp-03"); pg.click("button:has-text('Buka panel')")
    pg.wait_for_selector(".step"); assert "A-CP-03" in pg.inner_text(".topbar h1")
    pg.click(".nav button:has-text('Akun')"); pg.wait_for_selector("text=Keamanan"); shot("11_account")
    pg.click(".line:has-text('English')"); pg.wait_for_selector(".gauges"); time.sleep(1); shot("12_home_en")
    pg.click(".nav button:has-text('Panel')"); time.sleep(0.6); shot("13_panels_en")
    pg.click(".nav button:has-text('Account')"); pg.click(".line:has-text('Bahasa Indonesia')"); pg.wait_for_selector(".gauges")
    time.sleep(2)
    pg.click(".nav button:has-text('Akun')"); pg.click(".line:has-text('Keluar')"); pg.wait_for_selector("text=Masuk ke tim")
    pg.fill("#u", "viewer"); pg.fill("#p", "Lihat-Saja-77x"); pg.click("button.btn.primary")
    pg.wait_for_selector(".gauges", timeout=20000); time.sleep(1.5); shot("14_viewer_home")
    pg.click(".nav button:has-text('Panel')"); pg.click(".cubicle >> nth=0"); pg.wait_for_selector(".step"); shot("15_viewer_panel")
    assert pg.locator(".push button:not([disabled])").count() == 0, "viewer tidak boleh klik OK/NG"
    pg.click(".nav button:has-text('Punch')"); time.sleep(0.5)
    assert pg.locator(".fab").count() == 0, "viewer tidak boleh punya tombol punch baru"
    b.close()
# verifikasi di desktop
c2 = SupabaseClient(URL, "k"); c2.sign_in("seed@x.id", "Kuat-Sekali-123a"); print("desktop pull:", SyncEngine(lap, c2).run())
new = [i for i in lap.issues(pid) if "tidak sesuai" in (i["title"] or "")]
print("punch dari HP di laptop:", [(i["code"], i["status"], len(lap.attachments(i["id"]))) for i in new])
ERR = [e for e in ERR if "400 (Bad Request)" not in e]  # 400 = tes password salah (disengaja)
print("JS errors:", ERR)
srv.shutdown(); web.shutdown()
print("MOBILE UI OK" if new and not ERR else "MOBILE UI PROBLEM")
if CONTRAST:
    print("CONTRAST ISSUES:")
    for k, v in CONTRAST.items():
        for x in sorted(set(v)): print(f"  [{k}] {x}")
else:
    print("CONTRAST OK (semua layar)")
