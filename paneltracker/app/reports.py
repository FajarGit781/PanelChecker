"""Generator report PDF (ReportLab)."""
from __future__ import annotations

from .i18n import tr

import datetime as dt
import io

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    CondPageBreak, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .sas_matrix import is_dido_section
from .db import Database, ISSUE_STATUSES, PANEL_STATUSES, SEV_LABEL, SEV_SHORT, SEVERITIES, fmt_date, parse_date, today

NAVY = colors.HexColor("#0E1A2B")
ACCENT = colors.HexColor("#2563EB")
GRID = colors.HexColor("#B8C2CF")
HEAD_BG = colors.HexColor("#E3E8EF")
C_DONE = colors.HexColor("#A5D6A7")
C_PROG = colors.HexColor("#FFE082")
C_LATE = colors.HexColor("#FFCDD2")
SEV = {"Critical": colors.HexColor("#DC2626"), "Major": colors.HexColor("#EA580C"),
       "Minor": colors.HexColor("#CA8A04")}
RES = {"OK": (colors.HexColor("#DCFCE7"), colors.HexColor("#166534")),
       "NG": (colors.HexColor("#FEE2E2"), colors.HexColor("#B91C1C")),
       "NA": (colors.HexColor("#E2E8F0"), colors.HexColor("#334155"))}
PSTAT = {"Tanpa checklist": "#94A3B8", "Belum dicek": "#64748B", "Sedang dicek": "#2563EB", "Ada temuan": "#DC2626",
         "Lulus": "#16A34A", "Diterima": "#0F766E"}
STAT = {"Open": colors.HexColor("#DC2626"), "In Progress": colors.HexColor("#D97706"),
        "Ready to Verify": colors.HexColor("#2563EB"), "Closed": colors.HexColor("#16A34A")}
STAT_BG = {"Open": colors.HexColor("#FDECEC"), "In Progress": colors.HexColor("#FFF4DE"),
           "Ready to Verify": colors.HexColor("#E8F0FE"), "Closed": colors.HexColor("#EAF7EE")}
STAT_LABEL = {"Open": "OPEN", "In Progress": "IN PROGRESS", "Ready to Verify": "VERIFY", "Closed": "CLOSED"}

ss = getSampleStyleSheet()
P = ParagraphStyle("p", parent=ss["Normal"], fontName="Helvetica", fontSize=8, leading=10)
PS = ParagraphStyle("ps", parent=P, fontSize=7, leading=8.5)
PB = ParagraphStyle("pb", parent=P, fontName="Helvetica-Bold")
H1 = ParagraphStyle("h1", parent=P, fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=NAVY)
H2 = ParagraphStyle("h2", parent=P, fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=NAVY,
                    spaceBefore=8, spaceAfter=4)
PC = ParagraphStyle("pc", parent=P, alignment=TA_CENTER)


def esc(s) -> str:
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


class _Raw(str):
    """Teks yang sudah berformat markup ReportLab (jangan di-escape)."""


def _cell(v, style):
    return Paragraph(v if isinstance(v, _Raw) else esc(v), style)


def _clip(s, n):
    """Batasi teks sangat panjang di sel tabel (satu baris tabel tidak boleh lebih tinggi dari 1 halaman)."""
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n].rstrip() + " …"


def _one_line(text) -> str:
    """Rapikan teks untuk drawString: baris baru/tab/spasi ganda → satu spasi (bukan kotak hitam ■)."""
    return " ".join(str(text or "").split())


def viewer_base(url) -> str:
    """Alamat viewer web dari Pengaturan; hanya https yang dipakai."""
    url = (url or "").strip()
    return url if url.lower().startswith("https://") else ""


def qr_payload(p, viewer_url="") -> str:
    """Isi QR panel. uuid tetap sama di semua laptop & HP.

    - Alamat viewer web diisi (v2.7.2): "https://<viewer>/?p=<uuid>". Kamera HP biasa langsung membuka halaman
      progress panel tanpa login; scanner USB di aplikasi ini juga tetap mengenalinya.
    - Tidak diisi: "PT:<uuid>:<tag>" seperti v2.7.1."""
    base = viewer_base(viewer_url)
    if base:
        return f"{base}{'&' if '?' in base else '?'}p={p['uuid']}"
    return f"PT:{p['uuid']}:{_one_line(p['tag'])}"


def _elide(text, font, size, maxw):
    """Potong teks dengan '…' agar lebarnya tidak melebihi maxw (satuan point). Baris baru dijadikan spasi."""
    text = _one_line(text)
    if stringWidth(text, font, size) <= maxw:
        return text
    while text and stringWidth(text + "…", font, size) > maxw:
        text = text[:-1]
    return text.rstrip() + "…"


def _fit_size(text, font, size, maxw, min_size):
    """Perkecil ukuran huruf (sampai min_size) agar teks muat; kembalikan ukuran yang dipakai."""
    while size > min_size and stringWidth(text or "", font, size) > maxw:
        size -= 0.5
    return size


def _base_style(extra=None, head_rows=1):
    st = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
        ("FONT", (0, 0), (-1, head_rows - 1), "Helvetica-Bold", 7.5),
        ("BACKGROUND", (0, 0), (-1, head_rows - 1), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, head_rows - 1), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    return TableStyle(st + (extra or []))


class _NumberedCanvas(rl_canvas.Canvas):
    """Canvas yang bisa menulis 'Halaman x dari y'."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor("#6B7785"))
            w = self._pagesize[0]
            self.drawRightString(w - 12 * mm, 8 * mm, tr('Halaman {0} dari {1}', self._pageNumber, n))
            super().showPage()
        super().save()


class ReportBuilder:
    def __init__(self, db: Database, project_id: int, site_id=None):
        self.db = db
        self.pid = project_id
        self.sid = site_id
        self.project = db.project(project_id)
        self.site_name = db.site(site_id)["name"] if site_id else tr('Semua site')
        self.company = db.get_setting("company_name")
        self.address = db.get_setting("company_address")
        logo = db.get_logo()
        self.logo = ImageReader(io.BytesIO(logo)) if logo else None
        self.printed = dt.datetime.now().strftime("%d-%m-%Y %H:%M")
        self.user = db.user

    # ------------------------------------------------------------ framework
    def _header_footer(self, title):
        def draw(c: rl_canvas.Canvas, doc):
            w, h = doc.pagesize
            c.saveState()
            top = h - 10 * mm
            x = 12 * mm
            right = w - 12 * mm
            if self.logo:
                iw, ih = self.logo.getSize()
                lh = 13 * mm
                lw = min(40 * mm, lh * iw / ih)
                c.drawImage(self.logo, x, top - lh, lw, lh, mask="auto", preserveAspectRatio=True)
                x += lw + 4 * mm
            # blok kanan (judul dokumen + project): lebar dibatasi, sisanya untuk nama perusahaan
            ttl = title.upper()
            sub = f"{self.project['code']} — {self.project['name']}"
            avail = right - x
            rmax = avail * 0.48
            tw = stringWidth(ttl, "Helvetica-Bold", 12)
            rw = min(max(tw, stringWidth(sub, "Helvetica", 8)), rmax)
            lmax = avail - rw - 8 * mm  # jarak minimal 8 mm antara blok kiri & kanan
            c.setFillColor(NAVY)
            fs = _fit_size(self.company, "Helvetica-Bold", 11, lmax, 8.5)
            c.setFont("Helvetica-Bold", fs)
            c.drawString(x, top - 5 * mm, _elide(self.company, "Helvetica-Bold", fs, lmax))
            c.setFont("Helvetica", 7.5)
            c.setFillColor(colors.HexColor("#4A5568"))
            fa = _fit_size(self.address, "Helvetica", 7.5, lmax, 6.5)
            c.setFont("Helvetica", fa)
            c.drawString(x, top - 9 * mm, _elide(self.address, "Helvetica", fa, lmax))
            c.setFillColor(NAVY)
            ft = _fit_size(ttl, "Helvetica-Bold", 12, rw, 9)
            c.setFont("Helvetica-Bold", ft)
            c.drawRightString(right, top - 5 * mm, _elide(ttl, "Helvetica-Bold", ft, rw))
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor("#4A5568"))
            c.drawRightString(right, top - 9.5 * mm, _elide(sub, "Helvetica", 8, rw))
            c.setStrokeColor(NAVY)
            c.setLineWidth(1.2)
            c.line(12 * mm, top - 15 * mm, w - 12 * mm, top - 15 * mm)
            c.setLineWidth(0.4)
            c.setStrokeColor(GRID)
            c.line(12 * mm, 12 * mm, w - 12 * mm, 12 * mm)
            c.setFont("Helvetica", 7)
            c.setFillColor(colors.HexColor("#6B7785"))
            c.drawString(12 * mm, 8 * mm, tr('Dicetak: {0} oleh {1}  |  Panel Tracker — Check & Punch List', self.printed, self.user))
            c.restoreState()
        return draw

    def _build(self, path, title, story, pagesize):
        doc = SimpleDocTemplate(path, pagesize=pagesize, leftMargin=12 * mm, rightMargin=12 * mm,
                                topMargin=29 * mm, bottomMargin=16 * mm, title=title,
                                author=self.company, subject=self.project["name"])
        hf = self._header_footer(title)
        doc.build(story, onFirstPage=hf, onLaterPages=hf, canvasmaker=_NumberedCanvas)

    def _info_table(self, width, extra=None):
        p = self.project
        per = f"{fmt_date(p['start_date']) or '-'} {tr('s/d')} {fmt_date(p['end_date']) or '-'}"
        rows = [
            ["Project", f"{p['code']} — {p['name']}", tr('Tanggal report'), dt.date.today().strftime("%d-%m-%Y")],
            [tr('Owner / Client'), p["client"] or "-", tr('Lingkup'), self.site_name],
            [tr('Kontraktor'), p["contractor"] or "-", tr('Periode project'), per],
        ] + (extra or [])
        cw = [width * 0.14, width * 0.40, width * 0.14, width * 0.32]
        t = Table([[Paragraph(f"<b>{esc(a)}</b>", P), Paragraph(esc(b), P), Paragraph(f"<b>{esc(c)}</b>", P),
                    Paragraph(esc(d), P)] for a, b, c, d in rows], colWidths=cw)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, GRID),
            ("BACKGROUND", (0, 0), (0, -1), HEAD_BG),
            ("BACKGROUND", (2, 0), (2, -1), HEAD_BG),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    def _kpi_row(self, width, items):
        """items: (label, value, warna[, keterangan kecil]). Tinggi sel menyesuaikan isi → tidak ada teks bertumpuk."""
        n = len(items)
        cw = width / n
        lab_st = ParagraphStyle("kl", parent=P, fontSize=6.8, leading=8.5, textColor=colors.HexColor("#5A6778"))
        sub_st = ParagraphStyle("ks", parent=P, fontSize=7, leading=8.5, textColor=colors.HexColor("#5A6778"))
        any_sub = any(len(it) > 3 and it[3] for it in items)
        row = []
        for it in items:
            label, value, col = it[:3]
            sub = it[3] if len(it) > 3 else ""
            # angka panjang → huruf diperkecil agar tetap 1 baris di dalam kotak
            fs = 15
            while fs > 8 and stringWidth(str(value), "Helvetica-Bold", fs) > cw - 12:
                fs -= 1
            val_st = ParagraphStyle("kv", parent=P, fontName="Helvetica-Bold", fontSize=fs, leading=fs + 3,
                                    textColor=colors.HexColor(col))
            cell = [Paragraph(esc(label), lab_st), Paragraph(esc(value), val_st)]
            if any_sub:
                cell.append(Paragraph(sub or "&nbsp;", sub_st))
            row.append(cell)
        t = Table([row], colWidths=[cw] * n)
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.4, GRID), ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    def _signatures(self, width):
        d = self.db
        keys = [("prepared", tr('Dibuat oleh')), ("checked", tr('Diperiksa oleh')), ("approved", tr('Disetujui oleh'))]
        head = [Paragraph(f"<b>{lab}</b>", PC) for _, lab in keys]
        space = ["", "", ""]
        names = [Paragraph(f"<u><b>{esc(d.get_setting('sign_' + k)) or '&nbsp;' * 30}</b></u><br/>"
                           f"{esc(d.get_setting('sign_' + k + '_title'))}", PC) for k, _ in keys]
        t = Table([head, space, names], colWidths=[width / 3] * 3, rowHeights=[14, 42, None])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, GRID), ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG)]))
        return KeepTogether([Spacer(1, 8), t])

    @staticmethod
    def _status_legend():
        cells, st, widths = [], [], []
        for k, (stt, lab) in enumerate((("Open", tr('OPEN — belum dikerjakan')), ("In Progress", tr('IN PROGRESS — sedang dikerjakan')),
                                        ("Ready to Verify", tr('VERIFY — siap diverifikasi')),
                                        ("Closed", tr('CLOSED — selesai')))):
            cells += ["", lab, ""]
            # lebar kolom teks mengikuti panjang teks (+ jarak) → label tidak menabrak kotak warna berikutnya
            widths += [10, stringWidth(lab, "Helvetica", 7) + 12, 8]
            st += [("BACKGROUND", (3 * k, 0), (3 * k, 0), STAT[stt]),
                   ("BACKGROUND", (3 * k + 1, 0), (3 * k + 1, 0), STAT_BG[stt])]
        t = Table([cells], colWidths=widths, hAlign="LEFT")
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)] + st))
        return t

    @staticmethod
    def _bar(pct, w=70, h=9):
        d = Drawing(w, h)
        d.add(Rect(0, 0, w, h, fillColor=colors.HexColor("#E2E8F0"), strokeColor=None))
        col = colors.HexColor("#43A047") if pct >= 99.999 else ACCENT if pct >= 50 else colors.HexColor("#FB8C00")
        d.add(Rect(0, 0, w * max(0, min(pct, 100)) / 100, h, fillColor=col, strokeColor=None))
        d.add(String(w / 2, 2, f"{pct:.1f}%", fontName="Helvetica-Bold", fontSize=6.5, textAnchor="middle"))
        return d

    def _issue_table(self, iss, W, compact=False, start_no=1):
        if compact:
            head = [tr('Kode'), "Site", tr('Panel'), tr('Judul / Temuan'), tr('Kategori'), tr('Kat.'), "Status", "PIC", tr('Target')]
            cw = [0.07, 0.09, 0.08, 0.36, 0.12, 0.04, 0.09, 0.09, 0.06]
        else:
            head = [tr('No'), tr('Kode'), "Site", tr('Panel'), tr('Temuan'), tr('Kategori'), tr('Kat.'), "Status", "PIC", tr('Ditemukan'),
                    tr('Target'), tr('Close'), tr('Tindakan perbaikan')]
            cw = [0.03, 0.06, 0.07, 0.07, 0.22, 0.08, 0.055, 0.075, 0.07, 0.055, 0.055, 0.055, 0.105]
        rows = [head]
        st = []
        t = today()
        for n, i in enumerate(iss, start=start_no):
            over = i["status"] != "Closed" and i["due_date"] and i["due_date"] < t
            title = f"<b>{esc(_clip(i['title'], 300))}</b>"
            if i["description"] and not compact:
                title += f"<br/><font size=6.5 color='#4A5568'>{esc(_clip(i['description'], 900))}</font>"
            if not compact and i["check_desc"]:
                title += tr("<br/><font size=6 color='#2563EB'>Item cek: {0}</font>", esc(i['check_desc']))
            if compact:
                row = [i["code"], Paragraph(esc(i["site_name"]), PS), Paragraph(esc(i["panel_tag"] or tr('(umum)')), PS),
                       Paragraph(title, PS), Paragraph(esc(tr(i["category"] or "")), PS), SEV_SHORT.get(i["severity"], "?"),
                       STAT_LABEL.get(i["status"], i["status"]),
                       Paragraph(esc(i["pic"]), PS), fmt_date(i["due_date"])]
                sev_c, stat_c, due_c = 5, 6, 8
            else:
                row = [n, i["code"], Paragraph(esc(i["site_name"]), PS), Paragraph(esc(i["panel_tag"] or tr('(umum)')), PS),
                       Paragraph(title, PS), Paragraph(esc(tr(i["category"] or "")), PS), SEV_SHORT.get(i["severity"], "?"),
                       STAT_LABEL.get(i["status"], i["status"]), Paragraph(esc(i["pic"]), PS),
                       fmt_date(i["raised_date"]), fmt_date(i["due_date"]), fmt_date(i["closed_date"]),
                       Paragraph(esc(_clip(i["action"], 450)), PS)]
                sev_c, stat_c, due_c = 6, 7, 10
            r = len(rows)
            rows.append(row)
            # warna baris mengikuti status: merah muda = open, kuning = in progress, hijau = closed
            st.append(("BACKGROUND", (0, r), (-1, r), STAT_BG.get(i["status"], colors.white)))
            st.append(("BACKGROUND", (stat_c, r), (stat_c, r), STAT.get(i["status"], colors.grey)))
            st.append(("TEXTCOLOR", (stat_c, r), (stat_c, r), colors.white))
            st.append(("FONT", (stat_c, r), (stat_c, r), "Helvetica-Bold", 6.5))
            st.append(("ALIGN", (stat_c, r), (stat_c, r), "CENTER"))
            st.append(("VALIGN", (stat_c, r), (stat_c, r), "MIDDLE"))
            # kategori A/B/C: huruf berwarna (bukan blok) supaya tidak tertukar dengan warna status
            st.append(("TEXTCOLOR", (sev_c, r), (sev_c, r), SEV.get(i["severity"], colors.black)))
            st.append(("FONT", (sev_c, r), (sev_c, r), "Helvetica-Bold", 10))
            st.append(("VALIGN", (sev_c, r), (sev_c, r), "MIDDLE"))
            st.append(("ALIGN", (sev_c, r), (sev_c, r), "CENTER"))
            if over:
                st.append(("BACKGROUND", (due_c, r), (due_c, r), C_LATE))
        tb = Table(rows, colWidths=[W * c for c in cw], repeatRows=1)
        tb.setStyle(_base_style([("FONTSIZE", (0, 1), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")] + st))
        return tb

    # ------------------------------------------------------------ punch list
    def punchlist_report(self, path, issue_ids=None, with_photos=True, title=None,
                         filter_text=None, group_by_panel=False, sort="code"):
        title = title or tr('Punch List / Daftar Temuan')
        db = self.db
        allr = db.issues(self.pid, site_id=self.sid)
        ids = set(issue_ids) if issue_ids is not None else None
        iss = [i for i in allr if ids is None or i["id"] in ids]
        st_rank = {s: k for k, s in enumerate(ISSUE_STATUSES)}
        sv_rank = {s: k for k, s in enumerate(SEVERITIES)}
        pan_order = {p["id"]: k for k, p in enumerate(db.panels(self.pid))}
        keys = {
            "code": lambda i: i["id"],
            "status": lambda i: (st_rank.get(i["status"], 9), i["id"]),
            "severity": lambda i: (sv_rank.get(i["severity"], 9), st_rank.get(i["status"], 9), i["id"]),
            "panel": lambda i: (pan_order.get(i["panel_id"], -1), i["id"]),
        }
        iss.sort(key=keys.get(sort, keys["code"]))
        pagesize = landscape(A4)
        W = pagesize[0] - 24 * mm
        story = [Paragraph(esc(title), H1), Spacer(1, 4)]
        extra = [[tr('Filter'), filter_text or tr('Semua punch'), tr('Jumlah'), tr('{0} punch', len(iss))]]
        story.append(self._info_table(W, extra))
        story.append(Spacer(1, 6))
        n_open = sum(1 for i in iss if i["status"] != "Closed")
        t = today()
        n_over = sum(1 for i in iss if i["status"] != "Closed" and i["due_date"] and i["due_date"] < t)
        n_prog = sum(1 for i in iss if i["status"] in ("In Progress", "Ready to Verify"))
        kp = [("TOTAL PUNCH", str(len(iss)), "#0E1A2B"), ("OPEN", str(n_open - n_prog), "#DC2626"),
              ("IN PROGRESS", str(n_prog), "#D97706"), ("CLOSED", str(len(iss) - n_open), "#16A34A"),
              (tr('LEWAT TARGET'), str(n_over), "#DB2777")]
        for s in SEVERITIES:
            kp.append((tr('KAT. {0} AKTIF', SEV_SHORT[s]), str(sum(1 for i in iss if i['severity'] == s and i['status'] != 'Closed')),
                       SEV[s].hexval().replace("0x", "#")))
        story.append(self._kpi_row(W, kp))
        story.append(Spacer(1, 8))
        if iss:
            story.append(self._status_legend())
            story.append(Spacer(1, 4))
            if group_by_panel:
                groups = {}
                for i in iss:
                    groups.setdefault(i["panel_id"], []).append(i)
                order = sorted(groups, key=lambda pid: pan_order.get(pid, -1))
                no = 0
                for pid in order:
                    g = groups[pid]
                    pn = db.panel(pid) if pid else None
                    name = f"{pn['tag']} — {pn['name']}" if pn else tr('Punch umum (tanpa panel)')
                    cnt = {s: sum(1 for i in g if i["status"] == s) for s in ISSUE_STATUSES}
                    parts = "  ".join(
                        f"<font color='{STAT[s].hexval().replace('0x', '#')}'><b>{STAT_LABEL[s]} {cnt[s]}</b></font>"
                        for s in ISSUE_STATUSES if cnt[s])
                    tb = self._issue_table(g, W, compact=False, start_no=no + 1)
                    # judul grup jangan tertinggal sendirian di bawah halaman: pastikan muat judul + header + baris 1
                    tb.wrap(W, 10000)
                    need = 14 * mm + sum(tb._rowHeights[:2])
                    story.append(CondPageBreak(min(need, 150 * mm)))
                    story.append(Paragraph(tr("{0} <font size=8 color='#64748B'>· {1} punch</font>&nbsp;&nbsp;<font size=8>{2}</font>", esc(name), len(g), parts), H2))
                    story.append(tb)
                    no += len(g)
            else:
                story.append(self._issue_table(iss, W, compact=False))
        else:
            story.append(Paragraph(tr('Tidak ada punch yang sesuai filter.'), P))
        story.append(self._signatures(W * 0.75))

        if with_photos:
            # Lampiran foto: kartu per punch, 2 kolom per baris halaman → hemat kertas, tidak ada yang tumpang tindih
            gap = 4 * mm
            cw = (W - gap) / 2               # lebar satu kartu
            pw = (cw - 6 * mm) / 2           # lebar maksimum satu foto (2 foto per baris dalam kartu)
            ph = 48 * mm                     # tinggi maksimum satu foto
            HC = ParagraphStyle("hc", parent=P, fontName="Helvetica-Bold", fontSize=8.5, leading=10.5,
                                textColor=NAVY)
            cards = []
            for i in iss:
                pics = []
                for a in db.attachments(i["id"]):
                    data = db.attachment_data(a["id"])
                    try:
                        iw, ih = ImageReader(io.BytesIO(data)).getSize()
                    except Exception:
                        continue
                    k = min(pw / iw, ph / ih)
                    lab = {"before": tr('SEBELUM'), "after": tr('SESUDAH')}.get(a["kind"], tr('LAMPIRAN'))
                    pics.append([Image(io.BytesIO(data), iw * k, ih * k),
                                 Paragraph(f"<b>{lab}</b> {esc(a['caption'] or '')}", PS)])
                if not pics:
                    continue
                scol = STAT.get(i["status"], colors.grey).hexval().replace("0x", "#")
                head = Paragraph(f"{esc(i['code'])} — {esc(i['title'])}<br/>"
                                 f"<font size=7 color='#4A5568'>{esc(i['site_name'])} / "
                                 f"{esc(i['panel_tag'] or tr('umum'))}</font>  "
                                 f"<font size=7 color='{scol}'><b>[{STAT_LABEL.get(i['status'], i['status'])}]</b>"
                                 f"</font>", HC)
                grid = []
                for k in range(0, len(pics), 2):
                    ch = pics[k:k + 2] + [["", ""]] * (2 - len(pics[k:k + 2]))
                    grid += [[c[0] for c in ch], [c[1] for c in ch]]
                g = Table(grid, colWidths=[(cw - 4) / 2] * 2)
                g.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                                       ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
                card = Table([[head], [g]], colWidths=[cw])
                card.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, GRID),
                                          ("BACKGROUND", (0, 0), (0, 0), STAT_BG.get(i["status"], HEAD_BG)),
                                          ("LINEBELOW", (0, 0), (0, 0), 0.5, GRID),
                                          ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                          ("TOPPADDING", (0, 0), (0, 0), 4), ("BOTTOMPADDING", (0, 0), (0, 0), 4)]))
                cards.append(card)
            if cards:
                story.append(PageBreak())
                story.append(Paragraph(tr('Lampiran Foto'), H1))
                story.append(Spacer(1, 4))
                for k in range(0, len(cards), 2):
                    pair = cards[k:k + 2] + ([""] if len(cards[k:k + 2]) == 1 else [])
                    row = Table([[pair[0], "", pair[1]]], colWidths=[cw, gap, cw])
                    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                    story.append(row)
                    story.append(Spacer(1, gap))
        self._build(path, tr('Punch List'), story, pagesize)

    # ------------------------------------------------------------ panel sheet

    # ------------------------------------------------------------ check sheet
    @staticmethod
    def check_item_filter(rows, sections=None, items="all"):
        """Filter item checklist: sections = set nama seksi (None = semua);
        items = all | pending (belum dicek) | ng | pending_ng."""
        out = []
        for c in rows:
            if sections is not None and c["section"] not in sections:
                continue
            done = c["result"] in ("OK", "NG", "NA")
            if items == "pending" and done:
                continue
            if items == "ng" and c["result"] != "NG":
                continue
            if items == "pending_ng" and done and c["result"] != "NG":
                continue
            out.append(c)
        return out

    def check_sheets(self, path, panel_ids, sections=None, items="all", blank=False, with_punch=True,
                     with_sign=True, title=None, note="", with_photos=True):
        """Lembar uji per panel (portrait A4). Item uji DI/DO tidak ikut — dicetak terpisah (dido_report).

        sections/items: filter isi (lihat check_item_filter); panel yang tidak punya item setelah difilter dilewati.
        blank: form kosong untuk diisi manual di lapangan (hasil/nilai/catatan tidak dicetak).
        Mengembalikan jumlah panel yang dicetak."""
        db = self.db
        pagesize = A4
        W = pagesize[0] - 24 * mm
        ov = {o["panel"]["id"]: o for o in db.panel_overview(self.pid)}
        filtered = sections is not None or items != "all"
        story = []
        first = True
        printed = 0
        for pnid in panel_ids:
            p = db.panel(pnid)
            o = ov.get(pnid)
            if not p or not o:
                continue
            checks = self.check_item_filter([c for c in db.panel_checks(pnid) if not is_dido_section(c["section"])],
                                            sections, items)
            ev_counts = db.check_photo_counts(pnid)
            if filtered and not checks:
                continue
            if not first:
                story.append(PageBreak())
            first = False
            printed += 1
            s, pu = o["stats"], o["punch"]
            story.append(Paragraph(tr('Lembar Uji Panel — {0}', esc(p['tag'])), H1))
            if note:
                story.append(Paragraph(f"<font color='#586064'>{esc(note)}</font>", PS))
            story.append(Spacer(1, 4))
            col = PSTAT.get(o["status"], "#334155")
            info = [
                [tr('Site / GI'), p["site_name"], tr('Tag panel'), p["tag"]],
                [tr('Bay'), p["bay"], tr('Nama'), p["name"]],
                [tr('Tipe'), p["panel_type"], "Vendor", p["vendor"]],
                [tr('Serial number'), p["serial_no"], "Status",
                 _Raw(f"<font color='{col}'><b>{esc(tr(o['status']))}</b></font>"
                      + (f" — {esc(p['accepted_by'])}, {fmt_date(p['accepted_at'])}" if p["accepted_at"] else ""))],
                [tr('Hasil'), _Raw(tr("<b>{0}/{1}</b> item diuji ({2:.0f}%) · <font color='#166534'><b>{3} OK</b></font> · <font color='#B91C1C'><b>{4} NG</b></font> · {5} N/A", s['checked'], s['total'], s['pct'], s['OK'], s['NG'], s['NA'])),
                 tr('Punch'), _Raw(tr('<b>{0}</b> open dari {1}', pu.get('open', 0), pu.get('total', 0)))],
            ]
            if blank:   # form lapangan: status & hasil diisi tangan
                info[3][3] = ""
                info[4] = [tr('Tanggal uji'), "", tr('Penguji'), ""]
            ti = Table([[Paragraph(f"<b>{esc(a)}</b>", P), _cell(b, P),
                         Paragraph(f"<b>{esc(c)}</b>", P), _cell(d, P)]
                        for a, b, c, d in info], colWidths=[W * 0.13, W * 0.37, W * 0.11, W * 0.39 - 30 * mm])
            ti.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GRID), ("BACKGROUND", (0, 0), (0, -1), HEAD_BG),
                                    ("BACKGROUND", (2, 0), (2, -1), HEAD_BG), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            qr = QrCodeWidget(qr_payload(p, db.get_setting("viewer_url")))
            b = qr.getBounds()
            sz = 27 * mm
            dq = Drawing(sz, sz, transform=[sz / (b[2] - b[0]), 0, 0, sz / (b[3] - b[1]), 0, 0])
            dq.add(qr)
            top = Table([[ti, dq]], colWidths=[W - 30 * mm, 30 * mm])
            top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
            story.append(top)
            story.append(Spacer(1, 6))
            punches = {}
            for i in db.issues(self.pid, panel_id=pnid):
                if i["check_id"]:
                    punches.setdefault(i["check_id"], []).append(i["code"])
            photos = {}
            if not blank:
                for c in checks:
                    if c["id"] in ev_counts:
                        photos[c["id"]] = db.check_photos(c["id"])
            rows = [[tr('No'), tr('Item pengecekan'), tr('Kriteria'), tr('Hasil'), tr('Nilai'), tr('Catatan / Punch'), tr('Oleh · Tgl')]]
            st = []
            cur = None
            no = 0
            for c in checks:
                if c["section"] != cur:
                    cur = c["section"]
                    rows.append([Paragraph(f"<b>{esc(cur)}</b>", P), "", "", "", "", "", ""])
                    r = len(rows) - 1
                    st += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F1F5F9"))]
                no += 1
                if blank:
                    crit = esc(c["criteria"]) + (f" {esc(c['unit'])}" if c["unit"] else "")
                    rows.append([no, Paragraph(esc(c["description"]), PS), Paragraph(crit, PS),
                                 Paragraph("<font color='#8C9396' size='6'>OK · NG · N/A</font>", PS), "", "", ""])
                    continue
                note = esc(c["remark"])
                if c["id"] in punches:
                    note += ("<br/>" if note else "") + f"<font color='#B91C1C'>→ {', '.join(punches[c['id']])}</font>"
                if photos.get(c["id"]):
                    note += ("<br/>" if note else "") + \
                        f"<font color='#0F766E'>{esc(tr('Foto evidence: {0}', len(photos[c['id']])))}</font>"
                crit = esc(c["criteria"]) + (f" {esc(c['unit'])}" if c["unit"] else "")
                d_ = parse_date(c["checked_at"])
                by = f"{esc(c['checked_by'])} · {d_.strftime('%d/%m/%y')}" if c["checked_by"] and d_ else \
                    esc(c["checked_by"])
                res = {"NA": "N/A"}.get(c["result"], c["result"] or "")
                rows.append([no, Paragraph(esc(c["description"]), PS), Paragraph(crit, PS), res,
                             Paragraph(esc(c["value"]), PS), Paragraph(note, PS), Paragraph(by, PS)])
                r = len(rows) - 1
                if c["result"] in RES:
                    bg, fg = RES[c["result"]]
                    st += [("BACKGROUND", (3, r), (3, r), bg), ("TEXTCOLOR", (3, r), (3, r), fg),
                           ("FONT", (3, r), (3, r), "Helvetica-Bold", 7.5)]
            widths = (0.05, 0.32, 0.15, 0.12, 0.10, 0.16, 0.10) if blank else (0.05, 0.34, 0.15, 0.07, 0.09, 0.16, 0.14)
            tb = Table(rows, colWidths=[W * x for x in widths], repeatRows=1)
            tb.setStyle(_base_style([("ALIGN", (0, 0), (0, -1), "CENTER"), ("ALIGN", (3, 0), (3, -1), "CENTER"),
                                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE")] + st))
            story.append(tb if checks else Paragraph(tr('<i>Panel belum memiliki checklist.</i>'), P))
            if with_photos and photos:
                self._evidence_photos(story, [c for c in checks if c["id"] in photos], photos, W,
                                      tr('Foto Evidence Pengukuran'), lambda c: c["section"])
            iss = db.issues(self.pid, panel_id=pnid) if with_punch and not blank else []
            if iss:
                story.append(CondPageBreak(30 * mm))
                story.append(Paragraph(tr('Punch List Panel ({0})', len(iss)), H2))
                rows = [[tr('Kode'), tr('Kat.'), tr('Temuan'), "Status", "PIC", tr('Target'), tr('Close')]]
                st = []
                for k, i in enumerate(iss, start=1):
                    rows.append([i["code"], SEV_SHORT.get(i["severity"], "?"),
                                 Paragraph(f"<b>{esc(_clip(i['title'], 300))}</b>"
                                           + (f"<br/>{esc(_clip(i['action'], 700))}" if i["action"] else ""), PS),
                                 STAT_LABEL.get(i["status"], i["status"]), Paragraph(esc(i["pic"]), PS), fmt_date(i["due_date"]),
                                 fmt_date(i["closed_date"])])
                    st += [("BACKGROUND", (0, k), (-1, k), STAT_BG.get(i["status"], colors.white)),
                           ("TEXTCOLOR", (1, k), (1, k), SEV.get(i["severity"], colors.black)),
                           ("FONT", (1, k), (1, k), "Helvetica-Bold", 9), ("ALIGN", (1, k), (1, k), "CENTER"),
                           ("BACKGROUND", (3, k), (3, k), STAT.get(i["status"], colors.grey)),
                           ("TEXTCOLOR", (3, k), (3, k), colors.white), ("FONT", (3, k), (3, k), "Helvetica-Bold", 6.5),
                           ("ALIGN", (3, k), (3, k), "CENTER"), ("VALIGN", (3, k), (3, k), "MIDDLE"),
                           ("VALIGN", (1, k), (1, k), "MIDDLE")]
                tb = Table(rows, colWidths=[W * x for x in (0.09, 0.05, 0.42, 0.13, 0.13, 0.09, 0.09)], repeatRows=1)
                tb.setStyle(_base_style([("VALIGN", (0, 0), (-1, -1), "TOP")] + st))
                story.append(tb)
            if with_sign:
                story.append(self._signatures(W))
        if not printed:
            story.append(Paragraph(tr('<i>Tidak ada item yang cocok dengan filter.</i>'), P))
        self._build(path, title or tr('Lembar Uji Panel'), story, pagesize)
        return printed

    # ------------------------------------------------------------ foto evidence (grid 2 kolom)
    def _evidence_photos(self, story, checks, photos, W, title, group_of):
        """Lampiran foto evidence: 2 foto per baris, caption = grup · item (· caption foto)."""
        db = self.db
        story.append(CondPageBreak(60 * mm))
        story.append(Paragraph(title, H2))
        gap = 4 * mm
        cw = (W - gap) / 2
        pw, ph = cw - 4 * mm, 62 * mm
        cells = []
        for c in checks:
            grp = group_of(c)
            for a in photos.get(c["id"], []):
                data = db.attachment_data(a["id"])
                try:
                    iw, ih = ImageReader(io.BytesIO(data)).getSize()
                except Exception:
                    continue
                k = min(pw / iw, ph / ih)
                cap = (f"<b>{esc(grp)}</b> · " if grp else "") + esc(c["description"]) + \
                    (f" — {esc(c['value'])} {esc(c['unit'] or '')}" if c["value"] else "") + \
                    (f"<br/><i>{esc(a['caption'])}</i>" if a["caption"] else "")
                cells.append(Table([[Image(io.BytesIO(data), iw * k, ih * k)], [Paragraph(cap, PS)]],
                                   colWidths=[cw], style=[("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                                          ("BOX", (0, 0), (-1, -1), 0.5, GRID)]))
        for k in range(0, len(cells), 2):
            pair = cells[k:k + 2] + [""] * (2 - len(cells[k:k + 2]))
            g = Table([pair], colWidths=[cw + gap / 2] * 2)
            g.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), gap / 2)]))
            story += [g, Spacer(1, 3 * mm)]

    # ------------------------------------------------------------ uji DI/DO
    def dido_report(self, path, panel_ids, items="all", with_photos=True, with_sign=True, title=None):
        """Report Uji DI/DO per panel (terpisah dari Lembar Uji): per device, item DI (slot/opto) & DO
        (kontrol/trip/sinyal) dengan hasil, catatan, punch, jumlah foto, lalu lampiran foto evidence.
        Mengembalikan jumlah panel yang dicetak."""
        db = self.db
        pagesize = A4
        W = pagesize[0] - 24 * mm
        story, printed = [], 0
        for pnid in panel_ids:
            p = db.panel(pnid)
            if not p:
                continue
            checks = self.check_item_filter([c for c in db.panel_checks(pnid) if is_dido_section(c["section"])],
                                            None, items)
            if not checks:
                continue
            if printed:
                story.append(PageBreak())
            printed += 1
            photos = {c["id"]: db.check_photos(c["id"]) for c in checks}
            punches = {}
            for i in db.issues(self.pid, panel_id=pnid):
                if i["check_id"]:
                    punches.setdefault(i["check_id"], []).append(i["code"])
            n = {k: sum(1 for c in checks if c["result"] == k) for k in ("OK", "NG", "NA")}
            done = n["OK"] + n["NG"] + n["NA"]
            n_ev = sum(1 for c in checks if photos[c["id"]])
            story.append(Paragraph(tr('Report Uji DI/DO — {0}', esc(p['tag'])), H1))
            story.append(Spacer(1, 4))
            info = [
                [tr('Site / GI'), p["site_name"], tr('Tag panel'), p["tag"]],
                [tr('Bay'), p["bay"], tr('Nama'), p["name"]],
                [tr('Hasil'), _Raw(tr("<b>{0}/{1}</b> item diuji · <font color='#166534'><b>{2} OK</b></font> · "
                                      "<font color='#B91C1C'><b>{3} NG</b></font> · {4} N/A",
                                      done, len(checks), n["OK"], n["NG"], n["NA"])),
                 tr('Evidence'), _Raw(tr('<b>{0}</b> item berfoto · {1} foto', n_ev,
                                         sum(len(v) for v in photos.values())))],
            ]
            ti = Table([[Paragraph(f"<b>{esc(a)}</b>", P), _cell(b, P), Paragraph(f"<b>{esc(c)}</b>", P), _cell(d, P)]
                        for a, b, c, d in info], colWidths=[W * 0.13, W * 0.40, W * 0.13, W * 0.34])
            ti.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GRID), ("BACKGROUND", (0, 0), (0, -1), HEAD_BG),
                                    ("BACKGROUND", (2, 0), (2, -1), HEAD_BG), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            story += [ti, Spacer(1, 6)]
            rows = [[tr('No'), tr('Item uji (lembar drawing)'), tr('Kriteria'), tr('Hasil'), tr('Catatan / Punch'),
                     tr('Foto'), tr('Oleh · Tgl')]]
            st, cur, no = [], None, 0
            for c in checks:
                if c["section"] != cur:
                    cur = c["section"]
                    dev = cur.split("DI/DO", 1)[-1].strip()
                    rows.append([Paragraph(f"<b>{esc(dev)}</b>", P), "", "", "", "", "", ""])
                    r = len(rows) - 1
                    st += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F1F5F9"))]
                no += 1
                note = esc(c["remark"])
                if c["id"] in punches:
                    note += ("<br/>" if note else "") + f"<font color='#B91C1C'>→ {', '.join(punches[c['id']])}</font>"
                d_ = parse_date(c["checked_at"])
                by = f"{esc(c['checked_by'])} · {d_.strftime('%d/%m/%y')}" if c["checked_by"] and d_ else \
                    esc(c["checked_by"])
                k = len(photos[c["id"]])
                rows.append([no, Paragraph(esc(c["description"]), PS), Paragraph(esc(c["criteria"]), PS),
                             {"NA": "N/A"}.get(c["result"], c["result"] or ""), Paragraph(note, PS),
                             str(k) if k else ("–" if c["result"] != "OK" else "!"), Paragraph(by, PS)])
                r = len(rows) - 1
                if c["result"] in RES:
                    bg, fg = RES[c["result"]]
                    st += [("BACKGROUND", (3, r), (3, r), bg), ("TEXTCOLOR", (3, r), (3, r), fg),
                           ("FONT", (3, r), (3, r), "Helvetica-Bold", 7.5)]
                if c["result"] == "OK" and not k:     # OK tanpa bukti
                    st += [("TEXTCOLOR", (5, r), (5, r), colors.HexColor("#C2410C")),
                           ("FONT", (5, r), (5, r), "Helvetica-Bold", 8)]
            tb = Table(rows, colWidths=[W * x for x in (0.05, 0.37, 0.19, 0.07, 0.15, 0.05, 0.12)], repeatRows=1)
            tb.setStyle(_base_style([("ALIGN", (0, 0), (0, -1), "CENTER"), ("ALIGN", (3, 0), (3, -1), "CENTER"),
                                     ("ALIGN", (5, 0), (5, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")] + st))
            story.append(tb)
            story.append(Paragraph(tr("<font size=6.5 color='#586064'>Foto: jumlah foto evidence · "
                                      "<font color='#C2410C'><b>!</b></font> = OK tanpa foto evidence</font>"), P))
            if with_photos and n_ev:
                self._evidence_photos(story, checks, photos, W, tr('Foto Evidence'),
                                      lambda c: c["section"].split("DI/DO", 1)[-1].strip())
            if with_sign:
                story.append(self._signatures(W))
        if not printed:
            story.append(Paragraph(tr('<i>Tidak ada item uji DI/DO pada panel yang dipilih.</i>'), P))
        self._build(path, title or tr('Report Uji DI/DO'), story, pagesize)
        return printed

    # ------------------------------------------------------------ summary
    def summary_report(self, path):
        db, pid, sid = self.db, self.pid, self.sid
        pagesize = landscape(A4)
        W = pagesize[0] - 24 * mm
        o = db.overall(pid, sid)
        story = [Paragraph(tr('Ringkasan Checking Panel & Punch List'), H1), Spacer(1, 4), self._info_table(W),
                 Spacer(1, 6)]
        sv = o["by_severity"]
        story.append(self._kpi_row(W, [
            (tr('PANEL DICEK'), f"{o['panels_started']} / {o['panels']}", "#2563EB"),
            (tr('LULUS / DITERIMA'), str(o["panels_done"]), "#16A34A"),
            (tr('ITEM DIUJI'), f"{o['items_pct']:.0f}%", "#7C3AED"),
            (tr('ITEM NG'), str(o["items"]["NG"]), "#DC2626"),
            (tr('PUNCH OPEN'), str(o['issues_open']), "#EA580C",
             f"<font color='#DC2626'><b>A {sv['Critical']}</b></font> · <font color='#EA580C'><b>B {sv['Major']}</b>"
             f"</font> · <font color='#CA8A04'><b>C {sv['Minor']}</b></font>"),
            (tr('LEWAT TARGET'), str(o["issues_overdue"]), "#DB2777"),
        ]))
        ov = db.panel_overview(pid, sid)
        # per site
        story.append(Paragraph(tr('Rekap per Site'), H2))
        rows = [[tr('Site / GI'), tr('Panel'), tr('Mulai dicek'), tr('Lulus / diterima'), tr('Item diuji'), "", "NG", tr('Punch open'),
                 tr('Kat. A open')]]
        sites = [s for s in db.sites(pid) if not sid or s["id"] == sid]
        open_iss = [i for i in db.issues(pid, site_id=sid) if i["status"] != "Closed"]
        for s in sites:
            sub = [x for x in ov if x["panel"]["site_id"] == s["id"]]
            tot = sum(x["stats"]["total"] for x in sub)
            chk = sum(x["stats"]["checked"] for x in sub)
            pct = 100 * chk / tot if tot else 0
            rows.append([s["name"], len(sub), sum(1 for x in sub if x["stats"]["checked"]),
                         sum(1 for x in sub if x["status"] in ("Lulus", "Diterima")), f"{chk}/{tot}",
                         self._bar(pct, 90), sum(x["stats"]["NG"] for x in sub),
                         # termasuk punch umum (tanpa panel) di site tsb → sama dengan angka KPI
                         sum(1 for i in open_iss if i["site_id"] == s["id"]),
                         sum(1 for i in open_iss if i["site_id"] == s["id"] and i["severity"] == "Critical")])
        t = Table(rows, colWidths=[W * x for x in (0.25, 0.07, 0.09, 0.11, 0.09, 0.14, 0.07, 0.09, 0.09)],
                  repeatRows=1, hAlign="LEFT")
        t.setStyle(_base_style([("ALIGN", (1, 0), (-1, -1), "CENTER")]))
        story.append(t)
        # status panel
        story.append(Paragraph(tr('Status Setiap Panel'), H2))
        rows = [["Site", tr('Bay'), tr('Tag'), tr('Nama'), "Status", tr('Diuji'), "", "OK", "NG", "N/A", tr('Punch open'), tr("Diterima")]]
        st = []
        for k, x in enumerate(ov, start=1):
            pn, s, pu = x["panel"], x["stats"], x["punch"]
            rows.append([Paragraph(esc(pn["site_name"]), PS), Paragraph(esc(pn["bay"]), PS),
                         Paragraph(f"<b>{esc(pn['tag'])}</b>", PS), Paragraph(esc(pn["name"]), PS), tr(x["status"]),
                         f"{s['checked']}/{s['total']}", self._bar(s["pct"], 70), s["OK"], s["NG"] or "", s["NA"] or "",
                         pu.get("open", 0) or "",
                         Paragraph(f"{esc(pn['accepted_by'])}<br/>{fmt_date(pn['accepted_at'])}"
                                   if pn["accepted_at"] else "", PS)])
            st.append(("TEXTCOLOR", (4, k), (4, k), colors.HexColor(PSTAT.get(x["status"], "#334155"))))
            st.append(("FONT", (4, k), (4, k), "Helvetica-Bold", 7.5))
            if s["NG"]:
                st.append(("TEXTCOLOR", (8, k), (8, k), colors.HexColor("#B91C1C")))
            if pu.get("open"):
                st.append(("BACKGROUND", (10, k), (10, k), C_LATE if pu.get("Critical") else colors.HexColor("#FEF3C7")))
        t = Table(rows, colWidths=[W * x for x in (0.09, 0.08, 0.09, 0.2, 0.09, 0.06, 0.1, 0.04, 0.04, 0.04, 0.07,
                                                   0.1)], repeatRows=1)
        t.setStyle(_base_style([("ALIGN", (5, 0), (10, -1), "CENTER")] + st))
        story.append(t)
        # punch A/B open
        iss = [i for i in db.issues(pid, site_id=sid) if i["status"] != "Closed" and i["severity"] in ("Critical", "Major")]
        iss.sort(key=lambda i: (SEVERITIES.index(i["severity"]), i["due_date"] or "9999"))
        story.append(CondPageBreak(40 * mm))
        story.append(Paragraph(tr('Punch Kategori A & B yang Masih Open ({0})', len(iss)), H2))
        story.append(self._issue_table(iss, W, compact=True) if iss else Paragraph(tr('Tidak ada.'), P))
        story.append(self._signatures(W * 0.75))
        self._build(path, tr('Ringkasan Checking'), story, pagesize)

    def qr_label_rolls(self, path, panel_ids, width_mm=50.0, height_mm=30.0, margin_mm=2.0):
        """Label QR untuk printer label thermal (mis. Xprinter): 1 label = 1 halaman PDF seukuran label.

        Hanya hitam pekat (tanpa abu-abu/garis putus) supaya tajam di printer thermal 203 dpi.
        Label melebar → QR di kiri, teks di kanan. Label persegi/tegak → QR di atas, teks di bawah (rata tengah)."""
        from reportlab.lib.utils import simpleSplit
        db = self.db
        W_, H_ = width_mm * mm, height_mm * mm
        m = margin_mm * mm
        url = db.get_setting("viewer_url")
        proj = _one_line(self.project["code"])
        # ukuran huruf mengikuti tinggi label (30 mm → tag 12 pt, info 7 pt)
        short = min(width_mm, height_mm)
        tag_max = max(9.0, min(20.0, short * 0.40))
        tag_min = max(6.5, tag_max * 0.6)
        small = max(5.5, min(10.0, short * 0.23))
        landscape = width_mm >= height_mm * 1.25
        BLACK = colors.black
        c = rl_canvas.Canvas(path, pagesize=(W_, H_))
        c.setTitle(tr('Label QR Panel'))
        n = 0
        for pnid in panel_ids:
            p = db.panel(pnid)
            if not p:
                continue
            if n:
                c.showPage()
            n += 1
            tag = _one_line(p["tag"]) or "-"
            name, bay, site = _one_line(p["name"]), _one_line(p["bay"]), _one_line(p["site_name"])
            if landscape:
                qs = min(H_ - 2 * m, W_ * 0.45)   # sisakan kolom teks yang cukup untuk tag
                qx, qy = m, (H_ - qs) / 2
                tx, avail = qx + qs + 1.5 * mm, W_ - (qx + qs + 1.5 * mm) - m
                top, bottom, align = H_ - m, m, "left"
            else:
                # sisakan tempat untuk tag (≤2 baris) + 1 baris info di bawah QR
                text_h = tag_max * 1.18 * 2 + small * 1.2 + 1.5 * mm
                qs = max(10 * mm, min(W_ - 2 * m, H_ - 2 * m - text_h))
                qx, qy = (W_ - qs) / 2, H_ - m - qs
                tx, avail = m, W_ - 2 * m
                top, bottom, align = qy - 1 * mm, m, "center"
            qr = QrCodeWidget(qr_payload(p, url))
            qr.barFillColor = BLACK
            b = qr.getBounds()
            d = Drawing(qs, qs, transform=[qs / (b[2] - b[0]), 0, 0, qs / (b[3] - b[1]), 0, 0])
            d.add(qr)
            renderPDF.draw(d, c, qx, qy)

            tsz = _fit_size(tag, "Helvetica-Bold", tag_max, avail, tag_min)
            tl = simpleSplit(tag, "Helvetica-Bold", tsz, avail)
            tmax = 3 if landscape else 2   # tag = info terpenting: boleh 3 baris di kolom samping QR
            if len(tl) > tmax:
                tl = tl[:tmax - 1] + [_elide(" ".join(tl[tmax - 1:]), "Helvetica-Bold", tsz, avail)]
            lines = [(ln, "Helvetica-Bold", tsz) for ln in tl]
            info = [(name, 2), (tr('Bay: {0}', bay) if bay and bay.lower() != name.lower() else "", 1),
                    (site, 1), (proj, 1)]
            if not landscape:
                info = [(name, 1)]   # label kecil/tegak: cukup tag + nama
            for txt, nmax in info:
                if not txt:
                    continue
                parts = simpleSplit(txt, "Helvetica", small, avail)
                if len(parts) > nmax:
                    parts = parts[:nmax - 1] + [_elide(" ".join(parts[nmax - 1:]), "Helvetica", small, avail)]
                lines += [(ln, "Helvetica", small) for ln in parts]
            c.setFillColor(BLACK)
            cy = top
            for txt, font, size in lines:
                if cy - size < bottom:   # label penuh: sisa baris tidak digambar (tidak menimpa)
                    break
                c.setFont(font, size)
                y = cy - size * 0.82
                if align == "center":
                    c.drawCentredString(W_ / 2, y, txt)
                else:
                    c.drawString(tx, y, txt)
                cy -= size * 1.18
        if not n:
            c.setFont("Helvetica", 6)
            c.drawString(m, m, "-")
        c.save()
        return n

    def qr_labels(self, path, panel_ids, cols=3, rows=8):
        """Label QR untuk ditempel di panel. Isi QR: lihat qr_payload() (link viewer web atau PT:<uuid>:<tag>).

        Teks disusun baris demi baris dari atas dengan jarak tetap, dibungkus (wrap) bila panjang dan dipotong rapi
        bila kotak penuh, jadi tidak pernah saling menimpa."""
        from reportlab.lib.utils import simpleSplit
        db = self.db
        w, h = A4
        mx, my = 8 * mm, 12 * mm
        lw = (w - 2 * mx) / cols
        lh = (h - 2 * my) / rows
        c = rl_canvas.Canvas(path, pagesize=A4)
        c.setTitle(tr('Label QR Panel'))
        k = 0
        for pnid in panel_ids:
            p = db.panel(pnid)
            if not p:
                continue
            if k and k % (cols * rows) == 0:
                c.showPage()
            pos = k % (cols * rows)
            col, row = pos % cols, pos // cols
            x = mx + col * lw
            y = h - my - (row + 1) * lh
            c.setStrokeColor(colors.HexColor("#C0C8D2"))
            c.setLineWidth(0.5)
            c.setDash(2, 2)
            c.rect(x + 1, y + 1, lw - 2, lh - 2)
            c.setDash()
            # QR di kiri, kotak persegi dengan margin tenang di sekelilingnya
            qs = min(lh - 5 * mm, lw * 0.42)
            qr = QrCodeWidget(qr_payload(p, db.get_setting("viewer_url")))
            b = qr.getBounds()
            d = Drawing(qs, qs, transform=[qs / (b[2] - b[0]), 0, 0, qs / (b[3] - b[1]), 0, 0])
            d.add(qr)
            renderPDF.draw(d, c, x + 1.5 * mm, y + (lh - qs) / 2)
            tx = x + qs + 3 * mm
            avail = x + lw - 2.5 * mm - tx
            top = y + lh - 3.5 * mm          # batas atas teks
            bottom = y + 6.5 * mm            # di bawah ini hanya kode project

            tag = _one_line(p["tag"]) or "-"
            # tag: perkecil dulu (12 → 8 pt); kalau masih kepanjangan, bungkus jadi maks 2 baris
            tsz = _fit_size(tag, "Helvetica-Bold", 12, avail, 8)
            tlines = simpleSplit(tag, "Helvetica-Bold", tsz, avail)
            if len(tlines) > 2:
                tlines = tlines[:1] + [_elide(" ".join(tlines[1:]), "Helvetica-Bold", tsz, avail)]
            lines = [(ln, "Helvetica-Bold", tsz, NAVY) for ln in tlines]
            lines.append(None)   # jarak kecil setelah tag
            name, bay, site = _one_line(p["name"]), _one_line(p["bay"]), _one_line(p["site_name"])
            for txt, nmax in ((name, 2),
                              (tr('Bay: {0}', bay) if bay and bay.lower() != name.lower() else "", 2),
                              (site, 1)):
                if not txt:
                    continue
                parts = simpleSplit(txt, "Helvetica", 7, avail)
                if len(parts) > nmax:
                    parts = parts[:nmax - 1] + [_elide(" ".join(parts[nmax - 1:]), "Helvetica", 7, avail)]
                lines += [(ln, "Helvetica", 7, colors.black) for ln in parts]
            cy = top
            for i, ln in enumerate(lines):
                if ln is None:
                    cy -= 1.2 * mm
                    continue
                txt, font, size, col = ln
                lead = size * 1.18
                if cy - size < bottom:            # kotak penuh: baris sisanya tidak digambar (tidak menimpa)
                    break
                c.setFillColor(col)
                c.setFont(font, size)
                c.drawString(tx, cy - size * 0.82, txt)
                cy -= lead
            c.setFillColor(colors.HexColor("#6B7785"))
            c.setFont("Helvetica", 6)
            c.drawString(tx, y + 3.5 * mm, _elide(_one_line(self.project["code"]), "Helvetica", 6, avail))
            k += 1
        c.save()
