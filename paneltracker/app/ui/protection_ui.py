"""Uji proteksi relay di halaman Checking (blok "<huruf>. SAS · Uji Proteksi <device>"). Data = item checklist biasa
(lihat app/relaytest.py); tampilan & aturan sama dengan aplikasi HP (src/ui/Protection.tsx)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from .. import relaytest as R
from ..i18n import tr
from . import theme as T
from . import widgets as W
from .injection_ui import _clear_layout, ratio_devices
from .widgets import Pill, ResultButtons, ask, btn, warn


def add_items(db, panel_id, items):
    mx = db.q1("SELECT COALESCE(MAX(sort),0) m FROM panel_check WHERE panel_id=?", (panel_id,))["m"]
    for i, (sec, desc, crit, unit) in enumerate(items, 1):
        cid = db._insert("panel_check", dict(panel_id=panel_id, section=sec, description=desc, criteria=crit, unit=unit, sort=mx + i))
        if unit == R.SETUP_UNIT:
            db.set_check(cid, result="OK")


def _unit(code, u, p=None):
    if u == "@":
        return R.pickup_unit(code)
    if p is not None and u == "" and p.get("kurva") == "DT":
        return "s"
    return u


def setting_summary(code, p):
    out = []
    for k, lab, u in R.PARAMS[R.kind_of(code)]:
        if p.get(k):
            un = _unit(code, u, p)
            out.append(f"{tr(lab)} {p[k]}{(' ' + un) if un else ''}")
    return " · ".join(out)


# ---------------------------------------------------------------- dialog
class CreateDialog(QDialog):
    def __init__(self, parent, rows):
        super().__init__(parent)
        self.setWindowTitle(tr("Uji proteksi relay baru"))
        self.resize(520, 640)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.dev = QComboBox()
        self.dev.setEditable(True)
        devs = [d for d in ratio_devices(rows) if "C264" not in d and "PM8240" not in d]
        self.dev.addItems(devs)
        f.addRow(tr("Relay"), self.dev)
        v.addLayout(f)
        note = QLabel(tr("Fungsi tercentang otomatis sesuai model relay. Setting bisa diisi nanti; uji fungsional bisa langsung diisi OK/NG."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{T.MUTED};")
        v.addWidget(note)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        self.dev.currentTextChanged.connect(self._fill)
        self._fill(self.dev.currentText())
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.button(QDialogButtonBox.Ok).setText(tr("Buat"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _fill(self, dev):
        pre = R.preset_for(dev)
        self.list.clear()
        for code in pre + [c for c in R.FUNCS if c not in pre]:
            it = QListWidgetItem(f"{code}  ·  {tr(R.FUNCS[code][0])}")
            it.setData(Qt.UserRole, code)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if code in pre else Qt.Unchecked)
            self.list.addItem(it)

    def codes(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def accept(self):
        if not self.dev.currentText().strip():
            warn(self, tr("Isi nama device / alat baca."))
            return
        if not self.codes():
            warn(self, tr("Pilih minimal satu fungsi."))
            return
        super().accept()


class SettingDialog(QDialog):
    def __init__(self, parent, f, p, tol):
        super().__init__(parent)
        self.code, self.tol = f["code"], tol
        self.setWindowTitle(f"F{f['n']} · {f['code']} · {tr(f['name'])}")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.w = {}
        for k, lab, u in R.PARAMS[R.kind_of(self.code)]:
            if k == "kurva":
                e = QComboBox()
                e.addItems(list(R.CURVES))
                e.setCurrentText(p.get("kurva") or "IEC SI")
                e.currentTextChanged.connect(self._preview)
            else:
                e = QLineEdit(p.get(k, ""))
                e.textChanged.connect(self._preview)
            self.w[k] = e
            un = _unit(self.code, u)
            form.addRow(tr(lab) + (f" ({un})" if un else ""), e)
        v.addLayout(form)
        self.prev = QLabel()
        self.prev.setWordWrap(True)
        self.prev.setStyleSheet("background:#DFEAF6; color:#12416b; border-radius:6px; padding:8px;")
        v.addWidget(self.prev)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._preview()

    def params(self):
        return {k: (e.currentText() if isinstance(e, QComboBox) else e.text().strip().replace(",", ".")) for k, e in self.w.items()}

    def _preview(self, *_):
        ex = R.expected(self.code, self.params(), self.tol)
        if not ex:
            self.prev.setText(tr("Setting belum diisi — expected muncul setelah setting diisi."))
            return
        self.prev.setText("<b>" + tr("Expected yang akan dipakai:") + "</b><br>" + "<br>".join(
            f"{tr(l)} → " + ("—" if e is None else f"{R.fmt(e, u)} {u} ±{R.fmt(t, u)}") for l, u, e, t in ex))


class TolDialog(QDialog):
    def __init__(self, parent, tol):
        super().__init__(parent)
        self.setWindowTitle(tr("Toleransi uji"))
        f = QFormLayout(self)
        self.tp, self.tm, self.pp = (QLineEdit(R._g(tol[k])) for k in ("t_pct", "t_ms", "p_pct"))
        f.addRow(tr("Waktu trip ±") + " (%)", self.tp)
        f.addRow(tr("minimal") + " (ms)", self.tm)
        f.addRow(tr("Pickup ±") + " (%)", self.pp)
        n = QLabel(tr("Standar IEC 60255-151: waktu ±5% atau ±40 ms (ambil yang lebih besar), pickup ±5%."))
        n.setWordWrap(True)
        n.setStyleSheet(f"color:{T.MUTED};")
        f.addRow(n)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def value(self):
        vals = [R.num(x.text()) for x in (self.tp, self.tm, self.pp)]
        if any(x is None or x < 0 for x in vals):
            return None
        return dict(t_pct=vals[0], t_ms=vals[1], p_pct=vals[2])


# ---------------------------------------------------------------- blok
class ProtectionBlock(QFrame):
    def __init__(self, view, section, rows, punches):
        super().__init__()
        self.view, self.section, self.rows, self.punches = view, section, rows, punches
        self.setObjectName("protBlock")
        self.setStyleSheet("QFrame#protBlock { background:#FFFFFF; border-bottom:1px solid #E3E6E3; }")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 8)
        self.lay.setSpacing(0)
        self.build()

    @property
    def db(self):
        return self.view.main.db

    def reload_rows(self):
        self.rows = [r for r in self.db.panel_checks(self.view.panel_id) if r["section"] == self.section]

    def tests(self):
        return [r for r in self.rows if r["unit"] != R.SETUP_UNIT]

    def stats(self):
        ts = self.tests()
        return sum(1 for r in ts if r["result"]), sum(1 for r in ts if r["result"] == "NG"), len(ts)

    def used(self):
        n = sum(1 for r in self.tests() if r["result"] or (r["value"] or "").strip())
        return n + sum(self.view.photo_counts.get(r["id"], 0) for r in self.rows)

    def matches(self, key, q):
        if q and q not in (self.section + " " + " ".join(r["description"] for r in self.rows)).lower():
            return False
        done, ng, total = self.stats()
        if key == "todo":
            return done < total
        if key == "NG":
            return ng > 0 or any(p["status"] != "Closed" for ps in self.punches.values() for p in ps)
        if key == "note":
            return any((r["remark"] or "").strip() for r in self.rows)
        return True

    def refresh(self):
        self.reload_rows()
        self.view.photo_counts = self.db.check_photo_counts(self.view.panel_id)
        self.build()
        self.view.stats_changed()

    def build(self):
        _clear_layout(self.lay)
        g = R.group(self.rows)
        head = QWidget()
        head.setStyleSheet("background:#F6F7F5;")
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 9, 10, 7)
        lab = QLabel(self.section)
        lab.setStyleSheet(f"font-weight:700; color:{T.TEXT}; font-size:9.5pt; background:transparent;")
        h.addWidget(lab)
        done, ng, total = self.stats()
        cnt = QLabel(f"{done}/{total}" + (f"  ·  <span style='color:{T.NG}'>{ng} NG</span>" if ng else ""))
        cnt.setTextFormat(Qt.RichText)
        cnt.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt; background:transparent;")
        h.addWidget(cnt)
        h.addStretch()
        if not W.RO:
            h.addWidget(btn(tr("Toleransi…"), "edit", "ghost", tr("Toleransi uji"), lambda: self.edit_tol(g)))
            if not self.used():
                h.addWidget(btn(tr("Hapus blok"), "trash", "ghost", tr("Hapus blok uji proteksi"), self.delete_block, color=T.NG))
        self.lay.addWidget(head)
        tl = QLabel(tr("Toleransi: waktu ±{0}% (min {1} ms) · pickup ±{2}%", R._g(g["tol"]["t_pct"]), R._g(g["tol"]["t_ms"]),
                       R._g(g["tol"]["p_pct"])))
        tl.setContentsMargins(14, 6, 14, 2)
        tl.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
        self.lay.addWidget(tl)
        for f in g["funcs"]:
            self.lay.addWidget(self._func_widget(f, g["tol"]))

    def _result_buttons(self, row):
        rb = ResultButtons(row["result"])
        rb.setEnabled(not W.RO)
        rb.changed.connect(lambda val, cid=row["id"]: self._set_result(cid, val))
        return rb

    def _set_result(self, cid, val):
        self.db.set_check(cid, result=val)
        QTimer.singleShot(0, self.refresh)

    def _func_widget(self, f, tol):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 10, 14, 4)
        v.setSpacing(4)
        top = QHBoxLayout()
        tests = [r for _, r in f["points"]]
        res = [r["result"] for r in tests]
        nng = res.count("NG")
        st = ("NG", T.NG) if nng else (("OK", T.OK) if tests and all(res) else ("", T.MUTED))
        top.addWidget(QLabel(f"<b>F{f['n']}</b> &nbsp;<span style='background:{T.SIDEBAR}; color:{T.ENGRAVE};'>&nbsp;{f['code']}&nbsp;</span>"
                             f"&nbsp; {tr(f['name'])}"))
        top.addWidget(Pill(tr("Lulus") if st[0] == "OK" else (tr("{0} NG", nng) if nng else tr("{0} belum diisi", res.count(""))), st[1]))
        top.addStretch()
        first = tests[0] if tests else None
        if first is not None:
            photos = sum(self.view.photo_counts.get(r["id"], 0) for r in tests)
            cam = QToolButton()
            cam.setIcon(T.icon("camera", T.OK if photos else T.SUBTLE, 16))
            cam.setText(str(photos) if photos else "")
            cam.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            cam.setAutoRaise(True)
            cam.setToolTip(tr("Foto evidence (layar test set / relay)"))
            cam.clicked.connect(lambda _=False, cid=first["id"]: self._evidence(cid))
            top.addWidget(cam)
        v.addLayout(top)
        p = R.parse_params(f["fset"]["criteria"]) if f["fset"] is not None else {}
        if f["kind"] == "check":
            row = QHBoxLayout()
            row.addWidget(self._result_buttons(first))
            row.addWidget(self._punch_btn(first))
            row.addStretch()
            v.addLayout(row)
            return w
        srow = QHBoxLayout()
        ok = R.complete(f["code"], p)
        sl = QLabel(setting_summary(f["code"], p) if ok else tr("Setting belum diisi — expected muncul setelah setting diisi."))
        sl.setStyleSheet(f"color:{T.MUTED if ok else T.WARN}; font-size:8.5pt;")
        srow.addWidget(sl)
        if not W.RO:
            srow.addWidget(btn(tr("Setting…"), "edit", "ghost", None, lambda _=False, ff=f, tt=tol: self.edit_setting(ff, tt)))
        srow.addStretch()
        if f["fset"] is not None and ok:
            srow.addWidget(QLabel(tr("Setting di relay sesuai approval?")))
            srow.addWidget(self._result_buttons(f["fset"]))
        v.addLayout(srow)
        ex = {l: (e, t) for l, _, e, t in R.expected(f["code"], p, tol)}
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        for c, txt in enumerate([tr("Titik uji"), tr("Expected"), tr("Panduan injeksi"), tr("Actual"), tr("Status"), ""]):
            lb = QLabel(txt)
            lb.setStyleSheet(f"color:{T.MUTED}; font-size:8pt; font-weight:600;")
            grid.addWidget(lb, 0, c)
        for i, (label, r) in enumerate(f["points"], 1):
            grid.addWidget(QLabel(f"<b>{tr(label)}</b>"), i, 0)
            if not r["unit"]:
                grid.addWidget(QLabel(tr(r["criteria"] or "")), i, 1, 1, 3)
                grid.addWidget(self._result_buttons(r), i, 4)
                grid.addWidget(self._punch_btn(r), i, 5)
                continue
            e, t = ex.get(label, (None, None))
            grid.addWidget(QLabel("—" if e is None else f"{R.fmt(e, r['unit'])} <span style='color:{T.MUTED}'>{r['unit']} ±{R.fmt(t, r['unit'])}</span>"), i, 1)
            hl = QLabel(R.inject_hint(f["code"], p, label))
            hl.setStyleSheet("color:#12416b; font-size:8.5pt;")
            grid.addWidget(hl, i, 2)
            ed = QLineEdit(r["value"] or "")
            ed.setFixedWidth(100)
            ed.setAlignment(Qt.AlignRight)
            ed.setReadOnly(W.RO)
            ed.setStyleSheet("QLineEdit { border:1px solid #C9CEC9; background:white; }")
            ed.editingFinished.connect(lambda cid=r["id"], ee=e, tt=t, w_=ed: self._save(cid, ee, tt, w_.text()))
            grid.addWidget(ed, i, 3)
            res_ = r["result"] or ""
            grid.addWidget(Pill({"OK": "OK", "NG": "NG"}.get(res_, tr("Belum")), {"OK": T.OK, "NG": T.NG}.get(res_, T.MUTED)), i, 4)
            grid.addWidget(self._punch_btn(r), i, 5)
        grid.setColumnStretch(6, 1)
        v.addLayout(grid)
        return w

    def _punch_btn(self, r):
        pb = QToolButton()
        pb.setAutoRaise(True)
        ps = self.punches.get(r["id"], [])
        open_n = sum(1 for x in ps if x["status"] != "Closed")
        col = T.NG if (open_n or r["result"] == "NG") else (T.OK if ps else T.SUBTLE)
        pb.setIcon(T.icon("punch", col, 15))
        pb.setText(f"{open_n}/{len(ps)}" if ps else "")
        pb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        pb.setToolTip(tr("Punch dari besaran ini"))
        pb.clicked.connect(lambda _=False, rr=r: self._punch(rr))
        pb.setVisible(bool(ps) or (r["result"] == "NG" and not W.RO))
        return pb

    def _punch(self, r):
        from .dialogs import IssueDialog
        main = self.view.main
        ps = self.punches.get(r["id"], [])
        if ps:
            iid = next((x["id"] for x in ps if x["status"] != "Closed"), ps[0]["id"])
            ok = IssueDialog(self, main.db, main.project_id, iid).exec()
        else:
            desc = tr("Uji proteksi: {0} — {1}.", self.section, r["description"])
            if r["criteria"]:
                desc += tr("\nExpected: {0} {1}", r["criteria"], r["unit"] or "")
            if r["value"]:
                desc += tr("\nActual: {0} {1}", r["value"], r["unit"] or "")
            ok = IssueDialog(self, main.db, main.project_id, panel_id=self.view.panel_id, check_id=r["id"],
                             preset={"title": f"{r['description']} — {tr('tidak sesuai')} ({R.device_of(self.section)})",
                                     "description": desc, "category": "Setting Relay", "severity": "Major"}).exec()
        if ok:
            self.view.reload_punches()
            main.refresh_all(except_page=self.view.page)

    def _evidence(self, cid):
        from .dialogs import EvidenceDialog
        EvidenceDialog(self, self.db, cid, getattr(self.view, "tag_text", "")).exec()
        self.refresh()
        self.view.main.refresh_all(except_page=self.view.page)

    def _save(self, cid, e, t, text):
        text = (text or "").strip()
        r = self.db.check(cid)
        if text == (r["value"] or ""):
            return
        res = R.judge(e, t, text)
        f = dict(value=text)
        if res != (r["result"] or ""):
            f["result"] = res
        self.db.set_check(cid, **f)
        QTimer.singleShot(0, self.refresh)

    def _redefine(self, defs):
        from .injection_ui import InjectionBlock
        return InjectionBlock._redefine(self, defs)

    def _apply_function(self, f, p, tol):
        ex = {l: (e, t) for l, _, e, t in R.expected(f["code"], p, tol)}
        defs = []
        if f["fset"] is not None and R.params_text(p) != (f["fset"]["criteria"] or ""):
            defs.append((f["fset"]["id"], dict(criteria=R.params_text(p))))
        for label, r in f["points"]:
            if not r["unit"]:
                continue
            e, t = ex.get(label, (None, None))
            c = R.criteria_text(r["unit"], e, t)
            if c != (r["criteria"] or ""):
                defs.append((r["id"], dict(criteria=c)))
        if not self._redefine(defs):
            return False
        for label, r in f["points"]:
            r = self.db.check(r["id"])
            if r["unit"] and (r["value"] or "").strip():
                e, t = ex.get(label, (None, None))
                res = R.judge(e, t, r["value"])
                if res != (r["result"] or ""):
                    self.db.set_check(r["id"], result=res)
        return True

    def edit_setting(self, f, tol):
        p = R.parse_params(f["fset"]["criteria"]) if f["fset"] is not None else {}
        d = SettingDialog(self, f, p, tol)
        if d.exec() and self._apply_function(f, d.params(), tol):
            self.refresh()

    def edit_tol(self, g):
        d = TolDialog(self, g["tol"])
        if not d.exec():
            return
        tol = d.value()
        if tol is None:
            warn(self, tr("Isi semua angka toleransi."))
            return
        if g["setup"] is not None and not self._redefine([(g["setup"]["id"], dict(criteria=R.tol_text(tol)))]):
            return
        for f in g["funcs"]:
            if f["kind"] != "check":
                p = R.parse_params(f["fset"]["criteria"]) if f["fset"] is not None else {}
                if not self._apply_function(f, p, tol):
                    return
        self.refresh()

    def delete_block(self):
        if self.used():
            warn(self, tr("Blok ini sudah berisi hasil uji atau foto, tidak bisa dihapus. Kosongkan nilainya dulu bila memang salah buat."))
            return
        if not ask(self, tr("Hapus blok {0}? Semua titik uji di blok ini ikut terhapus.", self.section)):
            return
        for r in self.rows:
            self.db.delete_check_item(r["id"])
        self.view.load(self.view.panel_id)
        self.view.stats_changed()


def create_block(view):
    db = view.main.db
    rows = db.panel_checks(view.panel_id)
    d = CreateDialog(view, rows)
    if not d.exec():
        return False
    dev, codes = d.dev.currentText().strip(), d.codes()
    secs = [r["section"] for r in rows]
    if any(R.is_protection_section(x) and R.device_of(x) == dev for x in secs):
        if not ask(view, tr("Panel ini sudah punya uji proteksi untuk {0}. Buat blok kedua?", dev)):
            return False
    add_items(db, view.panel_id, R.block_items(dev, R.next_letter(secs), codes))
    p = db.panel(view.panel_id)
    db.log(p["project_id"], "panel", view.panel_id, "protection", f"{p['tag']}: uji proteksi {dev} ({len(codes)} fungsi)")
    return True
