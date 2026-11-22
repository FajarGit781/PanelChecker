"""Tema visual "ruang relay": abu-abu cat panel (RAL 7035), pelat nama traffolyte, lampu indikator IEC 60073,
kuning sinyal (RAL 1003) hanya untuk aksi utama. Sama dengan aplikasi HP.

Semua warna teks di sini sudah dicek kontrasnya terhadap latarnya (min. ±4.5:1 untuk teks biasa).
Palet Qt dipaksa terang, jadi tampilan tidak ikut mode gelap Windows (penyebab teks putih di atas latar putih).
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

# ---------------------------------------------------------------- palette
BG = "#DFE2DF"          # cat panel
CARD = "#FBFBFA"        # lembar
INPUT = "#FFFFFF"
BORDER = "#C9CEC9"
TEXT = "#16191B"
MUTED = "#586064"
SUBTLE = "#62696C"
SIDEBAR = "#1E2225"     # pelat nama
SIDEBAR_2 = "#2A3034"
SIDE_TEXT = "#D7DCDD"
SIDE_MUTED = "#9AA3A6"
ENGRAVE = "#F2F3F1"
SIGNAL = "#F5B300"      # aksi utama
SIGNAL_D = "#D99D00"
ON_SIGNAL = "#1A1400"
PRIMARY = "#1E2225"     # aksen tinta (garis pilihan, ikon)
PRIMARY_D = "#000000"
PRIMARY_L = "#FBF0CC"   # latar terpilih / hover (kuning muda)
OK = "#1A7A36"
OK_L = "#DFF1E4"
NG = "#C4221B"
NG_L = "#FBE3E1"
NA = "#586064"
NA_L = "#E4E7E4"
WARN = "#9A5B00"        # teks kuning tua (lampu kuning terlalu terang untuk teks)
WARN_L = "#FCEFD6"
INFO = "#1F6FB2"

LAMP = {"red": "#D7261E", "amber": "#E08A00", "green": "#1E8E3E", "blue": "#1F6FB2", "off": "#C9CECC"}

SEV_COLOR = {"Critical": "#C4221B", "Major": "#B04A12", "Minor": "#7A5E00"}
SEV_BG = {"Critical": "#FBE3E1", "Major": "#F9E7DA", "Minor": "#F4EDCF"}
STATUS_COLOR = {"Open": "#C4221B", "In Progress": "#9A5B00", "Ready to Verify": "#1F6FB2", "Closed": "#1A7A36"}
STATUS_LAMP = {"Open": LAMP["red"], "In Progress": LAMP["amber"], "Ready to Verify": LAMP["blue"], "Closed": LAMP["green"]}
from ..i18n import TrDict  # noqa: E402

STATUS_LABEL = TrDict({"Open": "Open", "In Progress": "Dikerjakan", "Ready to Verify": "Siap Verifikasi",
                "Closed": "Closed"})
PANEL_STATUS_COLOR = {   # aman untuk teks
    "Tanpa checklist": "#6E7578", "Belum dicek": "#586064", "Sedang dicek": "#9A5B00",
    "Ada temuan": "#C4221B", "Lulus": "#1A7A36", "Diterima": "#1F5C4A",
}
PANEL_LAMP = {
    "Tanpa checklist": LAMP["off"], "Belum dicek": LAMP["off"], "Sedang dicek": LAMP["amber"],
    "Ada temuan": LAMP["red"], "Lulus": LAMP["green"], "Diterima": LAMP["green"],
}
RESULT_COLOR = {"OK": OK, "NG": NG, "NA": NA}
RESULT_BG = {"OK": OK_L, "NG": NG_L, "NA": NA_L}

FONT = "IBM Plex Sans"
FONT_COND = "IBM Plex Sans Condensed"


def light_palette() -> QPalette:
    """Palet terang tetap — dipakai apa pun mode warna Windows."""
    p = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: INPUT, QPalette.AlternateBase: "#F3F4F2",
        QPalette.Text: TEXT, QPalette.Button: CARD, QPalette.ButtonText: TEXT, QPalette.BrightText: "#FFFFFF",
        QPalette.Highlight: SIGNAL, QPalette.HighlightedText: ON_SIGNAL, QPalette.ToolTipBase: SIDEBAR,
        QPalette.ToolTipText: ENGRAVE, QPalette.PlaceholderText: "#646B6E", QPalette.Link: INFO,
        QPalette.LinkVisited: INFO, QPalette.Light: "#FFFFFF", QPalette.Midlight: "#ECEEEB", QPalette.Mid: "#B3B9B5",
        QPalette.Dark: "#8C9396", QPalette.Shadow: "#5A6164",
    }
    for r, c in roles.items():
        p.setColor(QPalette.All, r, QColor(c))
    for r, c in {QPalette.WindowText: "#8C9396", QPalette.Text: "#8C9396", QPalette.ButtonText: "#8C9396",
                 QPalette.Base: "#F1F2F0", QPalette.Button: "#F1F2F0"}.items():
        p.setColor(QPalette.Disabled, r, QColor(c))
    return p


def setup_app(app, base_dir: str | None = None):
    """Font, palet terang, gaya Fusion & stylesheet. Dipanggil sekali saat aplikasi mulai."""
    import os
    from PySide6.QtGui import QFont, QFontDatabase
    app.setStyle("Fusion")
    try:   # Qt 6.8+: abaikan mode gelap Windows
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except Exception:
        pass
    fdir = os.path.join(base_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."),
                        "assets", "fonts")
    if os.path.isdir(fdir):
        for f in sorted(os.listdir(fdir)):
            if f.lower().endswith(".ttf"):
                QFontDatabase.addApplicationFont(os.path.join(fdir, f))
    fam = FONT if FONT in QFontDatabase.families() else "Segoe UI"
    app.setPalette(light_palette())
    f = QFont(fam, 9)
    f.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(f)
    app.setStyleSheet(STYLE + _asset_style(os.path.join(base_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                             "..", ".."), "assets", "ui")))


def _asset_style(udir: str) -> str:
    """Aturan yang butuh gambar (centang, panah combo/tanggal/spin). Path absolut dengan '/'."""
    import os
    if not os.path.isdir(udir):
        return ""
    u = os.path.abspath(udir).replace("\\", "/")
    return f"""
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #6E7578; border-radius: 3px; background: {INPUT}; }}
QCheckBox::indicator:hover {{ border-color: {TEXT}; }}
QCheckBox::indicator:checked {{ background: {SIDEBAR}; border-color: {SIDEBAR}; image: url("{u}/check.svg"); }}
QCheckBox::indicator:disabled {{ background: #ECEEEB; border-color: #B3B9B5; }}
QCheckBox::indicator:checked:disabled {{ background: #8C9396; border-color: #8C9396; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid #6E7578; border-radius: 8px; background: {INPUT}; }}
QRadioButton::indicator:checked {{ background: {SIDEBAR}; border-color: {SIDEBAR}; image: url("{u}/radio.svg"); }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; border: none;
    width: 24px; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{u}/chevron.svg"); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled, QDateEdit::down-arrow:disabled {{ image: none; }}
QFrame#sidebar QComboBox::down-arrow {{ image: url("{u}/chevron-light.svg"); }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 18px;
    border: none; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 18px;
    border: none; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{u}/chevron-up.svg"); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{u}/chevron-down-s.svg"); width: 10px; height: 10px; }}
"""


def cond_font(size: float, weight: int = 700):
    """Huruf condensed untuk tag panel, judul & angka."""
    from PySide6.QtGui import QFont
    f = QFont(FONT_COND)
    f.setPointSizeF(size)
    f.setWeight(QFont.Weight(weight))
    return f


STYLE = f"""
* {{ font-family: "{FONT}", "Segoe UI", Arial; }}
QWidget {{ color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#page {{ background: {BG}; }}
QLabel {{ color: {TEXT}; background: transparent; }}
QToolTip {{ background: {SIDEBAR}; color: {ENGRAVE}; border: 1px solid #3A4247; padding: 6px; }}

/* ---------- sidebar = pelat ---------- */
QFrame#sidebar {{ background: {SIDEBAR}; }}
QFrame#sidebar QLabel {{ color: {SIDE_TEXT}; }}
QLabel#brand {{ color: {ENGRAVE}; font-family: "{FONT_COND}"; font-size: 16pt; font-weight: 700; letter-spacing: 1px; }}
QLabel#brandSub {{ color: {SIDE_MUTED}; font-family: "{FONT_COND}"; font-size: 8.5pt; }}
QLabel#sideCaption {{ color: {SIDE_MUTED}; font-family: "{FONT_COND}"; font-size: 9pt; font-weight: 600; }}
QPushButton#nav {{ color: {SIDE_TEXT}; background: transparent; border: none; border-left: 4px solid transparent;
    border-radius: 0; text-align: left; padding: 9px 12px; font-size: 10.5pt; }}
QPushButton#nav:hover {{ background: {SIDEBAR_2}; color: #FFFFFF; }}
QPushButton#nav:checked {{ background: {SIDEBAR_2}; color: #FFFFFF; font-weight: 600; border-left: 4px solid {SIGNAL}; }}
QFrame#sidebar QComboBox {{ background: {SIDEBAR_2}; color: #FFFFFF; border: 1px solid #3A4247; border-radius: 4px;
    padding: 6px 8px; }}
QFrame#sidebar QComboBox QAbstractItemView {{ background: {INPUT}; color: {TEXT}; selection-background-color: {PRIMARY_L};
    selection-color: {TEXT}; }}
QFrame#sidebar QLineEdit {{ background: {SIDEBAR_2}; color: #FFFFFF; border: 1px solid #3A4247; border-radius: 4px;
    padding: 7px 8px; selection-background-color: {SIGNAL}; selection-color: {ON_SIGNAL};
    placeholder-text-color: {SIDE_MUTED}; }}
QFrame#sidebar QToolButton {{ color: {SIDE_TEXT}; background: {SIDEBAR_2}; border: 1px solid #3A4247; border-radius: 4px;
    padding: 5px; }}
QFrame#sidebar QToolButton:hover {{ background: #353C41; color: #FFFFFF; }}

/* ---------- kartu & judul ---------- */
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}
QLabel#cardTitle {{ font-family: "{FONT_COND}"; font-size: 12pt; font-weight: 600; color: {TEXT}; }}
QLabel#pageTitle {{ font-family: "{FONT_COND}"; font-size: 19pt; font-weight: 600; color: {TEXT}; }}
QLabel#pageSub {{ color: {MUTED}; font-size: 9.5pt; }}

/* ---------- tombol ---------- */
QPushButton {{ background: {CARD}; color: {TEXT}; border: 1px solid #B3B9B5; border-radius: 5px; padding: 6px 12px;
    font-size: 9.5pt; font-weight: 500; }}
QPushButton:hover {{ border-color: {TEXT}; background: #FFFFFF; }}
QPushButton:pressed {{ background: #ECEEEB; }}
QPushButton:disabled {{ color: #8C9396; background: #ECEEEB; border-color: {BORDER}; }}
QPushButton#primary {{ background: {SIGNAL}; color: {ON_SIGNAL}; border: 1px solid {SIGNAL_D}; font-weight: 700; }}
QPushButton#primary:hover {{ background: #FFC21A; border-color: {SIGNAL_D}; }}
QPushButton#primary:pressed {{ background: {SIGNAL_D}; }}
QPushButton#primary:disabled {{ background: #EADFB8; color: #7A6F4A; border-color: #E0D3A3; }}
QPushButton#danger {{ color: {NG}; }}
QPushButton#danger:hover {{ background: {NG_L}; border-color: {NG}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED}; padding: 4px 6px; }}
QPushButton#ghost:hover {{ background: #E9ECE9; color: {TEXT}; }}
QPushButton#seg {{ border-radius: 0; padding: 5px 14px; margin: 0; }}
QPushButton#seg:checked {{ background: {SIDEBAR}; color: #FFFFFF; border-color: {SIDEBAR}; }}
QPushButton#segL {{ border-top-right-radius: 0; border-bottom-right-radius: 0; padding: 5px 14px; }}
QPushButton#segR {{ border-top-left-radius: 0; border-bottom-left-radius: 0; padding: 5px 14px; margin-left: -1px; }}
QPushButton#segL:checked, QPushButton#segR:checked {{ background: {SIDEBAR}; color: #FFFFFF; border-color: {SIDEBAR}; }}
QDialogButtonBox QPushButton {{ min-width: 84px; }}

QPushButton#resOK, QPushButton#resNG, QPushButton#resNA {{ min-width: 38px; padding: 5px 8px; font-weight: 700;
    font-family: "{FONT_COND}"; font-size: 10.5pt; border-radius: 5px; color: {MUTED}; background: #EEF0ED;
    border: 1px solid #B3B9B5; border-bottom: 2px solid #A3AAA6; }}
QPushButton#resOK:hover {{ border-color: {OK}; color: {OK}; background: #FFFFFF; }}
QPushButton#resNG:hover {{ border-color: {NG}; color: {NG}; background: #FFFFFF; }}
QPushButton#resNA:hover {{ border-color: {NA}; color: {TEXT}; background: #FFFFFF; }}
QPushButton#resOK:checked {{ background: {LAMP["green"]}; color: #FFFFFF; border-color: #166B2F; }}
QPushButton#resNG:checked {{ background: {LAMP["red"]}; color: #FFFFFF; border-color: #A51D17; }}
QPushButton#resNA:checked {{ background: #5B6266; color: #FFFFFF; border-color: #464C50; }}

/* ---------- isian ---------- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {INPUT}; color: {TEXT}; border: 1px solid #B3B9B5; border-radius: 4px; padding: 5px 7px;
    selection-background-color: {SIGNAL}; selection-color: {ON_SIGNAL}; placeholder-text-color: #646B6E; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {TEXT}; }}
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QPlainTextEdit:disabled {{ background: #F1F2F0; color: #8C9396; }}
QLineEdit:read-only {{ background: #F6F7F5; }}
QLineEdit#inline {{ border: 1px solid transparent; background: transparent; padding: 3px 5px; }}
QLineEdit#inline:hover {{ border: 1px solid {BORDER}; background: {INPUT}; }}
QLineEdit#inline:focus {{ border: 1px solid {TEXT}; background: {INPUT}; }}
QComboBox QAbstractItemView {{ background: {INPUT}; color: {TEXT}; border: 1px solid {BORDER};
    selection-background-color: {PRIMARY_L}; selection-color: {TEXT}; outline: 0; }}
QCheckBox, QRadioButton {{ spacing: 6px; color: {TEXT}; background: transparent; }}
/* ---------- kalender (popup tanggal) ---------- */
QCalendarWidget QWidget {{ alternate-background-color: #F3F4F2; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: #E9ECE9; border-bottom: 1px solid {BORDER}; }}
QCalendarWidget QToolButton {{ color: {TEXT}; background: transparent; border: none; font-weight: 600; padding: 4px 8px;
    icon-size: 18px; }}
QCalendarWidget QToolButton:hover {{ background: {PRIMARY_L}; border-radius: 4px; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; }}
QCalendarWidget QMenu {{ background: {INPUT}; color: {TEXT}; }}
QCalendarWidget QSpinBox {{ background: {INPUT}; color: {TEXT}; selection-background-color: {SIGNAL};
    selection-color: {ON_SIGNAL}; }}
QCalendarWidget QAbstractItemView:enabled {{ background: {INPUT}; color: {TEXT}; selection-background-color: {SIGNAL};
    selection-color: {ON_SIGNAL}; outline: 0; }}
QCalendarWidget QAbstractItemView:disabled {{ color: #A3AAA6; }}

/* ---------- tabel & daftar ---------- */
QTableWidget, QTableView {{ background: {INPUT}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 4px;
    gridline-color: #E3E6E3; selection-background-color: {PRIMARY_L}; selection-color: {TEXT};
    alternate-background-color: #F6F7F5; }}
QHeaderView::section {{ background: #EEF0ED; color: {MUTED}; font-weight: 600; font-size: 8.5pt; padding: 7px 6px;
    border: none; border-bottom: 1px solid {BORDER}; border-right: 1px solid #E3E6E3; }}
QTableCornerButton::section {{ background: #EEF0ED; border: none; }}
QListWidget {{ background: transparent; border: none; outline: none; color: {TEXT}; }}
QListWidget::item {{ border: none; color: {TEXT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #AEB4B0; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #8C9396; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #AEB4B0; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 4px; background: {CARD}; top: -1px; }}
QTabBar::tab {{ padding: 8px 16px; color: {MUTED}; background: transparent; border: none; border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 3px solid {SIGNAL}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QMenu {{ background: {INPUT}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; border-radius: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 3px; color: {TEXT}; }}
QMenu::item:selected {{ background: {PRIMARY_L}; color: {TEXT}; }}
QMenu::item:disabled {{ color: #8C9396; }}
QMenu::section {{ color: {MUTED}; font-weight: 600; padding: 6px 12px 2px; background: transparent; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QGroupBox {{ font-weight: 600; border: 1px solid {BORDER}; border-radius: 4px; margin-top: 12px; background: {CARD};
    padding-top: 6px; color: {TEXT}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {TEXT}; }}
QStatusBar {{ background: {CARD}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {MUTED}; }}
QSplitter::handle {{ background: transparent; }}
QMessageBox, QInputDialog {{ background: {BG}; }}
QMessageBox QLabel, QInputDialog QLabel {{ color: {TEXT}; }}
QProgressBar {{ background: #E4E7E4; border: none; border-radius: 3px; color: {TEXT}; text-align: center; }}
QProgressBar::chunk {{ background: {LAMP["green"]}; border-radius: 3px; }}
"""

# ---------------------------------------------------------------- icons
_P = {
    "home": '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    "check": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="m8.5 13 2.5 2.5 4.5-5"/>',
    "punch": '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.3" r=".6"/>',
    "report": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 15.5h6M9 19h4"/>',
    "template": '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/><path d="m3 12 9 4.5 9-4.5"/><path d="m3 16.5 9 4.5 9-4.5"/>',
    "settings": '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1'
                'M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "qr": '<rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1"/><rect x="14" y="3.5" width="6.5" height="6.5" rx="1"/>'
          '<rect x="3.5" y="14" width="6.5" height="6.5" rx="1"/><path d="M14 14h3v3h-3zM18 18h2.5v2.5M14 20.5h2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    "camera": '<path d="M4 8h3l2-2.5h6L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    "more": '<circle cx="5.5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="18.5" cy="12" r="1"/>',
    "panel": '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M8 7h8M8 10.5h8M8 14h5"/>'
             '<circle cx="15.5" cy="17.5" r="1"/>',
    "folder": '<path d="M3 6.5h6l2 2h10V19H3z"/>',
    "download": '<path d="M12 4v11"/><path d="m7.5 11 4.5 4.5 4.5-4.5"/><path d="M5 20h14"/>',
    "upload": '<path d="M12 16V5"/><path d="M7.5 9.5 12 5l4.5 4.5"/><path d="M5 20h14"/>',
    "printer": '<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="7.5" rx="1.5"/><path d="M7 14h10v6.5H7z"/>',
    "board": '<rect x="3.5" y="4" width="5" height="16" rx="1"/><rect x="9.5" y="4" width="5" height="11" rx="1"/>'
             '<rect x="15.5" y="4" width="5" height="13.5" rx="1"/>',
    "table": '<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10"/>',
    "user": '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20.5c1.2-4 4-5.5 7.5-5.5s6.3 1.5 7.5 5.5"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="1.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "shield": '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.8 7.5 9 4.3-1.2 7.5-4.5 7.5-9V6z"/><path d="m8.8 12 2.3 2.3 4.2-4.6"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    "trash": '<path d="M4.5 6.5h15M9.5 6.5V4h5v2.5M6.5 6.5l1 14h9l1-14"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.8"/><path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13'
                '"/><path d="M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
    "list": '<path d="M9 6.5h11M9 12h11M9 17.5h11"/><circle cx="4.8" cy="6.5" r=".9"/><circle cx="4.8" cy="12" r=".9"/>'
            '<circle cx="4.8" cy="17.5" r=".9"/>',
    "x": '<path d="m6 6 12 12M18 6 6 18"/>',
    "excel": '<rect x="4" y="3.5" width="16" height="17" rx="1.5"/><path d="m8.5 8.5 7 7M15.5 8.5l-7 7"/>',
    "cloud": '<path d="M7 18.5h10.2a4.3 4.3 0 0 0 .7-8.55A6 6 0 0 0 6.4 9.1 4.7 4.7 0 0 0 7 18.5z"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 3.5V8h4.5"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/>'
               '<path d="M20 20.5V16h-4.5"/>',
    "tool": '<path d="M14.5 6.5a4 4 0 0 0 5 5L12 19a2.1 2.1 0 0 1-3-3l7.5-7.5"/><path d="M14.5 6.5 17 4l3 3-2.5 2.5"/>',
}

_cache: dict = {}


def icon(name: str, color: str = MUTED, size: int = 20, stroke: float = 1.8) -> QIcon:
    key = (name, color, size, stroke)
    if key in _cache:
        return _cache[key]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_P.get(name, "")}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, size * scale, size * scale))
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    _cache[key] = ic
    return ic


def nav_icon(name: str) -> QIcon:
    """Ikon sidebar: abu saat normal, putih saat aktif."""
    ic = QIcon()
    for mode_color, state in ((SIDE_MUTED, QIcon.Off), ("#FFFFFF", QIcon.On)):
        base = icon(name, mode_color, 20)
        for sz in (QSize(20, 20), QSize(40, 40)):
            ic.addPixmap(base.pixmap(sz), QIcon.Normal, state)
    return ic


def qcolor(hexstr: str, alpha: int | None = None) -> QColor:
    c = QColor(hexstr)
    if alpha is not None:
        c.setAlpha(alpha)
    return c
