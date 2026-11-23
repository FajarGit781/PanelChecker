"""Uji injeksi CT/VT: logika expected/toleransi/format item + parser teks OCR (sama dengan aplikasi HP)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from app import injection as INJ

S = INJ.DEFAULT_SETUP

# ---- setup: teks ↔ dict
t = INJ.setup_text(S)
assert t == "CT 2000/1 A · VT 150 kV/110 V · tol 1% · PF ±0.01 · f ±0.02 Hz", t
assert INJ.parse_setup(t) == S
assert INJ.parse_setup("Sesuai drawing") is None
assert INJ.parse_setup("CT 0/1 A · VT 150 kV/110 V · tol 1% · PF ±0.01 · f ±0.02 Hz") is None
s5 = dict(S, ct_p=800, ct_s=5, vt_p=20, vt_s=100, tol=0.5)
assert INJ.parse_setup(INJ.setup_text(s5)) == s5

# ---- deskripsi titik uji
d = INJ.point_desc(1, 10, 100, 0, 50, "IA")
assert d == "T1 · I 10% · V 100% · φ 0° · 50 Hz · IA", d
assert INJ.parse_point(d) == dict(n=1, pi=10, pv=100, phi=0, hz=50, key="IA")
assert INJ.parse_point(INJ.point_desc(12, 12.5, 90, -30, 49.5, "f"))["phi"] == -30
assert INJ.parse_point("T1 · I 10% · V 100% · φ 0° · 50 Hz · XX") is None
assert INJ.parse_point("Kekencangan terminal") is None

# ---- expected (CT 2000/1, VT 150 kV/110 V) — sama dengan demo
ex = INJ.expected(S, dict(pi=10, pv=100, phi=0, hz=50))
assert abs(ex["IA"][0] - 200) < 1e-9 and abs(ex["IA"][1] - 2) < 1e-9
assert abs(ex["VAB"][0] - 150) < 1e-9 and abs(ex["VAB"][1] - 1.5) < 1e-9
assert abs(ex["P"][0] - 51.9615) < 1e-3 and abs(ex["Q"][0]) < 1e-9
assert abs(ex["P"][1] - 0.519615) < 1e-5           # P/Q: tol% dari S
assert ex["PF"] == (1.0, 0.01) and ex["f"] == (50, 0.02)
ex = INJ.expected(S, dict(pi=50, pv=100, phi=30, hz=50))
assert abs(ex["P"][0] - 225.0) < 1e-6 and abs(ex["Q"][0] - 129.9038) < 1e-3
assert abs(ex["PF"][0] - 0.8660) < 1e-4
sec = INJ.secondary(S, dict(pi=10, pv=100, phi=30, hz=50))
assert abs(sec["i"] - 0.1) < 1e-12 and abs(sec["v_ln"] - 63.5085) < 1e-3

# ---- kriteria teks & penilaian
assert INJ.criteria_text("IA", 200, 2) == "200.0 ± 2.0"
assert INJ.criteria_text("Q", -1e-12, 0.5196) == "0.000 ± 0.520"          # bukan "-0.000"
assert INJ.criteria_text("PF", 0.866025, 0.01) == "0.866 ± 0.010"
assert INJ.judge(200, 2, "201.9") == "OK" and INJ.judge(200, 2, "202.1") == "NG"
assert INJ.judge(200, 2, "") == "" and INJ.judge(200, 2, "abc") == ""
assert INJ.judge(129.9038, 2.598, "126.9") == "NG"                        # contoh demo: Q −1,16 % dari S
assert INJ.judge(0.866, 0.01, "0,871") == "OK"
assert INJ.to_num("1.001,5") == 1001.5 and INJ.to_num("1001,5") == 1001.5 and INJ.to_num("1,001.5") == 1001.5
assert INJ.to_num(" 200 A") == 200
ex = INJ.expected(S, dict(pi=50, pv=100, phi=30, hz=50))
assert INJ.error_text("Q", *ex["Q"], "126.9", S) == "-1.16 %", INJ.error_text("Q", *ex["Q"], "126.9", S)
assert INJ.error_text("IA", *ex["IA"], "1001", S) == "+0.10 %"
assert INJ.error_text("PF", *ex["PF"], "0.871", S) == "+0.005"
assert INJ.error_text("f", *ex["f"], "50.01", S) == "+0.01 Hz"
assert INJ.error_text("PF", 0.8660254, 0.01, "0.866", S) == "+0.000"          # bukan "-0.000"

# ---- blok item
items = INJ.block_items("-A30 MiCOM C264 (BCU)", "Q", S, [(10, 100, 0, 50), (50, 100, 30, 50)])
assert len(items) == 1 + 2 * 10
assert items[0] == ("Q. SAS · Injeksi CT/VT -A30 MiCOM C264 (BCU)", "Setup injeksi", INJ.setup_text(S), "setup")
assert items[1] == ("Q. SAS · Injeksi CT/VT -A30 MiCOM C264 (BCU)", "T1 · I 10% · V 100% · φ 0° · 50 Hz · IA", "200.0 ± 2.0", "A")
assert items[10][1].endswith("· f") and items[10][3] == "Hz" and items[10][2] == "50.00 ± 0.02"
assert INJ.is_injection_section(items[0][0]) and INJ.device_of(items[0][0]) == "-A30 MiCOM C264 (BCU)"
assert not INJ.is_injection_section("Q. SAS · DI/DO -A30")
rows = [dict(section=a, description=b, criteria=c, unit=u) for a, b, c, u in items]
g = INJ.group(rows)
assert g["setup"]["unit"] == "setup" and [p["n"] for p in g["points"]] == [1, 2]
assert list(g["points"][1]["rows"]) == list(INJ.KEYS) and g["points"][1]["phi"] == 30

# ---- huruf seksi berikutnya
assert INJ.next_letter(["A. Umum", "P. SAS · Rasio CT/VT", "C. X"]) == "Q"
assert INJ.next_letter(["Z. SAS · DI/DO"]) == "AA" and INJ.next_letter(["AA. x"]) == "AB" and INJ.next_letter([]) == "A"

# ---- parser teks OCR (kasus sama dengan paneltracker-mobile/tests/injection.test.ts)
def vals(t):
    return {k: round(v["value"], 4) for k, v in INJ.parse_hmi(t).items()}
def confs(t):
    return {k: v["conf"] for k, v in INJ.parse_hmi(t).items()}
assert vals("BCU =E01 MEASUREMENT\nP 225.1 MW\nQ 126.9 MVAR\nPF 0.871\nf 50.00 Hz") == dict(P=225.1, Q=126.9, PF=0.871, f=50.0)
assert vals("IA 200.4 A VAB 150.10 kV\nP 51.98 MW\nQ 0.05 MVAR\nPF 1.000") == dict(IA=200.4, VAB=150.1, P=51.98, Q=0.05, PF=1.0)
assert vals("I R = 1.001 kA  I S = 998,6 A  I T = 1000.2 A\nV RS 150.0 kV  V ST 150100 V  V TR 149.9 kV\nCOS φ 0.87\nFreq 49.98 Hz") == \
    dict(IA=1001.0, IB=998.6, IC=1000.2, VAB=150.0, VBC=150.1, VCA=149.9, PF=0.87, f=49.98)
r = vals("IL1 1001 A\nIL2 998.6 A\nIL3 1000.2 A\nU12 150.0 kV\nU23 150.1 kV\nU31 149.9 kV\nP: 225100 kW\nQ: 126900 kvar\nPF: 0.871\n50.01 Hz")
assert r == dict(IA=1001.0, IB=998.6, IC=1000.2, VAB=150.0, VBC=150.1, VCA=149.9, P=225.1, Q=126.9, PF=0.871, f=50.01), r
assert confs("225.1 MW | 126.9 Mvar\n50.00 Hz") == dict(P="low", Q="low", f="low")
assert vals("BCU =E@1 MEASUREMENT\nP 225.1 MW\n\nQ 126.9 MVAR\nPF 0.871\n\nf 50.00 Hz") == dict(P=225.1, Q=126.9, PF=0.871, f=50.0)  # output Tesseract asli
assert vals("Tidak ada angka di sini") == {}
print("ALL OK")
