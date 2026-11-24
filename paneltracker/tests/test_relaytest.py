"""Uji proteksi relay: katalog/preset, rumus kurva IDMT & slope differential, format item (kembar dengan
paneltracker-mobile/tests/relaytest.test.ts)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from app import relaytest as R

T = R.DEFAULT_TOL

# ---- preset per model relay
assert R.preset_for("-F87T MiCOM P643")[:3] == ["87T", "87H2", "87H5"]
assert R.preset_for("-F87L NR PCS-931")[0] == "87L"
assert R.preset_for("-N90 RTF")[0] == "90"
assert R.preset_for("-P501 Easergy P5F30") == ["50", "51", "50N", "51N", "51NS", "TRIP", "74", "EVT"]
assert R.preset_for("Relay X") == R.DEFAULT_PRESET
assert all(c in R.FUNCS for _, cs in R.PRESETS for c in cs)

# ---- kurva IDMT (IEC 60255-151): SI TMS 1 di 10× = 2.971 s, VI = 1.5 s, EI = 0.808 s, LTI = 13.33 s
assert abs(R.idmt_time("IEC SI", 1, 10) - 2.9706) < 1e-3
assert abs(R.idmt_time("IEC VI", 1, 10) - 1.5) < 1e-9
assert abs(R.idmt_time("IEC EI", 1, 10) - 0.80808) < 1e-4
assert abs(R.idmt_time("IEC LTI", 1, 10) - 13.333) < 1e-3
assert abs(R.idmt_time("IEEE MI", 1, 5) - (0.0515 / (5 ** 0.02 - 1) + 0.114)) < 1e-9
assert R.idmt_time("DT", 0.3, 5) == 0.3
assert R.idmt_time("IEC SI", 1, 1) is None

# ---- setting & kelengkapan
p = {"kurva": "IEC SI", "Is": "1", "TMS": "0.1"}
assert R.parse_params(R.params_text(p)) == p and R.params_text({"Is": "", "TMS": "0.1"}) == "TMS=0.1"
assert R.complete("51", p) and not R.complete("51", {"kurva": "IEC SI", "Is": "1"}) and not R.complete("51", {})
assert not R.complete("51", {"kurva": "XYZ", "Is": "1", "TMS": "0.1"})
assert R.complete("50", {"P": "8"}) and not R.complete("50", {"t": "0.1"})
assert R.complete("87T", {"Is1": "0.2", "K1": "30", "Is2": "1", "K2": "80"})

# ---- expected + toleransi (waktu: maks(5 %, 40 ms); pickup 5 %)
ex = R.expected("51", p, T)
assert [x[0] for x in ex] == ["pickup", "2×Is", "5×Is", "10×Is"]
assert ex[0][2] == 1 and abs(ex[0][3] - 0.05) < 1e-12
assert abs(ex[1][2] - 1.0029) < 1e-3 and abs(ex[1][3] - 0.0501) < 1e-3                 # 0.1·0.14/(2^0.02−1)
assert abs(ex[3][2] - 0.29706) < 1e-4 and abs(ex[3][3] - 0.04) < 1e-12                  # 5 % = 14.9 ms < 40 ms
assert R.expected("51", {}, T) == []
dt = R.expected("50", {"P": "8"}, T)
assert dt[0][2] == 8 and dt[1][2] is None                                                 # tanpa waktu → titik dilewati
d = {"Is1": "0.2", "K1": "30", "Is2": "1", "K2": "80"}
assert abs(R.diff_threshold(d, 0) - 0.2) < 1e-12 and abs(R.diff_threshold(d, 1) - 0.5) < 1e-12
assert abs(R.diff_threshold(d, 4) - (0.2 + 0.3 + 0.8 * 3)) < 1e-12
ed = R.expected("87T", d, T)
assert [round(x[2], 3) for x in ed] == [0.2, 0.5, 1.3, 2.9]
avr = R.expected("90", {"V": "110", "BW": "1", "T1": "30"}, T)
assert [x[2] for x in avr] == [30, 30] and abs(avr[0][3] - 1.5) < 1e-12
assert R.expected("50BF", {"I": "0.1", "t1": "0.05", "t2": "0.15"}, T)[2][2] == 0.15
assert R.judge(1.0029, 0.0501, "1.04") == "OK" and R.judge(1.0029, 0.0501, "1.06") == "NG" and R.judge(1, 0.1, "") == ""
assert R.judge(None, None, "1") == ""
assert R.criteria_text("s", 1.00287, 0.05014) == "1.003 ± 0.050" and R.criteria_text("s", None, None) == ""
assert R.inject_hint("51", p, "5×Is") == "injeksi 5.000 A"
assert R.inject_hint("90", {"V": "110", "BW": "1", "T1": "30"}, "V di atas band → Lower") == "injeksi 111.65 V (band 108.90–111.10 V)"
assert R.inject_hint("51", {}, "5×Is") == ""

# ---- toleransi blok
assert R.tol_text(T) == "waktu 5% / 40 ms · pickup 5%" and R.parse_tol(R.tol_text(T)) == T
assert R.parse_tol("rusak") == T

# ---- item blok & pengelompokan
items = R.block_items("-F87T MiCOM P643", "S", ["51", "87T", "TRIP", "90"])
sec = "S. SAS · Uji Proteksi -F87T MiCOM P643"
assert items[0] == (sec, "Toleransi uji", R.tol_text(T), "psetup")
assert items[1] == (sec, "F1 · 51 · OCR fasa (IDMT)", "", "fset")
assert items[2] == (sec, "F1 · 51 · pickup", "", "A") and items[5] == (sec, "F1 · 51 · 10×Is", "", "s")
assert (sec, "F3 · TRIP · Matriks trip ke CB (coil 1 & 2)", "", "") in items
assert items[-1] == (sec, "F4 · 90 · V di dalam band → tidak ada perintah", "Tidak ada Raise/Lower", "")
assert R.is_protection_section(sec) and R.device_of(sec) == "-F87T MiCOM P643" and not R.is_protection_section("S. SAS · DI/DO x")
filled = R.function_items(sec, 1, "51", p, T)
assert filled[0][2] == "kurva=IEC SI; Is=1; TMS=0.1" and filled[1][2] == "1.000 ± 0.050" and filled[4][2] == "0.297 ± 0.040"
rows = [dict(section=a, description=b, criteria=c, unit=u) for a, b, c, u in items]
g = R.group(rows)
assert g["tol"] == T and [f["code"] for f in g["funcs"]] == ["51", "87T", "TRIP", "90"]
assert g["funcs"][0]["fset"]["unit"] == "fset" and [l for l, _ in g["funcs"][0]["points"]] == ["pickup", "2×Is", "5×Is", "10×Is"]
assert g["funcs"][2]["fset"] is None and len(g["funcs"][2]["points"]) == 1 and g["funcs"][2]["kind"] == "check"
assert len(g["funcs"][3]["points"]) == 3
print("ALL OK")
