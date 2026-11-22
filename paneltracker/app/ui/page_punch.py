"""Halaman Punch List: board kanban (drag & drop) + tabel."""
from __future__ import annotations

from ..i18n import tr

import datetime as dt

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QStackedWidget, QTableWidget, QVBoxLayout, QWidget,
)

from ..db import ISSUE_STATUSES, SEV_LABEL, SEV_SHORT, SEVERITIES, fmt_date, parse_date, today
from . import theme as T
from .dialogs import IssueDialog
from .widgets import PageHeader, PunchCardDelegate, ask, btn, item, label, warn


class BoardList(QListWidget):
    dropped = Signal(list, str)
    opened = Signal(int)

    def __init__(self, status):
        super().__init__()
        self.status = status
        self.setItemDelegate(PunchCardDelegate(self))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSpacing(1)
        self.setMouseTracking(True)
        self.itemDoubleClicked.connect(lambda it: self.opened.emit(it.data(Qt.UserRole)))

    def dragEnterEvent(self, e):
        if isinstance(e.source(), BoardList) and e.source() is not self:
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self.setStyleSheet(f"QListWidget {{ background:{T.PRIMARY_L}; border-radius:4px; }}")
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if isinstance(e.source(), BoardList) and e.source() is not self:
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.setStyleSheet("")
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        self.setStyleSheet("")
        src = e.source()
        if not isinstance(src, BoardList) or src is self:
            e.ignore()
            return
        ids = [it.data(Qt.UserRole) for it in src.selectedItems()]
        e.setDropAction(Qt.CopyAction)
        e.accept()
        if ids:
            QTimer.singleShot(0, lambda: self.dropped.emit(ids, self.status))


class Column(QFrame):
    def __init__(self, status):
        super().__init__()
        self.setObjectName("col")
        self.setStyleSheet("QFrame#col { background:#E3E6E3; border-radius:5px; }")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 10, 6, 8)
        v.setSpacing(6)
        h = QHBoxLayout()
        h.setContentsMargins(6, 0, 6, 0)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background:{T.STATUS_LAMP[status]}; border-radius:5px; border:1px solid rgba(0,0,0,40);")
        h.addWidget(dot)
        h.addWidget(label(T.STATUS_LABEL[status], 10, True))
        self.cnt = QLabel("0")
        self.cnt.setStyleSheet(f"color:{T.TEXT}; background:{T.CARD}; border:1px solid {T.BORDER}; border-radius:3px; padding:1px 7px; font-weight:700;")
        h.addWidget(self.cnt)
        h.addStretch()
        v.addLayout(h)
        self.list = BoardList(status)
        v.addWidget(self.list, 1)


def table_cols():
    return [tr('Kode'), tr('Kat.'), tr('Judul'), tr('Panel'), "Site", tr('Kategori'), "Status", "PIC", tr('Ditemukan'), tr('Due'), tr('Close'),
              tr('Umur'), tr('Foto')]


class PunchPage(QWidget):
    def _b_new_btn(self):
        self.b_new = btn(tr('Punch baru'), "plus", "primary", None, self.new)
        return self.b_new

    def set_read_only(self, ro):
        self.b_new.setVisible(not ro)
        for lst in self.findChildren(BoardList):
            lst.setDragEnabled(not ro)
            lst.setAcceptDrops(not ro)

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(12)
        self.header = PageHeader(tr('Punch List'), "")
        seg = QWidget()
        sh = QHBoxLayout(seg)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(0)
        self.vgroup = QButtonGroup(self)
        for i, (key, text, ic) in enumerate((("board", tr('Board'), "board"), ("table", tr('Tabel'), "table"))):
            b = btn(text, ic, "segL" if i == 0 else "segR")
            b.setCheckable(True)
            b.setProperty("key", key)
            self.vgroup.addButton(b)
            sh.addWidget(b)
            if i == 0:
                b.setChecked(True)
        self.vgroup.buttonClicked.connect(self._view_changed)
        self.header.add(seg, btn(tr('Cetak PDF'), "printer", None, tr('Cetak punch list (filter mengikuti tampilan ini)'),
                                 self.print_pdf),
                        self._b_new_btn())
        lay.addWidget(self.header)

        fl = QHBoxLayout()
        fl.setSpacing(8)
        self.q = QLineEdit()
        self.q.setPlaceholderText(tr('Cari kode, judul, panel, PIC…'))
        self.q.setClearButtonEnabled(True)
        self.q.addAction(T.icon("search", T.SUBTLE, 16), QLineEdit.LeadingPosition)
        self.f_sev = QComboBox()
        self.f_sev.addItem(tr('Semua A/B/C'), None)
        for s in SEVERITIES:
            self.f_sev.addItem(SEV_LABEL[s], s)
        self.f_panel = QComboBox()
        self.f_cat = QComboBox()
        self.f_pic = QComboBox()
        self.f_closed = QCheckBox(tr('Tampilkan closed'))
        self.f_closed.setChecked(True)
        self.f_over = QCheckBox(tr('Hanya lewat target'))
        self.q.setMinimumWidth(170)
        fl.addWidget(self.q, 3)
        for w in (self.f_panel, self.f_sev, self.f_cat, self.f_pic):
            w.setMinimumWidth(110)
            w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(10)
            fl.addWidget(w, 1)
        self.fl1 = fl
        self.fl2 = QHBoxLayout()
        self.fl2.setSpacing(14)
        lay.addLayout(fl)
        lay.addLayout(self.fl2)
        self._wide = None
        self._arrange_filters(True)
        self.q.textChanged.connect(self.apply)
        for cb in (self.f_panel, self.f_sev, self.f_cat, self.f_pic):
            cb.currentIndexChanged.connect(self.apply)
        self.f_closed.toggled.connect(self.apply)
        self.f_over.toggled.connect(self.apply)

        self.stack = QStackedWidget()
        board = QWidget()
        bh = QHBoxLayout(board)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(12)
        self.cols = {}
        for s in ISSUE_STATUSES:
            c = Column(s)
            c.list.dropped.connect(self.move_to)
            c.list.opened.connect(self.open)
            c.list.setContextMenuPolicy(Qt.CustomContextMenu)
            c.list.customContextMenuRequested.connect(lambda pos, l_=c.list: self._ctx(l_, pos))
            self.cols[s] = c
            bh.addWidget(c, 1)
        self.stack.addWidget(board)

        self.tbl = QTableWidget(0, len(table_cols()))
        self.tbl.setHorizontalHeaderLabels(table_cols())
        self.tbl.verticalHeader().hide()
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setShowGrid(False)
        self.tbl.verticalHeader().setDefaultSectionSize(34)
        hh = self.tbl.horizontalHeader()
        hh.setSectionsClickable(True)
        hh.setSortIndicatorShown(True)
        hh.sectionClicked.connect(self._sort_by)
        self.sort_col, self.sort_desc = 0, True
        hh.setSortIndicator(0, Qt.DescendingOrder)
        self.tbl.doubleClicked.connect(lambda idx: self.open(self.tbl.item(idx.row(), 0).data(Qt.UserRole)))
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(lambda pos: self._ctx(self.tbl, pos))
        self.stack.addWidget(self.tbl)
        lay.addWidget(self.stack, 1)
        self.rows, self.shown, self.photos = [], [], {}

    # ------------------------------------------------------------ data
    def _arrange_filters(self, wide):
        """Layar lebar: checkbox satu baris dengan filter. Layar sempit: pindah ke baris kedua."""
        if wide == self._wide:
            return
        self._wide = wide
        for cb in (self.f_closed, self.f_over):
            (self.fl2 if wide else self.fl1).removeWidget(cb)
        if wide:
            self.fl1.addWidget(self.f_closed)
            self.fl1.addWidget(self.f_over)
        else:
            self.fl2.addWidget(self.f_closed)
            self.fl2.addWidget(self.f_over)
            self.fl2.addStretch()
        while not wide and self.fl2.count() > 3:
            self.fl2.takeAt(self.fl2.count() - 1)
        while wide and self.fl2.count():
            self.fl2.takeAt(0)

    def resizeEvent(self, e):
        self._arrange_filters(self.width() >= 1100)
        super().resizeEvent(e)

    def refresh(self):
        db, pid, sid = self.main.db, self.main.project_id, self.main.site_id
        self.rows = db.issues(pid, site_id=sid) if pid else []
        self.photos = db.attachment_count(pid) if pid else {}
        cur = self.f_panel.currentData()
        self.f_panel.blockSignals(True)
        self.f_panel.clear()
        self.f_panel.addItem(tr('Semua panel'), None)
        if any(not r["panel_id"] for r in self.rows):
            self.f_panel.addItem(tr('(Umum — tanpa panel)'), -1)
        for p in (db.panels(pid, sid) if pid else []):
            self.f_panel.addItem(f"{p['tag']} · {p['bay'] or '-'}", p["id"])
        i = self.f_panel.findData(cur)
        self.f_panel.setCurrentIndex(i if i >= 0 else 0)
        self.f_panel.blockSignals(False)
        for cb, key, lab in ((self.f_cat, "category", tr('Semua kategori')), (self.f_pic, "pic", tr('Semua PIC'))):
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem(lab)
            cb.addItems(sorted({r[key] for r in self.rows if r[key]}))
            i = cb.findText(cur)
            cb.setCurrentIndex(i if i >= 0 else 0)
            cb.blockSignals(False)
        self.apply()

    def _match(self, r, t):
        q = self.q.text().strip().lower()
        if q and q not in " ".join(str(r[k] or "") for k in ("code", "title", "description", "panel_tag", "site_name",
                                                              "pic", "category", "action")).lower():
            return False
        fp = self.f_panel.currentData()
        if fp is not None and (r["panel_id"] or -1) != fp:
            return False
        if self.f_sev.currentData() and r["severity"] != self.f_sev.currentData():
            return False
        if self.f_cat.currentIndex() > 0 and r["category"] != self.f_cat.currentText():
            return False
        if self.f_pic.currentIndex() > 0 and r["pic"] != self.f_pic.currentText():
            return False
        if not self.f_closed.isChecked() and r["status"] == "Closed":
            return False
        if self.f_over.isChecked() and not (r["status"] != "Closed" and r["due_date"] and r["due_date"] < t):
            return False
        return True

    def _key(self, r):
        c = self.sort_col
        if c == 1:
            return SEVERITIES.index(r["severity"]) if r["severity"] in SEVERITIES else 9
        if c == 6:
            return ISSUE_STATUSES.index(r["status"]) if r["status"] in ISSUE_STATUSES else 9
        if c == 11:
            return self._age(r) or 0
        if c == 12:
            return self.photos.get(r["id"], 0)
        if c == 0:
            return r["id"]
        k = [None, None, "title", "panel_tag", "site_name", "category", None, "pic", "raised_date", "due_date",
             "closed_date"][c]
        v = r[k] or ("9999" if c == 9 else "")
        return str(v).lower()

    @staticmethod
    def _age(r):
        a = parse_date(r["raised_date"])
        b = parse_date(r["closed_date"]) if r["status"] == "Closed" else dt.date.today()
        return (b - a).days if a and b else None

    def apply(self, *_):
        t = today()
        rows = [r for r in self.rows if self._match(r, t)]
        self.shown = rows
        # board
        sev_rank = {s: i for i, s in enumerate(SEVERITIES)}
        for s, col in self.cols.items():
            lst = col.list
            lst.clear()
            sub = [r for r in rows if r["status"] == s]
            if s == "Closed":
                sub.sort(key=lambda r: r["closed_date"] or "", reverse=True)
            else:
                sub.sort(key=lambda r: (sev_rank.get(r["severity"], 9), r["due_date"] or "9999"))
            for r in sub:
                it = QListWidgetItem()
                d = dict(r)
                d["_photos"] = self.photos.get(r["id"], 0)
                it.setData(Qt.UserRole, r["id"])
                it.setData(Qt.UserRole + 1, d)
                it.setSizeHint(QSize(220, PunchCardDelegate.H))
                it.setToolTip(f"{r['code']} — {r['title']}\n{r['description'] or ''}\nPIC: {r['pic'] or '-'}")
                lst.addItem(it)
            col.cnt.setText(str(len(sub)))
        # tabel
        rows_t = sorted(rows, key=self._key, reverse=self.sort_desc)
        self.tbl.setRowCount(len(rows_t))
        for i, r in enumerate(rows_t):
            over = r["status"] != "Closed" and r["due_date"] and r["due_date"] < t
            age = self._age(r)
            n_ph = self.photos.get(r["id"], 0)
            vals = [
                item(r["code"], r["id"], bold=True),
                item(SEV_SHORT.get(r["severity"], "?"), align=Qt.AlignCenter, fg="white",
                     bg=T.SEV_COLOR.get(r["severity"]), bold=True, tip=SEV_LABEL.get(r["severity"])),
                item(r["title"], tip=r["description"]),
                item(r["panel_tag"] or tr('(umum)')),
                item(r["site_name"] or ""),
                item(tr(r["category"] or "")),
                item("● " + T.STATUS_LABEL[r["status"]], fg=T.STATUS_COLOR.get(r["status"]), bold=True),
                item(r["pic"]),
                item(fmt_date(r["raised_date"])),
                item(fmt_date(r["due_date"]) + ("  ⚠" if over else ""), fg=T.NG if over else None, bold=bool(over)),
                item(fmt_date(r["closed_date"])),
                item(tr('{0} hr', age) if age is not None else "", align=Qt.AlignCenter),
                item(f"📷 {n_ph}" if n_ph else "", align=Qt.AlignCenter),
            ]
            for c, it in enumerate(vals):
                self.tbl.setItem(i, c, it)
        self.tbl.resizeColumnsToContents()
        self.tbl.setColumnWidth(1, 44)
        for c, mx in ((3, 110), (4, 110), (5, 150), (7, 130)):
            self.tbl.setColumnWidth(c, min(self.tbl.columnWidth(c), mx))
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        open_n = sum(1 for r in rows if r["status"] != "Closed")
        over_n = sum(1 for r in rows if r["status"] != "Closed" and r["due_date"] and r["due_date"] < t)
        self.header.sub.setText(tr('{0} dari {1} punch  ·  {2} belum close  ·  {3} lewat target  ·  seret kartu antar kolom untuk ubah status', len(rows), len(self.rows), open_n, over_n))

    def print_pdf(self):
        pre = {"photos": True}
        if not self.f_closed.isChecked():
            pre["status"] = ["Open", "In Progress", "Ready to Verify"]
        if self.f_sev.currentData():
            pre["severity"] = [self.f_sev.currentData()]
        if self.f_panel.currentData() is not None:
            pre["panels"] = [self.f_panel.currentData()]
        if self.q.text().strip():
            pre["search"] = self.q.text().strip()
        self.main.report_punchlist(preset=pre)

    def visible_ids(self):
        return [r["id"] for r in self.shown]

    def _sort_by(self, col):
        self.sort_desc = (not self.sort_desc) if col == self.sort_col else False
        self.sort_col = col
        self.tbl.horizontalHeader().setSortIndicator(col, Qt.DescendingOrder if self.sort_desc else Qt.AscendingOrder)
        self.apply()

    def _view_changed(self, b):
        self.stack.setCurrentIndex(0 if b.property("key") == "board" else 1)

    # ------------------------------------------------------------ actions
    def move_to(self, ids, status):
        db = self.main.db
        for iid in ids:
            db.update_issue(iid, status=status)
        self.main.refresh_all()
        self.main.statusBar().showMessage(f"{len(ids)} punch → {T.STATUS_LABEL[status]}", 4000)

    def open(self, iid):
        if iid and IssueDialog(self, self.main.db, self.main.project_id, iid).exec():
            self.main.refresh_all()

    def new(self):
        if not self.main.project_id:
            return
        if IssueDialog(self, self.main.db, self.main.project_id).exec():
            self.main.refresh_all()

    def _sel_ids(self, w):
        if isinstance(w, QTableWidget):
            return [w.item(r, 0).data(Qt.UserRole) for r in sorted({i.row() for i in w.selectedItems()})]
        return [it.data(Qt.UserRole) for it in w.selectedItems()]

    def _ctx(self, w, pos):
        ids = self._sel_ids(w)
        if not ids:
            return
        m = QMenu(self)
        if len(ids) == 1:
            m.addAction(T.icon("edit"), tr('Buka / edit…'), lambda: self.open(ids[0]))
            r = self.main.db.issue(ids[0])
            if r["panel_id"]:
                m.addAction(T.icon("check"), tr('Lihat di checklist panel'), lambda: self.main.go_panel(r["panel_id"]))
        sm = m.addMenu(tr('Ubah status'))
        for s in ISSUE_STATUSES:
            sm.addAction(T.STATUS_LABEL[s], lambda st=s: self.move_to(ids, st))
        m.addSeparator()
        m.addAction(T.icon("trash", T.NG), tr('Hapus {0} punch', len(ids)), lambda: self._delete(ids))
        m.exec(w.viewport().mapToGlobal(pos))

    def _delete(self, ids):
        if ask(self, tr('Hapus {0} punch beserta fotonya?', len(ids))):
            for i in ids:
                self.main.db.delete_issue(i)
            self.main.refresh_all()
