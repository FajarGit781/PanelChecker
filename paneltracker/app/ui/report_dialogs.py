"""Dialog filter untuk cetak report punch list."""
from __future__ import annotations

from ..i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from ..db import ISSUE_STATUSES, PANEL_STATUSES, SEV_LABEL, SEVERITIES, today
from . import theme as T
from .widgets import btn, label, warn

UMUM = -1  # id semu untuk punch tanpa panel


def _check_list(items, checked=True, height=None):
    lw = QListWidget()
    lw.setStyleSheet("QListWidget { background:white; border:1px solid #C9CEC9; border-radius:6px; }"
                     "QListWidget::item { padding:3px 4px; }")
    for text, data in items:
        it = QListWidgetItem(text)
        it.setData(Qt.UserRole, data)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        lw.addItem(it)
    if height:
        lw.setFixedHeight(height)
    return lw


def _checked(lw):
    return [lw.item(i).data(Qt.UserRole) for i in range(lw.count()) if lw.item(i).checkState() == Qt.Checked]


def _set_all(lw, on, only=None):
    lw.blockSignals(True)
    for i in range(lw.count()):
        it = lw.item(i)
        on_i = on if only is None else (it.data(Qt.UserRole) in only)
        it.setCheckState(Qt.Checked if on_i else Qt.Unchecked)
    lw.blockSignals(False)
    lw.itemChanged.emit(lw.item(0)) if lw.count() else None


class PunchReportDialog(QDialog):
    """Pilih punch yang dicetak: status, panel/bay, kategori A/B/C, kategori temuan, PIC."""

    def __init__(self, main, preset=None):
        super().__init__(main)
        self.main = main
        self.db = main.db
        self.pid = main.project_id
        preset = preset or {}
        self.setWindowTitle(tr('Cetak Punch List — Filter'))
        self.resize(900, 640)
        self.rows = self.db.issues(self.pid, site_id=main.site_id)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label(tr('Cetak Punch List'), 14, True))
        head.addStretch()
        head.addWidget(QLabel(tr('Cepat:')))
        for text, fn in ((tr('Semua'), self._p_all), (tr('Belum close'), self._p_active), (tr('Open saja'), self._p_open),
                         (tr('Closed saja'), self._p_closed), (tr('Kategori A aktif'), self._p_crit)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            head.addWidget(b)
        lay.addLayout(head)

        g = QGridLayout()
        g.setSpacing(10)
        # status
        gb1 = QGroupBox("Status")
        v1 = QVBoxLayout(gb1)
        self.st = {}
        cnt = {s: sum(1 for r in self.rows if r["status"] == s) for s in ISSUE_STATUSES}
        for s in ISSUE_STATUSES:
            cb = QCheckBox(f"{T.STATUS_LABEL[s]}  ({cnt[s]})")
            cb.setChecked(s in preset.get("status", ISSUE_STATUSES))
            cb.setStyleSheet(f"QCheckBox {{ color:{T.STATUS_COLOR[s]}; font-weight:600; }}")
            cb.toggled.connect(self._update)
            v1.addWidget(cb)
            self.st[s] = cb
        v1.addStretch()
        # kategori A/B/C
        gb2 = QGroupBox(tr('Kategori A/B/C'))
        v2 = QVBoxLayout(gb2)
        self.sv = {}
        for s in SEVERITIES:
            n = sum(1 for r in self.rows if r["severity"] == s)
            cb = QCheckBox(f"{SEV_LABEL[s]}  ({n})")
            cb.setChecked(s in preset.get("severity", SEVERITIES))
            cb.setStyleSheet(f"QCheckBox {{ color:{T.SEV_COLOR[s]}; font-weight:600; }}")
            cb.toggled.connect(self._update)
            v2.addWidget(cb)
            self.sv[s] = cb
        self.overdue = QCheckBox(tr('Hanya yang lewat target'))
        self.overdue.toggled.connect(self._update)
        v2.addSpacing(6)
        v2.addWidget(self.overdue)
        v2.addStretch()
        # panel / bay
        gb3 = QGroupBox(tr('Panel / Bay'))
        v3 = QVBoxLayout(gb3)
        pitems = []
        n_umum = sum(1 for r in self.rows if not r["panel_id"])
        if n_umum:
            pitems.append((tr('(Umum — tanpa panel)  · {0} punch', n_umum), UMUM))
        for p in self.db.panels(self.pid, main.site_id):
            n = sum(1 for r in self.rows if r["panel_id"] == p["id"])
            site = f"{p['site_name']} · " if not main.site_id else ""
            pitems.append((tr('{0}  —  {1}Bay {2}  · {3} punch', p['tag'], site, p['bay'] or '-', n), p["id"]))
        pre_p = preset.get("panels")
        self.pl = _check_list(pitems)
        if pre_p is not None:
            _set_all(self.pl, False, only=set(pre_p))
        self.pl.itemChanged.connect(self._update)
        v3.addWidget(self.pl, 1)
        hb = QHBoxLayout()
        hb.addWidget(btn(tr('Semua'), None, "ghost", None, lambda: _set_all(self.pl, True)))
        hb.addWidget(btn(tr('Kosongkan'), None, "ghost", None, lambda: _set_all(self.pl, False)))
        hb.addStretch()
        hb.addWidget(QLabel(tr('Bay:')))
        self.bay = QComboBox()
        self.bay.addItem(tr('pilih bay…'), None)
        for b in sorted({p["bay"] for p in self.db.panels(self.pid, main.site_id) if p["bay"]}):
            self.bay.addItem(b, b)
        self.bay.currentIndexChanged.connect(self._pick_bay)
        hb.addWidget(self.bay)
        v3.addLayout(hb)
        # kategori temuan
        gb4 = QGroupBox(tr('Kategori temuan'))
        v4 = QVBoxLayout(gb4)
        cats = sorted({r["category"] or "(tanpa kategori)" for r in self.rows})
        self.cl = _check_list([(f"{tr(c)}  ({sum(1 for r in self.rows if (r['category'] or '(tanpa kategori)') == c)})", c)
                               for c in cats])
        self.cl.itemChanged.connect(self._update)
        v4.addWidget(self.cl, 1)
        hb2 = QHBoxLayout()
        hb2.addWidget(btn(tr('Semua'), None, "ghost", None, lambda: _set_all(self.cl, True)))
        hb2.addWidget(btn(tr('Kosongkan'), None, "ghost", None, lambda: _set_all(self.cl, False)))
        hb2.addStretch()
        v4.addLayout(hb2)

        g.addWidget(gb1, 0, 0)
        g.addWidget(gb2, 1, 0)
        g.addWidget(gb3, 0, 1, 2, 1)
        g.addWidget(gb4, 0, 2, 2, 1)
        g.setColumnStretch(1, 3)
        g.setColumnStretch(2, 2)
        lay.addLayout(g, 1)

        # opsi
        gb5 = QGroupBox(tr('Tampilan report'))
        o = QGridLayout(gb5)
        self.pic = QComboBox()
        self.pic.addItem(tr('Semua PIC'), None)
        for p in sorted({r["pic"] for r in self.rows if r["pic"]}):
            self.pic.addItem(p, p)
        self.pic.currentIndexChanged.connect(self._update)
        self.sort = QComboBox()
        for text, key in ((tr('Kode punch'), "code"), (tr('Status (Open dulu)'), "status"), (tr('Kategori A/B/C'), "severity"),
                          (tr('Panel'), "panel")):
            self.sort.addItem(text, key)
        self.group = QCheckBox(tr('Kelompokkan per panel (dengan subtotal)'))
        self.group.setChecked(preset.get("group", False))
        self.photos = QCheckBox(tr('Sertakan lampiran foto'))
        self.photos.setChecked(preset.get("photos", True))
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr('otomatis dari filter'))
        self._auto_title = True
        self.title.textEdited.connect(lambda *_: setattr(self, "_auto_title", False))
        o.addWidget(QLabel("PIC"), 0, 0)
        o.addWidget(self.pic, 0, 1)
        o.addWidget(QLabel(tr('Urutkan')), 0, 2)
        o.addWidget(self.sort, 0, 3)
        o.addWidget(self.group, 0, 4)
        o.addWidget(self.photos, 0, 5)
        o.addWidget(QLabel(tr('Judul report')), 1, 0)
        o.addWidget(self.title, 1, 1, 1, 3)
        from ..i18n import LANGS
        self.rlang = QComboBox()
        for code, name in LANGS.items():
            self.rlang.addItem(name, code)
        self.rlang.setCurrentIndex(max(0, self.rlang.findData(main.report_lang())))
        self.rlang.currentIndexChanged.connect(self._update)
        o.addWidget(QLabel(tr('Bahasa report PDF')), 1, 4)
        o.addWidget(self.rlang, 1, 5)
        o.setColumnStretch(1, 1)
        o.setColumnStretch(3, 1)
        lay.addWidget(gb5)

        foot = QHBoxLayout()
        self.count = QLabel()
        self.count.setTextFormat(Qt.RichText)
        foot.addWidget(self.count, 1)
        foot.addWidget(btn(tr('Batal'), None, None, None, self.reject))
        self.ok = btn(tr('Buat PDF'), "printer", "primary", None, self.accept)
        foot.addWidget(self.ok)
        lay.addLayout(foot)
        if preset.get("search"):
            self._search = preset["search"].lower()
        else:
            self._search = ""
        self._update()

    # ------------------------------------------------------------ presets
    def _set_status(self, sts):
        for s, cb in self.st.items():
            cb.setChecked(s in sts)

    def _p_all(self):
        self._set_status(ISSUE_STATUSES)
        for cb in self.sv.values():
            cb.setChecked(True)
        self.overdue.setChecked(False)
        _set_all(self.pl, True)
        _set_all(self.cl, True)
        self.pic.setCurrentIndex(0)

    def _p_active(self):
        self._set_status(["Open", "In Progress", "Ready to Verify"])

    def _p_open(self):
        self._set_status(["Open"])

    def _p_closed(self):
        self._set_status(["Closed"])

    def _p_crit(self):
        self._set_status(["Open", "In Progress", "Ready to Verify"])
        for s, cb in self.sv.items():
            cb.setChecked(s == "Critical")

    def _pick_bay(self):
        bay = self.bay.currentData()
        if bay:
            ids = {p["id"] for p in self.db.panels(self.pid, self.main.site_id) if p["bay"] == bay}
            _set_all(self.pl, False, only=ids)
            self.bay.blockSignals(True)
            self.bay.setCurrentIndex(0)
            self.bay.blockSignals(False)

    # ------------------------------------------------------------ filter
    def selection(self):
        sts = {s for s, cb in self.st.items() if cb.isChecked()}
        svs = {s for s, cb in self.sv.items() if cb.isChecked()}
        pans = set(_checked(self.pl))
        cats = set(_checked(self.cl))
        pic = self.pic.currentData()
        t = today()
        out = []
        for r in self.rows:
            if r["status"] not in sts or r["severity"] not in svs:
                continue
            if (r["panel_id"] or UMUM) not in pans:
                continue
            if (r["category"] or "(tanpa kategori)") not in cats:
                continue
            if pic and r["pic"] != pic:
                continue
            if self.overdue.isChecked() and not (r["status"] != "Closed" and r["due_date"] and r["due_date"] < t):
                continue
            if self._search and self._search not in " ".join(
                    str(r[k] or "") for k in ("code", "title", "description", "panel_tag", "pic", "category")).lower():
                continue
            out.append(r)
        return out

    def describe(self):
        parts = []
        sts = [s for s, cb in self.st.items() if cb.isChecked()]
        if len(sts) < len(ISSUE_STATUSES):
            parts.append(tr('Status: ') + ", ".join(T.STATUS_LABEL[s] for s in sts))
        svs = [s for s, cb in self.sv.items() if cb.isChecked()]
        if len(svs) < len(SEVERITIES):
            parts.append(tr('Kategori ') + "/".join(SEV_LABEL[s].split(" · ")[0] for s in svs))
        pans = _checked(self.pl)
        if len(pans) < self.pl.count():
            names = []
            for pid in pans:
                if pid == UMUM:
                    names.append("Umum")
                else:
                    p = self.db.panel(pid)
                    names.append(p["tag"] if p else "?")
            parts.append(tr('Panel: ') + (", ".join(names) if len(names) <= 6 else tr('{0} panel', len(names))))
        cats = _checked(self.cl)
        if len(cats) < self.cl.count():
            parts.append(tr('Temuan: ') + (", ".join(tr(c) for c in cats) if len(cats) <= 3 else tr('{0} kategori', len(cats))))
        if self.pic.currentData():
            parts.append(tr('PIC: {0}', self.pic.currentText()))
        if self.overdue.isChecked():
            parts.append(tr('Lewat target'))
        if self._search:
            parts.append(tr('Cari: "{0}"', self._search))
        return " · ".join(parts) if parts else tr('Semua punch')

    def auto_title(self):
        sts = [s for s, cb in self.st.items() if cb.isChecked()]
        t = tr('Punch List')
        if sts == ["Open"]:
            t += tr(' — OPEN')
        elif sts == ["Closed"]:
            t += tr(' — CLOSED')
        elif set(sts) == {"Open", "In Progress", "Ready to Verify"}:
            t += tr(' — Belum Close')
        pans = _checked(self.pl)
        if 0 < len(pans) < self.pl.count() and len(pans) <= 3:
            names = []
            for pid in pans:
                p = self.db.panel(pid) if pid != UMUM else None
                names.append(p["tag"] if p else "Umum")
            t += " — " + ", ".join(names)
        return t

    def _update(self, *_):
        sel = self.selection()
        n_open = sum(1 for r in sel if r["status"] == "Open")
        n_prog = sum(1 for r in sel if r["status"] in ("In Progress", "Ready to Verify"))
        n_cl = sum(1 for r in sel if r["status"] == "Closed")
        self.count.setText(tr("<b style='font-size:11pt'>{0}</b> punch akan dicetak &nbsp; ", len(sel)) +
                           f"<span style='color:{T.STATUS_COLOR['Open']}'>● {n_open} open</span> &nbsp; "
                           f"<span style='color:{T.STATUS_COLOR['In Progress']}'>● {n_prog} in progress</span> &nbsp; "
                           f"<span style='color:{T.STATUS_COLOR['Closed']}'>● {n_cl} closed</span>"
                           f"<br><span style='color:{T.MUTED}'>{self.describe()}</span>")
        self.ok.setEnabled(bool(sel))
        if self._auto_title:
            self.title.setText(self.auto_title())

    def accept(self):
        if not self.selection():
            warn(self, tr('Tidak ada punch yang sesuai filter.'))
            return
        super().accept()

    def options(self):
        from ..i18n import using
        with using(self.rlang.currentData()):
            auto, desc = self.auto_title(), self.describe()
        title = auto if self._auto_title else (self.title.text().strip() or auto)
        return dict(issue_ids=[r["id"] for r in self.selection()], with_photos=self.photos.isChecked(),
                    title=title, filter_text=desc, group_by_panel=self.group.isChecked(),
                    sort=self.sort.currentData(), lang=self.rlang.currentData())


# ukuran roll label thermal yang umum (lebar × tinggi mm)
LABEL_PRESETS = [(40, 30), (50, 30), (50, 40), (60, 40), (70, 50), (80, 50), (100, 50), (100, 70), (100, 100)]


class QrLabelDialog(QDialog):
    """Pilih cara cetak label QR: printer label (1 label per halaman, seukuran label) atau A4 24 label.

    Pilihan disimpan per laptop (printer bisa berbeda tiap laptop)."""

    def __init__(self, main, count):
        super().__init__(main)
        from PySide6.QtWidgets import QButtonGroup, QDoubleSpinBox, QFormLayout, QRadioButton
        self.qs = getattr(main, "settings", None)
        g = (lambda k, d: self.qs.value(k, d)) if self.qs is not None else (lambda k, d: d)
        self.setWindowTitle(tr('Cetak Label QR'))
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr('{0} panel akan dicetak.', count), bold=True))

        self.rb_roll = QRadioButton(tr('Printer label (1 label per halaman, mis. Xprinter)'))
        self.rb_a4 = QRadioButton(tr('Kertas A4 (24 label per halaman)'))
        grp = QButtonGroup(self)
        grp.addButton(self.rb_roll)
        grp.addButton(self.rb_a4)
        lay.addWidget(self.rb_roll)

        self.box = QGroupBox(tr('Ukuran label'))
        f = QFormLayout(self.box)
        self.preset = QComboBox()
        for w, h in LABEL_PRESETS:
            self.preset.addItem(f"{w} × {h} mm", (w, h))
        self.preset.addItem(tr('Ukuran lain…'), None)
        self.w = QDoubleSpinBox()
        self.h = QDoubleSpinBox()
        self.margin = QDoubleSpinBox()
        for sp, lo, hi in ((self.w, 20, 110), (self.h, 15, 200), (self.margin, 0, 6)):
            sp.setRange(lo, hi)
            sp.setDecimals(1)
            sp.setSingleStep(1 if sp is not self.margin else 0.5)
            sp.setSuffix(" mm")
        self.w.setValue(float(g("label/w", 50)))
        self.h.setValue(float(g("label/h", 30)))
        self.margin.setValue(float(g("label/margin", 2)))
        wh = QHBoxLayout()
        wh.addWidget(self.w)
        wh.addWidget(QLabel("×"))
        wh.addWidget(self.h)
        f.addRow(tr('Preset'), self.preset)
        f.addRow(tr('Lebar × tinggi'), wh)
        f.addRow(tr('Margin aman'), self.margin)
        hint = QLabel(tr('Di driver printer (Printing Preferences), pilih ukuran kertas yang sama dengan label ini. '
                         'Saat mencetak PDF, pilih skala 100% / Actual size (jangan "Fit").'))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{T.MUTED};")
        f.addRow(hint)
        lay.addWidget(self.box)
        lay.addWidget(self.rb_a4)

        self._sync_preset()
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.w.valueChanged.connect(self._sync_preset)
        self.h.valueChanged.connect(self._sync_preset)
        (self.rb_a4 if g("label/mode", "roll") == "a4" else self.rb_roll).setChecked(True)
        self.rb_roll.toggled.connect(lambda on: self.box.setEnabled(on))
        self.box.setEnabled(self.rb_roll.isChecked())

        from .dialogs import _buttons
        lay.addWidget(_buttons(self, tr('Buat PDF'), data=False))

    def _preset_changed(self):
        v = self.preset.currentData()
        if v:
            self.w.blockSignals(True)
            self.h.blockSignals(True)
            self.w.setValue(v[0])
            self.h.setValue(v[1])
            self.w.blockSignals(False)
            self.h.blockSignals(False)

    def _sync_preset(self):
        cur = (round(self.w.value(), 1), round(self.h.value(), 1))
        idx = next((i for i, v in enumerate(LABEL_PRESETS) if (float(v[0]), float(v[1])) == cur), len(LABEL_PRESETS))
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(idx)
        self.preset.blockSignals(False)

    def result_options(self):
        return {"mode": "roll" if self.rb_roll.isChecked() else "a4",
                "w": self.w.value(), "h": self.h.value(), "margin": self.margin.value()}

    def accept(self):
        o = self.result_options()
        if o["mode"] == "roll" and min(o["w"], o["h"]) - 2 * o["margin"] < 12:
            warn(self, tr('Label terlalu kecil untuk QR yang bisa di-scan. Perkecil margin atau pilih label lebih besar.'))
            return
        if self.qs is not None:
            self.qs.setValue("label/mode", o["mode"])
            self.qs.setValue("label/w", o["w"])
            self.qs.setValue("label/h", o["h"])
            self.qs.setValue("label/margin", o["margin"])
        super().accept()


class CheckSheetDialog(QDialog):
    """Cetak check sheet (lembar uji) untuk panel mana saja.

    - Panel: cari tag/nama, saring tipe, bay & status panel; centang panel yang dicetak.
    - Isi: pilih seksi (mis. hanya 'SAS'), dan item: semua / belum dicek / NG.
    - Opsi: form kosong untuk diisi manual di lapangan, punch list panel, kolom tanda tangan."""

    ITEM_MODES = (("all", 'Semua item'), ("pending", 'Belum dicek saja'), ("ng", 'NG saja'),
                  ("pending_ng", 'Belum dicek + NG'))

    def __init__(self, main, preset_panels=None, preset_status=None):
        super().__init__(main)
        from PySide6.QtWidgets import QButtonGroup, QRadioButton
        self.main = main
        self.db = main.db
        self.pid = main.project_id
        self.setWindowTitle(tr('Cetak Check Sheet'))
        self.resize(980, 660)
        self.ov = self.db.panel_overview(self.pid, main.site_id)
        self.checks = {o["panel"]["id"]: self.db.panel_checks(o["panel"]["id"]) for o in self.ov}
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label(tr('Cetak Check Sheet'), 14, True))
        head.addStretch()
        head.addWidget(QLabel(tr('Cepat:')))
        for text, fn in ((tr('Semua panel'), self._q_all), (tr('Belum selesai'), self._q_open),
                         (tr('Ada temuan'), self._q_ng), (tr('Hanya seksi SAS'), self._q_sas)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            head.addWidget(b)
        lay.addLayout(head)

        g = QGridLayout()
        g.setSpacing(10)
        # ---------------------------------------------------------------- panel
        gb1 = QGroupBox(tr('Panel'))
        v1 = QVBoxLayout(gb1)
        fr = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText(tr('Cari tag / nama / bay…'))
        self.q.setMinimumWidth(200)
        self.q.textChanged.connect(self._refilter)
        fr.addWidget(self.q, 3)
        self.ptype = QComboBox()
        self.ptype.addItem(tr('Semua tipe'), None)
        for t_ in sorted({o["panel"]["panel_type"] for o in self.ov if o["panel"]["panel_type"]}):
            self.ptype.addItem(t_, t_)
        self.ptype.currentIndexChanged.connect(self._refilter)
        self.ptype.setMaximumWidth(190)
        fr.addWidget(self.ptype, 1)
        self.bay = QComboBox()
        self.bay.addItem(tr('Semua bay'), None)
        for b_ in sorted({" ".join((o["panel"]["bay"] or "").split()) for o in self.ov if o["panel"]["bay"]}):
            self.bay.addItem(b_, b_)
        self.bay.currentIndexChanged.connect(self._refilter)
        self.bay.setMaximumWidth(190)
        fr.addWidget(self.bay, 1)
        self.pstat = QComboBox()
        self.pstat.addItem(tr('Semua status'), None)
        for s_ in PANEL_STATUSES:
            n = sum(1 for o in self.ov if o["status"] == s_)
            if n:
                self.pstat.addItem(f"{tr(s_)} ({n})", s_)
        self.pstat.currentIndexChanged.connect(self._refilter)
        self.pstat.setMaximumWidth(190)
        fr.addWidget(self.pstat, 1)
        v1.addLayout(fr)
        items = []
        for o in self.ov:
            p, st = o["panel"], o["stats"]
            site = f"{p['site_name']} · " if not main.site_id else ""
            items.append((tr('{0}  —  {1}{2} · {3}/{4} diuji ({5:.0f}%) · {6}', " ".join(p['tag'].split()), site,
                             " ".join((p['bay'] or p['panel_type'] or '-').split())[:40], st['checked'], st['total'],
                             st['pct'], tr(o['status'])), p["id"]))
        self.pl = _check_list(items)
        if preset_panels is not None:
            _set_all(self.pl, False, only=set(preset_panels))
        elif preset_status is not None:
            ids = {o["panel"]["id"] for o in self.ov if o["status"] in preset_status}
            _set_all(self.pl, False, only=ids)
        self.pl.itemChanged.connect(self._update)
        v1.addWidget(self.pl, 1)
        hb = QHBoxLayout()
        hb.addWidget(btn(tr('Centang yang tampil'), None, "ghost", None, lambda: self._mark_visible(True)))
        hb.addWidget(btn(tr('Kosongkan yang tampil'), None, "ghost", None, lambda: self._mark_visible(False)))
        hb.addStretch()
        v1.addLayout(hb)
        # ---------------------------------------------------------------- isi
        gb2 = QGroupBox(tr('Isi checklist'))
        v2 = QVBoxLayout(gb2)
        secs = []
        for o in self.ov:
            for c in self.checks[o["panel"]["id"]]:
                if c["section"] not in secs:
                    secs.append(c["section"])
        self.all_secs = sorted(secs, key=lambda x: (" SAS · " in x, x))
        self.sl = _check_list([(s_ or tr('(tanpa seksi)'), s_) for s_ in self.all_secs])
        self.sl.itemChanged.connect(self._update)
        v2.addWidget(QLabel(tr('Seksi:')))
        v2.addWidget(self.sl, 1)
        hb2 = QHBoxLayout()
        hb2.addWidget(btn(tr('Semua'), None, "ghost", None, lambda: _set_all(self.sl, True)))
        hb2.addWidget(btn(tr('Hanya SAS'), None, "ghost", None, self._only_sas))
        hb2.addWidget(btn(tr('Tanpa SAS'), None, "ghost", None, self._no_sas))
        hb2.addStretch()
        v2.addLayout(hb2)
        v2.addWidget(QLabel(tr('Item:')))
        self.mode = QButtonGroup(self)
        mr = QGridLayout()
        for k, (key, text) in enumerate(self.ITEM_MODES):
            rb = QRadioButton(tr(text))
            rb.setProperty("mode", key)
            rb.setChecked(key == "all")
            rb.toggled.connect(self._update)
            self.mode.addButton(rb)
            mr.addWidget(rb, k // 2, k % 2)
        v2.addLayout(mr)
        g.addWidget(gb1, 0, 0)
        g.addWidget(gb2, 0, 1)
        g.setColumnStretch(0, 3)
        g.setColumnStretch(1, 2)
        lay.addLayout(g, 1)
        # ---------------------------------------------------------------- opsi
        gb3 = QGroupBox(tr('Opsi cetak'))
        o3 = QGridLayout(gb3)
        self.blank = QCheckBox(tr('Form kosong (diisi manual di lapangan)'))
        self.blank.toggled.connect(self._update)
        self.punch = QCheckBox(tr('Sertakan punch list panel'))
        self.punch.setChecked(True)
        self.sign = QCheckBox(tr('Sertakan kolom tanda tangan'))
        self.sign.setChecked(True)
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr('Lembar Uji Panel'))
        from ..i18n import LANGS
        self.rlang = QComboBox()
        for code, name in LANGS.items():
            self.rlang.addItem(name, code)
        self.rlang.setCurrentIndex(max(0, self.rlang.findData(main.report_lang())))
        o3.addWidget(self.blank, 0, 0)
        o3.addWidget(self.punch, 0, 1)
        o3.addWidget(self.sign, 0, 2)
        o3.addWidget(QLabel(tr('Judul report')), 1, 0)
        o3.addWidget(self.title, 1, 1)
        o3.addWidget(QLabel(tr('Bahasa report PDF')), 1, 2)
        o3.addWidget(self.rlang, 1, 3)
        o3.setColumnStretch(1, 1)
        lay.addWidget(gb3)
        foot = QHBoxLayout()
        self.count = QLabel()
        self.count.setTextFormat(Qt.RichText)
        foot.addWidget(self.count, 1)
        foot.addWidget(btn(tr('Batal'), None, None, None, self.reject))
        self.ok = btn(tr('Buat PDF'), "printer", "primary", None, self.accept)
        foot.addWidget(self.ok)
        lay.addLayout(foot)
        self._refilter()

    # ------------------------------------------------------------ panel filter
    def _visible(self, o):
        p = o["panel"]
        q = self.q.text().strip().lower()
        hay = " ".join(" ".join(str(p[k] or "").split()) for k in ("tag", "name", "bay", "site_name")).lower()
        if q and q not in hay:
            return False
        if self.ptype.currentData() and p["panel_type"] != self.ptype.currentData():
            return False
        if self.bay.currentData() and " ".join((p["bay"] or "").split()) != self.bay.currentData():
            return False
        if self.pstat.currentData() and o["status"] != self.pstat.currentData():
            return False
        return True

    def _refilter(self):
        vis = {o["panel"]["id"]: self._visible(o) for o in self.ov}
        for i in range(self.pl.count()):
            it = self.pl.item(i)
            it.setHidden(not vis.get(it.data(Qt.UserRole), False))
        self._update()

    def _mark_visible(self, on):
        self.pl.blockSignals(True)
        for i in range(self.pl.count()):
            it = self.pl.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.pl.blockSignals(False)
        self._update()

    def _reset_filters(self):
        for w in (self.ptype, self.bay, self.pstat):
            w.blockSignals(True)
            w.setCurrentIndex(0)
            w.blockSignals(False)
        self.q.blockSignals(True)
        self.q.clear()
        self.q.blockSignals(False)
        self._refilter()

    # ------------------------------------------------------------ cepat
    def _q_all(self):
        self._reset_filters()
        _set_all(self.pl, True)
        _set_all(self.sl, True)

    def _q_open(self):
        self._reset_filters()
        ids = {o["panel"]["id"] for o in self.ov if o["status"] in ("Belum dicek", "Sedang dicek", "Ada temuan")}
        _set_all(self.pl, False, only=ids)

    def _q_ng(self):
        self._reset_filters()
        ids = {o["panel"]["id"] for o in self.ov if o["status"] == "Ada temuan"}
        _set_all(self.pl, False, only=ids)

    def _q_sas(self):
        self._only_sas()

    def _only_sas(self):
        _set_all(self.sl, False, only={s_ for s_ in self.all_secs if " SAS · " in (s_ or "")})

    def _no_sas(self):
        _set_all(self.sl, False, only={s_ for s_ in self.all_secs if " SAS · " not in (s_ or "")})

    # ------------------------------------------------------------ hasil
    def _mode(self):
        b = self.mode.checkedButton()
        return b.property("mode") if b else "all"

    def panel_ids(self):
        chosen = set(_checked(self.pl))
        hidden = {self.pl.item(i).data(Qt.UserRole) for i in range(self.pl.count()) if self.pl.item(i).isHidden()}
        return [o["panel"]["id"] for o in self.ov if o["panel"]["id"] in chosen and o["panel"]["id"] not in hidden]

    def sections(self):
        sel = set(_checked(self.sl))
        return None if len(sel) == len(self.all_secs) else sel

    def _note(self):
        parts = []
        secs = self.sections()
        if secs is not None:
            sas = {s_ for s_ in self.all_secs if " SAS · " in (s_ or "")}
            if secs and secs == sas:
                parts.append(tr('Seksi: integrasi SAS'))
            elif secs and not (secs & sas) and secs == set(self.all_secs) - sas:
                parts.append(tr('Seksi: tanpa SAS'))
            else:
                parts.append(tr('Seksi: {0} dari {1}', len(secs), len(self.all_secs)))
        m = self._mode()
        if m != "all":
            parts.append(tr('Item: {0}', tr(dict(self.ITEM_MODES)[m]).lower()))
        if self.blank.isChecked():
            parts.append(tr('Form kosong'))
        return " · ".join(parts)

    def _update(self, *_):
        from ..reports import ReportBuilder
        ids = self.panel_ids()
        secs, mode = self.sections(), self._mode()
        n_items = n_pan = 0
        for pid_ in ids:
            k = len(ReportBuilder.check_item_filter(self.checks.get(pid_, []), secs, mode))
            if k or (secs is None and mode == "all"):
                n_pan += 1
                n_items += k
        skipped = len(ids) - n_pan
        txt = tr('<b>{0}</b> panel · <b>{1}</b> item akan dicetak', n_pan, n_items)
        if skipped:
            txt += tr(" <span style='color:#586064'>({0} panel dilewati: tidak ada item yang cocok)</span>", skipped)
        self.count.setText(txt)
        self.ok.setEnabled(n_pan > 0)
        self.punch.setEnabled(not self.blank.isChecked())

    def options(self):
        return {"panel_ids": self.panel_ids(), "sections": self.sections(), "items": self._mode(),
                "blank": self.blank.isChecked(), "with_punch": self.punch.isChecked() and not self.blank.isChecked(),
                "with_sign": self.sign.isChecked(), "title": self.title.text().strip() or None,
                "note": self._note(), "lang": self.rlang.currentData()}
