// Uji injeksi CT/VT: kasus sama dengan paneltracker/tests/test_injection.py (laptop & HP harus identik).
import { describe, expect, it } from "vitest";
import * as I from "../src/injection";

const S = I.DEFAULT_SETUP;

describe("format setup & titik uji", () => {
  it("setup teks ↔ objek", () => {
    const t = I.setupText(S);
    expect(t).toBe("CT 2000/1 A · VT 150 kV/110 V · tol 1% · PF ±0.01 · f ±0.02 Hz");
    expect(I.parseSetup(t)).toEqual(S);
    expect(I.parseSetup("Sesuai drawing")).toBeNull();
    expect(I.parseSetup("CT 0/1 A · VT 150 kV/110 V · tol 1% · PF ±0.01 · f ±0.02 Hz")).toBeNull();
    const s5 = { ...S, ct_p: 800, ct_s: 5, vt_p: 20, vt_s: 100, tol: 0.5 };
    expect(I.parseSetup(I.setupText(s5))).toEqual(s5);
    expect(I.setupText({ ...S, vt_p: 150, vt_s: 110, ct_p: 2010.5 })).toContain("CT 2010.5/1 A");
  });
  it("deskripsi titik", () => {
    const d = I.pointDesc(1, 10, 100, 0, 50, "IA");
    expect(d).toBe("T1 · I 10% · V 100% · φ 0° · 50 Hz · IA");
    expect(I.parsePoint(d)).toEqual({ n: 1, pi: 10, pv: 100, phi: 0, hz: 50, key: "IA" });
    expect(I.parsePoint(I.pointDesc(12, 12.5, 90, -30, 49.5, "f"))!.phi).toBe(-30);
    expect(I.parsePoint("T1 · I 10% · V 100% · φ 0° · 50 Hz · XX")).toBeNull();
    expect(I.parsePoint("Kekencangan terminal")).toBeNull();
  });
});

describe("expected & penilaian", () => {
  it("expected sama dengan demo", () => {
    let ex = I.expected(S, { pi: 10, pv: 100, phi: 0, hz: 50 });
    expect(ex.IA[0]).toBeCloseTo(200, 9); expect(ex.IA[1]).toBeCloseTo(2, 9);
    expect(ex.VAB[0]).toBeCloseTo(150, 9); expect(ex.VAB[1]).toBeCloseTo(1.5, 9);
    expect(ex.P[0]).toBeCloseTo(51.9615, 3); expect(Math.abs(ex.Q[0])).toBeLessThan(1e-9);
    expect(ex.P[1]).toBeCloseTo(0.519615, 5);
    expect(ex.PF).toEqual([1, 0.01]); expect(ex.f).toEqual([50, 0.02]);
    ex = I.expected(S, { pi: 50, pv: 100, phi: 30, hz: 50 });
    expect(ex.P[0]).toBeCloseTo(225, 6); expect(ex.Q[0]).toBeCloseTo(129.9038, 3); expect(ex.PF[0]).toBeCloseTo(0.866, 4);
    const sec = I.secondary(S, { pi: 10, pv: 100, phi: 30, hz: 50 });
    expect(sec.i).toBeCloseTo(0.1, 12); expect(sec.v_ln).toBeCloseTo(63.5085, 3);
  });
  it("kriteria & OK/NG", () => {
    expect(I.criteriaText("IA", 200, 2)).toBe("200.0 ± 2.0");
    expect(I.criteriaText("Q", -1e-12, 0.5196)).toBe("0.000 ± 0.520");
    expect(I.criteriaText("PF", 0.866025, 0.01)).toBe("0.866 ± 0.010");
    expect(I.judge(200, 2, "201.9")).toBe("OK"); expect(I.judge(200, 2, "202.1")).toBe("NG");
    expect(I.judge(200, 2, "")).toBe(""); expect(I.judge(200, 2, "abc")).toBe("");
    expect(I.judge(129.9038, 2.598, "126.9")).toBe("NG");
    expect(I.judge(0.866, 0.01, "0,871")).toBe("OK");
    expect(I.toNum("1.001,5")).toBe(1001.5); expect(I.toNum("1001,5")).toBe(1001.5); expect(I.toNum("1,001.5")).toBe(1001.5);
    expect(I.toNum(" 200 A")).toBe(200);
    const ex = I.expected(S, { pi: 50, pv: 100, phi: 30, hz: 50 });
    expect(I.errorText("Q", ex.Q[0], ex.Q[1], "126.9", S)).toBe("-1.16 %");
    expect(I.errorText("IA", ex.IA[0], ex.IA[1], "1001", S)).toBe("+0.10 %");
    expect(I.errorText("PF", ex.PF[0], ex.PF[1], "0.871", S)).toBe("+0.005");
    expect(I.errorText("f", ex.f[0], ex.f[1], "50.01", S)).toBe("+0.01 Hz");
    expect(I.errorText("PF", 0.8660254, 0.01, "0.866", S)).toBe("+0.000");
  });
});

describe("blok item", () => {
  it("item blok & pengelompokan", () => {
    const items = I.blockItems("-A30 MiCOM C264 (BCU)", "Q", S, [[10, 100, 0, 50], [50, 100, 30, 50]]);
    expect(items.length).toBe(21);
    expect(items[0]).toEqual(["Q. SAS · Injeksi CT/VT -A30 MiCOM C264 (BCU)", "Setup injeksi", I.setupText(S), "setup"]);
    expect(items[1]).toEqual(["Q. SAS · Injeksi CT/VT -A30 MiCOM C264 (BCU)", "T1 · I 10% · V 100% · φ 0° · 50 Hz · IA", "200.0 ± 2.0", "A"]);
    expect(items[10][1].endsWith("· f")).toBe(true); expect(items[10][3]).toBe("Hz"); expect(items[10][2]).toBe("50.00 ± 0.02");
    expect(I.isInjectionSection(items[0][0])).toBe(true);
    expect(I.deviceOf(items[0][0])).toBe("-A30 MiCOM C264 (BCU)");
    expect(I.isInjectionSection("Q. SAS · DI/DO -A30")).toBe(false);
    const rows = items.map(([section, description, criteria, unit]) => ({ section, description, criteria, unit }));
    const g = I.group(rows);
    expect(g.setup!.unit).toBe("setup");
    expect(g.points.map((p) => p.n)).toEqual([1, 2]);
    expect(Object.keys(g.points[1].rows)).toEqual([...I.KEYS]);
    expect(g.points[1].phi).toBe(30);
  });
  it("huruf seksi berikutnya", () => {
    expect(I.nextLetter(["A. Umum", "P. SAS · Rasio CT/VT", "C. X"])).toBe("Q");
    expect(I.nextLetter(["Z. SAS · DI/DO"])).toBe("AA");
    expect(I.nextLetter(["AA. x"])).toBe("AB");
    expect(I.nextLetter([])).toBe("A");
  });
  it("prefill rasio dari item Rasio CT/VT", () => {
    const D = "-A30 MiCOM C264 (BCU)";
    const rows = [
      { section: "J. SAS · Rasio CT/VT", description: `${D} · CT ratio`, value: "1600/1 A" },
      { section: "J. SAS · Rasio CT/VT", description: `${D} · VT ratio`, value: "150/0.11 kV" },
    ];
    const s = I.prefillFromRatio(rows, D);
    expect([s.ct_p, s.ct_s, s.vt_p, s.vt_s]).toEqual([1600, 1, 150, 110]);
    rows[1].value = "150000/110 V";
    expect(I.prefillFromRatio(rows, D).vt_p).toBe(150);
    expect(I.ratioDevices(rows)).toEqual([D]);
  });
  it("teks nilai dari foto", () => {
    expect(I.valueText("IA", 1005.1)).toBe("1005.1");
    expect(I.valueText("VAB", 150.02)).toBe("150.02");
    expect(I.valueText("f", 50)).toBe("50");
    expect(I.valueText("PF", 0.866)).toBe("0.866");
  });
});

describe("parser teks OCR layar HMI", () => {
  const vals = (t: string) => Object.fromEntries(Object.entries(I.parseHmi(t)).map(([k, v]) => [k, Math.round(v!.value * 1e4) / 1e4]));
  const confs = (t: string) => Object.fromEntries(Object.entries(I.parseHmi(t)).map(([k, v]) => [k, v!.conf]));
  it("format BCU", () => {
    expect(vals("BCU =E01 MEASUREMENT\nP 225.1 MW\nQ 126.9 MVAR\nPF 0.871\nf 50.00 Hz")).toEqual({ P: 225.1, Q: 126.9, PF: 0.871, f: 50 });
    expect(vals("IA 200.4 A VAB 150.10 kV\nP 51.98 MW\nQ 0.05 MVAR\nPF 1.000")).toEqual({ IA: 200.4, VAB: 150.1, P: 51.98, Q: 0.05, PF: 1 });
  });
  it("label R/S/T dan satuan dikonversi", () => {
    expect(vals("I R = 1.001 kA  I S = 998,6 A  I T = 1000.2 A\nV RS 150.0 kV  V ST 150100 V  V TR 149.9 kV\nCOS φ 0.87\nFreq 49.98 Hz"))
      .toEqual({ IA: 1001, IB: 998.6, IC: 1000.2, VAB: 150, VBC: 150.1, VCA: 149.9, PF: 0.87, f: 49.98 });
  });
  it("label IEC L1/L2/L3 + kW/kvar", () => {
    expect(vals("IL1 1001 A\nIL2 998.6 A\nIL3 1000.2 A\nU12 150.0 kV\nU23 150.1 kV\nU31 149.9 kV\nP: 225100 kW\nQ: 126900 kvar\nPF: 0.871\n50.01 Hz"))
      .toEqual({ IA: 1001, IB: 998.6, IC: 1000.2, VAB: 150, VBC: 150.1, VCA: 149.9, P: 225.1, Q: 126.9, PF: 0.871, f: 50.01 });
  });
  it("tanpa label → keyakinan rendah", () => {
    expect(confs("225.1 MW | 126.9 Mvar\n50.00 Hz")).toEqual({ P: "low", Q: "low", f: "low" });
  });
  it("output Tesseract asli", () => {
    expect(vals("BCU =E@1 MEASUREMENT\nP 225.1 MW\n\nQ 126.9 MVAR\nPF 0.871\n\nf 50.00 Hz")).toEqual({ P: 225.1, Q: 126.9, PF: 0.871, f: 50 });
    expect(vals("Tidak ada angka di sini")).toEqual({});
  });
});

describe("update otomatis APK", () => {
  it("bandingkan versi", async () => {
    const { cmpVer } = await import("../src/updater");
    expect(cmpVer("1.3.1", "1.3.0")).toBe(1);
    expect(cmpVer("1.3.0", "1.3.0")).toBe(0);
    expect(cmpVer("1.2.10", "1.3")).toBe(-1);
    expect(cmpVer("2.0", "1.99.99")).toBe(1);
  });
});
