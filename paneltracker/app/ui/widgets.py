"""Komponen UI custom (kartu, chart, tombol hasil, delegate kartu)."""
from __future__ import annotations

from ..i18n import tr

import datetime as dt
import math

from PySide6.QtCore import QEvent, QObject, QDate, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QCheckBox, QDateEdit, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSizePolicy, QStyle, QStyledItemDelegate, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..db import SEV_SHORT, parse_date
from . import theme as T

RO = False  # mode viewer (baca saja) — diatur MainWindow.apply_role()


# ------------------------------------------------------------------ dialogs
def info(parent, text, title="Info"):
    QMessageBox.information(parent, title, text)


def warn(parent, text, title=None):
    title = title or tr('Perhatian')
    QMessageBox.warning(parent, title, text)


def ask(parent, text, title=None) -> bool:
    title = title or tr('Konfirmasi')
    return QMessageBox.question(parent, title, text, QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) == QMessageBox.Yes


def item(text="", data=None, align=None, fg=None, bg=None, bold=False, tip=None):
    it = QTableWidgetItem("" if text is None else str(text))
    if data is not None:
        it.setData(Qt.UserRole, data)
    if align is not None:
        it.setTextAlignment(align)
    if fg is not None:
        it.setForeground(QBrush(QColor(fg)))
    if bg is not None:
        it.setBackground(QBrush(QColor(bg)))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    if tip:
        it.setToolTip(tip)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


def btn(text="", icon_name=None, obj=None, tip=None, slot=None, color=None):
    # '&' di QPushButton = tanda shortcut (jadi garis bawah); tampilkan apa adanya
    text = (text or "").replace("&&", "\0").replace("&", "&&").replace("\0", "&&")
    b = QPushButton(text)
    if icon_name:
        b.setIcon(T.icon(icon_name, color or (T.ON_SIGNAL if obj == "primary" else T.MUTED), 18))
        b.setIconSize(QSize(16, 16))
    if obj:
        b.setObjectName(obj)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(slot)
    b.setCursor(Qt.PointingHandCursor)
    return b


def label(text="", size=None, bold=False, color=None, wrap=False):
    l_ = QLabel(text)
    css = []
    if size:
        css.append(f"font-size:{size}pt")
    if bold:
        css.append("font-weight:700")
    if color:
        css.append(f"color:{color}")
    if css:
        l_.setStyleSheet(";".join(css) + ";")
    l_.setWordWrap(wrap)
    return l_


def shadow(w, blur=18, alpha=22, dy=3):
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setColor(QColor(15, 23, 42, alpha))
    eff.setOffset(0, dy)
    w.setGraphicsEffect(eff)


class Card(QFrame):
    def __init__(self, title=None, parent=None, pad=16, right=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(pad, pad - 2, pad, pad)
        self.lay.setSpacing(10)
        if title:
            h = QHBoxLayout()
            t = QLabel(title)
            t.setObjectName("cardTitle")
            h.addWidget(t)
            h.addStretch()
            if right:
                for w in right if isinstance(right, (list, tuple)) else [right]:
                    h.addWidget(w)
            self.lay.addLayout(h)


class PageHeader(QWidget):
    def __init__(self, title, sub="", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        v = QVBoxLayout()
        v.setSpacing(0)
        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")
        self.sub = QLabel(sub)
        self.sub.setObjectName("pageSub")
        self.sub.setWordWrap(True)
        v.addWidget(self.title)
        v.addWidget(self.sub)
        lay.addLayout(v, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)

    def add(self, *widgets):
        for w in widgets:
            self.actions.addWidget(w)


class Pill(QLabel):
    def __init__(self, text="", color=T.PRIMARY, bg=None, parent=None):
        super().__init__(text, parent)
        self.set(text, color, bg)

    def set(self, text, color, bg=None):
        self.setText(text)
        bg = bg or T.qcolor(color, 28).name(QColor.HexArgb)
        self.setStyleSheet(f"QLabel {{ color:{color}; background:{bg}; border-radius:3px; padding:2px 8px;"
                           f" font-size:8.5pt; font-weight:700; }}")


class KpiCard(QFrame):
    def __init__(self, title, icon_name, color=T.PRIMARY, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.color = color
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 14, 12)
        lay.setSpacing(10)
        v = QVBoxLayout()
        v.setSpacing(1)
        th = QHBoxLayout()
        th.setSpacing(6)
        self.t = label(title.upper(), 7.5, True, T.MUTED)
        th.addWidget(self.t, 1)
        ic = QLabel()
        ic.setPixmap(T.icon(icon_name, T.SUBTLE, 16).pixmap(16, 16))
        th.addWidget(ic, 0, Qt.AlignRight | Qt.AlignTop)
        v.addLayout(th)
        self.v = label("–", 19, True, T.TEXT)
        self.s = QLabel("")
        self.s.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
        self.s.setTextFormat(Qt.RichText)
        v.addWidget(self.t)
        v.addWidget(self.v)
        v.addWidget(self.s)
        lay.addLayout(v, 1)

    def set(self, value, sub="", alert=False):
        self.v.setText(str(value))
        self.v.setStyleSheet(f"color:{self.color if alert else T.TEXT}; font-size:19pt; font-weight:700;")
        self.s.setText(sub)


class SegmentBar(QWidget):
    """Bar horizontal bertumpuk: [(nilai, warna)]."""

    def __init__(self, height=10, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.parts = []

    def set_parts(self, parts):
        self.parts = parts
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setClipPath(path)
        p.fillRect(r, QColor("#E4E7E4"))
        tot = sum(v for v, _ in self.parts) or 1
        x = 0.0
        for v, c in self.parts:
            w = r.width() * v / tot
            p.fillRect(QRectF(x, 0, w, r.height()), QColor(c))
            x += w
        p.end()


class Ring(QWidget):
    def __init__(self, size=64, width=7, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.w = width
        self.pct = 0.0
        self.color = T.PRIMARY
        self.text = None

    def set(self, pct, color=None, text=None):
        self.pct = max(0.0, min(100.0, pct))
        self.color = color or self.color
        self.text = text
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(self.w / 2 + 1, self.w / 2 + 1, -self.w / 2 - 1, -self.w / 2 - 1)
        p.setPen(QPen(QColor("#E4E7E4"), self.w, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(r)
        if self.pct > 0:
            p.setPen(QPen(QColor(self.color), self.w, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(r, 90 * 16, int(-360 * 16 * self.pct / 100))
        p.setPen(QColor(T.TEXT))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(7.0, self.width() / 6.5))
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self.text or f"{self.pct:.0f}%")
        p.end()


class DonutChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.center_text = ("", "")
        self.setMinimumHeight(200)

    def set_data(self, data, center=("", "")):
        self.data = [(l_, v, c) for l_, v, c in data]
        self.center_text = center
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        lf = QFont(p.font())
        lf.setPointSizeF(9)
        lfm = QFontMetrics(lf)
        legend_w = max([lfm.horizontalAdvance(l_) for l_, _, _ in self.data] or [60]) + 18 + 44
        # donut mengecil dulu agar legenda tidak menimpa lingkaran
        d = max(70, min(h - 16, int(self.width() - legend_w - 32), int(self.width() * 0.5)))
        rect = QRectF(8, (h - d) / 2, d, d)
        tot = sum(v for _, v, _ in self.data)
        width = d * 0.16
        rr = rect.adjusted(width / 2, width / 2, -width / 2, -width / 2)
        if tot == 0:
            p.setPen(QPen(QColor("#E4E7E4"), width))
            p.drawEllipse(rr)
        else:
            start = 90.0
            for _, v, c in self.data:
                if v <= 0:
                    continue
                span = 360.0 * v / tot
                p.setPen(QPen(QColor(c), width, Qt.SolidLine, Qt.FlatCap))
                p.drawArc(rr, int(start * 16), int(-span * 16))
                start -= span
        f = p.font()
        f.setPointSizeF(17)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(T.TEXT))
        p.drawText(rect.adjusted(0, -10, 0, -10), Qt.AlignCenter, self.center_text[0])
        f.setPointSizeF(8)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(T.MUTED))
        p.drawText(rect.adjusted(0, 26, 0, 26), Qt.AlignCenter, self.center_text[1])
        # legend
        x0 = rect.right() + 24
        n = len(self.data)
        lh = 24
        y = (h - n * lh) / 2
        f.setPointSizeF(9)
        p.setFont(f)
        fm = QFontMetrics(f)
        for l_, v, c in self.data:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c))
            p.drawRoundedRect(QRectF(x0, y + 6, 11, 11), 3, 3)
            p.setPen(QColor(T.TEXT))
            txt = str(v)
            room = self.width() - 12 - QFontMetrics(f).horizontalAdvance(txt) - 10 - (x0 + 18)
            p.drawText(QPointF(x0 + 18, y + 16), fm.elidedText(l_, Qt.ElideRight, max(20, int(room))))
            p.setPen(QColor(T.MUTED))
            f.setBold(True)
            p.setFont(f)
            p.drawText(QPointF(self.width() - 12 - QFontMetrics(f).horizontalAdvance(txt), y + 16), txt)
            f.setBold(False)
            p.setFont(f)
            y += lh
        p.end()


class BarChart(QWidget):
    """Grouped bar chart sederhana: labels, series [(nama, [nilai], warna)]."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels, self.series = [], []
        self.setMinimumHeight(200)

    def set_data(self, labels, series):
        self.labels, self.series = labels, series
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        left, right, top, bottom = 30, 8, 26, 24
        f = p.font()
        f.setPointSizeF(8)
        p.setFont(f)
        # legend
        x = left
        for name, _, c in self.series:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c))
            p.drawRoundedRect(QRectF(x, 6, 10, 10), 2, 2)
            p.setPen(QColor(T.MUTED))
            p.drawText(QPointF(x + 15, 15), name)
            x += 26 + QFontMetrics(f).horizontalAdvance(name)
        vmax = max([max(v) if v else 0 for _, v, _ in self.series] + [1])
        step = max(1, math.ceil(vmax / 4))
        vmax = step * 4
        ph = H - top - bottom
        pw = W - left - right
        for k in range(5):
            y = top + ph - ph * k / 4
            p.setPen(QPen(QColor("#E3E6E3"), 1))
            p.drawLine(QPointF(left, y), QPointF(W - right, y))
            p.setPen(QColor(T.SUBTLE))
            p.drawText(QRectF(0, y - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter, str(step * k))
        n = len(self.labels) or 1
        gw = pw / n
        ns = len(self.series) or 1
        bw = min(14.0, gw * 0.7 / ns)
        for i, lab in enumerate(self.labels):
            gx = left + gw * i + (gw - bw * ns - 3 * (ns - 1)) / 2
            for s, (_, vals, c) in enumerate(self.series):
                v = vals[i] if i < len(vals) else 0
                bh = ph * v / vmax
                r = QRectF(gx + s * (bw + 3), top + ph - bh, bw, bh)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c))
                if bh > 0:
                    p.drawRoundedRect(r, 3, 3)
            p.setPen(QColor(T.SUBTLE))
            p.drawText(QRectF(left + gw * i, H - bottom + 4, gw, 16), Qt.AlignCenter, lab)
        p.end()


class ResultButtons(QWidget):
    """Tombol OK / NG / N/A; klik lagi tombol aktif untuk mengosongkan."""
    changed = Signal(str)

    def __init__(self, value="", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.btns = {}
        for key, text in (("OK", "OK"), ("NG", "NG"), ("NA", "N/A")):
            b = QPushButton(text)
            b.setObjectName("res" + key)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda checked, k=key: self._click(k, checked))
            lay.addWidget(b)
            self.btns[key] = b
        self.value = ""
        self.set_value(value)

    def set_value(self, v):
        self.value = v or ""
        for k, b in self.btns.items():
            b.setChecked(k == self.value)

    def _click(self, key, checked):
        if RO:
            self.set_value(self.value)
            return
        self.set_value(key if checked else "")
        self.changed.emit(self.value)


def style_calendar(cal):
    """Warna kalender diset eksplisit (tidak ikut palet/tema Windows) supaya angka selalu terbaca."""
    from PySide6.QtWidgets import QCalendarWidget
    from PySide6.QtGui import QTextCharFormat
    cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
    cal.setFirstDayOfWeek(Qt.Monday)
    cal.setGridVisible(False)
    wd = QTextCharFormat()
    wd.setForeground(QColor(T.TEXT))
    we = QTextCharFormat()
    we.setForeground(QColor(T.NG))
    for d in (Qt.Monday, Qt.Tuesday, Qt.Wednesday, Qt.Thursday, Qt.Friday):
        cal.setWeekdayTextFormat(d, wd)
    for d in (Qt.Saturday, Qt.Sunday):
        cal.setWeekdayTextFormat(d, we)
    hd = QTextCharFormat()
    hd.setForeground(QColor(T.MUTED))
    hd.setBackground(QColor("#F3F4F2"))
    hd.setFontWeight(QFont.DemiBold)
    cal.setHeaderTextFormat(hd)
    today = QTextCharFormat()
    today.setFontWeight(QFont.Bold)
    today.setForeground(QColor(T.INFO))
    cal.setDateTextFormat(QDate.currentDate(), today)
    cal.setMinimumSize(280, 220)


class OptionalDateEdit(QWidget):
    changed = Signal()

    def __init__(self, value=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.chk = QCheckBox()
        self.de = QDateEdit()
        self.de.setCalendarPopup(True)
        self.de.setDisplayFormat("dd-MM-yyyy")
        style_calendar(self.de.calendarWidget())
        lay.addWidget(self.chk)
        lay.addWidget(self.de, 1)
        self.chk.toggled.connect(self.de.setEnabled)
        self.chk.toggled.connect(lambda *_: self.changed.emit())
        self.de.dateChanged.connect(lambda *_: self.changed.emit())
        self.set_value(value)

    def set_value(self, value):
        d = parse_date(value)
        self.chk.setChecked(bool(d))
        self.de.setEnabled(bool(d))
        q = QDate(d.year, d.month, d.day) if d else QDate.currentDate()
        self.de.setDate(q)

    def value(self):
        if not self.chk.isChecked():
            return None
        q = self.de.date()
        return dt.date(q.year(), q.month(), q.day()).isoformat()


def initials(name: str) -> str:
    parts = [p for p in (name or "").replace("/", " ").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()


def avatar_color(name: str) -> str:
    pal = ["#4F5B66", "#5A5F73", "#5E5A52", "#4B6168", "#56604B", "#615459"]
    return pal[sum(map(ord, name or "?")) % len(pal)]


def draw_pill(p: QPainter, x, y, text, color, bg=None, font=None, h=18):
    f = font or p.font()
    fm = QFontMetrics(f)
    w = fm.horizontalAdvance(text) + 14
    r = QRectF(x, y, w, h)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg) if bg else T.qcolor(color, 30))
    p.drawRoundedRect(r, 3, 3)
    p.setPen(QColor(color))
    p.setFont(f)
    p.drawText(r, Qt.AlignCenter, text)
    return w


# ------------------------------------------------------------- elemen "ruang relay"
SEV_FILL = {"Critical": "#D7261E", "Major": "#C4561C", "Minor": "#8A6D00"}   # teks putih di atasnya


def draw_lamp(p: QPainter, cx, cy, r, color):
    """Lampu indikator: bulatan berwarna dengan cincin gelap tipis & pantulan kecil."""
    p.save()
    p.setPen(QPen(QColor(0, 0, 0, 45), 1.5))
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(cx, cy), r, r)
    if color != T.LAMP["off"]:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 90))
        p.drawEllipse(QPointF(cx - r * 0.35, cy - r * 0.35), r * 0.35, r * 0.35)
    p.restore()


def draw_plate(p: QPainter, rect: QRectF, text: str, font: QFont, screws=True):
    """Pelat nama traffolyte: hitam, huruf putih, dua sekrup."""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(T.SIDEBAR))
    p.drawRoundedRect(rect, 3, 3)
    if screws:
        p.setBrush(QColor("#7A8387"))
        for sx in (rect.left() + 6, rect.right() - 6):
            p.drawEllipse(QPointF(sx, rect.center().y()), 2.2, 2.2)
    p.setFont(font)
    p.setPen(QColor(T.ENGRAVE))
    fm = QFontMetrics(font)
    pad = 14 if screws else 8
    p.drawText(rect.adjusted(pad, 0, -pad, 0), Qt.AlignCenter,
               fm.elidedText(text, Qt.ElideRight, int(rect.width() - 2 * pad)))
    p.restore()


def plate_width(text: str, font: QFont, screws=True) -> float:
    return QFontMetrics(font).horizontalAdvance(text) + (34 if screws else 22)


class LampLabel(QWidget):
    """Lampu kecil + teks (status)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color, self.text, self.tcolor = T.LAMP["off"], "", T.TEXT
        self.setMinimumHeight(20)

    def set(self, text, lamp_color, text_color=None):
        self.text, self.color, self.tcolor = text, lamp_color, text_color or T.TEXT
        fm = QFontMetrics(self._font())
        self.setFixedWidth(fm.horizontalAdvance(text) + 26)
        self.update()

    def _font(self):
        f = T.cond_font(10.5, 600)
        return f

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        draw_lamp(p, 8, self.height() / 2, 6, self.color)
        p.setFont(self._font())
        p.setPen(QColor(self.tcolor))
        p.drawText(QRectF(20, 0, self.width() - 20, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)


class PlateLabel(QWidget):
    """Pelat nama panel besar (judul halaman checklist)."""

    def __init__(self, size=16, parent=None):
        super().__init__(parent)
        self.text, self.sub = "", ""
        self.f = T.cond_font(size, 700)
        self.fs = T.cond_font(8.5, 500)
        self.setMinimumHeight(40)

    def set(self, text, sub=""):
        self.text, self.sub = text, sub
        w = max(plate_width(text, self.f), QFontMetrics(self.fs).horizontalAdvance(sub) + 28)
        self.setFixedWidth(int(w) + 8)
        self.setFixedHeight(54 if sub else 40)
        self.update()

    def paintEvent(self, e):
        if not self.text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 0, -8, 0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.SIDEBAR))
        p.drawRoundedRect(r, 3, 3)
        p.setBrush(QColor("#7A8387"))
        for sx in (r.left() + 7, r.right() - 7):
            p.drawEllipse(QPointF(sx, r.center().y()), 2.6, 2.6)
        p.setPen(QColor(T.ENGRAVE))
        p.setFont(self.f)
        if self.sub:
            p.drawText(QRectF(r.left(), r.top() + 4, r.width(), 28), Qt.AlignCenter, self.text)
            p.setFont(self.fs)
            p.setPen(QColor("#B9C1C3"))
            p.drawText(QRectF(r.left() + 14, r.top() + 31, r.width() - 28, 18), Qt.AlignCenter,
                       QFontMetrics(self.fs).elidedText(self.sub, Qt.ElideRight, int(r.width() - 28)))
        else:
            p.drawText(r, Qt.AlignCenter, self.text)


# ------------------------------------------------------------- delegates
class PanelCardDelegate(QStyledItemDelegate):
    """Kartu panel di daftar kiri halaman Checking: lampu status + pelat nama + progres uji."""
    H = 96

    def sizeHint(self, option, index):
        return QSize(200, self.H)

    def paint(self, p: QPainter, option, index):
        d = index.data(Qt.UserRole + 1)
        if not d:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(4, 4, -6, -4)
        sel = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        p.setPen(QPen(QColor(T.TEXT if sel else ("#8C9396" if hover else T.BORDER)), 2 if sel else 1))
        p.setBrush(QColor(T.PRIMARY_L if sel else T.CARD))
        p.drawRoundedRect(r, 5, 5)
        status = d["status"]
        x = r.left() + 12
        # lampu status + lampu punch
        draw_lamp(p, x + 6, r.top() + 20, 6, T.PANEL_LAMP.get(status, T.LAMP["off"]))
        if d["punch"].get("open"):
            draw_lamp(p, x + 22, r.top() + 20, 6, T.LAMP["amber"])
        # pelat nama
        ft = T.cond_font(10.5, 700)
        tag = d["panel"]["tag"]
        px = x + (36 if d["punch"].get("open") else 20)
        pw = min(plate_width(tag, ft, False), r.width() * 0.55)
        draw_plate(p, QRectF(px, r.top() + 9, pw, 23), tag, ft, screws=False)
        # status (teks) kanan atas
        fs = T.cond_font(9, 600)
        p.setFont(fs)
        p.setPen(QColor(T.PANEL_STATUS_COLOR.get(status, T.MUTED)))
        p.drawText(QRectF(px + pw + 6, r.top() + 9, r.right() - (px + pw + 6) - 10, 23), Qt.AlignRight | Qt.AlignVCenter,
                   QFontMetrics(fs).elidedText(tr(status), Qt.ElideRight, int(r.right() - (px + pw + 16))))
        f3 = QFont(option.font)
        f3.setPointSizeF(8.5)
        p.setFont(f3)
        fm3 = QFontMetrics(f3)
        p.setPen(QColor(T.TEXT))
        p.drawText(QPointF(x, r.top() + 50), fm3.elidedText(d["panel"]["name"] or "-", Qt.ElideRight, int(r.width() - 24)))
        p.setPen(QColor(T.MUTED))
        sub = f"{d['panel']['site_name']}  ›  {d['panel']['bay'] or '-'}"
        p.drawText(QPointF(x, r.top() + 66), fm3.elidedText(sub, Qt.ElideRight, int(r.width() - 24)))
        # progres uji
        s = d["stats"]
        bar = QRectF(x, r.bottom() - 15, r.width() - 120, 6)
        path = QPainterPath()
        path.addRoundedRect(bar, 3, 3)
        p.save()
        p.setClipPath(path)
        p.fillRect(bar, QColor("#E4E7E4"))
        tot = s["total"] or 1
        bx = bar.left()
        for k, c in (("OK", T.LAMP["green"]), ("NA", "#8C9396"), ("NG", T.LAMP["red"])):
            w = bar.width() * s[k] / tot
            p.fillRect(QRectF(bx, bar.top(), w, bar.height()), QColor(c))
            bx += w
        p.restore()
        f4 = T.cond_font(9, 600)
        p.setFont(f4)
        p.setPen(QColor(T.MUTED))
        p.drawText(QRectF(bar.right() + 6, bar.top() - 7, 40, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{s['pct']:.0f}%" if s["total"] else "–")
        n = d["punch"].get("open", 0)
        if n:
            p.setPen(QColor(T.NG))
            p.drawText(QRectF(r.right() - 70, bar.top() - 7, 60, 20), Qt.AlignRight | Qt.AlignVCenter,
                       tr("{0} punch", n))
        p.restore()


class PunchCardDelegate(QStyledItemDelegate):
    """Kartu punch di board: blok huruf kategori di kiri, lampu status, judul 2 baris."""
    H = 112

    def sizeHint(self, option, index):
        return QSize(240, self.H)

    def paint(self, p: QPainter, option, index):
        d = index.data(Qt.UserRole + 1)
        if not d:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(2, 4, -4, -4)
        sel = bool(option.state & QStyle.State_Selected)
        path = QPainterPath()
        path.addRoundedRect(r, 5, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.PRIMARY_L if sel else T.CARD))
        p.drawPath(path)
        # blok kategori
        sev = d["severity"]
        blk = QRectF(r.left(), r.top(), 30, r.height())
        p.save()
        p.setClipPath(path)
        p.fillRect(blk, QColor(SEV_FILL.get(sev, "#586064")))
        p.restore()
        p.setPen(QColor("#FFFFFF"))
        p.setFont(T.cond_font(15, 700))
        p.drawText(QRectF(blk.left(), blk.top(), blk.width(), blk.height() - 14), Qt.AlignCenter, SEV_SHORT.get(sev, "?"))
        p.setPen(QPen(QColor(T.TEXT if sel else T.BORDER), 2 if sel else 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        x = blk.right() + 10
        # kode + tanggal
        fc = T.cond_font(9, 600)
        p.setFont(fc)
        p.setPen(QColor(T.MUTED))
        p.drawText(QRectF(x, r.top() + 7, 120, 18), Qt.AlignLeft | Qt.AlignVCenter, d["code"])
        t = dt.date.today().isoformat()
        over = d["status"] != "Closed" and d["due_date"] and d["due_date"] < t
        due = parse_date(d["closed_date"] if d["status"] == "Closed" else d["due_date"])
        if due:
            txt = (tr("selesai {0}", due.strftime("%d %b")) if d["status"] == "Closed" else
                   (tr("telat {0}", due.strftime("%d %b")) if over else due.strftime("%d %b")))
            p.setPen(QColor(T.NG if over else T.MUTED))
            p.drawText(QRectF(r.right() - 110, r.top() + 7, 100, 18), Qt.AlignRight | Qt.AlignVCenter, txt)
        # judul (2 baris)
        f2 = QFont(option.font)
        f2.setPointSizeF(9.5)
        f2.setWeight(QFont.DemiBold)
        p.setFont(f2)
        p.setPen(QColor(T.TEXT))
        trect = QRectF(x, r.top() + 27, r.right() - x - 10, 38)
        fm = QFontMetrics(f2)
        lines, cur = [], ""
        for wd in (d["title"] or "").split():
            test = (cur + " " + wd).strip()
            if fm.horizontalAdvance(test) <= trect.width():
                cur = test
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
        if len(lines) > 2:
            lines = [lines[0], fm.elidedText(" ".join(lines[1:]), Qt.ElideRight, int(trect.width()))]
        for k, ln in enumerate(lines[:2]):
            p.drawText(QPointF(x, trect.top() + 13 + k * 17), ln)
        # footer
        f3 = QFont(option.font)
        f3.setPointSizeF(8)
        p.setFont(f3)
        p.setPen(QColor(T.MUTED))
        loc = f"{d['panel_tag'] or tr('Umum')}  ›  {d['site_name'] or ''}"
        fm3 = QFontMetrics(f3)
        ax = r.right() - 30
        p.drawText(QPointF(x, r.bottom() - 11), fm3.elidedText(loc, Qt.ElideRight, int(ax - x - 50)))
        ph = d.get("_photos", 0)
        if d["pic"]:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(avatar_color(d["pic"])))
            p.drawEllipse(QRectF(ax, r.bottom() - 28, 22, 22))
            p.setPen(QColor("#FFFFFF"))
            f5 = T.cond_font(7.5, 700)
            p.setFont(f5)
            p.drawText(QRectF(ax, r.bottom() - 28, 22, 22), Qt.AlignCenter, initials(d["pic"]))
        if ph:
            p.setFont(T.cond_font(9, 600))
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(ax - 52, r.bottom() - 28, 46, 22), Qt.AlignRight | Qt.AlignVCenter, tr("{0} foto", ph))
        p.restore()


class DialogFitter(QObject):
    """Dialog yang lebih tinggi/lebar dari layar (laptop 1366×768 + scaling) diperkecil & dipusatkan,
    supaya tombol Simpan/Buat PDF tidak keluar layar."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QDialog) and obj.isWindow():
            scr = obj.screen() or QApplication.primaryScreen()
            if scr:
                ag = scr.availableGeometry()
                mw, mh = ag.width() - 40, ag.height() - 50
                if obj.width() > mw or obj.height() > mh:
                    obj.resize(min(obj.width(), mw), min(obj.height(), mh))
                    obj.move(ag.center().x() - obj.width() // 2, ag.top() + max(10, (ag.height() - obj.height()) // 2))
        return False
