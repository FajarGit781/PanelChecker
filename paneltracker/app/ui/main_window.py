"""Jendela utama v2: sidebar + halaman."""
from __future__ import annotations

from ..i18n import tr

import datetime as dt
import os
import re

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QPalette, QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..db import Database
from . import theme as T
from .dialogs import IssueDialog, ProjectDialog, SettingsDialog, SitesDialog
from .page_checklist import ChecklistPage
from .page_home import HomePage
from .page_punch import PunchPage
from .page_reports import ReportsPage, TemplatesPage
from .widgets import ask, info, warn

APP = "Panel Tracker"
_WINDOWS = []  # menahan referensi jendela baru saat ganti bahasa


def _safe(s):
    return re.sub(r"[^\w\-]+", "_", s or "").strip("_")


class MainWindow(QMainWindow):
    def __init__(self, db_path=None, remember=True, settings: QSettings | None = None, default_db=None):
        super().__init__()
        self.remember = remember
        self.settings = settings or QSettings("PanelTracker", "PanelTracker")
        self._default_db = default_db
        self.db: Database | None = None
        self.project_id = None
        self.site_id = None
        self._dirty = set()
        app = QApplication.instance()
        if app and not getattr(app, "_pt_fitter", None):
            from .widgets import DialogFitter
            app._pt_fitter = DialogFitter(app)
            app.installEventFilter(app._pt_fitter)
        from .cloud_ui import SyncController
        self.sync = SyncController(self)
        self.sync.finished.connect(self._sync_done)
        self.resize(1440, 880)
        self.setMinimumSize(1100, 680)

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        rl.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.p_home = HomePage(self)
        self.p_check = ChecklistPage(self)
        self.p_punch = PunchPage(self)
        self.p_reports = ReportsPage(self)
        self.p_tpl = TemplatesPage(self)
        self.pages = [self.p_home, self.p_check, self.p_punch, self.p_reports, self.p_tpl]
        for p in self.pages:
            self.stack.addWidget(p)
        self.stack.currentChanged.connect(lambda *_: self._refresh_current())
        self.statusBar().showMessage(tr('Siap'))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.scan.setFocus(), self.scan.selectAll()))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.p_punch.new())

        last = self.settings.value("last_db")
        path = db_path or (last if last and os.path.exists(last) else self.default_db_path())
        self.open_db(path)
        self.apply_role(refresh=False)
        self.nav_to(0)
        self.sync.refresh_state()
        if self.remember and self.sync.cfg.logged_in:
            QTimer.singleShot(2500, lambda: self.sync.sync(silent=True))

    # ------------------------------------------------------------ sidebar
    def _build_sidebar(self):
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(250)
        v = QVBoxLayout(sb)
        v.setContentsMargins(16, 18, 16, 14)
        v.setSpacing(6)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignCenter)
        logo.setPixmap(T.icon("shield", T.ON_SIGNAL, 22, 2).pixmap(22, 22))
        logo.setStyleSheet(f"background:{T.SIGNAL}; border-radius:5px;")
        brand.addWidget(logo)
        bv = QVBoxLayout()
        bv.setSpacing(0)
        t1 = QLabel("Panel Tracker")
        t1.setObjectName("brand")
        t2 = QLabel(tr('CHECK  ·  PUNCH LIST'))
        t2.setObjectName("brandSub")
        bv.addWidget(t1)
        bv.addWidget(t2)
        brand.addLayout(bv)
        brand.addStretch()
        v.addLayout(brand)
        self.ro_badge = QLabel(tr('MODE VIEWER · hanya lihat'))
        self.ro_badge.setAlignment(Qt.AlignCenter)
        self.ro_badge.setStyleSheet(f"background:{T.SIGNAL}; color:{T.ON_SIGNAL}; border-radius:3px; padding:4px;"
                                    " font-size:8pt; font-weight:700;")
        self.ro_badge.hide()
        v.addSpacing(6)
        v.addWidget(self.ro_badge)
        v.addSpacing(8)

        cap = QLabel(tr('PROJECT'))
        cap.setObjectName("sideCaption")
        v.addWidget(cap)
        ph = QHBoxLayout()
        ph.setSpacing(6)
        self.cb_project = QComboBox()
        self.cb_project.currentIndexChanged.connect(self._project_changed)
        ph.addWidget(self.cb_project, 1)
        self.b_pmenu = QToolButton()
        self.b_pmenu.setIcon(T.icon("more", "#B3B9B5", 18))
        self.b_pmenu.setToolTip(tr('Kelola project, site & database'))
        self.b_pmenu.clicked.connect(self._project_menu)
        ph.addWidget(self.b_pmenu)
        v.addLayout(ph)
        self.cb_site = QComboBox()
        self.cb_site.currentIndexChanged.connect(self._site_changed)
        v.addWidget(self.cb_site)
        v.addSpacing(14)

        cap2 = QLabel("MENU")
        cap2.setObjectName("sideCaption")
        v.addWidget(cap2)
        self.nav = QButtonGroup(self)
        self.nav_btns = []
        for i, (text, ic) in enumerate(((tr('Beranda'), "home"), (tr('Checking Panel'), "check"), (tr('Punch List'), "punch"),
                                        (tr('Laporan && Data'), "report"), (tr('Template Checklist'), "template"))):
            b = QPushButton("  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(T.nav_icon(ic))
            b.setIconSize(QSize(19, 19))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=i: self.nav_to(k))
            self.nav.addButton(b, i)
            v.addWidget(b)
            self.nav_btns.append(b)
        self.punch_badge = QLabel(self.nav_btns[2])
        self.punch_badge.setStyleSheet(f"background:{T.NG}; color:white; border-radius:3px; padding:1px 6px;"
                                       " font-size:8pt; font-weight:700;")
        self.punch_badge.move(180, 9)
        self.punch_badge.hide()
        v.addStretch()

        cap3 = QLabel(tr('SCAN QR / CARI PANEL'))
        cap3.setObjectName("sideCaption")
        v.addWidget(cap3)
        self.scan = QLineEdit()
        self.scan.setPlaceholderText(tr('scan label / ketik tag ↵'))
        self.scan.addAction(T.icon("qr", T.SIDE_MUTED, 16), QLineEdit.LeadingPosition)
        _pp = self.scan.palette()   # placeholder terang di atas isian gelap
        _pp.setColor(QPalette.PlaceholderText, QColor(T.SIDE_MUTED))
        self.scan.setPalette(_pp)
        self.scan.returnPressed.connect(self._scan)
        v.addWidget(self.scan)
        v.addSpacing(10)
        from .cloud_ui import SyncWidget
        self.sync_widget = SyncWidget(self.sync)
        v.addWidget(self.sync_widget)
        v.addSpacing(8)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#3A4247;")
        v.addWidget(line)
        fh = QHBoxLayout()
        self.user_av = QLabel()
        self.user_av.setFixedSize(32, 32)
        self.user_av.setAlignment(Qt.AlignCenter)
        fh.addWidget(self.user_av)
        uv = QVBoxLayout()
        uv.setSpacing(0)
        self.user_lbl = QLabel()
        self.user_lbl.setStyleSheet("color:white; font-weight:600;")
        self.db_lbl = QLabel()
        self.db_lbl.setStyleSheet(f"color:{T.SIDE_MUTED}; font-size:8pt;")
        uv.addWidget(self.user_lbl)
        uv.addWidget(self.db_lbl)
        fh.addLayout(uv, 1)
        from ..i18n import lang
        blang = QToolButton()
        blang.setText("EN" if lang() == "id" else "ID")
        blang.setToolTip("Switch to English" if lang() == "id" else "Ganti ke Bahasa Indonesia")
        blang.setStyleSheet("QToolButton { font-weight:700; font-size:8pt; padding:5px 6px; }")
        blang.clicked.connect(lambda: self.switch_lang("en" if lang() == "id" else "id"))
        fh.addWidget(blang)
        bset = QToolButton()
        bset.setIcon(T.icon("settings", "#B3B9B5", 18))
        bset.setToolTip(tr('Pengaturan'))
        bset.clicked.connect(self.edit_settings)
        fh.addWidget(bset)
        v.addLayout(fh)
        return sb

    def _update_footer(self):
        from .widgets import avatar_color, initials
        u = self.db.user if self.db else "-"
        self.user_lbl.setText(u)
        self.user_av.setText(initials(u))
        self.user_av.setStyleSheet(f"background:{avatar_color(u)}; color:white; border-radius:16px; font-weight:600;")
        self.db_lbl.setText(os.path.basename(self.db.path) if self.db else "")
        self.db_lbl.setToolTip(self.db.path if self.db else "")

    def nav_to(self, i):
        self.nav_btns[i].setChecked(True)
        self.stack.setCurrentIndex(i)
        self._refresh_current()

    # ------------------------------------------------------------ project menu
    def _project_menu(self):
        m = QMenu(self)
        m.addAction(T.icon("plus"), tr('Project baru…'), self.new_project)
        m.addAction(T.icon("edit"), tr('Edit project…'), self.edit_project)
        m.addAction(T.icon("panel"), tr('Kelola site / GI…'), self.manage_sites)
        m.addSeparator()
        m.addAction(T.icon("cloud"), tr('Akun cloud & sinkron…').replace('&', '&&'), self.cloud_dialog)
        m.addSeparator()
        m.addAction(T.icon("database"), tr('Buka database…'), self.choose_db)
        m.addAction(T.icon("plus"), tr('Database baru…'), self.new_db)
        m.addAction(T.icon("download"), tr('Backup database…'), self.backup_db)
        m.addAction(T.icon("folder"), tr('Buka folder data'), lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.dirname(os.path.abspath(self.db.path)))))
        m.addSeparator()
        m.addAction(T.icon("tool"), tr('Buat project contoh (demo)'), self.make_demo)
        m.addAction(T.icon("trash", T.NG), tr('Hapus project…'), self.delete_project)
        m.addSeparator()
        m.addAction(tr('Tentang aplikasi'), self.about)
        m.exec(self.b_pmenu.mapToGlobal(self.b_pmenu.rect().bottomLeft()))

    # ------------------------------------------------------------ db
    def default_db_path(self):
        if self._default_db:
            return self._default_db
        from PySide6.QtCore import QStandardPaths
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")
        folder = os.path.join(docs, "PanelTracker")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "paneltracker.db")

    def open_db(self, path):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            db = Database(path)
        except Exception as e:
            warn(self, tr('Gagal membuka database:\n{0}\n\n{1}', path, e))
            if self.db is None and os.path.abspath(path) != os.path.abspath(self.default_db_path()):
                return self.open_db(self.default_db_path())
            if self.db is None:
                raise
            return
        if self.db:
            self.db.close()
        self.db = db
        if self.remember:
            self.settings.setValue("last_db", os.path.abspath(path))
        self.setWindowTitle(f"{APP} v{__version__}  —  {os.path.abspath(path)}")
        self.apply_role(refresh=False)
        self._update_footer()
        self.load_projects(self.settings.value("last_project", type=int))

    def new_db(self):
        fp, _ = QFileDialog.getSaveFileName(self, tr('Database baru'), os.path.dirname(self.db.path), "Database (*.db)")
        if fp:
            if not fp.lower().endswith(".db"):
                fp += ".db"
            self.open_db(fp)

    def choose_db(self):
        fp, _ = QFileDialog.getOpenFileName(self, tr('Buka database'), os.path.dirname(self.db.path),
                                            tr('Database (*.db);;Semua file (*)'))
        if fp:
            self.open_db(fp)

    def backup_db(self):
        base = os.path.splitext(os.path.basename(self.db.path))[0]
        fp, _ = QFileDialog.getSaveFileName(
            self, tr('Backup database'),
            os.path.join(os.path.dirname(self.db.path), f"{base}_backup_{dt.datetime.now():%Y%m%d_%H%M}.db"),
            "Database (*.db)")
        if fp:
            self.db.backup(fp)
            info(self, tr('Backup tersimpan:\n{0}', fp))

    # ------------------------------------------------------------ project / site
    def load_projects(self, select=None):
        self.cb_project.blockSignals(True)
        self.cb_project.clear()
        for p in self.db.projects():
            self.cb_project.addItem(f"{p['code']} — {p['name']}", p["id"])
        if self.cb_project.count() == 0:
            self.cb_project.addItem(tr('(belum ada project)'), None)
        idx = self.cb_project.findData(select) if select else 0
        self.cb_project.setCurrentIndex(max(0, idx))
        self.cb_project.blockSignals(False)
        self._project_changed()

    def _project_changed(self, *_):
        self.project_id = self.cb_project.currentData()
        if self.project_id and self.remember:
            self.settings.setValue("last_project", self.project_id)
        self.site_id = None
        self.load_sites()

    def load_sites(self, select=None):
        self.cb_site.blockSignals(True)
        self.cb_site.clear()
        self.cb_site.addItem(tr('Semua site / GI'), None)
        if self.project_id:
            for s in self.db.sites(self.project_id):
                self.cb_site.addItem(s["name"], s["id"])
        i = self.cb_site.findData(select) if select else 0
        self.cb_site.setCurrentIndex(max(0, i))
        self.cb_site.blockSignals(False)
        self.site_id = self.cb_site.currentData()
        self.refresh_all()

    def _site_changed(self, *_):
        self.site_id = self.cb_site.currentData()
        self.refresh_all()

    def mark_dirty(self, except_page=None):
        self._dirty = {p for p in self.pages if p is not except_page}
        self._update_badge()
        self.sync.refresh_state()

    def cloud_dialog(self):
        from .cloud_ui import CloudDialog
        CloudDialog(self, self.sync).exec()

    def _sync_done(self, res):
        self.statusBar().showMessage(
            tr('Sinkron selesai: {0} diterima, {1} dikirim, {2} foto diupload, {3} foto diunduh ({4} dtk)', res['pulled'], res['pushed'], res['photos_up'], res['photos_down'], res['seconds']), 8000)
        if res["pulled"] or res["photos_down"]:
            self.load_projects(self.project_id)

    def refresh_all(self, except_page=None):
        self.mark_dirty(except_page)
        self._refresh_current()

    def _refresh_current(self):
        w = self.stack.currentWidget()
        if w in self._dirty:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                w.refresh()
            finally:
                QApplication.restoreOverrideCursor()
            self._dirty.discard(w)

    def _update_badge(self):
        if not (self.db and self.project_id):
            self.punch_badge.hide()
            return
        n = sum(1 for i in self.db.issues(self.project_id, site_id=self.site_id) if i["status"] != "Closed")
        self.punch_badge.setText(str(n))
        self.punch_badge.adjustSize()
        self.punch_badge.move(self.nav_btns[2].width() - self.punch_badge.width() - 10, 10)
        self.punch_badge.setVisible(n > 0)
        o = self.db.overall(self.project_id, self.site_id)
        self.statusBar().showMessage(
            tr('{0} panel  ·  {1:.0f}% item diuji  ·  {2} punch open  ·  {3} lewat target', o['panels'], o['items_pct'], o['issues_open'], o['issues_overdue']))

    def new_project(self):
        d = ProjectDialog(self)
        if d.exec():
            pid = self.db.add_project(**d.values())
            self.load_projects(pid)
            if ask(self, tr('Project dibuat. Tambahkan site / GI sekarang?')):
                self.manage_sites()

    def edit_project(self):
        if self._need_project():
            d = ProjectDialog(self, self.db.project(self.project_id))
            if d.exec():
                self.db.update_project(self.project_id, **d.values())
                self.load_projects(self.project_id)

    def delete_project(self):
        if not self._need_project():
            return
        p = self.db.project(self.project_id)
        if ask(self, tr("Hapus project '{0} — {1}' beserta semua panel, hasil cek & punch?", p['code'], p['name'])):
            self.db.delete_project(self.project_id)
            self.load_projects()

    def manage_sites(self):
        if self._need_project():
            SitesDialog(self, self.db, self.project_id).exec()
            self.load_sites(self.site_id)

    def _need_project(self):
        if not self.project_id:
            warn(self, tr('Belum ada project. Buat lewat menu ⋯ → Project baru (atau coba project contoh).'))
            return False
        return True

    def edit_settings(self):
        d = SettingsDialog(self, self.db)
        if d.exec():
            if getattr(d, "lang_changed", False):
                self.switch_lang(self.settings.value("ui/lang", "id"))
                return
            self._update_footer()
            self.refresh_all()
            if self.db.shared_settings_dirty():
                self.sync.sync(silent=True)   # pengaturan tim langsung dikirim ke cloud

    def switch_lang(self, code):
        """Ganti bahasa UI: simpan pilihan lalu muat ulang jendela."""
        from .. import i18n
        self.settings.setValue("ui/lang", code)
        self.settings.sync()
        i18n.set_lang(code)
        geo, page = self.saveGeometry(), self.stack.currentIndex()
        w = MainWindow(self.db.path, remember=self.remember, settings=self.settings, default_db=self._default_db)
        w.restoreGeometry(geo)
        w.nav_to(page)
        w.show()
        _WINDOWS.append(w)
        self.close()

    def report_lang(self):
        from ..i18n import lang
        return self.settings.value("report/lang", "") or lang()

    def make_demo(self):
        from ..demo import create_demo
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            pid = create_demo(self.db)
        finally:
            QApplication.restoreOverrideCursor()
        self.load_projects(pid)
        info(self, tr("Project contoh 'DEMO-SAT' dibuat (3 GI, 18 panel, checklist & punch).\nSilakan dicoba, lalu hapus lewat menu ⋯ → Hapus project."))

    def about(self):
        QMessageBox.about(self, tr('Tentang'), tr('<h3>{0} v{1}</h3><p>Checking panel (uji fungsi) &amp; punch list, dengan report PDF/Excel dan label QR.</p><p>Data: <code>{2}</code></p>', APP, __version__, self.db.path))

    # ------------------------------------------------------------ navigation helpers
    def go_panel(self, panel_id):
        if not panel_id:
            return
        p = self.db.panel(panel_id)
        if p and self.site_id and p["site_id"] != self.site_id:
            self.cb_site.setCurrentIndex(0)
        self.nav_to(1)
        self.p_check.select_panel(panel_id)

    def open_issue(self, iid):
        if iid and IssueDialog(self, self.db, self.project_id, iid).exec():
            self.refresh_all()

    def show_punch_for(self, text):
        self.nav_to(2)
        self.p_punch.q.setText(text)

    def _scan(self):
        text = self.scan.text().strip()
        if not text or not self.project_id:
            return
        p = self.db.find_panel(self.project_id, text)
        if p and p["project_id"] != self.project_id:
            self.cb_project.setCurrentIndex(self.cb_project.findData(p["project_id"]))
        if not p:
            self.statusBar().showMessage(tr("Panel '{0}' tidak ditemukan", text), 5000)
            QApplication.beep()
            self.scan.selectAll()
            return
        self.scan.clear()
        self.go_panel(p["id"])

    # ------------------------------------------------------------ excel
    def open_file(self, fp, title):
        if QMessageBox.question(self, title, tr("File tersimpan:\n{0}\n\nBuka sekarang?", fp),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(fp))

    def save_template(self):
        from ..excel_io import write_panel_template
        fp, _ = QFileDialog.getSaveFileName(self, tr('Simpan template'), "Template_Import_Panel.xlsx", "Excel (*.xlsx)")
        if fp:
            write_panel_template(self.db, fp)
            self.open_file(fp, tr('Template tersimpan'))

    def import_excel(self):
        if not self._need_project():
            return
        from ..excel_io import import_panels
        fp, _ = QFileDialog.getOpenFileName(self, tr('Import panel dari Excel'), "", "Excel (*.xlsx *.xlsm)")
        if not fp:
            return
        try:
            r = import_panels(self.db, self.project_id, fp)
        except Exception as e:
            warn(self, tr('Import gagal:\n{0}', e))
            return
        self.load_sites(self.site_id)
        info(self, tr('Import selesai:\n• {0} panel baru (checklist diterapkan: {1})\n• {2} panel di-update\n• {3} baris dilewati', r['added'], r['tpl'], r['updated'], r['skipped']))

    def import_fat(self):
        from PySide6.QtWidgets import QInputDialog
        from ..import_fat import import_fat_punchlist
        fp, _ = QFileDialog.getOpenFileName(self, tr('Import Punch List FAT'), "", "Excel (*.xlsx *.xlsm)")
        if not fp:
            return
        base = os.path.splitext(os.path.basename(fp))[0]
        m = re.search(r"(GI[ _][A-Za-z0-9 _]+?)(?:_\d{6,8}|$)", base, re.I)
        guess = m.group(1).replace("_", " ").strip().upper() if m else ""
        site, ok = QInputDialog.getText(self, tr('Import Punch List FAT'),
                                        tr('Nama site / GI (dipakai untuk project & site):'), text=guess)
        if not ok or not site.strip():
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = import_fat_punchlist(self.db, fp, site_name=site.strip(),
                                     progress=lambda t: (self.statusBar().showMessage(t), QApplication.processEvents()))
        except Exception as e:
            QApplication.restoreOverrideCursor()
            warn(self, tr('Import gagal:\n{0}', e))
            return
        QApplication.restoreOverrideCursor()
        self.load_projects(r["project_id"])
        self.nav_to(2)
        info(self, tr('Import selesai:\n• {0} punch baru\n• {1} foto\n• {2} panel baru\n• {3} punch sudah ada (dilewati)\n\nKategori A/B/C & kategori temuan ditebak otomatis dari deskripsi — silakan cek dan sesuaikan bila perlu.', r['issues'], r['photos'], r['panels'], r['skipped']))

    def export_excel(self):
        if not self._need_project():
            return
        from ..excel_io import export_project
        p = self.db.project(self.project_id)
        fp, _ = QFileDialog.getSaveFileName(self, tr('Export Excel'),
                                            f"{_safe(p['code'])}_Checking_{dt.date.today():%Y%m%d}.xlsx",
                                            "Excel (*.xlsx)")
        if fp:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                export_project(self.db, self.project_id, fp, self.site_id)
            finally:
                QApplication.restoreOverrideCursor()
            self.open_file(fp, tr('Export selesai'))

    # ------------------------------------------------------------ reports
    def _report_path(self, kind):
        p = self.db.project(self.project_id)
        site = self.db.site(self.site_id)["name"] if self.site_id else ""
        name = f"{_safe(p['code'])}_{kind}{'_' + _safe(site) if site else ''}_{dt.date.today():%Y%m%d}.pdf"
        last = self.settings.value("last_report_dir") or os.path.dirname(os.path.abspath(self.db.path))
        fp, _ = QFileDialog.getSaveFileName(self, tr('Simpan report'), os.path.join(last, name), "PDF (*.pdf)")
        if fp and self.remember:
            self.settings.setValue("last_report_dir", os.path.dirname(fp))
        return fp

    def _run_report(self, fn, fp, lang=None):
        from ..i18n import using
        from ..reports import ReportBuilder
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            with using(lang or self.report_lang()):
                fn(ReportBuilder(self.db, self.project_id, self.site_id), fp)
        except PermissionError:
            QApplication.restoreOverrideCursor()
            warn(self, tr('Tidak bisa menulis file (mungkin sedang terbuka di PDF reader):\n{0}', fp))
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            warn(self, tr('Gagal membuat report:\n{0}', e))
            return
        QApplication.restoreOverrideCursor()
        self.open_file(fp, tr('Report selesai'))

    def report_punchlist(self, issue_ids=None, only_open=False, photos=True, preset=None):
        """Buka dialog filter cetak punch list. preset: dict status/severity/panels/search/group/photos."""
        if not self._need_project():
            return
        from .report_dialogs import PunchReportDialog
        pre = dict(preset or {})
        if only_open and "status" not in pre:
            pre["status"] = ["Open", "In Progress", "Ready to Verify"]
        pre.setdefault("photos", photos)
        d = PunchReportDialog(self, pre)
        if not d.exec():
            return
        opt = d.options()
        name = _safe(opt["title"].replace("Punch List", "PunchList"))[:60] or "PunchList"
        rep_lang = opt.pop("lang", None)
        fp = self._report_path(name)
        if fp:
            self._run_report(lambda rb, f: rb.punchlist_report(f, **opt), fp, rep_lang)

    def report_check_sheet(self, panel_ids=None, only_started=False):
        """Dialog cetak check sheet: pilih panel (filter tipe/bay/status), seksi, item, form kosong."""
        if not self._need_project():
            return
        if not self.db.panels(self.project_id, self.site_id):
            warn(self, tr('Tidak ada panel.'))
            return
        from .report_dialogs import CheckSheetDialog
        pre_status = ("Sedang dicek", "Ada temuan", "Lulus", "Diterima") if only_started and panel_ids is None else None
        d = CheckSheetDialog(self, preset_panels=panel_ids, preset_status=pre_status)
        if not d.exec():
            return
        o = d.options()
        ids = o.pop("panel_ids")
        lang = o.pop("lang")
        kind = "CheckSheet" if len(ids) > 1 else "CheckSheet_" + _safe(self.db.panel(ids[0])["tag"])
        if o["blank"]:
            kind += "_Form"
        fp = self._report_path(kind)
        if fp:
            self._run_report(lambda rb, f: rb.check_sheets(f, ids, **o), fp, lang=lang)

    def report_summary(self):
        if self._need_project():
            fp = self._report_path("Ringkasan")
            if fp:
                self._run_report(lambda rb, f: rb.summary_report(f), fp)

    def report_qr(self, panel_ids=None):
        if not self._need_project():
            return
        if panel_ids is None:
            panel_ids = [p["id"] for p in self.db.panels(self.project_id, self.site_id)]
        if not panel_ids:
            warn(self, tr('Tidak ada panel.'))
            return
        from .report_dialogs import QrLabelDialog
        dlg = QrLabelDialog(self, len(panel_ids))
        if not dlg.exec():
            return
        o = dlg.result_options()
        if o["mode"] == "roll":
            fp = self._report_path(f"LabelQR_{o['w']:g}x{o['h']:g}mm")
            if fp:
                self._run_report(lambda rb, f: rb.qr_label_rolls(f, panel_ids, o["w"], o["h"], o["margin"]), fp)
        else:
            fp = self._report_path("LabelQR")
            if fp:
                self._run_report(lambda rb, f: rb.qr_labels(f, panel_ids), fp)

    def apply_role(self, refresh=True):
        """Peran viewer → mode baca saja (UI & database)."""
        from . import widgets as W
        cfg = self.sync.cfg
        ro = cfg.logged_in and cfg.get("role") == "viewer"
        self.read_only = W.RO = ro
        if self.db:
            self.db.read_only = ro
        self.ro_badge.setVisible(ro)
        for p in getattr(self, "pages", []):
            if hasattr(p, "set_read_only"):
                p.set_read_only(ro)
        if refresh and self.db:
            self.refresh_all()

    def closeEvent(self, e):
        self.sync.timer.stop()
        if self.sync.busy:
            self.sync.worker.wait(15000)
        if self.db:
            self.db.close()
        super().closeEvent(e)
