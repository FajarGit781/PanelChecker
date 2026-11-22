"""UI cloud: dialog akun, worker sinkron (background thread), widget status di sidebar."""
from __future__ import annotations

from ..i18n import tr

import datetime as dt
import html

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QMessageBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from ..cloud import (DEFAULT_KEY, DEFAULT_URL, AuthError, CloudError, SupabaseClient, SyncEngine, check_endpoint,
                     display_user, login_email, password_problems)
from .. import secure_store
from ..db import Database
from . import theme as T
from .widgets import btn, info, label, warn


class CloudConfig:
    def __init__(self, settings: QSettings):
        self.s = settings

    def get(self, k, d=""):
        v = self.s.value(f"cloud/{k}")
        if k == "refresh_token" and v:
            plain = secure_store.unprotect(v)
            if plain and not secure_store.is_protected(v):
                self.set(k, plain)          # token lama (teks biasa) → simpan ulang terenkripsi
            return plain or d
        return d if v in (None, "") else v

    def set(self, k, v):
        if k == "refresh_token":
            # Windows: terenkripsi DPAPI; macOS (.app): disimpan di Keychain, satu entri per folder data
            import hashlib
            acct = "cloud-token:" + hashlib.sha1(self.s.fileName().encode("utf-8")).hexdigest()[:12]
            v = secure_store.protect(v or "", acct)
        self.s.setValue(f"cloud/{k}", v)
        self.s.sync()

    @property
    def url(self):
        return self.get("url", DEFAULT_URL)

    @property
    def key(self):
        return self.get("key", DEFAULT_KEY)

    @property
    def logged_in(self):
        return bool(self.get("refresh_token"))

    @property
    def auto_minutes(self):
        try:
            return int(self.get("auto_minutes", 10))
        except ValueError:
            return 10


class SyncWorker(QThread):
    progress = Signal(str)
    done = Signal(dict)
    failed = Signal(str, bool)  # pesan, perlu login ulang
    token = Signal(str)

    def __init__(self, db_path, url, key, refresh_token, push=True):
        super().__init__()
        self.db_path, self.url, self.key, self.refresh = db_path, url, key, refresh_token
        self.push = push

    def run(self):
        db = None
        try:
            c = SupabaseClient(self.url, self.key)
            c.restore(self.refresh)
            self.token.emit(c.refresh_token or "")
            db = Database(self.db_path)
            res = SyncEngine(db, c, lambda m: self.progress.emit(tr(m)), push=self.push).run()
            self.token.emit(c.refresh_token or "")
            self.done.emit(res)
        except AuthError as e:
            self.failed.emit(str(e), True)
        except CloudError as e:
            self.failed.emit(str(e), False)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}", False)
        finally:
            if db:
                db.close()


class SyncController(QObject):
    """Mengatur kapan sinkron jalan + memberi tahu UI."""
    state = Signal(str, str)      # teks status, warna
    busy_changed = Signal(bool)
    finished = Signal(dict)

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.cfg = CloudConfig(main.settings)
        self.worker = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.sync(silent=True))
        self.apply_timer()

    def apply_timer(self):
        self.timer.stop()
        if self.cfg.logged_in and self.cfg.auto_minutes > 0:
            self.timer.start(self.cfg.auto_minutes * 60 * 1000)

    @property
    def busy(self):
        return self.worker is not None

    def describe(self):
        if not self.cfg.logged_in:
            return tr('Belum login cloud'), T.SIDE_MUTED
        last = self.cfg.get("last_status", "")
        pend = self.main.db.pending_changes() if self.main.db else 0
        txt = last or tr('Siap sinkron')
        if self.cfg.get("role") == "viewer":
            pend = 0
            txt += tr(' · viewer')
        if pend:
            txt += tr(' · {0} belum terkirim', pend)
        # warna untuk teks di atas sidebar gelap (versi terang dari lampu merah/kuning/hijau)
        col = "#FF9D94" if self.cfg.get("last_error") else ("#A8DDB5" if not pend else "#FFD27A")
        return txt, col

    def refresh_state(self):
        if not self.busy:
            self.state.emit(*self.describe())

    def sync(self, silent=False):
        if self.busy or not self.main.db:
            return
        if not self.cfg.logged_in:
            if not silent:
                CloudDialog(self.main, self).exec()
            return
        self.main.db.conn.commit()
        self.worker = SyncWorker(self.main.db.path, self.cfg.url, self.cfg.key, self.cfg.get("refresh_token"),
                                 push=self.cfg.get("role") != "viewer")
        self.worker.progress.connect(lambda m: self.state.emit(m, "#FFD27A"))
        self.worker.token.connect(lambda t: t and self.cfg.set("refresh_token", t))
        self.worker.done.connect(self._done)
        self.worker.failed.connect(lambda m, relog: self._failed(m, relog, silent))
        self.worker.finished.connect(self._cleanup)
        self.busy_changed.emit(True)
        self.state.emit(tr('Menyinkron…'), "#FFD27A")
        self.worker.start()

    def _cleanup(self):
        self.worker = None
        self.busy_changed.emit(False)
        self.refresh_state()

    def _done(self, res):
        t = dt.datetime.now().strftime("%H:%M")
        self.cfg.set("last_error", "")
        self.cfg.set("last_status", tr('✓ Sinkron {0}', t))
        self.cfg.set("last_sync", dt.datetime.now().isoformat(timespec="seconds"))
        self.finished.emit(res)

    def _failed(self, msg, relog, silent):
        self.cfg.set("last_error", msg)
        self.cfg.set("last_status", tr('⚠ Sinkron gagal'))
        if relog:
            self.cfg.set("refresh_token", "")
            self.apply_timer()
        if not silent:
            warn(self.main, tr('Sinkron gagal:\n{0}', msg) + (tr('\n\nSilakan login ulang.') if relog else
                                                         tr('\n\nData lokal aman; coba lagi saat ada koneksi.')))


class CloudDialog(QDialog):
    def __init__(self, main, ctrl: SyncController):
        super().__init__(main)
        self.main, self.ctrl, self.cfg = main, ctrl, ctrl.cfg
        self.setWindowTitle(tr('Akun Cloud & Sinkronisasi'))
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(T.icon("cloud", T.PRIMARY, 34).pixmap(34, 34))
        head.addWidget(ic)
        hv = QVBoxLayout()
        hv.addWidget(label(tr('Sinkronisasi Cloud (Supabase)'), 13, True))
        hv.addWidget(label(tr('Data tetap tersimpan di laptop dan bisa dipakai offline. Saat ada internet, perubahan dikirim & diambil dari cloud, termasuk foto.'), 9, False, T.MUTED, wrap=True))
        head.addLayout(hv, 1)
        lay.addLayout(head)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setStyleSheet(f"background:{T.PRIMARY_L}; border-radius:4px; padding:10px;")
        lay.addWidget(self.status)

        self.login_box = QGroupBox("Login")
        f = QFormLayout(self.login_box)
        self.email = QLineEdit(display_user(self.cfg.get("email")))
        self.email.setPlaceholderText(tr("mis. Fajar"))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.returnPressed.connect(self.login)
        f.addRow(tr("Username"), self.email)
        f.addRow("Password", self.pw)
        lay.addWidget(self.login_box)

        opt = QGroupBox(tr('Pengaturan'))
        f2 = QFormLayout(opt)
        self.auto = QComboBox()
        for m, t in ((0, tr('Manual saja')), (5, tr('Setiap 5 menit')), (10, tr('Setiap 10 menit')), (30, tr('Setiap 30 menit'))):
            self.auto.addItem(t, m)
        self.auto.setCurrentIndex(max(0, self.auto.findData(self.cfg.auto_minutes)))
        f2.addRow(tr('Sinkron otomatis'), self.auto)
        self.url = QLineEdit(self.cfg.url)
        self.key = QLineEdit(self.cfg.key)
        self.url.setVisible(False)
        self.key.setVisible(False)
        self.adv = QPushButton(tr('Tampilkan server…'))
        self.adv.setObjectName("ghost")
        self.adv.clicked.connect(self._toggle_adv)
        f2.addRow("", self.adv)
        self.url_lbl, self.key_lbl = QLabel("Project URL"), QLabel("Publishable key")
        self.url_lbl.setVisible(False)
        self.key_lbl.setVisible(False)
        f2.addRow(self.url_lbl, self.url)
        f2.addRow(self.key_lbl, self.key)
        lay.addWidget(opt)

        bb = QHBoxLayout()
        self.b_logout = btn(tr('Keluar'), None, "danger", None, self.logout)
        self.b_login = btn(tr('Masuk'), "user", "primary", None, self.login)
        self.b_pw = btn(tr('Ganti password…'), None, None, None, self.change_password)
        self.b_sync = btn(tr('Sinkron sekarang'), "cloud", "primary", None, self.sync_now)
        close = btn(tr('Tutup'), None, None, None, self.accept)
        bb.addWidget(self.b_logout)
        bb.addWidget(self.b_pw)
        bb.addStretch()
        bb.addWidget(close)
        bb.addWidget(self.b_login)
        bb.addWidget(self.b_sync)
        lay.addLayout(bb)
        self._refresh()

    def _toggle_adv(self):
        v = not self.url.isVisible()
        for w in (self.url, self.key, self.url_lbl, self.key_lbl):
            w.setVisible(v)

    def _refresh(self):
        li = self.cfg.logged_in
        self.login_box.setVisible(not li)
        self.b_login.setVisible(not li)
        self.b_logout.setVisible(li)
        self.b_sync.setVisible(li)
        self.b_pw.setVisible(li)
        pend = self.main.db.pending_changes()
        if li:
            role = self.cfg.get("role", "-")
            last = self.cfg.get("last_sync", "")
            err = self.cfg.get("last_error", "")
            self.status.setText(
                tr('<b>Login sebagai:</b> {0} &nbsp;·&nbsp; peran <b>{1}</b><br><b>Sinkron terakhir:</b> {2}<br><b>Perubahan belum terkirim:</b> {3}', display_user(self.cfg.get('email')), role, last.replace('T', ' ') if last else tr('belum pernah'), pend)
                + (f"<br><span style='color:{T.NG}'>Error terakhir: {html.escape(err)}</span>" if err else ""))
        else:
            self.status.setText(tr('Belum login. <b>{0}</b> perubahan lokal menunggu dikirim.<br>Masuk dengan username & password dari admin (mis. <b>Fajar</b>). Akun viewer hanya bisa melihat data.', pend))

    def _save_opts(self):
        self.cfg.set("auto_minutes", self.auto.currentData())
        url, key = self.url.text().strip(), self.key.text().strip()
        try:
            check_endpoint(url, key)
        except CloudError as e:
            warn(self, tr('Pengaturan server tidak disimpan: {0}', e))
            self.url.setText(self.cfg.url)
            self.key.setText(self.cfg.key)
            return False
        self.cfg.set("url", url)
        self.cfg.set("key", key)
        self.ctrl.apply_timer()
        return True

    def login(self):
        if not self._save_opts():
            return
        email, pw = self.email.text().strip(), self.pw.text()
        if not email or not pw:
            warn(self, tr('Isi username dan password.'))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            c = SupabaseClient(self.cfg.url, self.cfg.key, timeout=20)
            c.sign_in(login_email(email), pw)
            mem = c.membership()
        except AuthError as e:
            QApplication.restoreOverrideCursor()
            msg = str(e)
            if "invalid" in msg.lower() and ("credential" in msg.lower() or "grant" in msg.lower()):
                msg = tr('Username atau password salah.')
            warn(self, tr('Login gagal: {0}', msg))
            return
        except CloudError as e:
            QApplication.restoreOverrideCursor()
            warn(self, str(e))
            return
        QApplication.restoreOverrideCursor()
        if not mem:
            warn(self, tr('Login berhasil, tapi {0} belum terdaftar di daftar tim (tabel app_users).\nMinta admin menambahkan email ini, lalu login lagi.', display_user(login_email(email))))
            c.sign_out()
            return
        if password_problems(pw, email):
            # password bawaan / lemah → wajib diganti sebelum aplikasi menyimpan sesi
            QMessageBox.information(self, tr('Ganti password'), tr(
                'Password akun ini terlalu lemah (mis. password bawaan dari admin). Demi keamanan data, '
                'ganti dulu dengan password pribadi.'))
            d = ChangePasswordDialog(self, c, login_email(email), forced=True)
            if not d.exec():
                c.sign_out()
                warn(self, tr('Login dibatalkan. Password harus diganti dulu sebelum bisa sinkron.'))
                return
        email = login_email(email)
        self.cfg.set("email", email)
        self.cfg.set("role", mem.get("role", ""))
        self.cfg.set("refresh_token", c.refresh_token)
        self.cfg.set("last_error", "")
        from ..db import _default_user
        if mem.get("full_name") and self.main.db.user in ("", _default_user()):
            self.main.db.set_setting("user_name", mem["full_name"])
            self.main._update_footer()
        self.pw.clear()
        self.ctrl.apply_timer()
        self._refresh()
        self.ctrl.refresh_state()
        self.main.apply_role()
        self.sync_now()

    def change_password(self):
        try:
            c = SupabaseClient(self.cfg.url, self.cfg.key, timeout=20)
            c.restore(self.cfg.get("refresh_token"))
            self.cfg.set("refresh_token", c.refresh_token)
        except CloudError as e:
            warn(self, str(e))
            return
        ChangePasswordDialog(self, c, self.cfg.get("email"), forced=False).exec()
        if c.refresh_token:
            self.cfg.set("refresh_token", c.refresh_token)

    def logout(self):
        tok = self.cfg.get("refresh_token")
        if tok:   # cabut sesi di server juga, bukan hanya di laptop ini
            try:
                c = SupabaseClient(self.cfg.url, self.cfg.key, timeout=10)
                c.refresh_token = tok
                c.sign_out()
            except Exception:
                pass
        self.cfg.set("refresh_token", "")
        self.cfg.set("role", "")
        self.ctrl.apply_timer()
        self._refresh()
        self.ctrl.refresh_state()
        self.main.apply_role()

    def sync_now(self):
        self._save_opts()
        self.ctrl.sync()
        self.accept()

    def accept(self):
        self._save_opts()
        super().accept()


class SyncWidget(QFrame):
    """Baris status sinkron di sidebar."""

    def __init__(self, ctrl: SyncController):
        super().__init__()
        self.ctrl = ctrl
        self.setStyleSheet("QFrame { background:#2A3034; border-radius:4px; }")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 6, 6)
        h.setSpacing(8)
        self.ic = QLabel()
        self.ic.setPixmap(T.icon("cloud", "#9AA3A6", 18).pixmap(18, 18))
        h.addWidget(self.ic)
        v = QVBoxLayout()
        v.setSpacing(0)
        t = QLabel("Cloud sync")
        t.setStyleSheet("color:white; font-weight:600; background:transparent;")
        self.st = QLabel()
        self.st.setStyleSheet("font-size:8pt; background:transparent;")
        self.st.setWordWrap(True)
        v.addWidget(t)
        v.addWidget(self.st)
        h.addLayout(v, 1)
        self.b = QToolButton()
        self.b.setIcon(T.icon("refresh", "#B3B9B5", 18))
        self.b.setToolTip(tr('Sinkron sekarang'))
        self.b.clicked.connect(lambda: ctrl.sync())
        h.addWidget(self.b)
        self.g = QToolButton()
        self.g.setIcon(T.icon("settings", "#B3B9B5", 16))
        self.g.setToolTip(tr('Akun cloud & pengaturan sinkron'))
        self.g.clicked.connect(lambda: CloudDialog(ctrl.main, ctrl).exec())
        h.addWidget(self.g)
        ctrl.state.connect(self.set_state)
        ctrl.busy_changed.connect(lambda b: self.b.setEnabled(not b))

    def set_state(self, text, color):
        self.st.setText(text)
        self.st.setStyleSheet(f"font-size:8pt; color:{color}; background:transparent;")
        self.ic.setPixmap(T.icon("cloud", color, 18).pixmap(18, 18))   # ikon ikut warna status (seperti lampu)


class ChangePasswordDialog(QDialog):
    """Ganti password akun cloud. forced=True: dipanggil otomatis setelah login dengan password lemah."""

    def __init__(self, parent, client: SupabaseClient, email: str, forced=False):
        super().__init__(parent)
        self.c, self.email, self.forced = client, email, forced
        self.setWindowTitle(tr('Ganti password'))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr('Password baru untuk <b>{0}</b>', html.escape(display_user(email))), 10, False, wrap=True))
        f = QFormLayout()
        self.old = QLineEdit()
        self.new = QLineEdit()
        self.new2 = QLineEdit()
        for e in (self.old, self.new, self.new2):
            e.setEchoMode(QLineEdit.Password)
        if not forced:
            f.addRow(tr('Password sekarang'), self.old)
        f.addRow(tr('Password baru'), self.new)
        f.addRow(tr('Ulangi password baru'), self.new2)
        lay.addLayout(f)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        lay.addWidget(label(tr('Aturan: minimal 10 karakter, ada huruf dan angka, bukan password umum, '
                               'tidak mengandung username. Jangan pakai password yang sama dengan akun lain.'),
                            8.5, False, T.MUTED, wrap=True))
        bb = QHBoxLayout()
        bb.addStretch()
        bb.addWidget(btn(tr('Batal'), None, None, None, self.reject))
        self.ok = btn(tr('Simpan password'), "check", "primary", None, self.accept)
        bb.addWidget(self.ok)
        lay.addLayout(bb)
        self.new.textChanged.connect(self._check)
        self.new2.textChanged.connect(self._check)
        self._check()

    def _problems(self):
        p = password_problems(self.new.text(), self.email)
        if self.new.text() != self.new2.text():
            p.append(tr('ulangan password belum sama'))
        return p

    def _check(self):
        p = self._problems()
        self.ok.setEnabled(not p)
        self.hint.setText("" if not self.new.text() else
                          (f"<span style='color:{T.OK}'>✓ " + tr('Password memenuhi aturan') + "</span>" if not p else
                           f"<span style='color:{T.NG}'>" + html.escape(", ".join(p)) + "</span>"))

    def accept(self):
        if self._problems():
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if not self.forced:   # pastikan yang mengganti memang pemilik akun
                chk = SupabaseClient(self.c.url, self.c.key, timeout=20)
                chk.sign_in(self.email, self.old.text())
                chk.sign_out()
            self.c.update_password(self.new.text())
        except AuthError as e:
            QApplication.restoreOverrideCursor()
            m = str(e)
            if "invalid" in m.lower() and "credential" in m.lower():
                m = tr('Password sekarang salah.')
            warn(self, tr('Password tidak diganti: {0}', m))
            return
        except CloudError as e:
            QApplication.restoreOverrideCursor()
            warn(self, tr('Password tidak diganti: {0}', e))
            return
        QApplication.restoreOverrideCursor()
        info(self, tr('Password berhasil diganti. Gunakan password baru saat login berikutnya.'))
        super().accept()
