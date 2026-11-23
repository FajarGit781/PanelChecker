"""Dialog-dialog input data."""
from __future__ import annotations

from ..i18n import tr

import json
import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget, QCompleter, QSpinBox,
)

from ..db import Database, ISSUE_STATUSES, SEVERITIES, SEV_LABEL, SEV_HINT, fmt_date, today
from .widgets import OptionalDateEdit, ask, item, warn
from . import theme as T


def _buttons(dlg, ok_text=None, data=True):
    from . import widgets as W
    ok_text = ok_text or tr('Simpan')
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    if data and W.RO:
        bb.button(QDialogButtonBox.Ok).setEnabled(False)
        bb.button(QDialogButtonBox.Ok).setToolTip(tr('Mode viewer: data hanya bisa dilihat.'))
    bb.button(QDialogButtonBox.Ok).setText(ok_text)
    bb.button(QDialogButtonBox.Ok).setObjectName("primary")
    bb.button(QDialogButtonBox.Cancel).setText(tr('Batal'))
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


# ---------------------------------------------------------------- Project
class ProjectDialog(QDialog):
    def __init__(self, parent, row=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Edit Project') if row else tr('Project Baru'))
        self.setMinimumWidth(480)
        f = QFormLayout(self)
        self.code = QLineEdit(row["code"] if row else "")
        self.name = QLineEdit(row["name"] if row else "")
        self.client = QLineEdit(row["client"] if row else "")
        self.contractor = QLineEdit(row["contractor"] if row else "")
        self.location = QLineEdit(row["location"] if row else "")
        self.start = OptionalDateEdit(row["start_date"] if row else today())
        self.end = OptionalDateEdit(row["end_date"] if row else None)
        self.prefix = QLineEdit(row["issue_prefix"] if row else "PL")
        self.prefix.setMaxLength(8)
        self.desc = QPlainTextEdit(row["description"] if row else "")
        self.desc.setFixedHeight(70)
        f.addRow(tr('Kode project *'), self.code)
        f.addRow(tr('Nama project *'), self.name)
        f.addRow(tr('Owner / Client'), self.client)
        f.addRow(tr('Kontraktor'), self.contractor)
        f.addRow(tr('Lokasi'), self.location)
        f.addRow(tr('Tanggal mulai'), self.start)
        f.addRow(tr('Target selesai'), self.end)
        f.addRow(tr('Prefix kode issue'), self.prefix)
        f.addRow(tr('Keterangan'), self.desc)
        f.addRow(_buttons(self))

    def accept(self):
        if not self.code.text().strip() or not self.name.text().strip():
            warn(self, tr('Kode dan nama project wajib diisi.'))
            return
        super().accept()

    def values(self):
        return dict(
            code=self.code.text().strip(), name=self.name.text().strip(), client=self.client.text().strip(),
            contractor=self.contractor.text().strip(), location=self.location.text().strip(), start_date=self.start.value(), end_date=self.end.value(),
            issue_prefix=self.prefix.text().strip() or "PL", description=self.desc.toPlainText().strip(),
        )


# ---------------------------------------------------------------- Sites
class SitesDialog(QDialog):
    def __init__(self, parent, db: Database, project_id):
        super().__init__(parent)
        self.db, self.pid = db, project_id
        self.setWindowTitle(tr('Kelola Site / Gardu'))
        self.resize(520, 380)
        lay = QHBoxLayout(self)
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels([tr('Site / GI'), tr('Lokasi'), tr('Jumlah panel')])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.verticalHeader().hide()
        self.tbl.doubleClicked.connect(self.edit)
        lay.addWidget(self.tbl, 1)
        side = QVBoxLayout()
        for text, fn in [(tr('Tambah'), self.add), (tr('Edit'), self.edit), (tr('Naik ▲'), lambda: self.move(-1)),
                         (tr('Turun ▼'), lambda: self.move(1)), (tr('Hapus'), self.delete)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            if text == "Hapus":
                b.setObjectName("danger")
            side.addWidget(b)
        side.addStretch()
        close = QPushButton(tr('Tutup'))
        close.clicked.connect(self.accept)
        side.addWidget(close)
        lay.addLayout(side)
        self.load()

    def load(self, select_id=None):
        rows = self.db.sites(self.pid)
        self.tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            n = self.db.q1("SELECT COUNT(*) c FROM panel WHERE site_id=? AND deleted=0", (r["id"],))["c"]
            self.tbl.setItem(i, 0, item(r["name"], r["id"]))
            self.tbl.setItem(i, 1, item(r["location"]))
            self.tbl.setItem(i, 2, item(n, align=Qt.AlignCenter))
            if r["id"] == select_id:
                self.tbl.selectRow(i)

    def _sel(self):
        r = self.tbl.currentRow()
        return self.tbl.item(r, 0).data(Qt.UserRole) if r >= 0 else None

    def _ask(self, name="", loc=""):
        d = QDialog(self)
        d.setWindowTitle(tr('Site / GI'))
        f = QFormLayout(d)
        n = QLineEdit(name)
        l_ = QLineEdit(loc)
        f.addRow(tr('Nama site / GI *'), n)
        f.addRow(tr('Lokasi'), l_)
        f.addRow(_buttons(d))
        if d.exec() and n.text().strip():
            return n.text().strip(), l_.text().strip()
        return None

    def add(self):
        v = self._ask()
        if v:
            sid = self.db.add_site(self.pid, *v)
            self.load(sid)

    def edit(self):
        sid = self._sel()
        if not sid:
            return
        s = self.db.site(sid)
        v = self._ask(s["name"], s["location"])
        if v:
            self.db.update_site(sid, *v)
            self.load(sid)

    def move(self, d):
        sid = self._sel()
        if sid:
            self.db.move_site(sid, d)
            self.load(sid)

    def delete(self):
        sid = self._sel()
        if sid and ask(self, tr('Hapus site ini beserta SEMUA panel dan progress-nya?\n(Issue tetap ada tapi tidak terhubung ke site)')):
            self.db.delete_site(sid)
            self.load()


# ---------------------------------------------------------------- Panel
class PanelDialog(QDialog):
    def __init__(self, parent, db: Database, project_id, row=None, site_id=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(tr('Edit Panel') if row else tr('Panel Baru'))
        self.setMinimumWidth(460)
        f = QFormLayout(self)
        self.site = QComboBox()
        for s in db.sites(project_id):
            self.site.addItem(s["name"], s["id"])
        sel = row["site_id"] if row else site_id
        if sel:
            self.site.setCurrentIndex(max(0, self.site.findData(sel)))
        self.bay = QLineEdit(row["bay"] if row else "")
        self.tag = QLineEdit(row["tag"] if row else "")
        self.name = QLineEdit(row["name"] if row else "")
        self.ptype = QComboBox()
        self.ptype.setEditable(True)
        self.ptype.addItems(db.get_list_setting("panel_types"))
        self.ptype.setCurrentText(row["panel_type"] if row else "")
        self.vendor = QLineEdit(row["vendor"] if row else "")
        self.sn = QLineEdit(row["serial_no"] if row else "")
        self.remarks = QPlainTextEdit(row["remarks"] if row else "")
        self.remarks.setFixedHeight(60)
        self.tpl = None
        if not row:
            self.tpl = QComboBox()
            self.tpl.addItem(tr('— tanpa checklist (isi nanti) —'), None)
            for t in db.templates():
                self.tpl.addItem(tr('{0}  ({1} item)', t['name'], t['n']), t["id"])
            self.tpl.setCurrentIndex(1 if self.tpl.count() > 1 else 0)
            self.ptype.currentTextChanged.connect(self._guess_tpl)
        f.addRow(tr('Site / GI *'), self.site)
        f.addRow(tr('Bay'), self.bay)
        f.addRow(tr('Tag panel *'), self.tag)
        f.addRow(tr('Nama / deskripsi'), self.name)
        f.addRow(tr('Tipe panel'), self.ptype)
        f.addRow(tr('Vendor / pabrikan'), self.vendor)
        f.addRow(tr('Serial number'), self.sn)
        f.addRow(tr('Catatan'), self.remarks)
        if self.tpl is not None:
            f.addRow(tr('Template checklist'), self.tpl)
        f.addRow(_buttons(self))

    def _guess_tpl(self, t):
        from ..i18n import lang
        rtu = any(k in t.upper() for k in ("RTU", "GATEWAY", "STATION"))
        en = lang() == "en"
        key = "RTU" if rtu else ("Protection" if en else "Proteksi")
        for i in range(self.tpl.count()):
            txt = self.tpl.itemText(i)
            if key in txt and (txt.rstrip().endswith("EN") == en):
                self.tpl.setCurrentIndex(i)
                return
        for i in range(self.tpl.count()):
            if key in self.tpl.itemText(i):
                self.tpl.setCurrentIndex(i)
                return

    def accept(self):
        if self.site.currentData() is None:
            warn(self, tr('Buat site terlebih dahulu (menu Project → Kelola Site).'))
            return
        if not self.tag.text().strip():
            warn(self, tr('Tag panel wajib diisi.'))
            return
        super().accept()

    def values(self):
        return dict(site_id=self.site.currentData(), bay=self.bay.text().strip(), tag=self.tag.text().strip(),
                    name=self.name.text().strip(), panel_type=self.ptype.currentText().strip(),
                    vendor=self.vendor.text().strip(), serial_no=self.sn.text().strip(),
                    remarks=self.remarks.toPlainText().strip())

    def template_id(self):
        return self.tpl.currentData() if self.tpl is not None else None


# ---------------------------------------------------------------- Issue
class ImageViewer(QDialog):
    def __init__(self, parent, data: bytes, title=""):
        super().__init__(parent)
        self.setWindowTitle(title or tr('Foto'))
        lay = QVBoxLayout(self)
        sa = QScrollArea()
        lbl = QLabel()
        pm = QPixmap()
        pm.loadFromData(data)
        if pm.width() > 1400 or pm.height() > 900:
            pm = pm.scaled(1400, 900, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lbl.setPixmap(pm)
        sa.setWidget(lbl)
        lay.addWidget(sa)
        self.resize(min(pm.width() + 40, 1440), min(pm.height() + 40, 940))


class IssueDialog(QDialog):
    def __init__(self, parent, db: Database, project_id, issue_id=None, panel_id=None, check_id=None,
                 preset=None):
        super().__init__(parent)
        self.db, self.pid, self.iid = db, project_id, issue_id
        row = db.issue(issue_id) if issue_id else None
        preset = preset or {}
        self.check_id = row["check_id"] if row else check_id
        self.setWindowTitle(f"Punch {row['code']}" if row else tr('Punch / Temuan Baru'))
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # --- tab detail
        w = QWidget()
        g = QGridLayout(w)
        self.code = QLineEdit(row["code"] if row else db.next_issue_code(project_id))
        self.title = QLineEdit(row["title"] if row else preset.get("title", ""))
        self.panel = QComboBox()
        self.panel.addItem(tr('— (tidak terkait panel / umum site) —'), None)
        for p in db.panels(project_id):
            self.panel.addItem(f"{p['site_name']} | {p['bay']} | {p['tag']}", p["id"])
        self.site = QComboBox()
        for s in db.sites(project_id):
            self.site.addItem(s["name"], s["id"])
        pnl = row["panel_id"] if row else panel_id
        if pnl:
            self.panel.setCurrentIndex(max(0, self.panel.findData(pnl)))
        if row and row["site_id"]:
            self.site.setCurrentIndex(max(0, self.site.findData(row["site_id"])))
        self.panel.currentIndexChanged.connect(self._panel_changed)
        self._panel_changed()
        self.cat = QComboBox()
        self.cat.setEditable(True)
        cats = db.get_list_setting("categories")
        for c in db.distinct_values(project_id, "category"):
            if c not in cats:
                cats.append(c)
        self.cat.addItems(cats)
        self.cat.setCurrentText(row["category"] if row else preset.get("category", cats[0] if cats else ""))
        self.sev = QComboBox()
        for sv in SEVERITIES:
            self.sev.addItem(f"{SEV_LABEL[sv]} — {SEV_HINT[sv]}", sv)
        self.sev.setCurrentIndex(SEVERITIES.index(row["severity"] if row else preset.get("severity", "Major")))
        self.status = QComboBox()
        for s_ in ISSUE_STATUSES:
            self.status.addItem(T.STATUS_LABEL[s_], s_)
        self.status.setCurrentIndex(max(0, self.status.findData(row["status"] if row else "Open")))
        self.pic = QLineEdit(row["pic"] if row else "")
        self.pic.setCompleter(QCompleter(db.distinct_values(project_id, "pic")))
        self.raised_by = QLineEdit(row["raised_by"] if row else db.user)
        self.raised = OptionalDateEdit(row["raised_date"] if row else today())
        self.due = OptionalDateEdit(row["due_date"] if row else db.default_due(self.sev.currentData()))
        if not row:
            self.sev.currentIndexChanged.connect(lambda *_: self.due.set_value(db.default_due(self.sev.currentData())))
        self.closed = OptionalDateEdit(row["closed_date"] if row else None)
        self.verified = QLineEdit(row["verified_by"] if row else "")
        self.verified.setCompleter(QCompleter(db.distinct_values(project_id, "verified_by")))
        self.desc = QPlainTextEdit(row["description"] if row else preset.get("description", ""))
        self.action = QPlainTextEdit(row["action"] if row else "")
        for te in (self.desc, self.action):
            te.setMinimumHeight(48)
        self.status.currentIndexChanged.connect(lambda *_: self._status_changed(self.status.currentData()))

        r = 0
        for lab, wid, lab2, wid2 in [
            (tr('Kode'), self.code, "Status", self.status),
            (tr('Judul / temuan *'), self.title, None, None),
            (tr('Panel'), self.panel, None, None),
            (tr('Site / GI'), self.site, tr('Kategori'), self.cat),
            (tr('Kategori punch'), self.sev, tr('PIC (penanggung jawab)'), self.pic),
            (tr('Tgl temuan'), self.raised, tr('Ditemukan oleh'), self.raised_by),
            (tr('Target selesai (due)'), self.due, tr('Tgl close'), self.closed),
            (tr('Diverifikasi oleh'), self.verified, None, None),
        ]:
            g.addWidget(QLabel(lab), r, 0)
            if lab2 is None:
                g.addWidget(wid, r, 1, 1, 3)
            else:
                g.addWidget(wid, r, 1)
                g.addWidget(QLabel(lab2), r, 2)
                g.addWidget(wid2, r, 3)
            r += 1
        if self.check_id:
            c = db.check(self.check_id)
            if c:
                lk = QLabel(tr('🔗 Item cek: <b>{0}</b> — {1}', c['section'], c['description']))
                lk.setStyleSheet(f"color:{T.TEXT}; background:{T.PRIMARY_L}; border-left:3px solid {T.SIGNAL}; padding:6px 8px; border-radius:3px;")
                lk.setWordWrap(True)
                g.addWidget(lk, r, 0, 1, 4)
                r += 1
        g.addWidget(QLabel(tr('Deskripsi temuan')), r, 0, Qt.AlignTop)
        g.addWidget(self.desc, r, 1, 1, 3)
        r += 1
        g.addWidget(QLabel(tr('Tindakan perbaikan')), r, 0, Qt.AlignTop)
        g.addWidget(self.action, r, 1, 1, 3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        tabs.addTab(w, tr('Detail'))

        # --- tab foto
        fw = QWidget()
        fl = QVBoxLayout(fw)
        self.photos = QListWidget()
        self.photos.setViewMode(QListWidget.IconMode)
        self.photos.setIconSize(QSize(180, 135))
        self.photos.setResizeMode(QListWidget.Adjust)
        self.photos.setSpacing(8)
        self.photos.itemDoubleClicked.connect(self._view)
        fl.addWidget(self.photos, 1)
        hb = QHBoxLayout()
        for text, fn in [(tr('Tambah foto…'), self._add_photo), (tr('Lihat'), self._view), (tr('Ubah jenis/caption'), self._edit_photo),
                         (tr('Simpan ke file…'), self._save_photo), (tr('Hapus foto'), self._del_photo)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            hb.addWidget(b)
        hb.addStretch()
        fl.addLayout(hb)
        self.photo_note = QLabel()
        fl.addWidget(self.photo_note)
        tabs.addTab(fw, tr('Foto / Lampiran'))
        self._pending = []  # foto untuk issue yang belum disimpan
        self._load_photos()

        lay.addWidget(_buttons(self))

    def _panel_changed(self):
        pid = self.panel.currentData()
        if pid:
            p = self.db.panel(pid)
            self.site.setCurrentIndex(max(0, self.site.findData(p["site_id"])))
            self.site.setEnabled(False)
        else:
            self.site.setEnabled(True)

    def _status_changed(self, s):
        if s == "Closed" and not self.closed.value():
            self.closed.set_value(today())
        if s != "Closed":
            self.closed.set_value(None)

    # foto
    def _load_photos(self):
        self.photos.clear()
        rows = []
        if self.iid:
            rows = [(r["id"], r["kind"], r["filename"], r["caption"], None) for r in self.db.attachments(self.iid)]
        rows += [(None, k, fn, cap, data) for (fn, data, k, cap) in self._pending]
        for idx, (aid, kind, fn, cap, data) in enumerate(rows):
            data = data if data is not None else self.db.attachment_data(aid)
            pm = QPixmap()
            pm.loadFromData(data)
            label = {"before": tr('SEBELUM'), "after": tr('SESUDAH')}.get(kind, "LAIN")
            it = QListWidgetItem(QIcon(pm.scaled(180, 135, Qt.KeepAspectRatio, Qt.SmoothTransformation)),
                                 f"[{label}] {cap or fn}")
            it.setData(Qt.UserRole, (aid, idx))
            self.photos.addItem(it)
        self.photo_note.setText(tr('{0} foto. Foto disimpan di dalam database (ikut ter-backup). Foto besar otomatis diperkecil ke maks 1600 px.', len(rows)))

    def _add_photo(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr('Pilih foto'), "", tr('Gambar (*.jpg *.jpeg *.png *.bmp)'))
        if not files:
            return
        kind = "after" if self.status.currentData() in ("Ready to Verify", "Closed") else "before"
        for fp in files:
            data = _load_image_resized(fp)
            if not data:
                continue
            name = os.path.basename(fp)
            if self.iid:
                self.db.add_attachment(self.iid, name, data, kind=kind, caption="")
            else:
                self._pending.append((name, data, kind, ""))
        self._load_photos()

    def _cur(self):
        it = self.photos.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _photo_data(self, cur):
        aid, idx = cur
        if aid:
            return self.db.attachment_data(aid)
        n_db = len(self.db.attachments(self.iid)) if self.iid else 0
        return self._pending[idx - n_db][1]

    def _view(self, *_):
        cur = self._cur()
        if cur:
            ImageViewer(self, self._photo_data(cur), self.photos.currentItem().text()).exec()

    def _save_photo(self):
        cur = self._cur()
        if not cur:
            return
        fp, _ = QFileDialog.getSaveFileName(self, tr('Simpan foto'), "foto.jpg", "JPEG (*.jpg);;PNG (*.png)")
        if fp:
            pm = QPixmap()
            pm.loadFromData(self._photo_data(cur))
            pm.save(fp)

    def _edit_photo(self):
        cur = self._cur()
        if not cur:
            return
        kinds = ["before", "after", "other"]
        labels = [tr('Sebelum perbaikan'), tr('Sesudah perbaikan'), tr('Lainnya')]
        k, ok = QInputDialog.getItem(self, tr('Jenis foto'), tr('Jenis:'), labels, 0, False)
        if not ok:
            return
        cap, ok2 = QInputDialog.getText(self, "Caption", tr('Keterangan foto:'))
        aid, idx = cur
        kind = kinds[labels.index(k)]
        if aid:
            self.db.update_attachment(aid, kind=kind, caption=cap if ok2 else None)
        else:
            n_db = len(self.db.attachments(self.iid)) if self.iid else 0
            fn, data, _, c0 = self._pending[idx - n_db]
            self._pending[idx - n_db] = (fn, data, kind, cap if ok2 else c0)
        self._load_photos()

    def _del_photo(self):
        cur = self._cur()
        if not cur or not ask(self, tr('Hapus foto ini?')):
            return
        aid, idx = cur
        if aid:
            self.db.delete_attachment(aid)
        else:
            n_db = len(self.db.attachments(self.iid)) if self.iid else 0
            self._pending.pop(idx - n_db)
        self._load_photos()

    def accept(self):
        if not self.title.text().strip():
            warn(self, tr('Judul temuan wajib diisi.'))
            return
        code = self.code.text().strip()
        if code and self.db.q1("SELECT 1 FROM issue WHERE project_id=? AND code=? AND deleted=0 AND id<>?",
                               (self.pid, code, self.iid or 0)):
            warn(self, tr("Kode punch '{0}' sudah dipakai di project ini. Gunakan kode lain.", code))
            return
        v = dict(
            code=self.code.text().strip() or self.db.next_issue_code(self.pid),
            title=self.title.text().strip(), panel_id=self.panel.currentData(),
            site_id=self.site.currentData(), category=self.cat.currentText().strip(),
            severity=self.sev.currentData(), status=self.status.currentData(), pic=self.pic.text().strip(),
            raised_by=self.raised_by.text().strip(), raised_date=self.raised.value(), due_date=self.due.value(),
            closed_date=self.closed.value(), verified_by=self.verified.text().strip(),
            description=self.desc.toPlainText().strip(), action=self.action.toPlainText().strip(),
        )
        if self.iid:
            self.db.update_issue(self.iid, **v)
        else:
            if self.check_id:
                v["check_id"] = self.check_id
            self.iid = self.db.add_issue(self.pid, **v)
            for fn, data, kind, cap in self._pending:
                self.db.add_attachment(self.iid, fn, data, kind=kind, caption=cap)
        super().accept()


class EvidenceDialog(QDialog):
    """Foto evidence satu item checklist (uji DI/DO): bukti DI masuk / DO bekerja.
    Foto dari file, atau screenshot HMI/BCU yang ditempel dari clipboard."""

    def __init__(self, parent, db: Database, check_id, title=""):
        super().__init__(parent)
        self.db = db
        self.cid = check_id
        c = db.check(check_id)
        self.setWindowTitle(tr('Foto evidence'))
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        head = QLabel(f"<b>{title or ''}</b><br/><span style='color:#586064'>{c['section']} — {c['description']}</span>")
        head.setWordWrap(True)
        lay.addWidget(head)
        self.photos = QListWidget()
        self.photos.setViewMode(QListWidget.IconMode)
        self.photos.setIconSize(QSize(200, 150))
        self.photos.setResizeMode(QListWidget.Adjust)
        self.photos.setSpacing(8)
        self.photos.itemDoubleClicked.connect(self._view)
        lay.addWidget(self.photos, 1)
        hb = QHBoxLayout()
        ro = getattr(db, "read_only", False)
        acts = [(tr('Tambah foto…'), self._add, True), (tr('Tempel dari clipboard'), self._paste, True),
                (tr('Lihat'), self._view, False), (tr('Ubah caption'), self._caption, True),
                (tr('Simpan ke file…'), self._save, False), (tr('Hapus foto'), self._delete, True)]
        for text, fn, write in acts:
            if write and ro:
                continue
            b = QPushButton(text)
            b.clicked.connect(fn)
            hb.addWidget(b)
        hb.addStretch()
        lay.addLayout(hb)
        self.note = QLabel()
        self.note.setStyleSheet("color:#586064;")
        lay.addWidget(self.note)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self._load()

    def _load(self):
        self.photos.clear()
        rows = self.db.check_photos(self.cid)
        for r in rows:
            pm = QPixmap()
            pm.loadFromData(self.db.attachment_data(r["id"]))
            it = QListWidgetItem(QIcon(pm.scaled(200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                 if not pm.isNull() else QIcon(), r["caption"] or r["filename"] or "")
            it.setData(Qt.UserRole, r["id"])
            self.photos.addItem(it)
        self.note.setText(tr('{0} foto evidence. Foto ikut sinkron ke cloud & tercetak di Report Uji DI/DO.', len(rows)))

    def _cur(self):
        it = self.photos.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr('Pilih foto'), "", tr('Gambar (*.jpg *.jpeg *.png *.bmp)'))
        for fp in files:
            data = _load_image_resized(fp)
            if data:
                self.db.add_check_photo(self.cid, os.path.basename(fp), data)
        self._load()

    def _paste(self):
        from PySide6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img.isNull():
            warn(self, tr('Clipboard tidak berisi gambar. Ambil screenshot dulu (mis. Win+Shift+S / Cmd+Ctrl+Shift+4).'))
            return
        data = _image_to_jpeg(img)
        import datetime as _dt
        self.db.add_check_photo(self.cid, f"screenshot_{_dt.datetime.now():%Y%m%d_%H%M%S}.jpg", data)
        self._load()

    def _view(self, *_):
        aid = self._cur()
        if aid:
            ImageViewer(self, self.db.attachment_data(aid), self.photos.currentItem().text()).exec()

    def _caption(self):
        aid = self._cur()
        if not aid:
            return
        cap, ok = QInputDialog.getText(self, "Caption", tr('Keterangan foto:'), text=self.photos.currentItem().text())
        if ok:
            self.db.update_attachment(aid, caption=cap.strip())
            self._load()

    def _save(self):
        aid = self._cur()
        if not aid:
            return
        fp, _ = QFileDialog.getSaveFileName(self, tr('Simpan foto'), "evidence.jpg", "JPEG (*.jpg);;PNG (*.png)")
        if fp:
            pm = QPixmap()
            pm.loadFromData(self.db.attachment_data(aid))
            pm.save(fp)

    def _delete(self):
        aid = self._cur()
        if aid and ask(self, tr('Hapus foto ini?')):
            self.db.delete_attachment(aid)
            self._load()


def _image_to_jpeg(img, max_px=1600) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    if img.width() > max_px or img.height() > max_px:
        img = img.scaled(max_px, max_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPG", 85)
    return bytes(ba)


def _load_image_resized(path, max_px=1600) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage, QImageReader
    reader = QImageReader(path)
    reader.setAutoTransform(True)  # rotasi EXIF dari HP
    img = reader.read()
    if img.isNull():
        return b""
    if img.width() > max_px or img.height() > max_px:
        img = img.scaled(max_px, max_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPG", 85)
    return bytes(ba)


# ---------------------------------------------------------------- Settings
class SettingsDialog(QDialog):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(tr('Pengaturan'))
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # umum
        w = QWidget()
        f = QFormLayout(w)
        self.user = QLineEdit(db.get_setting("user_name"))
        self.company = QLineEdit(db.get_setting("company_name"))
        self.address = QLineEdit(db.get_setting("company_address"))
        self.viewer_url = QLineEdit(db.get_setting("viewer_url"))
        self.viewer_url.setPlaceholderText("https://panel-viewer.netlify.app/")
        self.viewer_url.setToolTip(tr('Kalau diisi, label QR berisi link ke halaman progress panel. Scan dengan kamera HP '
                                      'biasa langsung membuka punch list & progress panel tanpa login. Kosongkan untuk '
                                      'label model lama (PT:…).'))
        self.due_days = {}
        due_row = QHBoxLayout()
        for sv in SEVERITIES:
            sp = QSpinBox()
            sp.setRange(0, 365)
            sp.setSuffix(tr(' hari'))
            sp.setValue(int(db.get_setting(f"due_days_{sv}", "7") or 7))
            self.due_days[sv] = sp
            due_row.addWidget(QLabel(SEV_LABEL[sv].split(" · ")[0]))
            due_row.addWidget(sp)
        due_row.addStretch()
        logo_row = QHBoxLayout()
        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(160, 60)
        self.logo_lbl.setStyleSheet("border:1px dashed #AAB; background:white;")
        self.logo_lbl.setAlignment(Qt.AlignCenter)
        self._logo = db.get_logo()
        self._logo_name = ""
        self._show_logo()
        b1 = QPushButton(tr('Pilih logo…'))
        b1.clicked.connect(self._pick_logo)
        b2 = QPushButton(tr('Hapus'))
        b2.clicked.connect(self._clear_logo)
        logo_row.addWidget(self.logo_lbl)
        logo_row.addWidget(b1)
        logo_row.addWidget(b2)
        logo_row.addStretch()
        from . import widgets as W
        note = QLabel(tr('Kop, logo, tanda tangan, daftar pilihan dan target default dipakai bersama tim dan ikut '
                         'sinkron cloud, jadi cukup diisi sekali. Nama user dan bahasa hanya untuk laptop ini.'))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{T.TEXT}; background:{T.PRIMARY_L}; border-left:3px solid {T.SIGNAL}; "
                           "padding:6px 8px; border-radius:3px;")
        f.addRow(note)
        self._ro = W.RO
        f.addRow(tr('Nama user (untuk log)'), self.user)
        f.addRow(tr('Nama perusahaan (kop report)'), self.company)
        f.addRow(tr('Alamat / keterangan kop'), self.address)
        f.addRow(tr('Logo report'), logo_row)
        f.addRow(tr('Default target selesai punch'), due_row)
        f.addRow(tr('Alamat viewer web (link label QR)'), self.viewer_url)
        from ..i18n import LANGS, lang
        self.qs = getattr(parent, "settings", None)
        self.ui_lang = QComboBox()
        self.rep_lang = QComboBox()
        self.rep_lang.addItem(tr('Sama dengan tampilan'), "")
        for code, name in LANGS.items():
            self.ui_lang.addItem(name, code)
            self.rep_lang.addItem(name, code)
        self.ui_lang.setCurrentIndex(max(0, self.ui_lang.findData(lang())))
        if self.qs is not None:
            self.rep_lang.setCurrentIndex(max(0, self.rep_lang.findData(self.qs.value("report/lang", "") or "")))
        f.addRow(tr('Bahasa tampilan'), self.ui_lang)
        f.addRow(tr('Bahasa report PDF'), self.rep_lang)
        tabs.addTab(w, tr('Umum & Kop Report').replace("&", "&&"))

        # tanda tangan
        w2 = QWidget()
        f2 = QFormLayout(w2)
        self.sig = {}
        for key, lab in [("prepared", tr('Dibuat oleh')), ("checked", tr('Diperiksa oleh')), ("approved", tr('Disetujui oleh'))]:
            n = QLineEdit(db.get_setting(f"sign_{key}"))
            t = QLineEdit(db.get_setting(f"sign_{key}_title"))
            self.sig[key] = (n, t)
            f2.addRow(QLabel(f"<b>{lab}</b>"))
            f2.addRow(tr('Nama'), n)
            f2.addRow(tr('Jabatan'), t)
        tabs.addTab(w2, tr('Tanda Tangan Report'))

        # daftar
        w3 = QWidget()
        h = QHBoxLayout(w3)
        self.cat = QPlainTextEdit("\n".join(db.get_list_setting("categories")))
        self.ptypes = QPlainTextEdit("\n".join(db.get_list_setting("panel_types")))
        for lab, wid in [(tr('Kategori issue (1 per baris)'), self.cat), (tr('Tipe panel (1 per baris)'), self.ptypes)]:
            gb = QGroupBox(lab)
            v = QVBoxLayout(gb)
            v.addWidget(wid)
            h.addWidget(gb)
        tabs.addTab(w3, tr('Daftar Pilihan'))

        lay.addWidget(_buttons(self, data=False))
        if self._ro:   # viewer: pengaturan tim hanya dilihat
            for wdg in [self.company, self.address, self.viewer_url, *[x for pair in self.sig.values() for x in pair]]:
                wdg.setReadOnly(True)
            for wdg in [self.cat, self.ptypes]:
                wdg.setReadOnly(True)
            for wdg in [*self.due_days.values(), b1, b2]:
                wdg.setEnabled(False)

    def _show_logo(self):
        if self._logo:
            pm = QPixmap()
            pm.loadFromData(self._logo)
            self.logo_lbl.setPixmap(pm.scaled(156, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo_lbl.setPixmap(QPixmap())
            self.logo_lbl.setText(tr('(tanpa logo)'))

    def _pick_logo(self):
        fp, _ = QFileDialog.getOpenFileName(self, tr('Pilih logo'), "", tr('Gambar (*.png *.jpg *.jpeg *.bmp)'))
        if fp:
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            from PySide6.QtGui import QImage
            img = QImage(fp)
            if img.isNull():
                return
            if img.width() > 800:
                img = img.scaledToWidth(800, Qt.SmoothTransformation)
            if img.height() > 400:
                img = img.scaledToHeight(400, Qt.SmoothTransformation)

            def enc(im, fmt, q=-1):
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.WriteOnly)
                im.save(buf, fmt, q)
                return bytes(ba)
            data = enc(img, "PNG")
            # logo ikut sinkron ke tim: jaga tetap kecil (< 300 KB)
            while len(data) > 300_000 and img.width() > 200:
                img = img.scaledToWidth(int(img.width() * 0.75), Qt.SmoothTransformation)
                data = enc(img, "PNG")
            if len(data) > 300_000:
                data = enc(img, "JPG", 85)
            self._logo = data
            self._logo_name = os.path.basename(fp)
            self._show_logo()

    def _clear_logo(self):
        self._logo = None
        self._show_logo()

    def accept(self):
        d = self.db
        d.set_setting("user_name", self.user.text().strip())
        if self._ro:
            self._save_lang()
            return super().accept()
        d.set_setting("company_name", self.company.text().strip())
        d.set_setting("company_address", self.address.text().strip())
        url = self.viewer_url.text().strip()
        if url and not url.lower().startswith("https://"):
            warn(self, tr('Alamat viewer web harus diawali https://'))
            self.viewer_url.setFocus()
            return
        d.set_setting("viewer_url", url)
        for sv, sp in self.due_days.items():
            d.set_setting(f"due_days_{sv}", str(sp.value()))
        for key, (n, t) in self.sig.items():
            d.set_setting(f"sign_{key}", n.text().strip())
            d.set_setting(f"sign_{key}_title", t.text().strip())
        d.set_setting("categories", json.dumps([x.strip() for x in self.cat.toPlainText().splitlines() if x.strip()]))
        d.set_setting("panel_types", json.dumps([x.strip() for x in self.ptypes.toPlainText().splitlines() if x.strip()]))
        d.set_logo(self._logo, self._logo_name)
        self._save_lang()
        super().accept()

    def _save_lang(self):
        self.lang_changed = False
        if self.qs is not None:
            from ..i18n import lang
            self.qs.setValue("report/lang", self.rep_lang.currentData())
            if self.ui_lang.currentData() != lang():
                self.qs.setValue("ui/lang", self.ui_lang.currentData())
                self.lang_changed = True
            self.qs.sync()


