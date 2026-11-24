// Uji proteksi relay: kasus sama dengan paneltracker/tests/test_relaytest.py (laptop & HP harus identik).
import { describe, expect, it } from "vitest";
import * as R from "../src/relaytest";

const T = R.DEFAULT_TOL;

describe("katalog & kurva", () => {
  it("preset per model relay", () => {
    expect(R.presetFor("-F87T MiCOM P643").slice(0, 3)).toEqual(["87T", "87H2", "87H5"]);
    expect(R.presetFor("-F87L NR PCS-931")[0]).toBe("87L");
    expect(R.presetFor("-N90 RTF")[0]).toBe("90");
    expect(R.presetFor("-P501 Easergy P5F30")).toEqual(["50", "51", "50N", "51N", "51NS", "TRIP", "74", "EVT"]);
    expect(R.presetFor("Relay X")).toEqual(R.DEFAULT_PRESET);
    for (const [, cs] of R.PRESETS) for (const c of cs) expect(R.FUNCS[c]).toBeTruthy();
  });
  it("kurva IDMT IEC/IEEE", () => {
    expect(R.idmtTime("IEC SI", 1, 10)).toBeCloseTo(2.9706, 3);
    expect(R.idmtTime("IEC VI", 1, 10)).toBeCloseTo(1.5, 9);
    expect(R.idmtTime("IEC EI", 1, 10)).toBeCloseTo(0.80808, 4);
    expect(R.idmtTime("IEC LTI", 1, 10)).toBeCloseTo(13.333, 3);
    expect(R.idmtTime("IEEE MI", 1, 5)).toBeCloseTo(0.0515 / (5 ** 0.02 - 1) + 0.114, 9);
    expect(R.idmtTime("DT", 0.3, 5)).toBe(0.3);
    expect(R.idmtTime("IEC SI", 1, 1)).toBeNull();
  });
});

describe("setting, expected, penilaian", () => {
  const p = { kurva: "IEC SI", Is: "1", TMS: "0.1" };
  it("setting & kelengkapan", () => {
    expect(R.parseParams(R.paramsText(p))).toEqual(p);
    expect(R.paramsText({ Is: "", TMS: "0.1" })).toBe("TMS=0.1");
    expect(R.complete("51", p)).toBe(true);
    expect(R.complete("51", { kurva: "IEC SI", Is: "1" })).toBe(false);
    expect(R.complete("51", {})).toBe(false);
    expect(R.complete("51", { kurva: "XYZ", Is: "1", TMS: "0.1" })).toBe(false);
    expect(R.complete("50", { P: "8" })).toBe(true);
    expect(R.complete("50", { t: "0.1" })).toBe(false);
    expect(R.complete("87T", { Is1: "0.2", K1: "30", Is2: "1", K2: "80" })).toBe(true);
  });
  it("expected + toleransi", () => {
    const ex = R.expected("51", p, T);
    expect(ex.map((x) => x[0])).toEqual(["pickup", "2×Is", "5×Is", "10×Is"]);
    expect(ex[0][2]).toBe(1); expect(ex[0][3]).toBeCloseTo(0.05, 12);
    expect(ex[1][2]).toBeCloseTo(1.0029, 3); expect(ex[1][3]).toBeCloseTo(0.0501, 3);
    expect(ex[3][2]).toBeCloseTo(0.29706, 4); expect(ex[3][3]).toBeCloseTo(0.04, 12);
    expect(R.expected("51", {}, T)).toEqual([]);
    const dt = R.expected("50", { P: "8" }, T);
    expect(dt[0][2]).toBe(8); expect(dt[1][2]).toBeNull();
    const d = { Is1: "0.2", K1: "30", Is2: "1", K2: "80" };
    expect(R.diffThreshold(d, 0)).toBeCloseTo(0.2, 12); expect(R.diffThreshold(d, 1)).toBeCloseTo(0.5, 12);
    expect(R.diffThreshold(d, 4)).toBeCloseTo(0.2 + 0.3 + 0.8 * 3, 12);
    expect(R.expected("87T", d, T).map((x) => Math.round(x[2]! * 1000) / 1000)).toEqual([0.2, 0.5, 1.3, 2.9]);
    const avr = R.expected("90", { V: "110", BW: "1", T1: "30" }, T);
    expect(avr.map((x) => x[2])).toEqual([30, 30]); expect(avr[0][3]).toBeCloseTo(1.5, 12);
    expect(R.expected("50BF", { I: "0.1", t1: "0.05", t2: "0.15" }, T)[2][2]).toBe(0.15);
    expect(R.judge(1.0029, 0.0501, "1.04")).toBe("OK"); expect(R.judge(1.0029, 0.0501, "1.06")).toBe("NG");
    expect(R.judge(1, 0.1, "")).toBe(""); expect(R.judge(null, null, "1")).toBe("");
    expect(R.criteriaText("s", 1.00287, 0.05014)).toBe("1.003 ± 0.050"); expect(R.criteriaText("s", null, null)).toBe("");
    expect(R.injectHint("51", p, "5×Is")).toBe("injeksi 5.000 A");
    expect(R.injectHint("90", { V: "110", BW: "1", T1: "30" }, "V di atas band → Lower")).toBe("injeksi 111.65 V (band 108.90–111.10 V)");
    expect(R.injectHint("51", {}, "5×Is")).toBe("");
  });
  it("toleransi blok", () => {
    expect(R.tolText(T)).toBe("waktu 5% / 40 ms · pickup 5%");
    expect(R.parseTol(R.tolText(T))).toEqual(T);
    expect(R.parseTol("rusak")).toEqual(T);
  });
});

describe("item blok", () => {
  it("item & pengelompokan", () => {
    const items = R.blockItems("-F87T MiCOM P643", "S", ["51", "87T", "TRIP", "90"]);
    const sec = "S. SAS · Uji Proteksi -F87T MiCOM P643";
    expect(items[0]).toEqual([sec, "Toleransi uji", R.tolText(T), "psetup"]);
    expect(items[1]).toEqual([sec, "F1 · 51 · OCR fasa (IDMT)", "", "fset"]);
    expect(items[2]).toEqual([sec, "F1 · 51 · pickup", "", "A"]); expect(items[5]).toEqual([sec, "F1 · 51 · 10×Is", "", "s"]);
    expect(items).toContainEqual([sec, "F3 · TRIP · Matriks trip ke CB (coil 1 & 2)", "", ""]);
    expect(items[items.length - 1]).toEqual([sec, "F4 · 90 · V di dalam band → tidak ada perintah", "Tidak ada Raise/Lower", ""]);
    expect(R.isProtectionSection(sec)).toBe(true); expect(R.deviceOf(sec)).toBe("-F87T MiCOM P643");
    expect(R.isProtectionSection("S. SAS · DI/DO x")).toBe(false);
    const filled = R.functionItems(sec, 1, "51", { kurva: "IEC SI", Is: "1", TMS: "0.1" }, T);
    expect(filled[0][2]).toBe("kurva=IEC SI; Is=1; TMS=0.1"); expect(filled[1][2]).toBe("1.000 ± 0.050"); expect(filled[4][2]).toBe("0.297 ± 0.040");
    const g = R.group(items.map(([section, description, criteria, unit]) => ({ section, description, criteria, unit })));
    expect(g.tol).toEqual(T);
    expect(g.funcs.map((f) => f.code)).toEqual(["51", "87T", "TRIP", "90"]);
    expect(g.funcs[0].fset!.unit).toBe("fset");
    expect(g.funcs[0].points.map(([l]) => l)).toEqual(["pickup", "2×Is", "5×Is", "10×Is"]);
    expect(g.funcs[2].fset).toBeNull(); expect(g.funcs[2].points.length).toBe(1); expect(g.funcs[2].kind).toBe("check");
    expect(g.funcs[3].points.length).toBe(3);
  });
});
