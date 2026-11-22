"""Screenshot + audit kontras semua halaman, dialog & popup desktop.
Mensimulasikan Windows mode gelap (palet gelap dipasang dulu) lalu setup_app() harus mengembalikannya ke terang.
Pemakaian: python shots_all.py [outdir] [lang]
"""
import sys, os, faulthandler, collections
faulthandler.enable()
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # paneltracker/
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dshots"
LANG = sys.argv[2] if len(sys.argv) > 2 else "id"
os.makedirs(OUT, exist_ok=True)
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox,
                               QMessageBox, QDialog, QMenu, QAbstractItemView, QPlainTextEdit, QTextEdit)
from PySide6.QtCore import QSettings, Qt, QTimer, QPoint
from PySide6.QtGui import QPalette, QColor, QImage

app = QApplication([])
# --- simulasi Windows dark mode: palet gelap + skema gelap sebelum tema dipasang
try:
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
except Exception:
    pass
dark = QPalette()
for r, c in {QPalette.Window: "#202020", QPalette.WindowText: "#FFFFFF", QPalette.Base: "#2B2B2B",
             QPalette.Text: "#FFFFFF", QPalette.Button: "#333333", QPalette.ButtonText: "#FFFFFF",
             QPalette.Highlight: "#0078D4", QPalette.HighlightedText: "#FFFFFF",
             QPalette.PlaceholderText: "#AAAAAA", QPalette.ToolTipBase: "#2B2B2B", QPalette.ToolTipText: "#FFFFFF"}.items():
    dark.setColor(r, QColor(c))
app.setPalette(dark)
from app import i18n
i18n.set_lang(LANG)
from app.ui.theme import setup_app
setup_app(app)
from app.ui.main_window import MainWindow
from app.demo import create_demo

PROBLEMS = []


def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def img_contrast(img: QImage):
    """(latar dominan, warna paling kontras, rasio)"""
    img = img.convertToFormat(QImage.Format_RGB32)
    w, h = img.width(), img.height()
    if w < 4 or h < 4:
        return None
    cnt = collections.Counter()
    step = max(1, (w * h) // 6000)
    px = []
    for i in range(0, w * h, step):
        x, y = i % w, i // w
        c = QColor(img.pixel(x, y))
        t = (c.red(), c.green(), c.blue())
        cnt[t] += 1
        px.append(t)
    bg = cnt.most_common(1)[0][0]
    best, br = bg, 1.0
    for t in set(px):
        r = ratio(bg, t)
        if r > br:
            best, br = t, r
    return bg, best, br


def audit(root: QWidget, where: str):
    """Cek tiap widget yang menampilkan teks: teks paling kontras vs latar dominan."""
    kinds = (QLabel, QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox, QPlainTextEdit, QTextEdit)
    top = root.window()
    full = top.grab().toImage()
    dpr = full.devicePixelRatio() or 1
    for wdg in [root] + root.findChildren(QWidget):
        if not isinstance(wdg, kinds) or not wdg.isVisible() or wdg.width() < 8 or wdg.height() < 8:
            continue
        txt = ""
        if isinstance(wdg, (QLabel, QAbstractButton)):
            txt = wdg.text()
            if isinstance(wdg, QLabel) and wdg.pixmap() is not None and not wdg.pixmap().isNull():
                continue
        elif isinstance(wdg, QLineEdit):
            txt = wdg.text() or wdg.placeholderText()
        elif isinstance(wdg, QComboBox):
            txt = wdg.currentText()
        elif isinstance(wdg, QAbstractSpinBox):
            txt = wdg.text()
        elif isinstance(wdg, (QPlainTextEdit, QTextEdit)):
            txt = wdg.toPlainText() or wdg.placeholderText()
        if not txt.strip() or txt.strip().startswith("<") and "img" in txt:
            continue
        if wdg.window() is not top:
            continue
        vr = wdg.visibleRegion().boundingRect()
        if vr.isEmpty() or vr.width() * vr.height() < 0.9 * wdg.width() * wdg.height():
            continue
        pos = wdg.mapTo(top, vr.topLeft())
        r = img_contrast(full.copy(int(pos.x() * dpr), int(pos.y() * dpr), int(vr.width() * dpr), int(vr.height() * dpr)))
        if not r:
            continue
        bg, fg, cr = r
        lim = 3.0 if not wdg.isEnabled() else 4.0
        if not wdg.isEnabled() and cr >= 2.2:
            continue
        if cr < lim:
            PROBLEMS.append(f"[{where}] {type(wdg).__name__} '{txt[:40]}' bg={'#%02X%02X%02X' % bg} fg={'#%02X%02X%02X' % fg} ratio={cr:.2f}")


def pump(n=4):
    for _ in range(n):
        app.processEvents()


def snap(w, name, where=None):
    pump()
    w.grab().save(f"{OUT}/{name}.png")
    audit(w, where or name)


def snap_popup(name):
    pump(6)
    p = QApplication.activePopupWidget()
    if p is None:
        PROBLEMS.append(f"[{name}] popup tidak muncul")
        return
    p.grab().save(f"{OUT}/{name}.png")
    audit(p, name)
    # tampilan item (daftar combo, grid kalender) dirender sendiri: audit viewport-nya juga
    for v in p.findChildren(QAbstractItemView):
        if v.isVisible():
            r = img_contrast(v.viewport().grab().toImage())
            if r and r[2] < 4.5:
                PROBLEMS.append(f"[{name}] view {type(v).__name__} ratio={r[2]:.2f}")
    p.close()
    pump()


for f in ("demo.db", "demo.db-wal", "demo.db-shm"):
    fp = os.path.join(OUT, f)
    if os.path.exists(fp):
        os.remove(fp)
st = QSettings(os.path.join(OUT, "s.ini"), QSettings.IniFormat)
w = MainWindow(os.path.join(OUT, "demo.db"), remember=False, settings=st)
w.resize(1440, 880)
w.show()
pid = create_demo(w.db)
w.load_projects(pid)
assert app.palette().color(QPalette.Window).name().upper() == "#DFE2DF", "palet terang tidak terpasang"

for i, n in enumerate(["home", "check", "punch", "reports", "templates"]):
    w.nav_to(i)
    snap(w, f"page_{n}")
ov = [o for o in w.db.panel_overview(pid) if o["stats"]["NG"]]
w.go_panel(ov[0]["panel"]["id"])
snap(w, "page_checkpanel")
# tampilan tabel punch (jika ada toggle)
w.nav_to(2)
pp = w.stack.currentWidget()
for b in pp.findChildren(QAbstractButton):
    if b.isCheckable() and b.objectName() in ("segR",) and b.isVisible():
        b.click()
        snap(w, "page_punch_table")
        break

# ---------------------------------------------------------------- dialog-dialog
from app.ui import dialogs, report_dialogs, cloud_ui
from app.ui.page_checklist import CheckItemDialog


def run_dialog(make, name, extra=None):
    d = make()
    d.show()
    pump()
    snap(d, f"dlg_{name}")
    if extra:
        extra(d)
    d.close()
    d.deleteLater()
    pump()


issues = w.db.list_issues(pid) if hasattr(w.db, "list_issues") else []


def open_date_popup(d, name):
    from app.ui.widgets import OptionalDateEdit
    des = [x for x in d.findChildren(OptionalDateEdit) if x.isVisible()]
    if not des:
        return
        return
    de = des[0]
    de.chk.setChecked(True)
    pump()
    snap(d, f"dlg_{name}_dateon")
    cal = de.de.calendarWidget()
    de.de.setFocus()
    # buka popup kalender seperti klik panah
    from PySide6.QtTest import QTest
    QTest.mouseClick(de.de, Qt.LeftButton, Qt.NoModifier, QPoint(de.de.width() - 8, de.de.height() // 2))
    snap_popup(f"popup_{name}_calendar")
    # menu bulan di kalender
    _ = cal


def open_combo_popup(d, name):
    cbs = [c for c in d.findChildren(QComboBox) if c.isVisible() and c.count() > 1]
    if cbs:
        cbs[0].showPopup()
        snap_popup(f"popup_{name}_combo")


def issue_extra(d):
    open_date_popup(d, "issue")
    open_combo_popup(d, "issue")


cur = w.db.conn.execute("SELECT id FROM issue WHERE project_id=? LIMIT 1", (pid,)).fetchone()
iss = cur[0] if cur else None
proj = w.db.project(pid)
from app.cloud import SupabaseClient
for nm, mk, ex in [
    ("issue_edit", lambda: dialogs.IssueDialog(w, w.db, pid, issue_id=iss), issue_extra),
    ("issue_new", lambda: dialogs.IssueDialog(w, w.db, pid), lambda d: open_combo_popup(d, "issue_new")),
    ("project", lambda: dialogs.ProjectDialog(w, proj), None),
    ("project_new", lambda: dialogs.ProjectDialog(w), None),
    ("sites", lambda: dialogs.SitesDialog(w, w.db, pid), None),
    ("panel", lambda: dialogs.PanelDialog(w, w.db, pid), lambda d: open_combo_popup(d, "panel")),
    ("settings", lambda: dialogs.SettingsDialog(w, w.db), lambda d: open_combo_popup(d, "settings")),
    ("checkitem", lambda: CheckItemDialog(w, ["A. Visual", "B. Fungsi"]), lambda d: open_combo_popup(d, "checkitem")),
    ("punchreport", lambda: report_dialogs.PunchReportDialog(w), lambda d: open_date_popup(d, "punchreport")),
    ("cloud", lambda: cloud_ui.CloudDialog(w, w.sync), None),
    ("chpwd", lambda: cloud_ui.ChangePasswordDialog(w, SupabaseClient("https://x.supabase.co", "sb_publishable_x"), "fajar@paneltracker.local", forced=True), None),
]:
    try:
        run_dialog(mk, nm, ex)
    except Exception as e:
        import traceback; traceback.print_exc()
        PROBLEMS.append(f"dialog {nm} ERR {type(e).__name__}: {e}")

# message box
mb = QMessageBox(QMessageBox.Warning, "Panel Tracker", "Hapus panel ini? Tindakan tidak bisa dibatalkan.",
                 QMessageBox.Yes | QMessageBox.No, w)
mb.show()
snap(mb, "dlg_msgbox")
mb.close()
# menu
m = QMenu(w)
m.addSection("Proyek")
m.addAction("Proyek baru…")
m.addAction("Buka…")
a = m.addAction("Nonaktif")
a.setEnabled(False)
m.popup(w.mapToGlobal(QPoint(300, 200)))
snap_popup("popup_menu")
# viewer mode
from app.ui import widgets as W
w.db.read_only = True
W.RO = True
w.apply_role()
w.nav_to(1)
w.go_panel(ov[0]["panel"]["id"])
snap(w, "viewer_checkpanel")
w.nav_to(0)
snap(w, "viewer_home")

print("\n".join(PROBLEMS) if PROBLEMS else "NO CONTRAST PROBLEMS")
print("shots ->", OUT)
os._exit(0)
