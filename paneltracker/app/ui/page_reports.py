"""Halaman Laporan & Template checklist."""
from __future__ import annotations

from ..i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QMenu, QListWidgetItem, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import theme as T
from .widgets import Card, PageHeader, ask, btn, info, label, warn


class ReportCard(Card):
    def __init__(self, icon_name, color, title, desc, options, button_text, action):
        super().__init__(pad=18)
        h = QHBoxLayout()
        ic = QLabel()
        ic.setFixedSize(44, 44)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(T.icon(icon_name, T.MUTED, 22).pixmap(22, 22))
        ic.setStyleSheet("background:#E3E6E3; border-radius:4px;")
        h.addWidget(ic)
        v = QVBoxLayout()
        v.setSpacing(2)
        v.addWidget(label(title, 11, True))
        d = label(desc, 9, False, T.MUTED, wrap=True)
        v.addWidget(d)
        h.addLayout(v, 1)
        self.lay.addLayout(h)
        self.opts = {}
        for key, text, default in options:
            cb = QCheckBox(text)
            cb.setChecked(default)
            self.opts[key] = cb
            self.lay.addWidget(cb)
        self.lay.addStretch()
        b = btn(button_text, "download" if "Excel" in button_text or "Template" in button_text else "printer",
                "primary", None, lambda: action(**{k: c.isChecked() for k, c in self.opts.items()}))
        hb = QHBoxLayout()
        hb.addStretch()
        hb.addWidget(b)
        self.lay.addLayout(hb)


class ReportsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        outer.addWidget(sa)
        body = QWidget()
        body.setObjectName("page")
        sa.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 22, 28, 24)
        lay.setSpacing(16)
        self.header = PageHeader(tr('Laporan & Data'), tr('Cetak report PDF atau ekspor/impor Excel. Lingkup mengikuti filter site di sidebar.'))
        lay.addWidget(self.header)
        g = QGridLayout()
        g.setSpacing(14)
        m = main
        cards = [
            ReportCard("punch", T.NG, tr('Punch List'), tr('Daftar temuan dengan warna status, kategori A/B/C, PIC, target, tindakan, plus lampiran foto. Bisa difilter: Open saja, per panel/bay (mis. Trafo, UGC), kategori, PIC, dan dikelompokkan per panel.'),
                       [], tr('Pilih filter & cetak…'), lambda: m.report_punchlist()),
            ReportCard("check", T.PRIMARY, tr('Lembar Uji Panel (Check Sheet)'),
                       tr('Satu halaman per panel: hasil setiap item cek (OK/NG/N/A, nilai ukur, catatan), punch terkait, QR code, dan kolom tanda tangan. Pilih panel mana saja (tipe, bay, status), seksi (mis. hanya SAS), item belum dicek/NG, atau cetak form kosong untuk lapangan.'),
                       [], tr('Pilih panel & cetak…'), lambda: m.report_check_sheet()),
            ReportCard("report", "#586064", tr('Ringkasan Checking'),
                       tr('Ringkasan untuk owner/PM: KPI, status setiap panel, rekap per site, dan punch kategori A/B yang masih open.'), [], tr('Buat PDF'), lambda: m.report_summary()),
            ReportCard("qr", T.TEXT, tr('Label QR Panel'), tr('A4 (24 label) atau printer label seperti Xprinter (1 label per halaman). Tempel di pintu panel; scan dengan kamera HP untuk melihat progress & punch list.'), [], tr('Buat PDF'), lambda: m.report_qr(None)),
            ReportCard("excel", T.OK, tr('Export Excel'), tr('Semua data dalam satu workbook: ringkasan panel, hasil cek per item, dan punch list (siap di-filter/pivot).'), [], tr('Simpan Excel'),
                       lambda: m.export_excel()),
            ReportCard("punch", "#9A5B00", tr('Import Punch List FAT (Excel)'),
                       tr('Format punchlist FAT per panel (No, Deskripsi Temuan, Dokumentasi Temuan, Rencana Tindakan, Dokumentasi Penyelesaian, Status, Remark). Foto di dalam sel ikut diimpor. Import ulang file yang sama tidak membuat data dobel.'), [], tr('Import…'), lambda: m.import_fat()),
            ReportCard("upload", INFO_COLOR, tr('Import Panel dari Excel'), tr('Isi daftar panel di template Excel (Site, Bay, Tag, Nama, Tipe, …), lalu import. Checklist otomatis diterapkan sesuai tipe.'),
                       [], tr('Import…'), lambda: m.import_excel()),
        ]
        self.grid, self.cards, self._cols = g, cards, 0
        self._relayout(3)
        lay.addLayout(g)
        hb = QHBoxLayout()
        hb.addWidget(btn(tr('Download template import panel'), "download", None, None, m.save_template))
        hb.addStretch()
        lay.addLayout(hb)
        lay.addStretch()

    def _relayout(self, cols):
        """Kartu 3 kolom di layar lebar, 2 kolom di laptop kecil (mis. 1366×768 + scaling 125%)."""
        if cols == self._cols:
            return
        self._cols = cols
        for c in self.cards:
            self.grid.removeWidget(c)
        for i, c in enumerate(self.cards):
            self.grid.addWidget(c, i // cols, i % cols)
        for k in range(3):
            self.grid.setColumnStretch(k, 1 if k < cols else 0)

    def resizeEvent(self, e):
        self._relayout(3 if self.width() >= 1050 else 2)
        super().resizeEvent(e)

    def refresh(self):
        pass


INFO_COLOR = "#586064"


# ======================================================================= Templates
class TemplatesPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(12)
        self.header = PageHeader(tr('Template Checklist'), tr('Item uji standar per tipe panel. Disalin ke panel saat diterapkan — hasil cek lama tidak berubah.'))
        self.header.add(btn(tr('Import Excel'), "upload", None, None, self.import_xlsx),
                        btn(tr('Template baru'), "plus", "primary", None, self.new))
        lay.addWidget(self.header)
        h = QHBoxLayout()
        h.setSpacing(14)
        left = Card(tr('Template'))
        self.list = QListWidget()
        self.list.setWordWrap(False)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setStyleSheet(f"QListWidget::item {{ padding:10px 8px; border-radius:3px; }}"
                                f"QListWidget::item:selected {{ background:{T.PRIMARY_L}; color:{T.TEXT}; }}")
        self.list.currentItemChanged.connect(lambda *_: self.load_current())
        left.lay.addWidget(self.list)
        left.setMinimumWidth(220)
        left.setMaximumWidth(300)
        h.addWidget(left)
        right = Card()
        top = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr('Nama template'))
        self.name.setStyleSheet("font-size:12pt; font-weight:700;")
        self.name.setMinimumWidth(160)
        top.addWidget(self.name, 2)
        self.desc = QLineEdit()
        self.desc.setPlaceholderText(tr('Keterangan'))
        top.addWidget(self.desc, 3)
        right.lay.addLayout(top)
        tb = QHBoxLayout()
        for text, ic, fn in ((tr('Baris'), "plus", self.add_row), (tr('Naik'), None, lambda: self.move(-1)),
                             (tr('Turun'), None, lambda: self.move(1)), (tr('Hapus baris'), "trash", self.del_rows)):
            tb.addWidget(btn(text, ic, None, None, fn))
        tb.addStretch()
        # aksi jarang dipakai dikumpulkan di menu ⋯ agar toolbar muat di layar laptop kecil
        more = btn("", "more", None, tr('Menu lainnya'))
        mm = QMenu(more)
        mm.addAction(T.icon("download"), tr('Export Excel'), self.export_xlsx)
        mm.addAction(T.icon("plus"), tr('Duplikat'), self.duplicate)
        mm.addSeparator()
        mm.addAction(T.icon("trash", T.NG), tr('Hapus template'), self.delete)
        more.setMenu(mm)
        more.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0; }")
        tb.addWidget(more)
        tb.addWidget(btn(tr('Simpan'), "check", "primary", None, self.save))
        right.lay.addLayout(tb)
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels([tr('Section'), tr('Item pengecekan'), tr('Kriteria terima'), tr('Satuan')])
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl.setColumnWidth(0, 160)
        self.tbl.setColumnWidth(2, 150)
        self.tbl.setColumnWidth(3, 60)
        self.tbl.verticalHeader().setDefaultSectionSize(30)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        right.lay.addWidget(self.tbl, 1)
        right.lay.addWidget(label(tr('Tips: double-click sel untuk mengedit. Item tanpa satuan cukup dinilai OK/NG/N/A; item bersatuan punya kolom nilai ukur.'), 8.5, False, T.MUTED))
        h.addWidget(right, 1)
        lay.addLayout(h, 1)
        self.tid = None

    def refresh(self, select=None):
        db = self.main.db
        cur = select or self.tid
        self.list.blockSignals(True)
        self.list.clear()
        for t in db.templates():
            it = QListWidgetItem(T.icon("template", T.PRIMARY), tr('{0}\n{1} item', t['name'], t['n']))
            it.setData(Qt.UserRole, t["id"])
            it.setToolTip(t['name'])
            self.list.addItem(it)
            if t["id"] == cur:
                self.list.setCurrentItem(it)
        if not self.list.currentItem() and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self.load_current()

    def load_current(self):
        it = self.list.currentItem()
        self.tid = it.data(Qt.UserRole) if it else None
        self.tbl.setRowCount(0)
        if not self.tid:
            self.name.clear()
            self.desc.clear()
            return
        db = self.main.db
        t = db.template(self.tid)
        self.name.setText(t["name"])
        self.name.setCursorPosition(0)
        self.desc.setText(t["description"])
        for r in db.template_items(self.tid):
            self._append([r["section"], r["description"], r["criteria"], r["unit"]])

    def _append(self, vals, row=None):
        r = self.tbl.rowCount() if row is None else row
        self.tbl.insertRow(r)
        for c, v in enumerate(vals):
            self.tbl.setItem(r, c, QTableWidgetItem(v or ""))

    def _rows(self):
        out = []
        for r in range(self.tbl.rowCount()):
            vals = [(self.tbl.item(r, c).text().strip() if self.tbl.item(r, c) else "") for c in range(4)]
            if vals[1]:
                out.append(tuple(vals))
        return out

    def add_row(self):
        r = self.tbl.currentRow()
        sec = self.tbl.item(r, 0).text() if r >= 0 and self.tbl.item(r, 0) else ""
        self._append([sec, "", "", ""], r + 1 if r >= 0 else None)
        nr = r + 1 if r >= 0 else self.tbl.rowCount() - 1
        self.tbl.setCurrentCell(nr, 1)
        self.tbl.editItem(self.tbl.item(nr, 1))

    def move(self, d):
        r = self.tbl.currentRow()
        j = r + d
        if r < 0 or not (0 <= j < self.tbl.rowCount()):
            return
        a = [self.tbl.item(r, c).text() if self.tbl.item(r, c) else "" for c in range(4)]
        b = [self.tbl.item(j, c).text() if self.tbl.item(j, c) else "" for c in range(4)]
        for c in range(4):
            self.tbl.setItem(r, c, QTableWidgetItem(b[c]))
            self.tbl.setItem(j, c, QTableWidgetItem(a[c]))
        self.tbl.selectRow(j)

    def del_rows(self):
        for r in sorted({i.row() for i in self.tbl.selectedItems()}, reverse=True):
            self.tbl.removeRow(r)

    def save(self):
        if not self.tid:
            return
        if not self.name.text().strip():
            warn(self, tr('Nama template wajib diisi.'))
            return
        self.main.db.save_template(self.tid, self.name.text().strip(), self.desc.text().strip(), self._rows())
        self.refresh(self.tid)
        self.main.statusBar().showMessage(tr('Template disimpan'), 3000)

    def new(self):
        name, ok = QInputDialog.getText(self, tr('Template baru'), tr('Nama template:'))
        if ok and name.strip():
            tid = self.main.db.add_template(name.strip(), "", [("A. Umum", "Item pengecekan pertama", "OK", "")])
            self.refresh(tid)

    def duplicate(self):
        if self.tid:
            tid = self.main.db.add_template(self.name.text().strip() + tr(' (salinan)'), self.desc.text().strip(),
                                            self._rows())
            self.refresh(tid)

    def delete(self):
        if self.tid and ask(self, tr("Hapus template '{0}'? Checklist yang sudah diterapkan ke panel tidak terpengaruh.", self.name.text())):
            self.main.db.delete_template(self.tid)
            self.tid = None
            self.refresh()

    def export_xlsx(self):
        if not self.tid:
            return
        from ..excel_io import export_template
        fp, _ = QFileDialog.getSaveFileName(self, tr('Export template'), f"Template_{self.name.text()}.xlsx",
                                            "Excel (*.xlsx)")
        if fp:
            export_template(self.main.db, self.tid, fp)
            self.main.open_file(fp, tr('Template diekspor'))

    def import_xlsx(self):
        from ..excel_io import import_template
        fp, _ = QFileDialog.getOpenFileName(self, tr('Import template'), "", "Excel (*.xlsx)")
        if not fp:
            return
        try:
            tid, n = import_template(self.main.db, fp)
        except Exception as e:
            warn(self, tr('Import gagal:\n{0}', e))
            return
        self.refresh(tid)
        info(self, tr('Template diimpor: {0} item.', n))
