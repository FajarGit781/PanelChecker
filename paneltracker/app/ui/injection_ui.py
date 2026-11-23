"""Uji injeksi sekunder CT/VT di halaman Checking (blok "<huruf>. SAS · Injeksi CT/VT <device>").

Expected I/V/MW/MVAR/PF/f dihitung dari setup rasio CT/VT + % injeksi; actual diketik atau dibaca dari foto layar
HMI (OCR bawaan OS, gratis/offline) lalu dicek; OK/NG otomatis. Data = item checklist biasa (lihat app/injection.py).
"""
from __future__ import annotations

import datetime as _dt
import os
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from .. import injection as INJ
from ..i18n import tr
from . import theme as T
from . import widgets as W
from .widgets import Pill, ask, btn, info, warn


def key_label(k):
    return tr("Frekuensi") if k == "f" else k


def _spin(val, lo, hi, dec, suffix="", step=None):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    if step:
        s.setSingleStep(step)
    s.setButtonSymbols(QDoubleSpinBox.NoButtons)
    return s


def _ratio_from_value(text):
    """'2000/1 A' → (2000, 1). None bila tidak terbaca."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(k?V|A)?\s*/\s*(\d+(?:[.,]\d+)?)\s*(k?V|A)?", text or "", re.I)
    if not m:
        return None
    a, ua, b, ub = float(m.group(1).replace(",", ".")), (m.group(2) or ""), float(m.group(3).replace(",", ".")), (m.group(4) or "")
    return a, ua.lower(), b, ub.lower()


def prefill_from_ratio_items(rows, device):
    """Ambil rasio CT/VT device dari item '… · Rasio CT/VT' (nilai teks bebas mis. '2000/1 A', '150/0.11 kV')."""
    s = dict(INJ.DEFAULT_SETUP)
    for r in rows:
        if "Rasio CT/VT" not in (r["section"] or "") or not (r["value"] or "").strip():
            continue
        d = r["description"] or ""
        if not d.startswith(device + " · "):
            continue
        rr = _ratio_from_value(r["value"])
        if not rr:
            continue
        a, ua, b, ub = rr
        if d.endswith("CT ratio"):
            s["ct_p"], s["ct_s"] = a, b
        elif d.endswith("VT ratio"):
            kv = a / 1000 if (ua == "v" or (not ua and a > 1000)) else a
            v = b * 1000 if (ub == "kv" or (not ub and b < 5)) else b
            s["vt_p"], s["vt_s"] = kv, v
    return s


def ratio_devices(rows):
    out = []
    for r in rows:
        if "Rasio CT/VT" in (r["section"] or ""):
            dev = (r["description"] or "").split(" · ")[0].strip()
            if dev and dev not in out:
                out.append(dev)
    return out


# ---------------------------------------------------------------- dialog: buat blok / setup / titik
class SetupForm(QWidget):
    def __init__(self, s):
        super().__init__()
        f = QFormLayout(self)
        f.setContentsMargins(0, 0, 0, 0)
        self.ct_p = _spin(s["ct_p"], 0.001, 1e6, 3)
        self.ct_s = QComboBox()
        self.ct_s.setEditable(True)
        self.ct_s.addItems(["1", "5"])
        self.ct_s.setCurrentText(INJ._g(s["ct_s"]))
        h = QHBoxLayout()
        h.addWidget(self.ct_p, 2)
        h.addWidget(QLabel("A  /"))
        h.addWidget(self.ct_s, 1)
        h.addWidget(QLabel("A"))
        f.addRow(tr("Rasio CT"), h)
        self.vt_p = _spin(s["vt_p"], 0.001, 2000, 3)
        self.vt_s = _spin(s["vt_s"], 1, 1000, 1)
        h = QHBoxLayout()
        h.addWidget(self.vt_p, 2)
        h.addWidget(QLabel("kV  /"))
        h.addWidget(self.vt_s, 1)
        h.addWidget(QLabel(tr("V (L-L)")))
        f.addRow(tr("Rasio VT"), h)
        self.tol = _spin(s["tol"], 0, 50, 2, " %")
        self.tol_pf = _spin(s["tol_pf"], 0, 1, 3)
        self.tol_f = _spin(s["tol_f"], 0, 5, 3, " Hz")
        f.addRow(tr("Toleransi I, V, P, Q"), self.tol)
        f.addRow(tr("Toleransi PF (±)"), self.tol_pf)
        f.addRow(tr("Toleransi frekuensi (±)"), self.tol_f)
        note = QLabel(tr("P dan Q dinilai terhadap daya semu S (MVA), supaya Q≈0 pada φ = 0° tidak menghasilkan error % tak hingga."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
        f.addRow(note)

    def value(self):
        try:
            cts = float(self.ct_s.currentText().replace(",", "."))
        except ValueError:
            cts = 0
        return dict(ct_p=self.ct_p.value(), ct_s=cts, vt_p=self.vt_p.value(), vt_s=self.vt_s.value(),
                    tol=self.tol.value(), tol_pf=self.tol_pf.value(), tol_f=self.tol_f.value())


def parse_list(text):
    out = []
    for p in re.split(r"[;\s]+|,(?=\s)|,(?!\d)", text or ""):
        p = p.strip().replace(",", ".")
        if not p:
            continue
        try:
            out.append(float(p))
        except ValueError:
            return None
    return out


class CreateDialog(QDialog):
    """Blok uji injeksi baru untuk satu device panel."""

    def __init__(self, parent, rows):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle(tr("Uji injeksi CT/VT baru"))
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.dev = QComboBox()
        self.dev.setEditable(True)
        devs = ratio_devices(rows)
        self.dev.addItems(devs or ["BCU"])
        bcu = next((d for d in devs if "BCU" in d), None)
        if bcu:
            self.dev.setCurrentText(bcu)
        self.dev.setToolTip(tr("Alat yang dibaca nilainya (BCU, meter, relay). Rasio diambil dari item Rasio CT/VT bila sudah diisi."))
        f.addRow(tr("Device / alat baca"), self.dev)
        v.addLayout(f)
        self.form = SetupForm(prefill_from_ratio_items(rows, self.dev.currentText()))
        v.addWidget(self.form)
        self.dev.currentTextChanged.connect(self._dev_changed)
        g = QFormLayout()
        self.pi = QLineEdit("10, 50, 100")
        self.pi.setToolTip(tr("Satu titik uji per angka, dipisah koma"))
        self.pv = _spin(100, 0, 200, 1, " %")
        self.phi = _spin(30, -180, 180, 1, " °")
        self.hz = _spin(50, 40, 70, 2, " Hz")
        g.addRow(tr("Injeksi arus (% In)"), self.pi)
        g.addRow(tr("Injeksi tegangan (% Vn)"), self.pv)
        g.addRow(tr("Sudut φ (V–I, + = lagging)"), self.phi)
        g.addRow(tr("Frekuensi"), self.hz)
        v.addLayout(g)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.button(QDialogButtonBox.Ok).setText(tr("Buat"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _dev_changed(self, dev):
        s = prefill_from_ratio_items(self.rows, dev)
        if s != INJ.DEFAULT_SETUP:
            self.form.ct_p.setValue(s["ct_p"])
            self.form.ct_s.setCurrentText(INJ._g(s["ct_s"]))
            self.form.vt_p.setValue(s["vt_p"])
            self.form.vt_s.setValue(s["vt_s"])

    def accept(self):
        s = self.form.value()
        if not self.dev.currentText().strip():
            warn(self, tr("Isi nama device / alat baca."))
            return
        if s["ct_s"] <= 0 or s["ct_p"] <= 0:
            warn(self, tr("Rasio CT belum benar."))
            return
        pis = parse_list(self.pi.text())
        if not pis:
            warn(self, tr("Isi % injeksi arus, contoh: 10, 50, 100"))
            return
        super().accept()

    def values(self):
        pis = parse_list(self.pi.text())
        return (self.dev.currentText().strip(), self.form.value(),
                [(p, self.pv.value(), self.phi.value(), self.hz.value()) for p in pis])


class SetupDialog(QDialog):
    def __init__(self, parent, s):
        super().__init__(parent)
        self.setWindowTitle(tr("Setup uji injeksi"))
        self.setMinimumWidth(480)
        v = QVBoxLayout(self)
        self.form = SetupForm(s)
        v.addWidget(self.form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def accept(self):
        s = self.form.value()
        if s["ct_s"] <= 0 or s["ct_p"] <= 0 or s["vt_p"] <= 0 or s["vt_s"] <= 0:
            warn(self, tr("Rasio CT/VT belum benar."))
            return
        super().accept()


class PointDialog(QDialog):
    def __init__(self, parent, last=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Tambah titik uji"))
        f = QFormLayout(self)
        last = last or dict(pi=0, pv=100, phi=30, hz=50)
        self.pi = _spin(min(200, last["pi"] + 10), 0, 300, 1, " %")
        self.pv = _spin(last["pv"], 0, 200, 1, " %")
        self.phi = _spin(last["phi"], -180, 180, 1, " °")
        self.hz = _spin(last["hz"], 40, 70, 2, " Hz")
        f.addRow(tr("Injeksi arus (% In)"), self.pi)
        f.addRow(tr("Injeksi tegangan (% Vn)"), self.pv)
        f.addRow(tr("Sudut φ (V–I, + = lagging)"), self.phi)
        f.addRow(tr("Frekuensi"), self.hz)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        return self.pi.value(), self.pv.value(), self.phi.value(), self.hz.value()


class OcrReviewDialog(QDialog):
    """Hasil baca foto HMI: centang nilai yang benar, lalu masukkan ke Actual."""

    def __init__(self, parent, image_data, found, exp, current, raw):
        super().__init__(parent)
        self.setWindowTitle(tr("Hasil baca foto HMI"))
        self.resize(860, 520)
        h = QHBoxLayout(self)
        pic = QLabel()
        pm = QPixmap()
        pm.loadFromData(image_data)
        pic.setPixmap(pm.scaled(360, 460, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        pic.setAlignment(Qt.AlignTop)
        h.addWidget(pic)
        v = QVBoxLayout()
        h.addLayout(v, 1)
        self.checks = {}
        if not found:
            lb = QLabel(tr("Tidak ada nilai yang terbaca. Coba foto yang lebih dekat, tegak lurus, dan tidak silau."))
            lb.setWordWrap(True)
            v.addWidget(lb)
        else:
            top = QLabel(tr("Cek setiap nilai dengan foto sebelum dimasukkan. Nilai yang ragu tidak dicentang otomatis."))
            top.setWordWrap(True)
            top.setStyleSheet(f"color:{T.MUTED};")
            v.addWidget(top)
            g = QGridLayout()
            g.setHorizontalSpacing(12)
            for c, t in enumerate([tr("Pakai"), tr("Besaran"), tr("Terbaca di foto"), tr("Nilai"), tr("Expected"), tr("Keyakinan")]):
                lb = QLabel(f"<b>{t}</b>")
                g.addWidget(lb, 0, c)
            for i, k in enumerate(k for k in INJ.KEYS if k in found):
                it = found[k]
                cb = QCheckBox()
                cb.setChecked(it["conf"] != "low")
                self.checks[k] = (cb, it["value"])
                g.addWidget(cb, i + 1, 0)
                g.addWidget(QLabel(key_label(k)), i + 1, 1)
                g.addWidget(QLabel(it["seen"]), i + 1, 2)
                val = INJ.fmt(it["value"], INJ.DEC[k]) + " " + INJ.UNIT[k]
                old = (current.get(k) or "").strip()
                g.addWidget(QLabel(f"<b>{val}</b>" + (f" <span style='color:{T.MUTED}'>(" + tr("ganti {0}", old) + ")</span>" if old else "")), i + 1, 3)
                g.addWidget(QLabel(INJ.fmt(exp[k][0], INJ.DEC[k])), i + 1, 4)
                col = {"high": T.OK, "medium": T.WARN, "low": T.NG}[it["conf"]]
                g.addWidget(QLabel(f"<span style='color:{col}'>" + {"high": tr("Jelas"), "medium": tr("Agak ragu"), "low": tr("Ragu")}[it["conf"]] + "</span>"), i + 1, 5)
            v.addLayout(g)
        missing = [key_label(k) for k in INJ.KEYS if k not in found]
        if found and missing:
            lb = QLabel(tr("Tidak terbaca: {0}. Isi manual atau coba foto lain.", ", ".join(missing)))
            lb.setWordWrap(True)
            lb.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
            v.addWidget(lb)
        raw_box = QLineEdit(" | ".join(x for x in raw.splitlines() if x.strip()))
        raw_box.setReadOnly(True)
        raw_box.setToolTip(tr("Teks mentah hasil OCR"))
        raw_box.setStyleSheet(f"color:{T.MUTED}; font-size:8pt;")
        v.addWidget(QLabel(tr("Teks mentah hasil OCR:")))
        v.addWidget(raw_box)
        v.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = bb.button(QDialogButtonBox.Ok)
        ok.setObjectName("primary")
        ok.setText(tr("Masukkan ke Actual"))
        ok.setEnabled(bool(found))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return {k: val for k, (cb, val) in self.checks.items() if cb.isChecked()}


# ---------------------------------------------------------------- blok di halaman Checking
class InjectionBlock(QFrame):
    def __init__(self, view, section, rows, punches):
        super().__init__()
        self.view = view
        self.section = section
        self.rows = rows
        self.punches = punches
        self.setObjectName("injBlock")
        self.setStyleSheet("QFrame#injBlock { background:#FFFFFF; border-bottom:1px solid #E3E6E3; }")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 8)
        self.lay.setSpacing(0)
        self.edits = {}          # cid → QLineEdit
        self.build()

    # ---- data
    @property
    def db(self):
        return self.view.main.db

    def setup(self):
        g = INJ.group(self.rows)
        s = INJ.parse_setup(g["setup"]["criteria"]) if g["setup"] is not None else None
        return g, s

    def reload_rows(self):
        self.rows = [r for r in self.db.panel_checks(self.view.panel_id) if r["section"] == self.section]

    def stats(self):
        g, s = self.setup()
        done = ng = total = 0
        for p in g["points"]:
            for r in p["rows"].values():
                total += 1
                done += 1 if r["result"] else 0
                ng += 1 if r["result"] == "NG" else 0
        return done, ng, total

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

    # ---- tampilan
    def clear(self):
        _clear_layout(self.lay)
        self.edits = {}

    def build(self):
        self.clear()
        g, s = self.setup()
        ro = W.RO
        head = QWidget()
        head.setStyleSheet("background:#F6F7F5;")
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 9, 10, 7)
        lab = QLabel(self.section)
        lab.setStyleSheet(f"font-weight:700; color:{T.TEXT}; font-size:9.5pt; background:transparent;")
        h.addWidget(lab)
        done, ng, total = self.stats()
        self.cnt = QLabel(f"{done}/{total}" + (f"  ·  <span style='color:{T.NG}'>{ng} NG</span>" if ng else ""))
        self.cnt.setTextFormat(Qt.RichText)
        self.cnt.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt; background:transparent;")
        h.addWidget(self.cnt)
        h.addStretch()
        if not ro:
            h.addWidget(btn(tr("Setup…"), "edit", "ghost", tr("Ubah rasio CT/VT dan toleransi"), self.edit_setup))
            h.addWidget(btn(tr("Titik uji"), "plus", "ghost", tr("Tambah titik uji"), self.add_point))
        self.lay.addWidget(head)

        info_ = QLabel()
        info_.setWordWrap(True)
        info_.setContentsMargins(14, 6, 14, 2)
        if s:
            info_.setText(tr("CT {0}/{1} A · VT {2} kV/{3} V · toleransi {4}% (P, Q terhadap S) · PF ±{5} · f ±{6} Hz",
                             INJ._g(s["ct_p"]), INJ._g(s["ct_s"]), INJ._g(s["vt_p"]), INJ._g(s["vt_s"]),
                             INJ._g(s["tol"]), INJ._g(s["tol_pf"]), INJ._g(s["tol_f"])))
            info_.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
        else:
            info_.setText(tr("Setup rasio CT/VT belum terbaca. Klik Setup… untuk mengisi rasio; sementara expected diambil dari kriteria item."))
            info_.setStyleSheet(f"color:{T.NG}; font-size:8.5pt;")
        self.lay.addWidget(info_)
        for p in g["points"]:
            self.lay.addWidget(self._point_widget(p, s))
        if not g["points"]:
            e = QLabel(tr("Belum ada titik uji. Klik + Titik uji."))
            e.setContentsMargins(14, 8, 14, 8)
            e.setStyleSheet(f"color:{T.MUTED};")
            self.lay.addWidget(e)

    def _exp(self, s, p, k, r):
        if s:
            return INJ.expected(s, p)[k]
        m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)", r["criteria"] or "")
        return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)

    def _point_widget(self, p, s):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 10, 14, 4)
        v.setSpacing(4)
        top = QHBoxLayout()
        res = [r["result"] for r in p["rows"].values()]
        nng = res.count("NG")
        st = ("NG", T.NG) if nng else (("OK", T.OK) if all(res) and res else ("", T.MUTED))
        t = QLabel(f"<b>T{p['n']}</b> &nbsp; " + tr("I {0}% · V {1}% · φ {2}° · {3} Hz",
                                                  INJ._g(p["pi"]), INJ._g(p["pv"]), INJ._g(p["phi"]), INJ._g(p["hz"])))
        top.addWidget(t)
        pill = Pill(tr("Lulus") if st[0] == "OK" else (tr("{0} NG", nng) if nng else tr("{0} belum diisi", res.count(""))), st[1])
        top.addWidget(pill)
        if s:
            sec = INJ.secondary(s, p)
            inj = QLabel(tr("Injeksi: {0} A ∠{1}° · {2} V L-N · {3} Hz", f"{sec['i']:.3f}", INJ._g(-p["phi"]),
                            f"{sec['v_ln']:.2f}", INJ._g(p["hz"])))
            inj.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
            top.addSpacing(8)
            top.addWidget(inj)
        top.addStretch()
        first = p["rows"].get("IA") or next(iter(p["rows"].values()))
        photos = sum(self.view.photo_counts.get(r["id"], 0) for r in p["rows"].values())
        cam = QToolButton()
        cam.setIcon(T.icon("camera", T.OK if photos else T.SUBTLE, 16))
        cam.setText(str(photos) if photos else "")
        cam.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        cam.setAutoRaise(True)
        cam.setCursor(Qt.PointingHandCursor)
        cam.setToolTip(tr("Foto evidence titik uji ini (layar HMI/BCU, test set)"))
        cam.clicked.connect(lambda _=False, cid=first["id"]: self._evidence(cid))
        top.addWidget(cam)
        if not W.RO:
            from .. import ocr
            if ocr.available():
                b = btn(tr("Baca foto HMI"), "camera", None, tr("Isi Actual otomatis dari foto layar HMI/BCU (OCR di laptop ini, gratis)"))
                b.clicked.connect(lambda _=False, pp=p: self._ocr_menu(pp, b))
                top.addWidget(b)
            more = QToolButton()
            more.setIcon(T.icon("more", T.MUTED, 18))
            more.setAutoRaise(True)
            m = QMenu(more)
            m.addAction(T.icon("trash", T.NG), tr("Hapus titik uji T{0}", p["n"]), lambda pp=p: self._delete_point(pp))
            more.setMenu(m)
            more.setPopupMode(QToolButton.InstantPopup)
            more.setStyleSheet("QToolButton::menu-indicator { image: none; }")
            top.addWidget(more)
        v.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        for c, txt in enumerate([tr("Besaran"), tr("Expected"), tr("Actual"), tr("Error"), tr("Status"), ""]):
            lb = QLabel(txt)
            lb.setStyleSheet(f"color:{T.MUTED}; font-size:8pt; font-weight:600;")
            grid.addWidget(lb, 0, c, alignment=Qt.AlignRight if c in (1, 3) else Qt.AlignLeft)
        for i, k in enumerate(k for k in INJ.KEYS if k in p["rows"]):
            r = p["rows"][k]
            exp, tol = self._exp(s, p, k, r)
            name = QLabel(key_label(k))
            name.setStyleSheet("font-weight:600;")
            grid.addWidget(name, i + 1, 0)
            el = QLabel(f"{INJ.fmt(exp, INJ.DEC[k])} <span style='color:{T.MUTED}'>{INJ.UNIT[k] if k != 'PF' else ''} ±{INJ.fmt(tol, INJ.DEC[k])}</span>")
            el.setTextFormat(Qt.RichText)
            grid.addWidget(el, i + 1, 1, alignment=Qt.AlignRight)
            e = QLineEdit(r["value"] or "")
            e.setFixedWidth(110)
            e.setAlignment(Qt.AlignRight)
            e.setReadOnly(W.RO)
            e.setStyleSheet("QLineEdit { border:1px solid #C9CEC9; background:white; }")
            e.editingFinished.connect(lambda cid=r["id"], kk=k, pp=p, ed=e: self._save(cid, kk, pp, ed.text()))
            self.edits[r["id"]] = e
            grid.addWidget(e, i + 1, 2)
            err = QLabel(INJ.error_text(k, exp, tol, r["value"], s))
            err.setStyleSheet(f"color:{T.MUTED}; font-family:monospace;")
            grid.addWidget(err, i + 1, 3, alignment=Qt.AlignRight)
            res = r["result"] or ""
            pl = Pill({"OK": "OK", "NG": "NG"}.get(res, tr("Belum")), {"OK": T.OK, "NG": T.NG}.get(res, T.MUTED))
            grid.addWidget(pl, i + 1, 4, alignment=Qt.AlignLeft)
            pb = QToolButton()
            pb.setAutoRaise(True)
            pb.setCursor(Qt.PointingHandCursor)
            ps = self.punches.get(r["id"], [])
            open_n = sum(1 for x in ps if x["status"] != "Closed")
            col = T.NG if open_n else (T.OK if ps else (T.NG if res == "NG" else T.SUBTLE))
            pb.setIcon(T.icon("punch", col, 15))
            pb.setText(f"{open_n}/{len(ps)}" if ps else "")
            pb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            pb.setToolTip(tr("Punch dari besaran ini"))
            pb.clicked.connect(lambda _=False, rr=r: self._punch(rr))
            pb.setVisible(bool(ps) or (res == "NG" and not W.RO))
            grid.addWidget(pb, i + 1, 5)
        grid.setColumnStretch(6, 1)
        v.addLayout(grid)
        return w

    # ---- aksi
    def _save(self, cid, key, p, text):
        text = (text or "").strip()
        r = self.db.check(cid)
        if text == (r["value"] or ""):
            return
        g, s = self.setup()
        exp, tol = self._exp(s, p, key, r)
        res = INJ.judge(exp, tol, text)
        f = dict(value=text)
        if res != (r["result"] or ""):
            f["result"] = res
        self.db.set_check(cid, **f)
        self.reload_rows()
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        self.reload_rows()
        self.build()
        self.view.stats_changed()

    def apply_values(self, p, vals):
        """vals: {key: angka} dari hasil baca foto."""
        g, s = self.setup()
        n = 0
        for k, val in vals.items():
            r = p["rows"].get(k)
            if r is None:
                continue
            exp, tol = self._exp(s, p, k, r)
            text = f"{val:.{max(INJ.DEC[k], 1)}f}".rstrip("0").rstrip(".") if k not in ("PF",) else f"{val:.3f}"
            self.db.set_check(r["id"], value=text, result=INJ.judge(exp, tol, text))
            n += 1
        self.refresh()
        return n

    def edit_setup(self):
        g, s = self.setup()
        d = SetupDialog(self, s or dict(INJ.DEFAULT_SETUP))
        if not d.exec():
            return
        ns = d.form.value()
        if ns == s:
            return
        filled = sum(1 for p in g["points"] for r in p["rows"].values() if (r["value"] or "").strip())
        if filled and not ask(self, tr("{0} nilai actual sudah terisi. Expected dan status OK/NG akan dihitung ulang dengan "
                                       "rasio baru. Lanjutkan?", filled)):
            return
        defs = []
        if g["setup"] is not None:
            defs.append((g["setup"]["id"], dict(criteria=INJ.setup_text(ns))))
        for p in g["points"]:
            ex = INJ.expected(ns, p)
            for k, r in p["rows"].items():
                c = INJ.criteria_text(k, *ex[k])
                if c != r["criteria"]:
                    defs.append((r["id"], dict(criteria=c)))
        if not self._redefine(defs):
            return
        if g["setup"] is None:
            add_items(self.db, self.view.panel_id, [(self.section, INJ.SETUP_DESC, INJ.setup_text(ns), INJ.SETUP_UNIT)],
                      setup_ok=True)
        self.reload_rows()
        g, s2 = self.setup()
        for p in g["points"]:
            ex = INJ.expected(ns, p)
            for k, r in p["rows"].items():
                if (r["value"] or "").strip():
                    res = INJ.judge(*ex[k], r["value"])
                    if res != (r["result"] or ""):
                        self.db.set_check(r["id"], result=res)
        self.refresh()

    def _redefine(self, defs):
        """Ubah kriteria item tanpa menimpa hasil yang sedang diisi tim (PATCH definisi ke cloud bila login)."""
        if not defs:
            return True
        main = self.view.main
        sync = getattr(main, "sync", None)
        if sync is not None and sync.cfg.logged_in:
            if sync.busy():
                warn(self, tr("Sinkron sedang berjalan. Tunggu sebentar lalu ulangi."))
                return False
            from ..cloud import SupabaseClient, rename_check
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                c = SupabaseClient(sync.cfg.url, sync.cfg.key, timeout=20)
                c.restore(sync.cfg.get("refresh_token"))
                sync.cfg.set("refresh_token", c.refresh_token)
                for cid, d in defs:
                    rename_check(self.db, c, cid, **d)
            except Exception as e:  # noqa: BLE001
                QApplication.restoreOverrideCursor()
                warn(self, tr("Setup tidak tersimpan. Ubah setup butuh koneksi ke cloud supaya hasil tim tidak tertimpa.\n\n{0}", e))
                return False
            QApplication.restoreOverrideCursor()
        else:
            for cid, d in defs:
                self.db.update_check_item(cid, **d)
        return True

    def add_point(self):
        g, s = self.setup()
        if not s:
            warn(self, tr("Isi setup rasio CT/VT dulu (tombol Setup…)."))
            return
        last = g["points"][-1] if g["points"] else None
        d = PointDialog(self, last)
        if not d.exec():
            return
        pi, pv, phi, hz = d.values()
        n = max([p["n"] for p in g["points"]] or [0]) + 1
        add_items(self.db, self.view.panel_id, INJ.point_items(self.section, s, n, pi, pv, phi, hz))
        self.refresh()

    def _delete_point(self, p):
        filled = [r for r in p["rows"].values() if r["result"] or (r["value"] or "").strip()]
        if filled:
            warn(self, tr("T{0} sudah berisi hasil uji, tidak bisa dihapus. Kosongkan nilainya dulu bila memang salah buat.", p["n"]))
            return
        if ask(self, tr("Hapus titik uji T{0}?", p["n"])):
            for r in p["rows"].values():
                self.db.delete_check_item(r["id"])
            self.refresh()

    def _evidence(self, cid):
        from .dialogs import EvidenceDialog
        EvidenceDialog(self, self.db, cid, getattr(self.view, "tag_text", "")).exec()
        self.view.photo_counts = self.db.check_photo_counts(self.view.panel_id)
        self.build()
        self.view.main.refresh_all(except_page=self.view.page)

    def _punch(self, r):
        from .dialogs import IssueDialog
        main = self.view.main
        ps = self.punches.get(r["id"], [])
        if ps:
            m = QMenu(self)
            for x in ps:
                m.addAction(f"{x['code']}  [{T.STATUS_LABEL.get(x['status'], x['status'])}]  {x['title'][:50]}".replace("&", "&&"),
                            lambda iid=x["id"]: self._open_punch(iid))
            if not W.RO:
                m.addSeparator()
                m.addAction(T.icon("plus"), tr("Punch baru dari besaran ini…"), lambda: self._new_punch(r))
            m.exec(QCursor.pos())
        else:
            self._new_punch(r)

    def _open_punch(self, iid):
        from .dialogs import IssueDialog
        main = self.view.main
        if IssueDialog(self, main.db, main.project_id, iid).exec():
            self._after_punch()

    def _new_punch(self, r):
        from .dialogs import IssueDialog
        main = self.view.main
        p = INJ.parse_point(r["description"]) or {}
        desc = tr("Uji injeksi CT/VT: {0} — {1}.", self.section, r["description"])
        desc += tr("\nExpected: {0} {1}", r["criteria"], r["unit"] or "")
        if r["value"]:
            desc += tr("\nActual: {0} {1}", r["value"], r["unit"] or "")
        d = IssueDialog(self, main.db, main.project_id, panel_id=self.view.panel_id, check_id=r["id"],
                        preset={"title": tr("{0} tidak sesuai saat injeksi {1}% ({2})", key_label(p.get("key", "")),
                                            INJ._g(p.get("pi", 0)), INJ.device_of(self.section)),
                                "description": desc, "category": "SCADA / HMI", "severity": "Major"})
        if d.exec():
            self._after_punch()

    def _after_punch(self):
        self.view.reload_punches()
        self.view.main.refresh_all(except_page=self.view.page)

    # ---- baca foto HMI
    def _ocr_menu(self, p, anchor):
        m = QMenu(self)
        m.addAction(T.icon("camera"), tr("Pilih foto…"), lambda: self._ocr_file(p))
        m.addAction(tr("Tempel screenshot dari clipboard"), lambda: self._ocr_clipboard(p))
        photos = []
        for r in p["rows"].values():
            photos += [(r["id"], a) for a in self.db.check_photos(r["id"])]
        if photos:
            m.addSection(tr("Foto evidence titik ini"))
            for cid, a in photos:
                m.addAction(a["caption"] or a["filename"] or "foto", lambda aid=a["id"]: self._ocr_run(p, self.db.attachment_data(aid), None))
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _ocr_file(self, p):
        fp, _ = QFileDialog.getOpenFileName(self, tr("Pilih foto layar HMI"), "", tr("Gambar (*.jpg *.jpeg *.png *.bmp *.heic)"))
        if not fp:
            return
        with open(fp, "rb") as fh:
            raw = fh.read()
        self._ocr_run(p, raw, os.path.basename(fp))

    def _ocr_clipboard(self, p):
        img = QApplication.clipboard().image()
        if img.isNull():
            warn(self, tr("Clipboard tidak berisi gambar. Ambil screenshot dulu (mis. Win+Shift+S / Cmd+Ctrl+Shift+4)."))
            return
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        self._ocr_run(p, bytes(buf.data()), f"screenshot_{_dt.datetime.now():%Y%m%d_%H%M%S}.jpg")

    def _ocr_run(self, p, data, save_name):
        """data: gambar asli (resolusi penuh untuk OCR). save_name: simpan juga sebagai foto evidence titik ini."""
        from .. import ocr
        g, s = self.setup()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            text = ocr.recognize(data)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            warn(self, tr("Foto tidak bisa dibaca: {0}", e))
            return
        QApplication.restoreOverrideCursor()
        found = INJ.parse_hmi(text)
        exp = {k: self._exp(s, p, k, p["rows"][k]) for k in p["rows"]}
        cur = {k: r["value"] for k, r in p["rows"].items()}
        d = OcrReviewDialog(self, data, found, exp, cur, text)
        if save_name:
            try:
                from ..imaging import compress
                first = p["rows"].get("IA") or next(iter(p["rows"].values()))
                self.db.add_check_photo(first["id"], save_name, compress(data), caption=tr("Foto HMI T{0}", p["n"]))
                self.view.photo_counts = self.db.check_photo_counts(self.view.panel_id)
            except Exception:  # noqa: BLE001 — foto evidence gagal disimpan tidak boleh menggagalkan baca nilai
                pass
        if d.exec():
            vals = d.values()
            if vals:
                n = self.apply_values(p, vals)
                self.view.main.statusBar().showMessage(tr("{0} nilai dimasukkan dari foto", n), 4000)
                return
        self.build()


def _clear_layout(lay):
    """Lepas widget lama dari blok sebelum dihapus, supaya tidak sempat tergambar bertumpuk dengan yang baru."""
    while lay.count():
        it = lay.takeAt(0)
        w_ = it.widget()
        if w_ is not None:
            w_.hide()
            w_.setParent(None)
            w_.deleteLater()
        elif it.layout() is not None:
            _clear_layout(it.layout())


def add_items(db, panel_id, items, setup_ok=True):
    """Tambah item di akhir checklist panel (tanpa menggeser sort item lain → hasil tim tidak ikut ter-push ulang).
    Item setup langsung bertanda OK (rasio sudah dikonfigurasi)."""
    mx = db.q1("SELECT COALESCE(MAX(sort),0) m FROM panel_check WHERE panel_id=?", (panel_id,))["m"]
    ids = []
    for i, (sec, desc, crit, unit) in enumerate(items, 1):
        cid = db._insert("panel_check", dict(panel_id=panel_id, section=sec, description=desc, criteria=crit,
                                             unit=unit, sort=mx + i))
        if unit == INJ.SETUP_UNIT and setup_ok:
            db.set_check(cid, result="OK")
        ids.append(cid)
    return ids


def create_block(view):
    """Dialog + tulis blok baru di panel yang sedang dibuka. True bila dibuat."""
    db = view.main.db
    rows = db.panel_checks(view.panel_id)
    d = CreateDialog(view, rows)
    if not d.exec():
        return False
    dev, s, points = d.values()
    secs = [r["section"] for r in rows]
    if any(INJ.is_injection_section(x) and INJ.device_of(x) == dev for x in secs):
        if not ask(view, tr("Panel ini sudah punya uji injeksi untuk {0}. Buat blok kedua?", dev)):
            return False
    items = INJ.block_items(dev, INJ.next_letter(secs), s, points)
    add_items(db, view.panel_id, items)
    p = db.panel(view.panel_id)
    db.log(p["project_id"], "panel", view.panel_id, "injection", f"{p['tag']}: uji injeksi CT/VT {dev} ({len(points)} titik)")
    return True
