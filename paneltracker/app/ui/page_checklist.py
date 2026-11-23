"""Halaman Checking Panel: daftar panel (kiri) + checklist uji fungsi (kanan)."""
from __future__ import annotations

from ..i18n import tr

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QToolButton, QVBoxLayout, QWidget, QButtonGroup,
)

from ..db import PANEL_STATUSES, fmt_date
from .. import sas_matrix as SM
from . import theme as T
from . import widgets as W
from .dialogs import IssueDialog, PanelDialog
from .widgets import (
    Card, PanelCardDelegate, Pill, ResultButtons, Ring, SegmentBar, ask, btn, info, label, warn,
)


# ---------------------------------------------------------------- item edit
class CheckItemDialog(QDialog):
    def __init__(self, parent, sections, row=None, section=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Edit item cek') if row else tr('Tambah item cek'))
        self.setMinimumWidth(520)
        f = QFormLayout(self)
        self.sec = QComboBox()
        self.sec.setEditable(True)
        self.sec.addItems(sections)
        self.sec.setCurrentText(row["section"] if row else (section or (sections[0] if sections else "Lainnya")))
        self.desc = QLineEdit(row["description"] if row else "")
        self.crit = QLineEdit(row["criteria"] if row else "")
        self.unit = QLineEdit(row["unit"] if row else "")
        self.unit.setPlaceholderText(tr('kosongkan jika cukup OK/NG (contoh: VDC, MΩ, ms)'))
        f.addRow(tr('Section'), self.sec)
        f.addRow(tr('Item pengecekan *'), self.desc)
        f.addRow(tr('Kriteria terima'), self.crit)
        f.addRow(tr('Satuan nilai ukur'), self.unit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def accept(self):
        if not self.desc.text().strip():
            warn(self, tr('Item pengecekan wajib diisi.'))
            return
        super().accept()

    def values(self):
        return dict(section=self.sec.currentText().strip() or "Lainnya", description=self.desc.text().strip(),
                    criteria=self.crit.text().strip(), unit=self.unit.text().strip())


# ---------------------------------------------------------------- one row
class CheckRow(QFrame):
    def __init__(self, view, row, no, punches):
        super().__init__()
        self.view = view
        self.cid = row["id"]
        self.row = row
        self.setObjectName("checkRow")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 8, 10, 4)
        h.setSpacing(10)
        n = QLabel(str(no))
        n.setFixedWidth(24)
        n.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt; font-weight:600;")
        h.addWidget(n, 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(1)
        d = QLabel(row["description"])
        d.setWordWrap(True)
        d.setMinimumWidth(90)
        d.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        d.setStyleSheet("font-weight:600;")
        v.addWidget(d)
        meta = []
        if row["criteria"]:
            meta.append(tr('Kriteria: {0}', row['criteria']) + (f" {row['unit']}" if row["unit"] else ""))
        if row["checked_by"]:
            meta.append(f"✓ {row['checked_by']} · {fmt_date(row['checked_at'])}")
        self.meta = QLabel("   ·   ".join(meta))
        self.meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.meta.setStyleSheet(f"color:{T.MUTED}; font-size:8pt;")
        v.addWidget(self.meta)
        self.remark = QLineEdit(row["remark"] or "")
        self.remark.setObjectName("inline")
        self.remark.setPlaceholderText(tr('＋ catatan…'))
        self.remark.setStyleSheet(f"font-size:8.5pt; color:{T.TEXT};")
        self.remark.editingFinished.connect(self._save_remark)
        v.addWidget(self.remark)
        h.addLayout(v, 1)

        self.value = QLineEdit(row["value"] or "")
        self.value.setObjectName("inline")
        self.value.setPlaceholderText(tr('nilai {0}', row['unit']) if row["unit"] else tr("nilai"))
        self.value.setFixedWidth(110 if row["unit"] == "rasio" else 72)   # rasio CT/VT: "2000/1 A"
        self.value.setToolTip(tr('Nilai hasil ukur') + (f" ({row['unit']})" if row["unit"] else ""))
        self.value.setStyleSheet("QLineEdit#inline { border:1px solid #C9CEC9; background:white; }" if row["unit"]
                                 else "")
        self.value.editingFinished.connect(self._save_value)
        h.addWidget(self.value, 0, Qt.AlignTop)

        self.res = ResultButtons(row["result"])
        self.res.changed.connect(self._result)
        if W.RO:
            self.value.setReadOnly(True)
            self.remark.setReadOnly(True)
            self.remark.setPlaceholderText("")
        h.addWidget(self.res, 0, Qt.AlignTop)

        self.pbtn = QToolButton()
        self.pbtn.setFixedWidth(50)
        self.pbtn.setCursor(Qt.PointingHandCursor)
        self.pbtn.setAutoRaise(True)
        self.pbtn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.pbtn.clicked.connect(self._punch)
        h.addWidget(self.pbtn, 0, Qt.AlignTop)
        more = QToolButton()
        more.setIcon(T.icon("more", T.MUTED, 18))
        more.setAutoRaise(True)
        more.setCursor(Qt.PointingHandCursor)
        m = QMenu(more)
        m.addAction(T.icon("edit"), tr('Edit item…'), self._edit)
        m.addAction(T.icon("plus"), tr('Tambah item di section ini…'), lambda: self.view.add_item(self.row["section"]))
        m.addSeparator()
        m.addAction(T.icon("trash", T.NG), tr('Hapus item'), self._delete)
        more.setMenu(m)
        more.setPopupMode(QToolButton.InstantPopup)
        more.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        h.addWidget(more, 0, Qt.AlignTop)
        more.setVisible(not W.RO)
        self.set_punches(punches)
        self._style()

    def set_punches(self, punches):
        self.punches = punches
        open_n = sum(1 for p in punches if p["status"] != "Closed")
        if punches:
            col = T.NG if open_n else T.OK
            self.pbtn.setIcon(T.icon("punch", col, 16))
            self.pbtn.setText(f"{open_n}/{len(punches)}" if open_n else f"✓{len(punches)}")
            self.pbtn.setStyleSheet(f"QToolButton {{ color:{col}; font-weight:700; }}")
            self.pbtn.setToolTip("\n".join(f"{p['code']} [{T.STATUS_LABEL.get(p['status'], p['status'])}] {p['title']}" for p in punches)
                                 + tr('\n\nKlik untuk buka / tambah punch'))
        else:
            self.pbtn.setIcon(T.icon("punch", T.SUBTLE, 16))
            self.pbtn.setText("")
            self.pbtn.setStyleSheet("")
            self.pbtn.setToolTip(tr('Buat punch dari item ini'))

    def _style(self):
        r = self.res.value
        bg = {"NG": "#FDF0EF", "OK": "#FFFFFF", "NA": "#F6F7F5"}.get(r, "#FFFFFF")
        bar = T.RESULT_COLOR.get(r, "transparent")
        self.setStyleSheet(f"QFrame#checkRow {{ background:{bg}; border:none; border-left:3px solid {bar};"
                           f" border-bottom:1px solid #E3E6E3; }}")

    def _result(self, value):
        self.apply_result(value, auto_punch=True)

    def apply_result(self, value, auto_punch=False):
        """Simpan hasil (dipakai tombol OK/NG/N/A di baris ini dan sel matriks SAS)."""
        db = self.view.main.db
        db.set_check(self.cid, result=value)
        if self.res.value != value:
            self.res.blockSignals(True)
            self.res.set_value(value)
            self.res.blockSignals(False)
        self.row = db.check(self.cid)
        self.meta.setText("   ·   ".join(x for x in [
            (tr('Kriteria: {0}', self.row['criteria']) + (f" {self.row['unit']}" if self.row["unit"] else ""))
            if self.row["criteria"] else "",
            f"✓ {self.row['checked_by']} · {fmt_date(self.row['checked_at'])}" if self.row["checked_by"] else ""] if x))
        self._style()
        self.view.stats_changed()
        if auto_punch and value == "NG" and not any(p["status"] != "Closed" for p in self.punches):
            QTimer.singleShot(50, lambda: self._punch(auto=True))

    def apply_value(self, text):
        text = (text or "").strip()
        if text != (self.row["value"] or ""):
            self.view.main.db.set_check(self.cid, value=text)
            self.row = self.view.main.db.check(self.cid)
        if self.value.text() != text:
            self.value.setText(text)

    def _save_value(self):
        if self.value.text() != (self.row["value"] or ""):
            self.view.main.db.set_check(self.cid, value=self.value.text().strip())
            self.row = self.view.main.db.check(self.cid)

    def _save_remark(self):
        if self.remark.text() != (self.row["remark"] or ""):
            self.view.main.db.set_check(self.cid, remark=self.remark.text().strip())
            self.row = self.view.main.db.check(self.cid)

    def _punch(self, auto=False):
        main = self.view.main
        if W.RO and not self.punches:
            return
        if self.punches and not auto:
            m = QMenu(self)
            for p in self.punches:
                m.addAction(f"{p['code']}  [{T.STATUS_LABEL.get(p['status'], p['status'])}]  {p['title'][:50]}"
                            .replace("&", "&&"), lambda iid=p["id"]: self._open(iid))
            if not W.RO:
                m.addSeparator()
                m.addAction(T.icon("plus"), tr('Punch baru dari item ini…'), lambda: self._new())
            m.exec(self.pbtn.mapToGlobal(self.pbtn.rect().bottomLeft()))
        else:
            self._new()

    def _new(self):
        main = self.view.main
        r = self.row
        desc = tr('Item cek: {0} — {1}.', r['section'], r['description'])
        if r["criteria"]:
            desc += tr('\nKriteria: {0} {1}', r['criteria'], r['unit'] or '').rstrip()
        if r["value"]:
            desc += tr('\nHasil ukur: {0} {1}', r['value'], r['unit'] or '').rstrip()
        if r["remark"]:
            desc += tr('\nCatatan: {0}', r['remark'])
        cat = guess_category(r["section"], r["description"], main.db.get_list_setting("categories"))
        d = IssueDialog(self, main.db, main.project_id, panel_id=self.view.panel_id, check_id=self.cid,
                        preset={"title": r["description"] if not r["remark"] else r["remark"],
                                "description": desc, "category": cat, "severity": "Major"})
        if d.exec():
            self.view.reload_punches()
            main.refresh_all(except_page=self.view.page)

    def _open(self, iid):
        main = self.view.main
        if IssueDialog(self, main.db, main.project_id, iid).exec():
            self.view.reload_punches()
            main.refresh_all(except_page=self.view.page)

    def _edit(self):
        d = CheckItemDialog(self, self.view.sections(), self.row)
        if d.exec():
            self.view.main.db.update_check_item(self.cid, **d.values())
            self.view.load(self.view.panel_id)

    def _delete(self):
        if ask(self, tr("Hapus item '{0}' dari checklist panel ini?", self.row['description'])):
            self.view.main.db.delete_check_item(self.cid)
            self.view.load(self.view.panel_id)
            self.view.stats_changed()


def guess_category(section, desc, cats):
    s = (section + " " + desc).lower()
    rules = [("wiring", "Wiring"), ("terminal", "Wiring"), ("ferrule", "Dokumen"), ("label", "Dokumen"),
             ("goose", "Komunikasi / IEC 61850"), ("61850", "Komunikasi / IEC 61850"), ("ping", "Komunikasi / IEC 61850"),
             ("sync", "Komunikasi / IEC 61850"), ("jaringan", "Komunikasi / IEC 61850"), ("scada", "SCADA / HMI"),
             ("hmi", "SCADA / HMI"), ("interlock", "Interlock"), ("relay", "Setting Relay"), ("setting", "Setting Relay"),
             ("proteksi", "Setting Relay"), ("supply", "Power Supply"), ("tegangan", "Power Supply"),
             ("mekanik", "Mekanikal"), ("pintu", "Mekanikal"), ("grounding", "Mekanikal"), ("dokumen", "Dokumen")]
    for k, c in rules:
        if k in s and c in cats:
            return c
    return cats[-1] if cats else ""


# ---------------------------------------------------------------- detail
# ---------------------------------------------------------------- matriks SAS
_MARK = {"OK": "✓", "NG": "✗", "NA": "N/A"}
_CELL = {"": "background:white; border:1px dashed #A7AEAB; color:#656C6F;",
         "OK": f"background:{T.OK_L}; border:1px solid #9FD0AD; color:{T.OK};",
         "NG": f"background:{T.NG_L}; border:1px solid #E7B3AE; color:{T.NG};",
         "NA": f"background:{T.NA_L}; border:1px solid #C3C8C5; color:{T.NA}; font-size:8pt;"}


class SasMatrix(QFrame):
    """Device × (Integrasi · IP · SNTP · CID · Setting). Sel terhubung ke CheckRow yang sama di daftar,
    jadi daftar & matriks selalu sinkron."""

    def __init__(self, view, rows):
        super().__init__()
        self.view = view
        self.setObjectName("sasMatrix")
        self.setStyleSheet("QFrame#sasMatrix { background:#FFFFFF; border-bottom:1px solid #E3E6E3; }")
        self.devices = SM.sas_matrix(rows, key=lambda r: r.row)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)
        head = QHBoxLayout()
        t_ = QLabel(tr('Integrasi SAS'))
        t_.setStyleSheet(f"font-weight:700; color:{T.TEXT}; font-size:10pt;")
        head.addWidget(t_)
        self.cnt = QLabel()
        self.cnt.setTextFormat(Qt.RichText)
        self.cnt.setStyleSheet(f"color:{T.MUTED}; font-size:9pt;")
        head.addWidget(self.cnt)
        head.addStretch()
        hint = QLabel(tr('Klik sel: kosong → ✓ OK → ✗ NG → N/A · IP diketik langsung (otomatis OK bila valid & tidak dobel)'))
        hint.setStyleSheet(f"color:{T.MUTED}; font-size:8pt;")
        head.addWidget(hint)
        lay.addLayout(head)
        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(4)
        g.addWidget(self._hdr(tr('Device')), 0, 0)
        for j, (_, lab, _) in enumerate(SM.SAS_COLS, start=1):
            g.addWidget(self._hdr(tr(lab)), 0, j, Qt.AlignCenter)
        self.cells = []      # (col, CheckRow, widget)
        self.dev_widgets = []
        for i, d in enumerate(self.devices, start=1):
            nm = QWidget()
            nh = QHBoxLayout(nm)
            nh.setContentsMargins(0, 0, 0, 0)
            nh.setSpacing(6)
            n = QLabel(d["name"])
            n.setStyleSheet("font-weight:600;")
            nh.addWidget(n)
            dc = QLabel()
            dc.setStyleSheet(f"color:{T.MUTED}; font-size:8pt;")
            nh.addWidget(dc)
            nh.addStretch()
            ok = btn(tr('Semua OK'), None, "ghost", tr('Tandai sel yang belum dicek di device ini sebagai OK'),
                     lambda _=False, d=d: self._all_ok(d))
            pb = btn("+ " + tr('Punch'), None, "ghost", tr('Buat punch untuk item NG'), lambda _=False, d=d: self._punch(d))
            pb.setStyleSheet(f"color:{T.NG};")
            for b in (ok, pb):
                b.setVisible(False)
                nh.addWidget(b)
            g.addWidget(nm, i, 0)
            self.dev_widgets.append((d, dc, ok, pb))
            for j, (key, lab, _) in enumerate(SM.SAS_COLS, start=1):
                r = d["cells"].get(key)
                if r is None:
                    x = QLabel("—")
                    x.setStyleSheet(f"color:{T.MUTED};")
                    g.addWidget(x, i, j, Qt.AlignCenter)
                    continue
                if key == "ip":
                    w = self._ip_cell(r)
                else:
                    w = QPushButton()
                    w.setFixedSize(46, 32)
                    w.setCursor(Qt.PointingHandCursor)
                    w.setEnabled(not W.RO)
                    w.clicked.connect(lambda _=False, r=r: self._cycle(r))
                self.cells.append((key, r, w))
                g.addWidget(w, i, j, Qt.AlignCenter)
        g.setColumnStretch(0, 1)
        lay.addLayout(g)
        self.refresh()

    @staticmethod
    def _hdr(text):
        lb = QLabel(text.upper())
        lb.setStyleSheet(f"color:{T.MUTED}; font-size:7.5pt; font-weight:700; letter-spacing:0.5px;")
        return lb

    def _ip_cell(self, r):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        h = QHBoxLayout()
        h.setSpacing(4)
        e = QLineEdit(r.row["value"] or "")
        e.setFixedWidth(118)
        e.setPlaceholderText((r.row["criteria"] or "").replace("Subnet ", ""))
        e.setReadOnly(W.RO)
        e.editingFinished.connect(lambda r=r, e=e: self._save_ip(r, e))
        e.textEdited.connect(lambda _t, r=r, e=e: self._ip_warn(r, e))
        b = QPushButton()
        b.setFixedSize(34, 30)
        b.setCursor(Qt.PointingHandCursor)
        b.setEnabled(not W.RO)
        b.clicked.connect(lambda _=False, r=r: self._cycle(r))
        h.addWidget(e)
        h.addWidget(b)
        v.addLayout(h)
        wl = QLabel()
        wl.setStyleSheet(f"color:{T.NG}; font-size:7.5pt;")
        wl.setVisible(False)
        v.addWidget(wl)
        w.edit, w.btn, w.warnlbl = e, b, wl
        return w

    # ------------------------------------------------------------ data
    def _others(self, r):
        """IP milik device lain (semua panel) → 'tag · device'."""
        out = {}
        rows = self.view.main.db.q(
            "SELECT c.id, c.value, c.section, c.description, p.tag FROM panel_check c JOIN panel p ON p.id=c.panel_id "
            "WHERE c.deleted=0 AND p.deleted=0 AND COALESCE(c.value,'')<>''")
        for x in rows:
            if x["id"] == r.cid or not SM.is_sas_section(x["section"]) or not SM.SAS_COLS[1][2].search(x["description"] or ""):
                continue
            who = SM.device_name(x["section"])
            if x["tag"] != r.row_tag:
                who = " ".join((x["tag"] or "").split()) + " · " + who
            out[(x["value"] or "").strip()] = who
        return out

    def _ip_warn(self, r, e):
        msg = SM.ip_warning(e.text(), r.row["criteria"] or "", self._others(r))
        for key, rr, cell in self.cells:
            if rr is r and key == "ip":
                cell.warnlbl.setText(tr(msg) if msg else "")
                cell.warnlbl.setVisible(bool(msg))
                e.setStyleSheet(f"background:{T.NG_L}; border:1px solid {T.LAMP['red']};" if msg else "")
        return msg

    def _save_ip(self, r, e):
        if W.RO:
            return
        val = e.text().strip()
        changed = val != (r.row["value"] or "")
        r.apply_value(val)
        msg = self._ip_warn(r, e)
        if changed and val and not r.res.value and not msg:
            r.apply_result("OK")
        self.refresh()

    def _cycle(self, r):
        if W.RO:
            return
        r.apply_result(SM.next_result(r.res.value))
        self.refresh()

    def _all_ok(self, d):
        for r in d["cells"].values():
            if not r.res.value:
                r.apply_result("OK")
        self.refresh()

    def _punch(self, d):
        r = next((r for r in d["cells"].values() if r.res.value == "NG"
                  and not any(p["status"] != "Closed" for p in r.punches)), None)
        if r:
            r._punch(auto=True)

    def refresh(self):
        done = total = ng = 0
        for key, r, w in self.cells:
            v = r.res.value or ""
            total += 1
            done += bool(v)
            ng += v == "NG"
            b = w.btn if key == "ip" else w
            b.setText(_MARK.get(v, "·"))
            b.setStyleSheet(f"QPushButton {{ {_CELL[v]} border-radius:6px; font-weight:700; font-size:11pt; }}")
            b.setToolTip(f"{r.row['description']}\n" + (f"✓ {r.row['checked_by']} · {fmt_date(r.row['checked_at'])}"
                                                         if r.row["checked_by"] else tr('belum dicek')))
            if key == "ip" and w.edit.text() != (r.row["value"] or "") and not w.edit.hasFocus():
                w.edit.setText(r.row["value"] or "")
            if key == "ip":
                self._ip_warn(r, w.edit)
        for d, dc, ok, pb in self.dev_widgets:
            cs = list(d["cells"].values())
            dc.setText(f"{sum(1 for r in cs if r.res.value)}/{len(cs)}")
            ok.setVisible(not W.RO and any(not r.res.value for r in cs))
            pb.setVisible(not W.RO and any(r.res.value == "NG" and not any(p["status"] != "Closed" for p in r.punches)
                                           for r in cs))
        self.cnt.setText(f"{done}/{total}" + (f" · <span style='color:{T.NG}'>{ng} NG</span>" if ng else ""))

    def mapped_rows(self):
        return {r.cid for d in self.devices for r in d["cells"].values()}


class PanelCheckView(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.main = page.main
        self.panel_id = None
        self.rows: list[CheckRow] = []
        self.section_heads = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # header card
        hc = Card(pad=18)
        top = QHBoxLayout()
        top.setSpacing(16)
        self.ring = Ring(78, 8)
        top.addWidget(self.ring)
        tv = QVBoxLayout()
        tv.setSpacing(3)
        t1 = QHBoxLayout()
        self.tag = label("", 17, True)
        self.status = Pill("")
        t1.addWidget(self.tag)
        t1.addWidget(self.status)
        t1.addStretch()
        tv.addLayout(t1)
        self.name = label("", 10, False, T.TEXT)
        self.meta = label("", 9, False, T.MUTED)
        for lb in (self.name, self.meta):   # satu baris; teks panjang dipotong (lengkap di tooltip)
            lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            lb.setMinimumWidth(60)
        tv.addWidget(self.name)
        tv.addWidget(self.meta)
        top.addLayout(tv, 1)
        acts = QHBoxLayout()
        acts.setSpacing(8)
        self.b_punch = btn(tr('Punch'), "plus", "primary", tr('Buat punch untuk panel ini'), self.new_punch)
        self.b_tpl = btn(tr('Template'), "template", None, tr('Terapkan template checklist'))
        self.b_tpl.clicked.connect(self._tpl_menu)
        self.b_item = btn(tr('Item'), "plus", None, tr('Tambah item cek'), lambda: self.add_item(None))
        self.b_more = btn("", "more", None, tr('Menu lainnya'))
        self.b_more.clicked.connect(self._more_menu)
        for b in (self.b_tpl, self.b_item, self.b_punch, self.b_more):
            acts.addWidget(b)
        top.addLayout(acts)
        top.setAlignment(acts, Qt.AlignTop)
        hc.lay.addLayout(top)
        self.bar = SegmentBar(8)
        hc.lay.addWidget(self.bar)
        st = QHBoxLayout()
        self.stat_lbl = QLabel()
        self.stat_lbl.setWordWrap(True)
        self.stat_lbl.setTextFormat(Qt.RichText)
        st.addWidget(self.stat_lbl, 1)
        self.accept_lbl = QLabel()
        st.addWidget(self.accept_lbl)
        hc.lay.addLayout(st)
        lay.addWidget(hc)

        # filter bar
        fb = QHBoxLayout()
        fb.setSpacing(0)
        self.fgroup = QButtonGroup(self)
        for i, (key, text) in enumerate((("all", tr('Semua')), ("todo", tr("Belum dicek")), ("NG", "NG"), ("note", tr('Ada catatan')))):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setObjectName("segL" if i == 0 else "segR")
            b.setCursor(Qt.PointingHandCursor)
            if 0 < i < 3:
                b.setStyleSheet("border-radius:0;")
            self.fgroup.addButton(b)
            b.setProperty("key", key)
            fb.addWidget(b)
            if i == 0:
                b.setChecked(True)
        self.fgroup.buttonClicked.connect(lambda *_: self.apply_filter())
        fb.addSpacing(12)
        self.q = QLineEdit()
        self.q.setPlaceholderText(tr('Cari item…'))
        self.q.setClearButtonEnabled(True)
        self.q.setFixedWidth(220)
        self.q.textChanged.connect(lambda *_: self.apply_filter())
        fb.addWidget(self.q)
        fb.addStretch()
        self.b_matrix = QPushButton(tr('Matriks SAS'))
        self.b_matrix.setCheckable(True)
        self.b_matrix.setCursor(Qt.PointingHandCursor)
        self.b_matrix.setToolTip(tr('Tampilkan item integrasi SAS sebagai tabel device × Integrasi/IP/SNTP/CID/Setting'))
        st_ = getattr(self.main, "settings", None)
        self.b_matrix.setChecked((st_.value("ui/sas_matrix", "1") if st_ is not None else "1") in ("1", "true", True))
        self.b_matrix.setStyleSheet(f"QPushButton:checked {{ background:{T.SIDEBAR}; color:{T.ENGRAVE}; border-color:{T.SIDEBAR}; }}")
        self.b_matrix.toggled.connect(self._toggle_matrix)
        self.b_matrix.setVisible(False)
        fb.addWidget(self.b_matrix)
        fb.addSpacing(8)
        self.b_allok = btn(tr('Sisa item = OK'), "check", None, tr('Tandai semua item yang belum dicek (yang tampil) sebagai OK'),
                           self.mark_rest_ok)
        fb.addWidget(self.b_allok)
        lay.addLayout(fb)
        self._compact = None

        # list
        self.list_card = QFrame()
        self.list_card.setObjectName("card")
        lc = QVBoxLayout(self.list_card)
        lc.setContentsMargins(0, 6, 0, 6)
        self.sa = QScrollArea()
        self.sa.setWidgetResizable(True)
        self.sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lc.addWidget(self.sa)
        lay.addWidget(self.list_card, 1)

        self.empty = None   # dibuat baru tiap load: isi scroll lama (beserta label ini) dihapus Qt saat diganti

    def resizeEvent(self, e):
        # layar sempit (laptop 1366×768 + scaling): tombol jadi ikon saja (teks tetap di tooltip)
        compact = self.width() < 780
        if compact != self._compact:
            self._compact = compact
            for b, text in ((self.b_punch, tr('Punch')), (self.b_tpl, tr('Template')), (self.b_item, tr('Item')),
                            (self.b_allok, tr('Sisa item = OK'))):
                b.setText("" if compact else text)
            self.q.setFixedWidth(130 if compact else 220)
            self.ring.setVisible(not compact)   # progres tetap terlihat di bar & teks
        super().resizeEvent(e)

    # ----------------------------------------------------------- load
    def sections(self):
        seen = []
        for r in self.main.db.panel_checks(self.panel_id) if self.panel_id else []:
            if r["section"] not in seen:
                seen.append(r["section"])
        return seen

    def load(self, panel_id):
        self.panel_id = panel_id
        db = self.main.db
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.rows, self.section_heads = [], []
        self.matrix = None
        en = bool(panel_id)
        for b in (self.b_punch, self.b_tpl, self.b_item, self.b_more, self.b_allok):
            b.setEnabled(en)
        for b in (self.b_punch, self.b_tpl, self.b_item, self.b_allok):
            b.setVisible(not W.RO)
        if not panel_id:
            self.tag.setText(tr('Pilih panel'))
            self.name.setText(tr('Pilih panel di daftar kiri untuk mulai checking.'))
            self.meta.setText("")
            self.status.setText("")
            self.status.setStyleSheet("")
            self.ring.set(0)
            self.bar.set_parts([])
            self.stat_lbl.setText("")
            self.accept_lbl.setText("")
            v.addWidget(self._empty_label(tr('Belum ada panel dipilih')))
            self.b_matrix.setVisible(False)
            self.sa.setWidget(body)
            return
        p = db.panel(panel_id)
        checks = db.panel_checks(panel_id)
        punches = {}
        for i in db.issues(p["project_id"], panel_id=panel_id):
            if i["check_id"]:
                punches.setdefault(i["check_id"], []).append(i)
        self.tag.setText(p["tag"])
        self.name.setText(p["name"] or "")
        self.meta.setText("   ·   ".join(x for x in [p["site_name"], tr('Bay {0}', p['bay']) if p["bay"] else "",
                                                   p["panel_type"], p["vendor"],
                                                   f"S/N {p['serial_no']}" if p["serial_no"] else ""] if x))
        cur = None
        no = 0
        for r in checks:
            if r["section"] != cur:
                cur = r["section"]
                head = self._section_head(cur)
                v.addWidget(head)
                self.section_heads.append(head)
            no += 1
            row = CheckRow(self, r, no, punches.get(r["id"], []))
            row.section = cur
            v.addWidget(row)
            self.rows.append(row)
        if not checks:
            v.addWidget(self._empty_label(tr('Panel ini belum punya checklist.\nKlik tombol “Template” untuk menerapkan template, atau “Item” untuk menambah item manual.')))
        for r in self.rows:
            r.row_tag = p["tag"]
        if any(SM.is_sas_section(r.section) for r in self.rows):
            self.matrix = SasMatrix(self, self.rows)
            v.insertWidget(0, self.matrix)
        self.b_matrix.setVisible(self.matrix is not None)
        v.addStretch()
        self.sa.setWidget(body)
        self.stats_changed(update_list=False)
        self.apply_filter()

    def _empty_label(self, text):
        self.empty = QLabel(text)
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet(f"color:{T.MUTED}; font-size:11pt; padding:40px;")
        return self.empty

    def _section_head(self, name):
        w = QWidget()
        w.setStyleSheet("background:#F6F7F5;")
        h = QHBoxLayout(w)
        h.setContentsMargins(14, 9, 10, 7)
        lab = QLabel(name)
        lab.setStyleSheet(f"font-weight:700; color:{T.TEXT}; font-size:9.5pt; background:transparent;")
        h.addWidget(lab)
        cnt = QLabel()
        cnt.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt; background:transparent;")
        h.addWidget(cnt)
        h.addStretch()
        b = btn(tr('Semua OK'), None, "ghost", tr("Tandai item '{0}' yang belum dicek sebagai OK", name),
                lambda: self.mark_section_ok(name))
        b.setVisible(not W.RO)
        h.addWidget(b)
        w.name = name
        w.cnt = cnt
        return w

    def reload_punches(self):
        if not self.panel_id:
            return
        punches = {}
        for i in self.main.db.issues(self.main.project_id, panel_id=self.panel_id):
            if i["check_id"]:
                punches.setdefault(i["check_id"], []).append(i)
        for r in self.rows:
            r.set_punches(punches.get(r.cid, []))
        self.stats_changed()

    def stats_changed(self, update_list=True):
        if not self.panel_id:
            return
        db = self.main.db
        ov = next((o for o in db.panel_overview(self.main.project_id)
                   if o["panel"]["id"] == self.panel_id), None)
        if not ov:
            return
        s = ov["stats"]
        col = T.PANEL_STATUS_COLOR[ov["status"]]
        self.status.set(tr(ov["status"]), col)
        self.ring.set(s["pct"], T.LAMP["green"] if s["pct"] >= 99.9 and not s["NG"] else (T.LAMP["red"] if s["NG"] else T.LAMP["blue"]))
        self.bar.set_parts([(s["OK"], T.OK), (s["NA"], "#8C9396"), (s["NG"], T.NG), (s["pending"], "#E4E7E4")])
        pu = ov["punch"]
        self.stat_lbl.setText(
            tr("<b>{0}/{1}</b> item diuji &nbsp;&nbsp;", s['checked'], s['total']) +
            f"<span style='color:{T.OK}'>● {s['OK']} OK</span> &nbsp; <span style='color:{T.NG}'>● {s['NG']} NG</span>"
            f" &nbsp; <span style='color:{T.NA}'>● {s['NA']} N/A</span> &nbsp; <span style='color:{T.SUBTLE}'>"
            + tr("● {0} belum", s['pending']) + "</span> &nbsp;&nbsp;|&nbsp;&nbsp; " + tr("Punch open: ") +
            f"<b style='color:{T.NG if pu.get('open') else T.TEXT}'>{pu.get('open', 0)}</b>" + tr(" dari ") +
            f"{pu.get('total', 0)}")
        p = ov["panel"]
        self.accept_lbl.setText("<span style='color:#1F5C4A'>" + tr("🛡 Diterima {0} · {1}", p['accepted_by'],
                                fmt_date(p['accepted_at'])) + "</span>" if p["accepted_at"] else "")
        if getattr(self, "matrix", None) is not None:
            self.matrix.refresh()
        for h in self.section_heads:
            rs = [r for r in self.rows if r.section == h.name]
            done = sum(1 for r in rs if r.res.value)
            ng = sum(1 for r in rs if r.res.value == "NG")
            h.cnt.setText(f"{done}/{len(rs)}" + (f"  ·  <span style='color:{T.NG}'>{ng} NG</span>" if ng else ""))
            h.cnt.setTextFormat(Qt.RichText)
        if update_list:
            self.page.update_card(self.panel_id, ov)
            self.main.mark_dirty(except_page=self.page)

    def apply_filter(self):
        b = self.fgroup.checkedButton()
        key = b.property("key") if b else "all"
        q = self.q.text().strip().lower()
        vis_sections = set()
        in_matrix = self.matrix.mapped_rows() if (self.matrix is not None and self.b_matrix.isChecked()) else set()
        if self.matrix is not None:
            self.matrix.setVisible(self.b_matrix.isChecked())
        for r in self.rows:
            ok = r.cid not in in_matrix
            if key == "todo":
                ok = ok and not r.res.value
            elif key == "NG":
                ok = ok and (r.res.value == "NG" or any(p["status"] != "Closed" for p in r.punches))
            elif key == "note":
                ok = ok and bool(r.remark.text().strip() or r.value.text().strip())
            if q and q not in (r.row["description"] + " " + r.row["section"] + " " + r.remark.text()).lower():
                ok = False
            r.setVisible(ok)
            if ok:
                vis_sections.add(r.section)
        for h in self.section_heads:
            h.setVisible(h.name in vis_sections)

    def _toggle_matrix(self, on):
        st_ = getattr(self.main, "settings", None)
        if st_ is not None:
            st_.setValue("ui/sas_matrix", "1" if on else "0")
        self.apply_filter()

    # ----------------------------------------------------------- actions
    def mark_rest_ok(self):
        targets = [r for r in self.rows if not r.isHidden() and not r.res.value]
        if not targets:
            info(self, tr('Tidak ada item kosong yang tampil.'))
            return
        if ask(self, tr('Tandai {0} item yang belum dicek (yang tampil) sebagai OK?', len(targets))):
            self._bulk(targets)

    def mark_section_ok(self, name):
        targets = [r for r in self.rows if r.section == name and not r.res.value]
        if targets:
            self._bulk(targets)

    def _bulk(self, targets):
        db = self.main.db
        for r in targets:
            db.set_check(r.cid, result="OK")
            r.res.set_value("OK")
            r.row = db.check(r.cid)
            r.meta.setText(tr('Kriteria: {0}   ·   ✓ {1} · {2}', r.row['criteria'], r.row['checked_by'], fmt_date(r.row['checked_at'])) if r.row["criteria"] else
                           f"✓ {r.row['checked_by']} · {fmt_date(r.row['checked_at'])}")
            r._style()
        self.stats_changed()
        self.apply_filter()

    def add_item(self, section=None):
        d = CheckItemDialog(self, self.sections() or ["A. Umum"], section=section)
        if d.exec():
            self.main.db.add_check_item(self.panel_id, **d.values())
            self.load(self.panel_id)
            self.stats_changed()

    def new_punch(self):
        if IssueDialog(self, self.main.db, self.main.project_id, panel_id=self.panel_id).exec():
            self.reload_punches()
            self.main.refresh_all(except_page=self.page)

    def _tpl_menu(self):
        db = self.main.db
        m = QMenu(self)
        m.addSection(tr('Tambahkan item dari template'))
        for t in db.templates():
            m.addAction(T.icon("template"), f"{t['name']}  ({t['n']})".replace("&", "&&"), lambda tid=t["id"]: self._apply(tid, False))
        m.addSection(tr('Ganti seluruh checklist'))
        for t in db.templates():
            m.addAction(tr('Ganti dengan: {0}', t['name']).replace("&", "&&"), lambda tid=t["id"]: self._apply(tid, True))
        m.addSeparator()
        m.addAction(T.icon("download"), tr('Simpan checklist panel ini sebagai template baru…'), self._save_as_template)
        m.exec(self.b_tpl.mapToGlobal(self.b_tpl.rect().bottomLeft()))

    def _apply(self, tid, replace):
        if replace and self.rows and not ask(self, tr('Ganti seluruh checklist? Hasil cek yang sudah diisi pada panel ini akan dihapus (punch tetap ada).')):
            return
        n = self.main.db.apply_template(self.panel_id, tid, replace=replace)
        self.load(self.panel_id)
        self.stats_changed()
        self.main.statusBar().showMessage(tr('{0} item ditambahkan dari template', n), 4000)

    def _save_as_template(self):
        name, ok = QInputDialog.getText(self, tr('Template baru'), tr('Nama template:'))
        if ok and name.strip():
            items = [(r.row["section"], r.row["description"], r.row["criteria"], r.row["unit"]) for r in self.rows]
            self.main.db.add_template(name.strip(), tr('Dari panel {0}', self.tag.text()), items)
            self.main.mark_dirty()
            info(self, tr("Template '{0}' disimpan ({1} item).", name, len(items)))

    def _more_menu(self):
        db = self.main.db
        p = db.panel(self.panel_id)
        m = QMenu(self)
        m.addAction(T.icon("edit"), tr('Edit data panel…'), self._edit_panel)
        m.addAction(T.icon("punch"), tr('Lihat punch panel ini'), lambda: self.main.show_punch_for(p["tag"]))
        m.addSeparator()
        m.addAction(T.icon("printer"), tr('Cetak check sheet (PDF)…'), lambda: self.main.report_check_sheet([self.panel_id]))
        m.addAction(T.icon("qr"), tr('Cetak label QR…'), lambda: self.main.report_qr([self.panel_id]))
        m.addSeparator()
        if p["accepted_at"]:
            m.addAction(T.icon("shield"), tr('Batalkan penerimaan panel'), lambda: self._accept(False))
        else:
            m.addAction(T.icon("shield", "#1F5C4A"), tr('Terima panel (sign-off)…'), lambda: self._accept(True))
        m.addSeparator()
        m.addAction(T.icon("trash", T.NG), tr('Hapus panel'), self._delete_panel)
        m.exec(self.b_more.mapToGlobal(self.b_more.rect().bottomLeft()))

    def _accept(self, yes):
        db = self.main.db
        if not yes:
            db.set_accepted(self.panel_id, None)
        else:
            ov = next(o for o in db.panel_overview(self.main.project_id) if o["panel"]["id"] == self.panel_id)
            s, pu = ov["stats"], ov["punch"]
            warn_txt = []
            if s["pending"]:
                warn_txt.append(tr('• {0} item belum dicek', s['pending']))
            if s["NG"]:
                warn_txt.append(tr('• {0} item masih NG', s['NG']))
            if pu.get("Critical"):
                warn_txt.append(tr('• {0} punch kategori A (Critical) belum close', pu['Critical']))
            if warn_txt and not ask(self, tr('Panel belum bersih:\n') + "\n".join(warn_txt) + tr('\n\nTetap terima panel?')):
                return
            name, ok = QInputDialog.getText(self, tr('Terima panel'), tr('Diterima / disetujui oleh:'), text=db.user)
            if not ok or not name.strip():
                return
            db.set_accepted(self.panel_id, name.strip())
        self.stats_changed()

    def _edit_panel(self):
        db = self.main.db
        d = PanelDialog(self, db, self.main.project_id, db.panel(self.panel_id))
        if d.exec():
            db.update_panel(self.panel_id, **d.values())
            self.load(self.panel_id)
            self.page.refresh()

    def _delete_panel(self):
        p = self.main.db.panel(self.panel_id)
        if ask(self, tr('Hapus panel {0} beserta hasil checking-nya?\n(Punch tetap tersimpan)', p['tag'])):
            self.main.db.delete_panel(self.panel_id)
            self.panel_id = None
            self.main.refresh_all()


# ---------------------------------------------------------------- page
class ChecklistPage(QWidget):
    def set_read_only(self, ro):
        self.b_add.setVisible(not ro)

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setObjectName("page")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(16)

        left = QWidget()
        left.setFixedWidth(330)
        self.left = left
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(10)
        h = QHBoxLayout()
        t = label(tr('Checking Panel'), 15, True)
        h.addWidget(t)
        h.addStretch()
        self.b_add = btn(tr('Panel'), "plus", "primary", tr('Tambah panel'), self.add_panel)
        h.addWidget(self.b_add)
        lv.addLayout(h)
        self.count = label("", 9, False, T.MUTED)
        lv.addWidget(self.count)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Cari tag, bay, nama…'))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(T.icon("search", T.SUBTLE, 16), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._filter)
        lv.addWidget(self.search)
        self.f_status = QComboBox()
        self.f_status.addItem(tr('Semua status'), None)
        for s in PANEL_STATUSES:
            self.f_status.addItem(tr(s), s)
        self.f_status.currentIndexChanged.connect(self._filter)
        lv.addWidget(self.f_status)
        self.list = QListWidget()
        self.list.setItemDelegate(PanelCardDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setUniformItemSizes(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(self._select)
        lv.addWidget(self.list, 1)
        lay.addWidget(left)

        self.detail = PanelCheckView(self)
        lay.addWidget(self.detail, 1)
        self._items = {}

    def resizeEvent(self, e):
        self.left.setFixedWidth(330 if self.width() >= 1150 else 265)
        super().resizeEvent(e)

    def refresh(self):
        db, pid, sid = self.main.db, self.main.project_id, self.main.site_id
        cur = self.detail.panel_id
        self.list.blockSignals(True)
        self.list.clear()
        self._items = {}
        if not pid:
            self.list.blockSignals(False)
            self.count.setText("")
            self.detail.load(None)
            return
        ov = db.panel_overview(pid, sid)
        for o in ov:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, o["panel"]["id"])
            it.setData(Qt.UserRole + 1, o)
            it.setSizeHint(QSize(300, PanelCardDelegate.H))
            self.list.addItem(it)
            self._items[o["panel"]["id"]] = it
        done = sum(1 for o in ov if o["status"] in ("Lulus", "Diterima"))
        self.count.setText(tr('{0} panel  ·  {1} lulus/diterima', len(ov), done))
        self.list.blockSignals(False)
        self._filter()
        target = cur if cur in self._items else None
        if target is None:
            vis = [self.list.item(i) for i in range(self.list.count()) if not self.list.item(i).isHidden()]
            target = vis[0].data(Qt.UserRole) if vis else None
        if target:
            self.list.setCurrentItem(self._items[target])
            if target == cur:
                self.detail.load(target)
        else:
            self.detail.load(None)

    def _filter(self, *_):
        q = self.search.text().strip().lower()
        st = self.f_status.currentData()
        for i in range(self.list.count()):
            it = self.list.item(i)
            o = it.data(Qt.UserRole + 1)
            p = o["panel"]
            hay = " ".join(str(p[k] or "") for k in ("tag", "bay", "name", "site_name", "panel_type")).lower()
            it.setHidden(bool(q and q not in hay) or bool(st and o["status"] != st))

    def _select(self, cur, prev):
        if cur:
            pid = cur.data(Qt.UserRole)
            if pid != self.detail.panel_id:
                self.detail.load(pid)

    def update_card(self, panel_id, ov):
        it = self._items.get(panel_id)
        if it:
            it.setData(Qt.UserRole + 1, ov)
            self.list.viewport().update()

    def select_panel(self, panel_id):
        if panel_id not in self._items:
            self.search.clear()
            self.f_status.setCurrentIndex(0)
        it = self._items.get(panel_id)
        if it:
            it.setHidden(False)
            self.list.setCurrentItem(it)
            self.list.scrollToItem(it)

    def add_panel(self):
        db, pid = self.main.db, self.main.project_id
        if not pid:
            return
        if not db.sites(pid):
            warn(self, tr('Belum ada site / GI. Tambahkan dulu lewat menu ⋯ → Kelola site / GI.'))
            return
        d = PanelDialog(self, db, pid, site_id=self.main.site_id)
        if d.exec():
            v = d.values()
            new = db.add_panel(v.pop("site_id"), template_id=d.template_id(), **v)
            self.detail.panel_id = new
            self.main.refresh_all()
            self.select_panel(new)
