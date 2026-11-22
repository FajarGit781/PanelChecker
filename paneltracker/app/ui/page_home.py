"""Halaman Beranda: ringkasan checking panel & punch list."""
from __future__ import annotations

from ..i18n import tr

import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QListWidget, QListWidgetItem, QScrollArea, QVBoxLayout, QWidget,
)

from ..db import PANEL_STATUSES, SEV_SHORT, SEVERITIES, fmt_date, parse_date, today
from . import theme as T
from .widgets import BarChart, Card, DonutChart, KpiCard, PageHeader, Pill, initials, avatar_color


class _RowList(QListWidget):
    """List baris sederhana berbasis widget, klik → callback."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self.on_click = on_click
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QListWidget.NoSelection)
        self.itemClicked.connect(lambda it: self.on_click(it.data(Qt.UserRole)))
        self.setMinimumHeight(250)
        self.setStyleSheet("QListWidget::item:hover { background:#FBF0CC; border-radius:3px; }")

    def add_row(self, data, widget):
        it = QListWidgetItem()
        it.setData(Qt.UserRole, data)
        it.setSizeHint(widget.sizeHint())
        self.addItem(it)
        self.setItemWidget(it, widget)


def _row(left_main, left_sub, right_widgets=(), dot=None):
    w = QWidget()
    w.setAttribute(Qt.WA_TransparentForMouseEvents)
    h = QHBoxLayout(w)
    h.setContentsMargins(6, 7, 6, 7)
    h.setSpacing(10)
    if dot:
        d = QLabel()
        d.setFixedSize(8, 8)
        d.setStyleSheet(f"background:{dot}; border-radius:4px;")
        h.addWidget(d, 0, Qt.AlignVCenter)
    v = QVBoxLayout()
    v.setSpacing(1)
    a = QLabel(left_main)
    a.setStyleSheet("font-weight:600;")
    a.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    b = QLabel(left_sub)
    b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    b.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
    v.addWidget(a)
    v.addWidget(b)
    h.addLayout(v, 1)
    for rw in right_widgets:
        h.addWidget(rw, 0, Qt.AlignVCenter)
    return w


class HomePage(QWidget):
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

        self.header = PageHeader(tr('Beranda'), "")
        lay.addWidget(self.header)

        kp = QHBoxLayout()
        kp.setSpacing(14)
        self.k_panel = KpiCard(tr('Panel dicek'), "panel", T.PRIMARY)
        self.k_items = KpiCard(tr('Item uji selesai'), "check", T.PRIMARY)
        self.k_ng = KpiCard(tr('Item NG'), "x", T.NG)
        self.k_open = KpiCard(tr('Punch open'), "punch", T.WARN)
        self.k_over = KpiCard(tr('Lewat target'), "clock", T.NG)
        for k in (self.k_panel, self.k_items, self.k_ng, self.k_open, self.k_over):
            kp.addWidget(k)
        lay.addLayout(kp)

        g = QGridLayout()
        g.setSpacing(14)
        c1 = Card(tr('Status panel'))
        self.donut = DonutChart()
        c1.lay.addWidget(self.donut)
        c2 = Card(tr('Punch dibuka vs ditutup · 10 minggu terakhir'))
        self.bars = BarChart()
        c2.lay.addWidget(self.bars)
        c3 = Card(tr('Punch open per kategori'))
        self.sev_box = QVBoxLayout()
        self.sev_box.setSpacing(10)
        c3.lay.addLayout(self.sev_box)
        c3.lay.addStretch()

        c4 = Card(tr('Panel perlu perhatian'))
        self.attn = _RowList(self.main.go_panel)
        c4.lay.addWidget(self.attn)
        c5 = Card(tr('Punch terbaru'))
        self.latest = _RowList(self.main.open_issue)
        c5.lay.addWidget(self.latest)
        c6 = Card(tr('Aktivitas terakhir'))
        self.act = _RowList(lambda *_: None)
        c6.lay.addWidget(self.act)
        for c in (c4, c5, c6):
            c.setMinimumHeight(250)
        self.grid, self.cards, self._wide = g, (c1, c2, c3, c4, c5, c6), None
        self._relayout(True)
        lay.addLayout(g)
        lay.addStretch()

    def _relayout(self, wide):
        """Lebar: 3 kolom. Sempit (laptop kecil): 2 kolom, halaman bisa di-scroll."""
        if wide == self._wide:
            return
        self._wide = wide
        for c in self.cards:
            self.grid.removeWidget(c)
        pos = ([(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)] if wide else
               [(0, 0), (0, 1), (1, 1), (1, 0), (2, 0), (2, 1)])
        for c, (r, k) in zip(self.cards, pos):
            self.grid.addWidget(c, r, k)
        for k, sv in enumerate((5, 5, 3) if wide else (1, 1, 0)):
            self.grid.setColumnStretch(k, sv)

    def resizeEvent(self, e):
        self._relayout(self.width() >= 1150)
        super().resizeEvent(e)

    def refresh(self):
        db, pid, sid = self.main.db, self.main.project_id, self.main.site_id
        for w in (self.attn, self.latest, self.act):
            w.clear()
        while self.sev_box.count():
            it = self.sev_box.takeAt(0)
            if it.widget():
                it.widget().hide()          # sembunyikan segera (deleteLater baru jalan di event loop)
                it.widget().deleteLater()
        if not pid:
            self.header.title.setText(tr('Selamat datang 👋'))
            self.header.sub.setText(tr('Buat project baru dari menu ⋯ di sidebar, atau coba project contoh.'))
            for k in (self.k_panel, self.k_items, self.k_ng, self.k_open, self.k_over):
                k.set("–")
            self.donut.set_data([])
            self.bars.set_data([], [])
            return
        p = db.project(pid)
        scope = db.site(sid)["name"] if sid else tr('Semua site')
        self.header.title.setText(p["name"])
        self.header.sub.setText(f"{p['code']}  ·  {p['client'] or '-'}  ·  {scope}  ·  "
                                f"{dt.date.today().strftime('%A, %d %B %Y')}")
        o = db.overall(pid, sid)
        it = o["items"]
        self.k_panel.set(f"{o['panels_started']}/{o['panels']}",
                         f"<b style='color:{T.OK}'>{o['panels_done']}</b> " + tr("lulus / diterima"))
        self.k_items.set(f"{o['items_pct']:.0f}%", tr('{0} dari {1} item', it['checked'], it['total']))
        self.k_ng.set(it["NG"], f"{it['OK']} OK · {it['NA']} N/A", alert=bool(it["NG"]))
        sv = o["by_severity"]
        self.k_open.set(o["issues_open"],
                        "  ".join(f"<b style='color:{T.SEV_COLOR[s]}'>{SEV_SHORT[s]} {sv[s]}</b>" for s in SEVERITIES), alert=bool(o["issues_open"]))
        self.k_over.set(o["issues_overdue"], tr('{0} punch sudah closed', o['issues_closed']), alert=bool(o["issues_overdue"]))

        ps = o["panel_status"]
        self.donut.set_data([(tr(s), ps[s], T.PANEL_STATUS_COLOR[s]) for s in PANEL_STATUSES if ps[s] or s != "Tanpa checklist"],
                            (str(o["panels"]), tr("panel")))
        trend = db.punch_trend(pid, sid, 10)
        self.bars.set_data([b[0].strftime("%d/%m") for b in trend],
                           [(tr('Dibuka'), [b[1] for b in trend], T.NG), (tr('Ditutup'), [b[2] for b in trend], T.OK)])

        # per kategori A/B/C
        open_i = [i for i in db.issues(pid, site_id=sid) if i["status"] != "Closed"]
        tot = max(1, len(open_i))
        from .widgets import SegmentBar
        for s in SEVERITIES:
            n = sum(1 for i in open_i if i["severity"] == s)
            row = QWidget()
            v = QVBoxLayout(row)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(4)
            h = QHBoxLayout()
            h.addWidget(Pill(f"{SEV_SHORT[s]} · {s}", T.SEV_COLOR[s], T.SEV_BG[s]))
            h.addStretch()
            lab = QLabel(f"<b>{n}</b>")
            lab.setStyleSheet("font-size:12pt;")
            h.addWidget(lab)
            v.addLayout(h)
            bar = SegmentBar(6)
            bar.set_parts([(n, T.SEV_COLOR[s]), (tot - n, "#E4E7E4")])
            v.addWidget(bar)
            self.sev_box.addWidget(row)
        st_cnt = o["by_status"]
        info_l = QLabel(" · ".join(f"{T.STATUS_LABEL[k]} {st_cnt[k]}" for k in st_cnt))
        info_l.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
        info_l.setWordWrap(True)
        self.sev_box.addWidget(info_l)

        # perlu perhatian
        ov = db.panel_overview(pid, sid)
        ov = [x for x in ov if x["punch"].get("open") or x["stats"]["NG"]]
        ov.sort(key=lambda x: (-x["punch"].get("Critical", 0), -x["punch"].get("open", 0), -x["stats"]["NG"]))
        for x in ov[:7]:
            pu = x["punch"]
            pills = []
            if pu.get("Critical"):
                pills.append(Pill(f"A {pu['Critical']}", T.SEV_COLOR["Critical"], T.SEV_BG["Critical"]))
            if pu.get("open"):
                pills.append(Pill(f"{pu['open']} open", T.WARN, T.WARN_L))
            if pu.get("overdue"):
                pills.append(Pill(tr('{0} telat', pu['overdue']), "#C4221B"))
            self.attn.add_row(x["panel"]["id"], _row(
                x["panel"]["tag"], f"{x['panel']['site_name']} · {x['panel']['bay']} · {x['stats']['NG']} NG",
                pills, T.PANEL_STATUS_COLOR[x["status"]]))
        if not ov:
            self.attn.add_row(None, _row(tr('Tidak ada panel bermasalah 🎉'), tr('Semua item NG & punch sudah beres')))

        # punch terbaru
        iss = sorted(db.issues(pid, site_id=sid), key=lambda i: i["updated_at"] or "", reverse=True)[:8]
        t = today()
        for i in iss:
            av = QLabel(initials(i["pic"]))
            av.setFixedSize(24, 24)
            av.setAlignment(Qt.AlignCenter)
            av.setStyleSheet(f"background:{avatar_color(i['pic'])}; color:white; border-radius:12px; font-size:7pt;"
                             f" font-weight:700;")
            over = i["status"] != "Closed" and i["due_date"] and i["due_date"] < t
            st = Pill(T.STATUS_LABEL[i["status"]], T.STATUS_COLOR[i["status"]])
            self.latest.add_row(i["id"], _row(
                f"{i['code']} · {i['title']}",
                f"{i['panel_tag'] or tr('(umum)')} · {i['site_name'] or ''} · due {fmt_date(i['due_date']) or '-'}"
                + (tr('  ⚠ telat') if over else ""), [st, av], T.SEV_COLOR.get(i["severity"])))

        # aktivitas
        for a in db.activities(pid, 12):
            ts = a["ts"].replace("T", " ")[5:16]
            self.act.add_row(None, _row(a["detail"] or a["action"], f"{a['user']} · {ts}"))
