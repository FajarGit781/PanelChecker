"""Uji proteksi relay (OCR/GFR, SBEF, 87L/87T/87B, REF, distance, 50BF, AR, sync, AVR, uji fungsional).

Disimpan sebagai item checklist biasa (tanpa tabel baru), sama persis dengan aplikasi HP (src/relaytest.ts):

  seksi    "<huruf>. SAS · Uji Proteksi <device>"
  toleransi  unit "psetup", deskripsi "Toleransi uji", kriteria "waktu 5% / 40 ms · pickup 5%" (hasil OK saat dibuat)
  setting  unit "fset", deskripsi "F1 · 51 · OCR fasa (IDMT)", kriteria "kurva=IEC SI; Is=1; TMS=0.1" (boleh kosong dulu;
           hasil OK/NG diisi teknisi = setting di relay sesuai approval)
  titik    deskripsi "F1 · 51 · 2×Is", unit "s"/"A"/"In"/…, kriteria "expected ± toleransi" (dihitung dari setting),
           nilai = actual, OK/NG otomatis
  cek      fungsi jenis "check" (TCS, lockout, Buchholz, …): satu item tanpa satuan, OK/NG/N/A manual.
Foto evidence satu fungsi ditempel di item titik pertamanya (atau item cek).
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- katalog fungsi
# code: (nama, jenis[, satuan pickup untuk jenis dt])
FUNCS = {
    "50": ("OCR instant fasa", "dt", "A"),
    "51": ("OCR fasa (IDMT)", "idmt"),
    "50N": ("GFR instant", "dt", "A"),
    "51N": ("GFR (IDMT)", "idmt"),
    "51NS": ("SBEF standby earth fault", "idmt"),
    "67N": ("DEF directional earth fault", "dt", "A"),
    "87L": ("Differential line", "diff"),
    "87T": ("Differential trafo", "diff"),
    "87B": ("Differential busbar", "diff"),
    "87H2": ("Blocking harmonik ke-2 (inrush)", "pct"),
    "87H5": ("Blocking harmonik ke-5 (overflux)", "pct"),
    "64REF": ("Restricted earth fault", "dt", "A"),
    "21Z1": ("Distance zona 1", "dt", "Ω"),
    "21Z2": ("Distance zona 2", "dt", "Ω"),
    "21Z3": ("Distance zona 3", "dt", "Ω"),
    "49": ("Thermal overload", "dt", "A"),
    "24": ("Overfluxing V/Hz", "dt", "%"),
    "50BF": ("CB failure", "bf"),
    "79": ("Auto-reclose", "ar"),
    "25": ("Check synchronizing", "sync"),
    "90": ("AVR (tap changer)", "avr"),
    "STAB": ("Stabilitas gangguan eksternal (through fault)", "check"),
    "CTS": ("CT supervision", "check"),
    "COMM": ("Kanal komunikasi differential (end-to-end)", "check"),
    "CZ": ("Check zone busbar", "check"),
    "DZ": ("Dead zone / end fault", "check"),
    "ISO": ("Replika isolator (topologi zona)", "check"),
    "85": ("Intertrip / DTT", "check"),
    "TRIP": ("Matriks trip ke CB (coil 1 & 2)", "check"),
    "74": ("Trip circuit supervision", "check"),
    "86": ("Lockout & reset", "check"),
    "EVT": ("Event & disturbance record ke SCADA/HMI", "check"),
    "BUCH": ("Buchholz alarm & trip", "check"),
    "SPR": ("Sudden pressure trip", "check"),
    "OLTCP": ("OLTC protective relay trip", "check"),
    "OTI": ("Oil temperature alarm & trip", "check"),
    "WTI": ("Winding temperature alarm & trip", "check"),
    "OLI": ("Oil level alarm", "check"),
    "TAP": ("Indikasi posisi tap (AVR, BCU, HMI)", "check"),
    "RL": ("Perintah Raise/Lower dari HMI/SCADA", "check"),
    "AM": ("Mode Auto/Manual & Local/Remote", "check"),
    "AVRB": ("Blocking AVR (UV, OV/fast lower, OC, batas tap)", "check"),
    "LDC": ("Line drop compensation (LDC)", "check"),
}

# preset fungsi per model relay (dicocokkan dari nama device); urutan = urutan blok
PRESETS = [
    (r"P643", ["87T", "87H2", "87H5", "64REF", "51", "51N", "49", "24", "STAB", "CTS", "BUCH", "SPR", "OLTCP", "OTI",
               "WTI", "OLI", "TRIP", "86", "74", "EVT"]),
    (r"PCS-?931", ["87L", "COMM", "21Z1", "21Z2", "21Z3", "67N", "51", "51N", "85", "STAB", "CTS", "TRIP", "74", "EVT"]),
    (r"P746", ["87B", "CZ", "STAB", "DZ", "ISO", "CTS", "TRIP", "EVT"]),
    (r"P841", ["50BF", "79", "25", "TRIP", "EVT"]),
    (r"P5F30", ["50", "51", "50N", "51N", "51NS", "TRIP", "74", "EVT"]),
    (r"P143", ["50", "51", "50N", "51N", "TRIP", "74", "EVT"]),
    (r"RTF|AVR", ["90", "TAP", "RL", "AM", "AVRB", "LDC"]),
]
DEFAULT_PRESET = ["51", "51N", "TRIP", "74", "EVT"]

CURVES = {  # IEC 60255-151 / IEEE C37.112: (k, alpha, B) → t = TMS·(k/(M^α−1) + B)
    "IEC SI": (0.14, 0.02, 0.0), "IEC VI": (13.5, 1.0, 0.0), "IEC EI": (80.0, 2.0, 0.0), "IEC LTI": (120.0, 1.0, 0.0),
    "IEEE MI": (0.0515, 0.02, 0.114), "IEEE VI": (19.61, 2.0, 0.491), "IEEE EI": (28.2, 2.0, 0.1217), "DT": None,
}

# parameter per jenis: (kunci, label, satuan)
PARAMS = {
    "idmt": [("kurva", "Kurva", ""), ("Is", "Is (sekunder)", "A"), ("TMS", "TMS / waktu DT", "")],
    "dt": [("P", "Pickup", "@"), ("t", "Waktu trip", "s")],
    "diff": [("Is1", "Is1", "In"), ("K1", "Slope K1", "%"), ("Is2", "Is2 (tekuk)", "In"), ("K2", "Slope K2", "%")],
    "pct": [("P", "Setting", "%")],
    "bf": [("I", "I> CB fail", "A"), ("t1", "t1 retrip", "s"), ("t2", "t2 backtrip", "s")],
    "ar": [("td", "Dead time", "s"), ("tr", "Reclaim time", "s")],
    "sync": [("dV", "ΔV", "V"), ("df", "Δf", "Hz"), ("dphi", "Δφ", "°")],
    "avr": [("V", "Setpoint (sekunder)", "V"), ("BW", "Bandwidth ±", "%"), ("T1", "Delay T1", "s")],
    "check": [],
}
DEC = {"s": 3, "A": 3, "In": 3, "%": 1, "V": 2, "Hz": 3, "°": 1, "Ω": 3}
SETUP_UNIT, FSET_UNIT = "psetup", "fset"
SETUP_DESC = "Toleransi uji"
DEFAULT_TOL = dict(t_pct=5.0, t_ms=40.0, p_pct=5.0)
IDMT_MULT = (2, 5, 10)
DIFF_BIAS = (0, 1, 2, 4)

_SEC = re.compile(r"^([A-Z]{1,2})\. SAS · Uji Proteksi (.+)$")
_DESC = re.compile(r"^F(\d+) · ([0-9A-Z]+) · (.+)$")


def is_protection_section(section) -> bool:
    return bool(_SEC.match(section or ""))


def device_of(section) -> str:
    m = _SEC.match(section or "")
    return m.group(2) if m else ""


def section_name(letter, device) -> str:
    return f"{letter}. SAS · Uji Proteksi {device.strip()}"


def kind_of(code):
    return FUNCS[code][1] if code in FUNCS else "check"


def pickup_unit(code):
    f = FUNCS.get(code)
    return f[2] if f and len(f) > 2 else "A"


def preset_for(device):
    for rx, codes in PRESETS:
        if re.search(rx, device or "", re.I):
            return list(codes)
    return list(DEFAULT_PRESET)


def _g(x) -> str:
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:.6g}"


def num(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- toleransi blok
def tol_text(t) -> str:
    return f"waktu {_g(t['t_pct'])}% / {_g(t['t_ms'])} ms · pickup {_g(t['p_pct'])}%"


def parse_tol(text):
    m = re.search(r"waktu (\d+(?:\.\d+)?)% / (\d+(?:\.\d+)?) ms · pickup (\d+(?:\.\d+)?)%", text or "")
    if not m:
        return dict(DEFAULT_TOL)
    return dict(t_pct=float(m.group(1)), t_ms=float(m.group(2)), p_pct=float(m.group(3)))


# ---------------------------------------------------------------- setting fungsi ("k=v; k=v")
def params_text(p) -> str:
    return "; ".join(f"{k}={v}" for k, v in p.items() if str(v).strip() != "")


def parse_params(text):
    out = {}
    for part in (text or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def complete(code, p) -> bool:
    """Semua parameter wajib terisi & valid (waktu dt boleh kosong = hanya uji pickup)."""
    kind = kind_of(code)
    for k, _, _ in PARAMS[kind]:
        if kind == "dt" and k == "t":
            continue
        if k == "kurva":
            if p.get(k) not in CURVES:
                return False
            continue
        v = num(p.get(k))
        if v is None or v < 0 or (k in ("Is", "P", "I", "V", "Is1") and v <= 0):
            return False
    if kind == "idmt" and (num(p.get("TMS")) or 0) <= 0:
        return False
    return True


# ---------------------------------------------------------------- titik uji
def points(code):
    """Label titik uji per fungsi (tetap; tidak tergantung nilai setting): [(label, satuan)]."""
    kind = kind_of(code)
    if kind == "idmt":
        return [("pickup", "A")] + [(f"{m}×Is", "s") for m in IDMT_MULT]
    if kind == "dt":
        return [("pickup", pickup_unit(code)), ("waktu trip", "s")]
    if kind == "diff":
        return [("pickup Ibias 0", "In")] + [(f"Ibias {b} In", "In") for b in DIFF_BIAS[1:]]
    if kind == "pct":
        return [("pickup", "%")]
    if kind == "bf":
        return [("pickup I>", "A"), ("t1 retrip", "s"), ("t2 backtrip", "s")]
    if kind == "ar":
        return [("dead time", "s"), ("reclaim time", "s")]
    if kind == "sync":
        return [("ΔV", "V"), ("Δf", "Hz"), ("Δφ", "°")]
    if kind == "avr":
        return [("V di atas band → Lower", "s"), ("V di bawah band → Raise", "s")]
    return []


def idmt_time(curve, tms, m):
    if curve == "DT":
        return tms
    k, a, b = CURVES[curve]
    d = m ** a - 1
    return tms * (k / d + b) if d > 0 else None


def diff_threshold(p, ibias):
    is1, k1, is2, k2 = (num(p.get(x)) for x in ("Is1", "K1", "Is2", "K2"))
    k1, k2 = k1 / 100, k2 / 100
    if ibias <= is2:
        return is1 + k1 * ibias
    return is1 + k1 * is2 + k2 * (ibias - is2)


def expected(code, p, tol):
    """[(label, satuan, expected, toleransi absolut)] atau [] bila setting belum lengkap. Titik 'waktu trip' dt
    tanpa setting waktu → expected None (titik dilewati)."""
    if not complete(code, p):
        return []
    kind = kind_of(code)
    tp, tms_, pp = tol["t_pct"] / 100, tol["t_ms"] / 1000, tol["p_pct"] / 100
    tt = lambda t: max(t * tp, tms_)                       # noqa: E731
    out = []
    for label, unit in points(code):
        e = None
        if kind == "idmt":
            if label == "pickup":
                e = num(p["Is"])
            else:
                e = idmt_time(p["kurva"], num(p["TMS"]), float(label.split("×")[0]))
        elif kind == "dt":
            e = num(p.get("P")) if label == "pickup" else num(p.get("t"))
        elif kind == "diff":
            b = 0 if label.startswith("pickup") else float(label.split()[1])
            e = diff_threshold(p, b)
        elif kind == "pct":
            e = num(p["P"])
        elif kind == "bf":
            e = num(p[{"pickup I>": "I", "t1 retrip": "t1", "t2 backtrip": "t2"}[label]])
        elif kind == "ar":
            e = num(p["td"] if label == "dead time" else p["tr"])
        elif kind == "sync":
            e = num(p[{"ΔV": "dV", "Δf": "df", "Δφ": "dphi"}[label]])
        elif kind == "avr":
            e = num(p["T1"])
        if e is None:
            out.append((label, unit, None, None))
            continue
        out.append((label, unit, e, tt(e) if unit == "s" else abs(e) * pp))
    return out


def inject_hint(code, p, label):
    """Panduan injeksi sekunder untuk satu titik ('' bila tidak ada)."""
    if not complete(code, p):
        return ""
    kind = kind_of(code)
    if kind == "idmt" and "×" in label:
        m = float(label.split("×")[0])
        return f"injeksi {m * num(p['Is']):.3f} A"
    if kind == "idmt" and label == "pickup":
        return f"naikkan arus pelan dari {0.9 * num(p['Is']):.3f} A"
    if kind == "dt" and label == "waktu trip" and pickup_unit(code) == "A":
        return f"injeksi {2 * num(p['P']):.3f} A (2× pickup)"
    if kind == "diff" and not label.startswith("pickup"):
        b = float(label.split()[1])
        return f"Ibias {_g(b)} In, naikkan Idiff dari {0.9 * diff_threshold(p, b):.3f} In"
    if kind == "bf" and label != "pickup I>":
        return f"injeksi {2 * num(p['I']):.3f} A + trip relay, CB tidak membuka"
    if kind == "avr":
        v, bw = num(p["V"]), num(p["BW"])
        f = 1 + (bw + 0.5) / 100 if "atas" in label else 1 - (bw + 0.5) / 100
        return f"injeksi {v * f:.2f} V (band {v * (1 - bw / 100):.2f}–{v * (1 + bw / 100):.2f} V)"
    return ""


def fmt(x, unit) -> str:
    return f"{x:.{DEC.get(unit, 3)}f}"


def criteria_text(unit, e, tol) -> str:
    return "" if e is None else f"{fmt(e, unit)} ± {fmt(tol, unit)}"


def to_num(text):
    m = re.search(r"-?\d[\d.,]*", str(text or ""))
    if not m:
        return None
    t = m.group(0)
    t = t.replace(",", ".") if ("," in t and "." not in t) else t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def judge(e, tol, actual) -> str:
    a = to_num(actual)
    if a is None or e is None:
        return ""
    return "OK" if abs(a - e) <= tol + 1e-9 else "NG"


# ---------------------------------------------------------------- item blok
def fn_desc(n, code) -> str:
    return f"F{n} · {code} · {FUNCS.get(code, (code,))[0]}"


def point_desc(n, code, label) -> str:
    return f"F{n} · {code} · {label}"


def function_items(sec, n, code, p=None, tol=None):
    """[(section, description, criteria, unit)] satu fungsi."""
    p, tol = p or {}, tol or DEFAULT_TOL
    if kind_of(code) == "check":
        return [(sec, point_desc(n, code, FUNCS.get(code, (code,))[0]), "", "")]
    out = [(sec, fn_desc(n, code), params_text(p), FSET_UNIT)]
    ex = {lab: (e, t) for lab, _, e, t in expected(code, p, tol)}
    for label, unit in points(code):
        e, t = ex.get(label, (None, None))
        out.append((sec, point_desc(n, code, label), criteria_text(unit, e, t), unit))
    if kind_of(code) == "avr":
        out.append((sec, point_desc(n, code, "V di dalam band → tidak ada perintah"), "Tidak ada Raise/Lower", ""))
    return out


def block_items(device, letter, codes, tol=None):
    sec = section_name(letter, device)
    tol = tol or dict(DEFAULT_TOL)
    out = [(sec, SETUP_DESC, tol_text(tol), SETUP_UNIT)]
    for n, code in enumerate(codes, 1):
        out += function_items(sec, n, code, None, tol)
    return out


def group(rows, key=lambda r: r):
    """{'setup': row|None, 'tol': dict, 'funcs': [{'n','code','name','kind','fset': row|None, 'points': [(label,row)]}]}"""
    setup, fs = None, {}
    for r in rows:
        d = key(r)
        if (d["unit"] or "") == SETUP_UNIT:
            setup = setup or r
            continue
        m = _DESC.match(d["description"] or "")
        if not m:
            continue
        n, code, rest = int(m.group(1)), m.group(2), m.group(3)
        f = fs.setdefault(n, dict(n=n, code=code, name=FUNCS.get(code, (code,))[0], kind=kind_of(code), fset=None, points=[]))
        if (d["unit"] or "") == FSET_UNIT:
            f["fset"] = f["fset"] or r
        else:
            f["points"].append((rest, r))
    tol = parse_tol(key(setup)["criteria"]) if setup is not None else dict(DEFAULT_TOL)
    return dict(setup=setup, tol=tol, funcs=[fs[k] for k in sorted(fs)])


def next_letter(sections) -> str:
    from .injection import next_letter as nl
    return nl(sections)
