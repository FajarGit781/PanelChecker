"""Project contoh supaya aplikasi bisa langsung dicoba."""
from __future__ import annotations

import datetime as dt
import random

from .db import Database


def _demo_photo(text: str, color) -> bytes:
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
        from PySide6.QtGui import QColor, QFont, QImage, QPainter
        img = QImage(640, 420, QImage.Format_RGB32)
        img.fill(QColor(*color))
        p = QPainter(img)
        p.setPen(QColor(255, 255, 255, 60))
        for k in range(0, 640, 40):
            p.drawLine(k, 0, k, 420)
        p.setPen(QColor(255, 255, 255))
        f = QFont()
        f.setPointSize(22)
        f.setBold(True)
        p.setFont(f)
        p.drawText(img.rect(), Qt.AlignCenter | Qt.TextWordWrap, text)
        p.end()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "JPG", 85)
        return bytes(ba)
    except Exception:
        return b""


NG_PUNCH = {
    "Kekencangan terminal (torque check)": ("Terminal kendor di TB-X1", "Wiring", "Major"),
    "Ferrule / marking kabel sesuai": ("Ferrule tidak sesuai wiring diagram", "Dokumen", "Minor"),
    "GOOSE publish / subscribe": ("GOOSE trip tidak diterima BCU", "Komunikasi / IEC 61850", "Critical"),
    "Firmware & setting relay sesuai approval": ("Setting OCR belum sesuai approval", "Setting Relay", "Major"),
    "Pintu, engsel, handle & kunci berfungsi": ("Engsel pintu belakang tidak rapat", "Mekanikal", "Minor"),
    "Point-to-point status & alarm ke SCADA": ("Alarm DC fail terbalik di HMI", "SCADA / HMI", "Major"),
    "Grounding body & pintu panel terpasang": ("Kabel grounding pintu belum terpasang", "Mekanikal", "Minor"),
    "Time synchronization (SNTP/PTP)": ("IED tidak sync ke SNTP server", "Komunikasi / IEC 61850", "Major"),
    "Logika interlock sesuai diagram": ("Interlock DS-ES tidak blok saat ES close", "Interlock", "Critical"),
    "Supervisi / alarm DC fail": ("Alarm DC fail tidak muncul", "Power Supply", "Major"),
    "Label komponen (MCB, relay, terminal) lengkap": ("Label MCB heater belum ada", "Dokumen", "Minor"),
    "Redundansi PRP/HSR / RSTP": ("Packet loss saat cabut link LAN-B", "Komunikasi / IEC 61850", "Major"),
}


def create_demo(db: Database) -> int:
    rnd = random.Random(7)
    t = dt.date.today()
    pid = db.add_project("DEMO-SAT", "Demo SAT SAS GI 150 kV", client="PLN UIP Contoh",
                         contractor="PT Kontraktor Contoh", start_date=(t - dt.timedelta(days=40)).isoformat(),
                         end_date=(t + dt.timedelta(days=60)).isoformat(), issue_prefix="PL",
                         description="Project contoh – boleh dihapus.")
    tpls = {r["name"]: r["id"] for r in db.templates()}
    t_prot = next(v for k, v in tpls.items() if k.startswith("Panel Proteksi"))
    t_rtu = next(v for k, v in tpls.items() if k.startswith("Panel RTU"))
    bays = [("Line 1", "CRP", "Control & Relay Panel Line 1"), ("Line 2", "CRP", "Control & Relay Panel Line 2"),
            ("Trafo 1", "CP", "Control Panel Trafo 1"), ("Trafo 1", "RP", "Relay Panel Trafo 1"),
            ("Kopel", "CRP", "Control & Relay Panel Kopel"), ("Common", "RTU / Gateway", "Gateway & Station Panel")]
    plan = {"GI Alpha": [1.0] * 6, "GI Bravo": [1.0, 0.8, 0.7, 0.6, 0.5, 0.4], "GI Charlie": [0.3, 0.15, 0, 0, 0, 0]}
    pics = ["Vendor Panel", "Engineer Proteksi", "Engineer SCADA", "Tim Wiring"]
    for sname, frac in plan.items():
        sid = db.add_site(pid, sname)
        for i, (bay, typ, nm) in enumerate(bays):
            tag = f"{sname.split()[-1][0]}-{typ.split()[0][:3].upper()}-{i + 1:02d}"
            tpl = t_rtu if typ.startswith("RTU") else t_prot
            pn = db.add_panel(sid, tag, template_id=tpl, bay=bay, name=nm, panel_type=typ, vendor="Vendor Contoh",
                              serial_no=f"SN{rnd.randint(10000, 99999)}")
            checks = db.panel_checks(pn)
            n_do = int(round(len(checks) * frac[i]))
            for k, c in enumerate(checks[:n_do]):
                res = "OK"
                if c["description"] in NG_PUNCH and rnd.random() < 0.22:
                    res = "NG"
                elif "Synchrocheck" in c["description"] and rnd.random() < 0.5:
                    res = "NA"
                val = ""
                if c["unit"] == "VDC":
                    val = f"{rnd.uniform(108, 114):.1f}"
                elif c["unit"] == "VAC":
                    val = f"{rnd.uniform(225, 233):.0f}"
                elif c["unit"] == "MΩ":
                    val = f">{rnd.choice([200, 500, 1000])}"
                ts = (t - dt.timedelta(days=rnd.randint(0, 25))).isoformat() + "T10:00:00"
                db.conn.execute("UPDATE panel_check SET result=?, value=?, checked_by=?, checked_at=? WHERE id=?",
                                (res, val, "Fajar", ts, c["id"]))
                if res == "NG":
                    title, cat, sev = NG_PUNCH[c["description"]]
                    raised = t - dt.timedelta(days=rnd.randint(1, 25))
                    due = raised + dt.timedelta(days={"Critical": 3, "Major": 7, "Minor": 14}[sev])
                    st = rnd.choice(["Open", "Open", "In Progress", "Ready to Verify", "Closed"])
                    iid = db.add_issue(pid, panel_id=pn, check_id=c["id"], title=title, category=cat, severity=sev,
                                       status=st, pic=rnd.choice(pics), raised_by="Fajar",
                                       description=f"Ditemukan saat cek: {c['description']}.",
                                       raised_date=raised.isoformat(), due_date=due.isoformat(),
                                       closed_date=(due - dt.timedelta(days=1)).isoformat() if st == "Closed" else None,
                                       verified_by="Owner" if st == "Closed" else "",
                                       action="Sudah diperbaiki & diuji ulang." if st == "Closed" else "")
                    if rnd.random() < 0.5:
                        db.add_attachment(iid, "temuan.jpg", _demo_photo(f"FOTO TEMUAN\n{title}", (150, 55, 55)),
                                          kind="before", caption="Kondisi saat ditemukan")
                    if st == "Closed":
                        db.conn.execute("UPDATE panel_check SET result='OK', remark='Re-test OK setelah perbaikan', dirty=1 "
                                        "WHERE id=?", (c["id"],))
                        db.add_attachment(iid, "perbaikan.jpg", _demo_photo("SETELAH PERBAIKAN", (40, 120, 75)),
                                          kind="after", caption="Setelah perbaikan")
            db.conn.commit()
    # punch umum (tidak terkait panel)
    s1 = db.sites(pid)[0]["id"]
    db.add_issue(pid, site_id=s1, title="As-built drawing belum diserahkan", category="Dokumen", severity="Minor",
                 status="Open", pic="Kontraktor", raised_date=(t - dt.timedelta(days=5)).isoformat(),
                 due_date=(t + dt.timedelta(days=9)).isoformat())
    # terima 2 panel yang lulus
    for o in db.panel_overview(pid):
        if o["status"] == "Lulus" and rnd.random() < 0.5:
            db.set_accepted(o["panel"]["id"], "Owner")
    return pid
