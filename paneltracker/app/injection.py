"""Uji injeksi sekunder CT/VT: expected I, V, MW, MVAR, PF, f dihitung dari rasio CT/VT dan % injeksi.

Disimpan sebagai item checklist biasa (tanpa tabel baru), sama persis dengan aplikasi HP
(paneltracker-mobile/src/injection.ts), sehingga sinkron, foto evidence, punch dan app versi lama tetap jalan:

  seksi   "<huruf>. SAS · Injeksi CT/VT <device>"
  setup   unit "setup", kriteria "CT 2000/1 A · VT 150 kV/110 V · tol 1% · PF ±0.01 · f ±0.02 Hz"
  titik   deskripsi "T1 · I 10% · V 100% · φ 0° · 50 Hz · IA", unit "A", kriteria "200.0 ± 2.0" (expected ± toleransi)
          nilai = actual, hasil OK/NG dihitung otomatis dari actual.

Toleransi: I dan V = tol% dari expected; P dan Q = tol% dari S (MVA) supaya Q≈0 tidak menghasilkan error % tak hingga;
PF dan f = selisih absolut. Foto evidence satu titik uji ditempel di item pertamanya (IA).
"""
from __future__ import annotations

import math
import re

SQ3 = math.sqrt(3)
KEYS = ("IA", "IB", "IC", "VAB", "VBC", "VCA", "P", "Q", "PF", "f")
UNIT = {"IA": "A", "IB": "A", "IC": "A", "VAB": "kV", "VBC": "kV", "VCA": "kV", "P": "MW", "Q": "MVAR", "PF": "PF", "f": "Hz"}
DEC = {"IA": 1, "IB": 1, "IC": 1, "VAB": 3, "VBC": 3, "VCA": 3, "P": 3, "Q": 3, "PF": 3, "f": 2}
LABEL = {"f": "Frekuensi"}
SETUP_UNIT = "setup"
SETUP_DESC = "Setup injeksi"

_SEC = re.compile(r"^([A-Z]{1,2})\. SAS · Injeksi CT/VT (.+)$")
_N = r"(-?\d+(?:\.\d+)?)"
_SETUP = re.compile(rf"CT {_N}/{_N} A · VT {_N} kV/{_N} V · tol {_N}% · PF ±{_N} · f ±{_N} Hz")
_POINT = re.compile(rf"^T(\d+) · I {_N}% · V {_N}% · φ {_N}° · {_N} Hz · ({'|'.join(KEYS)})$")
DEFAULT_SETUP = dict(ct_p=2000.0, ct_s=1.0, vt_p=150.0, vt_s=110.0, tol=1.0, tol_pf=0.01, tol_f=0.02)


def is_injection_section(section) -> bool:
    return bool(_SEC.match(section or ""))


def device_of(section) -> str:
    m = _SEC.match(section or "")
    return m.group(2) if m else ""


def section_name(letter, device) -> str:
    return f"{letter}. SAS · Injeksi CT/VT {device.strip()}"


def _g(x) -> str:
    """Angka ringkas untuk teks yang disimpan (titik desimal, tanpa nol berlebih)."""
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:.6g}"


# ---------------------------------------------------------------- setup
def setup_text(s) -> str:
    return (f"CT {_g(s['ct_p'])}/{_g(s['ct_s'])} A · VT {_g(s['vt_p'])} kV/{_g(s['vt_s'])} V · "
            f"tol {_g(s['tol'])}% · PF ±{_g(s['tol_pf'])} · f ±{_g(s['tol_f'])} Hz")


def parse_setup(text):
    m = _SETUP.search(text or "")
    if not m:
        return None
    v = [float(x) for x in m.groups()]
    s = dict(zip(("ct_p", "ct_s", "vt_p", "vt_s", "tol", "tol_pf", "tol_f"), v))
    if s["ct_p"] <= 0 or s["ct_s"] <= 0 or s["vt_p"] <= 0 or s["vt_s"] <= 0:
        return None
    return s


# ---------------------------------------------------------------- titik uji
def point_desc(n, pi, pv, phi, hz, key) -> str:
    return f"T{int(n)} · I {_g(pi)}% · V {_g(pv)}% · φ {_g(phi)}° · {_g(hz)} Hz · {key}"


def parse_point(desc):
    m = _POINT.match(desc or "")
    if not m:
        return None
    n, pi, pv, phi, hz, key = m.groups()
    return dict(n=int(n), pi=float(pi), pv=float(pv), phi=float(phi), hz=float(hz), key=key)


def expected(s, pt):
    """Dict key → (expected, toleransi absolut). s = setup, pt = dict pi/pv/phi/hz."""
    ctr = s["ct_p"] / s["ct_s"]
    vtr = s["vt_p"] * 1000 / s["vt_s"]
    i_sec = s["ct_s"] * pt["pi"] / 100
    v_sec_ll = s["vt_s"] * pt["pv"] / 100
    i_pri = i_sec * ctr
    v_ll = v_sec_ll * vtr / 1000                    # kV
    smva = SQ3 * v_ll * i_pri / 1000
    phi = math.radians(pt["phi"])
    t = s["tol"] / 100
    out = {}
    for k in ("IA", "IB", "IC"):
        out[k] = (i_pri, abs(i_pri) * t)
    for k in ("VAB", "VBC", "VCA"):
        out[k] = (v_ll, abs(v_ll) * t)
    out["P"] = (smva * math.cos(phi), smva * t)
    out["Q"] = (smva * math.sin(phi), smva * t)
    out["PF"] = (math.cos(phi), s["tol_pf"])
    out["f"] = (pt["hz"], s["tol_f"])
    return out


def secondary(s, pt):
    """Besaran yang diinjeksikan test set (per fasa)."""
    i_sec = s["ct_s"] * pt["pi"] / 100
    v_ll = s["vt_s"] * pt["pv"] / 100
    return dict(i=i_sec, v_ln=v_ll / SQ3, v_ll=v_ll, phi=pt["phi"], hz=pt["hz"])


def fmt(x, d) -> str:
    return f"{x:.{d}f}"


def criteria_text(key, exp, tol) -> str:
    d = DEC[key]
    e = 0.0 if abs(exp) < 0.5 * 10 ** -d else exp    # hindari "-0.000"
    return f"{fmt(e, d)} ± {fmt(tol, d)}"


def to_num(text):
    """Angka dari isian lapangan: '1.001,5', '1001,5', '1001.5', '  200 A'."""
    t = str(text or "").strip()
    m = re.search(r"-?\d[\d.,]*", t)
    if not m:
        return None
    t = m.group(0)
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+", t):
        t = t.replace(".", "").replace(",", ".")
    elif "," in t and "." not in t:
        t = t.replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def judge(exp, tol, actual) -> str:
    """'OK' bila |actual − expected| ≤ toleransi, 'NG' bila di luar, '' bila actual kosong/bukan angka."""
    a = to_num(actual)
    if a is None:
        return ""
    return "OK" if abs(a - exp) <= tol + 1e-9 else "NG"


def error_text(key, exp, tol, actual, s=None) -> str:
    a = to_num(actual)
    if a is None:
        return ""
    if key == "PF":
        return _signed(a - exp, 3)
    if key == "f":
        return _signed(a - exp, 2) + " Hz"
    if key in ("P", "Q"):
        base = tol / (s["tol"] / 100) if s and s["tol"] else None     # S (MVA)
    else:
        base = abs(exp)
    if not base:
        return ""
    return _signed((a - exp) / base * 100, 2) + " %"


def _signed(x, d) -> str:
    """'+0.005', '-1.16', dan '+0.000' (bukan '-0.000') untuk selisih yang terbulatkan ke nol."""
    if abs(x) < 0.5 * 10 ** -d:
        x = 0.0
    return f"{x:+.{d}f}"


# ---------------------------------------------------------------- blok
def block_items(device, letter, setup, points):
    """Item checklist untuk satu blok baru: [(section, description, criteria, unit)].
    points: [(pi, pv, phi, hz)], dinomori T1..Tn."""
    sec = section_name(letter, device)
    out = [(sec, SETUP_DESC, setup_text(setup), SETUP_UNIT)]
    for n, (pi, pv, phi, hz) in enumerate(points, 1):
        out += point_items(sec, setup, n, pi, pv, phi, hz)
    return out


def point_items(sec, setup, n, pi, pv, phi, hz):
    pt = dict(pi=pi, pv=pv, phi=phi, hz=hz)
    ex = expected(setup, pt)
    return [(sec, point_desc(n, pi, pv, phi, hz, k), criteria_text(k, *ex[k]), UNIT[k]) for k in KEYS]


def next_letter(sections) -> str:
    """Huruf seksi berikutnya setelah huruf terbesar yang dipakai panel ini (A..Z, AA..)."""
    best = 0
    for s in sections:
        m = re.match(r"^([A-Z]{1,2})\. ", s or "")
        if m:
            t = m.group(1)
            v = (ord(t[0]) - 64) if len(t) == 1 else 26 * (ord(t[0]) - 64) + (ord(t[1]) - 64)
            best = max(best, v)
    v = best + 1
    return chr(64 + v) if v <= 26 else chr(64 + (v - 1) // 26) + chr(65 + (v - 1) % 26)


def group(rows, key=lambda r: r):
    """Kelompokkan baris satu blok: {'setup': row|None, 'points': [{'n','pi','pv','phi','hz','rows':{key: row}}]}"""
    setup_row, pts = None, {}
    for r in rows:
        d = key(r)
        if (d["unit"] or "") == SETUP_UNIT:
            setup_row = setup_row or r
            continue
        p = parse_point(d["description"])
        if not p:
            continue
        g = pts.setdefault(p["n"], dict(n=p["n"], pi=p["pi"], pv=p["pv"], phi=p["phi"], hz=p["hz"], rows={}))
        g["rows"].setdefault(p["key"], r)
    return dict(setup=setup_row, points=[pts[k] for k in sorted(pts)])


# ---------------------------------------------------------------- baca foto HMI (teks OCR → nilai)
_NUM = r"(-?\d{1,6}(?:[.,]\d{1,4})?)"
_UNITRE = r"(MVAR|Mvar|MVAr|kvar|kVAR|kA|kV|kW|MW|Hz|HZ|A|V)?(?![A-Za-z])"
OCR_LABELS = {
    "IA": [r"I\s*[-_.]?\s*(?:A|R|L1|1)(?![A-Z0-9])", r"Ia(?![a-z])"],
    "IB": [r"I\s*[-_.]?\s*(?:B|S|L2|2)(?![A-Z0-9])", r"Ib(?![a-z])"],
    "IC": [r"I\s*[-_.]?\s*(?:C|T|L3|3)(?![A-Z0-9])", r"Ic(?![a-z])"],
    "VAB": [r"[VU]\s*[-_.]?\s*(?:AB|RS|L1\s*-?\s*L2|12)(?![A-Z0-9])"],
    "VBC": [r"[VU]\s*[-_.]?\s*(?:BC|ST|L2\s*-?\s*L3|23)(?![A-Z0-9])"],
    "VCA": [r"[VU]\s*[-_.]?\s*(?:CA|TR|L3\s*-?\s*L1|31)(?![A-Z0-9])"],
    "P": [r"(?<![A-Z])P(?:\s*(?:tot|total|3ph))?(?![A-Z])", r"Active\s*Power", r"Daya\s*Aktif"],
    "Q": [r"(?<![A-Z])Q(?:\s*(?:tot|total|3ph))?(?![A-Z])", r"Reactive\s*Power", r"Daya\s*Reaktif"],
    "PF": [r"P\.?\s*F\.?(?![A-Z])", r"cos\s*(?:φ|phi|ϕ|0|o)?", r"Power\s*Factor"],
    "f": [r"(?<![A-Z])f(?![A-Z])", r"Freq(?:uency|uensi)?"],
}
OCR_UNITS = {
    "IA": {"A": 1, "kA": 1000}, "IB": {"A": 1, "kA": 1000}, "IC": {"A": 1, "kA": 1000},
    "VAB": {"kV": 1, "V": 0.001}, "VBC": {"kV": 1, "V": 0.001}, "VCA": {"kV": 1, "V": 0.001},
    "P": {"MW": 1, "kW": 0.001}, "Q": {"MVAR": 1, "kvar": 0.001}, "PF": {"": 1}, "f": {"Hz": 1},
}


def _norm_unit(u):
    if not u:
        return ""
    lu = u.lower()
    if lu == "mvar":
        return "MVAR"
    if lu == "kvar":
        return "kvar"
    if lu == "hz":
        return "Hz"
    if lu in ("ka", "kv", "kw"):
        return "k" + u[1].upper()
    if lu == "mw":
        return "MW"
    return u


def _ocr_num(s):
    s = s.strip()
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_hmi(text):
    """Teks hasil OCR layar HMI/BCU/meter → {key: {'value', 'seen', 'conf': high|medium|low}}.
    Hanya angka yang punya label (atau satuan khas MW/MVAR/Hz) yang diambil; satuan dikonversi ke satuan target."""
    lines = [re.sub(r"\s+", " ", ln.replace("|", " ")).strip() for ln in str(text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    found = {}
    for line in lines:
        for k in KEYS:
            if k in found and found[k]["conf"] == "high":
                continue
            for lab in OCR_LABELS[k]:
                hit = False
                for m in re.finditer(f"({lab})\\s*[:=]?\\s*{_NUM}\\s*{_UNITRE}", line, re.I):
                    unit = _norm_unit(m.group(3))
                    conv = OCR_UNITS[k]
                    if unit and unit not in conv:
                        continue
                    v = _ocr_num(m.group(2))
                    if v is None:
                        continue
                    v *= conv[unit] if unit else 1
                    if k == "PF" and abs(v) > 1:
                        continue
                    if k == "f" and not 40 <= v <= 70:
                        continue
                    conf = "high" if (unit or k == "PF") else "medium"
                    if k not in found or (conf == "high" and found[k]["conf"] != "high"):
                        seen = m.group(0).strip()
                        if unit and conv[unit] != 1:
                            seen += f" (→ {next(iter(conv))})"
                        found[k] = dict(value=v, seen=seen, conf=conf)
                    hit = True
                    break
                if hit:
                    break
    allt = " ".join(lines)
    loose = {"P": r"(-?\d+(?:[.,]\d+)?)\s*MW\b", "Q": r"(-?\d+(?:[.,]\d+)?)\s*M?var\b", "f": r"(\d{2}(?:[.,]\d+)?)\s*Hz\b"}
    for k, rx in loose.items():
        if k in found:
            continue
        m = re.search(rx, allt, re.I)
        if m:
            v = _ocr_num(m.group(1))
            if v is not None:
                found[k] = dict(value=v, seen=m.group(0), conf="low")
    return found
