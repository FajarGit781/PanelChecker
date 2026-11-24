// Uji proteksi relay — sama persis dengan aplikasi laptop (paneltracker/app/relaytest.py).
// Item checklist biasa: seksi "<huruf>. SAS · Uji Proteksi <device>", item "psetup" (toleransi), per fungsi item "fset"
// (setting "k=v; k=v") + titik uji "F1 · 51 · 2×Is" (kriteria = expected ± toleransi, nilai = actual, OK/NG otomatis),
// fungsi jenis "check" = satu item OK/NG manual.
import type { Row } from "./logic";
import { nextLetter as nl } from "./injection";

type Kind = "idmt" | "dt" | "diff" | "pct" | "bf" | "ar" | "sync" | "avr" | "check";
export const FUNCS: Record<string, [string, Kind, string?]> = {
  "50": ["OCR instant fasa", "dt", "A"], "51": ["OCR fasa (IDMT)", "idmt"], "50N": ["GFR instant", "dt", "A"],
  "51N": ["GFR (IDMT)", "idmt"], "51NS": ["SBEF standby earth fault", "idmt"], "67N": ["DEF directional earth fault", "dt", "A"],
  "87L": ["Differential line", "diff"], "87T": ["Differential trafo", "diff"], "87B": ["Differential busbar", "diff"],
  "87H2": ["Blocking harmonik ke-2 (inrush)", "pct"], "87H5": ["Blocking harmonik ke-5 (overflux)", "pct"],
  "64REF": ["Restricted earth fault", "dt", "A"], "21Z1": ["Distance zona 1", "dt", "Ω"], "21Z2": ["Distance zona 2", "dt", "Ω"],
  "21Z3": ["Distance zona 3", "dt", "Ω"], "49": ["Thermal overload", "dt", "A"], "24": ["Overfluxing V/Hz", "dt", "%"],
  "50BF": ["CB failure", "bf"], "79": ["Auto-reclose", "ar"], "25": ["Check synchronizing", "sync"], "90": ["AVR (tap changer)", "avr"],
  STAB: ["Stabilitas gangguan eksternal (through fault)", "check"], CTS: ["CT supervision", "check"],
  COMM: ["Kanal komunikasi differential (end-to-end)", "check"], CZ: ["Check zone busbar", "check"],
  DZ: ["Dead zone / end fault", "check"], ISO: ["Replika isolator (topologi zona)", "check"], "85": ["Intertrip / DTT", "check"],
  TRIP: ["Matriks trip ke CB (coil 1 & 2)", "check"], "74": ["Trip circuit supervision", "check"], "86": ["Lockout & reset", "check"],
  EVT: ["Event & disturbance record ke SCADA/HMI", "check"], BUCH: ["Buchholz alarm & trip", "check"],
  SPR: ["Sudden pressure trip", "check"], OLTCP: ["OLTC protective relay trip", "check"],
  OTI: ["Oil temperature alarm & trip", "check"], WTI: ["Winding temperature alarm & trip", "check"], OLI: ["Oil level alarm", "check"],
  TAP: ["Indikasi posisi tap (AVR, BCU, HMI)", "check"], RL: ["Perintah Raise/Lower dari HMI/SCADA", "check"],
  AM: ["Mode Auto/Manual & Local/Remote", "check"], AVRB: ["Blocking AVR (UV, OV/fast lower, OC, batas tap)", "check"],
  LDC: ["Line drop compensation (LDC)", "check"],
};
export const PRESETS: [RegExp, string[]][] = [
  [/P643/i, ["87T", "87H2", "87H5", "64REF", "51", "51N", "49", "24", "STAB", "CTS", "BUCH", "SPR", "OLTCP", "OTI", "WTI", "OLI", "TRIP", "86", "74", "EVT"]],
  [/PCS-?931/i, ["87L", "COMM", "21Z1", "21Z2", "21Z3", "67N", "51", "51N", "85", "STAB", "CTS", "TRIP", "74", "EVT"]],
  [/P746/i, ["87B", "CZ", "STAB", "DZ", "ISO", "CTS", "TRIP", "EVT"]],
  [/P841/i, ["50BF", "79", "25", "TRIP", "EVT"]],
  [/P5F30/i, ["50", "51", "50N", "51N", "51NS", "TRIP", "74", "EVT"]],
  [/P143/i, ["50", "51", "50N", "51N", "TRIP", "74", "EVT"]],
  [/RTF|AVR/i, ["90", "TAP", "RL", "AM", "AVRB", "LDC"]],
];
export const DEFAULT_PRESET = ["51", "51N", "TRIP", "74", "EVT"];
export const CURVES: Record<string, [number, number, number] | null> = {
  "IEC SI": [0.14, 0.02, 0], "IEC VI": [13.5, 1, 0], "IEC EI": [80, 2, 0], "IEC LTI": [120, 1, 0],
  "IEEE MI": [0.0515, 0.02, 0.114], "IEEE VI": [19.61, 2, 0.491], "IEEE EI": [28.2, 2, 0.1217], DT: null,
};
export const PARAMS: Record<Kind, [string, string, string][]> = {
  idmt: [["kurva", "Kurva", ""], ["Is", "Is (sekunder)", "A"], ["TMS", "TMS / waktu DT", ""]],
  dt: [["P", "Pickup", "@"], ["t", "Waktu trip", "s"]],
  diff: [["Is1", "Is1", "In"], ["K1", "Slope K1", "%"], ["Is2", "Is2 (tekuk)", "In"], ["K2", "Slope K2", "%"]],
  pct: [["P", "Setting", "%"]],
  bf: [["I", "I> CB fail", "A"], ["t1", "t1 retrip", "s"], ["t2", "t2 backtrip", "s"]],
  ar: [["td", "Dead time", "s"], ["tr", "Reclaim time", "s"]],
  sync: [["dV", "ΔV", "V"], ["df", "Δf", "Hz"], ["dphi", "Δφ", "°"]],
  avr: [["V", "Setpoint (sekunder)", "V"], ["BW", "Bandwidth ±", "%"], ["T1", "Delay T1", "s"]],
  check: [],
};
const DEC: Record<string, number> = { s: 3, A: 3, In: 3, "%": 1, V: 2, Hz: 3, "°": 1, "Ω": 3 };
export const SETUP_UNIT = "psetup", FSET_UNIT = "fset", SETUP_DESC = "Toleransi uji";
export interface Tol { t_pct: number; t_ms: number; p_pct: number }
export const DEFAULT_TOL: Tol = { t_pct: 5, t_ms: 40, p_pct: 5 };
export const IDMT_MULT = [2, 5, 10];
export const DIFF_BIAS = [0, 1, 2, 4];

const SEC = /^([A-Z]{1,2})\. SAS · Uji Proteksi (.+)$/;
const DESC = /^F(\d+) · ([0-9A-Z]+) · (.+)$/;
export const isProtectionSection = (s?: string | null) => SEC.test(s || "");
export const deviceOf = (s?: string | null) => (SEC.exec(s || "") || [])[2] || "";
export const sectionName = (letter: string, device: string) => `${letter}. SAS · Uji Proteksi ${device.trim()}`;
export const kindOf = (code: string): Kind => FUNCS[code]?.[1] || "check";
export const pickupUnit = (code: string) => FUNCS[code]?.[2] || "A";
export const funcName = (code: string) => FUNCS[code]?.[0] || code;
export const nextLetter = nl;
export function presetFor(device: string): string[] {
  for (const [rx, codes] of PRESETS) if (rx.test(device || "")) return [...codes];
  return [...DEFAULT_PRESET];
}
const g = (x: number) => (Number.isInteger(x) ? String(x) : String(Number(x.toPrecision(6))));
export function num(v: any): number | null {
  if (v === undefined || v === null || String(v).trim() === "") return null;
  const x = parseFloat(String(v).trim().replace(",", "."));
  return Number.isFinite(x) ? x : null;
}

export const tolText = (t: Tol) => `waktu ${g(t.t_pct)}% / ${g(t.t_ms)} ms · pickup ${g(t.p_pct)}%`;
export function parseTol(text?: string | null): Tol {
  const m = /waktu (\d+(?:\.\d+)?)% \/ (\d+(?:\.\d+)?) ms · pickup (\d+(?:\.\d+)?)%/.exec(text || "");
  return m ? { t_pct: Number(m[1]), t_ms: Number(m[2]), p_pct: Number(m[3]) } : { ...DEFAULT_TOL };
}

export type Params = Record<string, string>;
export const paramsText = (p: Params) => Object.entries(p).filter(([, v]) => String(v ?? "").trim() !== "").map(([k, v]) => `${k}=${v}`).join("; ");
export function parseParams(text?: string | null): Params {
  const out: Params = {};
  for (const part of String(text || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}

export function complete(code: string, p: Params): boolean {
  const kind = kindOf(code);
  for (const [k] of PARAMS[kind]) {
    if (kind === "dt" && k === "t") continue;
    if (k === "kurva") { if (!(p[k] in CURVES)) return false; continue; }
    const v = num(p[k]);
    if (v === null || v < 0 || (["Is", "P", "I", "V", "Is1"].includes(k) && v <= 0)) return false;
  }
  if (kind === "idmt" && (num(p.TMS) || 0) <= 0) return false;
  return true;
}

export function points(code: string): [string, string][] {
  const kind = kindOf(code);
  if (kind === "idmt") return [["pickup", "A"], ...IDMT_MULT.map((m) => [`${m}×Is`, "s"] as [string, string])];
  if (kind === "dt") return [["pickup", pickupUnit(code)], ["waktu trip", "s"]];
  if (kind === "diff") return [["pickup Ibias 0", "In"], ...DIFF_BIAS.slice(1).map((b) => [`Ibias ${b} In`, "In"] as [string, string])];
  if (kind === "pct") return [["pickup", "%"]];
  if (kind === "bf") return [["pickup I>", "A"], ["t1 retrip", "s"], ["t2 backtrip", "s"]];
  if (kind === "ar") return [["dead time", "s"], ["reclaim time", "s"]];
  if (kind === "sync") return [["ΔV", "V"], ["Δf", "Hz"], ["Δφ", "°"]];
  if (kind === "avr") return [["V di atas band → Lower", "s"], ["V di bawah band → Raise", "s"]];
  return [];
}

export function idmtTime(curve: string, tms: number, m: number): number | null {
  if (curve === "DT") return tms;
  const c = CURVES[curve];
  if (!c) return null;
  const d = m ** c[1] - 1;
  return d > 0 ? tms * (c[0] / d + c[2]) : null;
}

export function diffThreshold(p: Params, ib: number): number {
  const [is1, k1, is2, k2] = ["Is1", "K1", "Is2", "K2"].map((k) => num(p[k]) as number);
  return ib <= is2 ? is1 + (k1 / 100) * ib : is1 + (k1 / 100) * is2 + (k2 / 100) * (ib - is2);
}

export type Exp = [label: string, unit: string, exp: number | null, tol: number | null];
export function expected(code: string, p: Params, tol: Tol): Exp[] {
  if (!complete(code, p)) return [];
  const kind = kindOf(code);
  const tt = (t: number) => Math.max(t * tol.t_pct / 100, tol.t_ms / 1000);
  return points(code).map(([label, unit]): Exp => {
    let e: number | null = null;
    if (kind === "idmt") e = label === "pickup" ? num(p.Is) : idmtTime(p.kurva, num(p.TMS)!, parseFloat(label));
    else if (kind === "dt") e = label === "pickup" ? num(p.P) : num(p.t);
    else if (kind === "diff") e = diffThreshold(p, label.startsWith("pickup") ? 0 : parseFloat(label.split(" ")[1]));
    else if (kind === "pct") e = num(p.P);
    else if (kind === "bf") e = num(p[({ "pickup I>": "I", "t1 retrip": "t1", "t2 backtrip": "t2" } as Record<string, string>)[label]]);
    else if (kind === "ar") e = num(label === "dead time" ? p.td : p.tr);
    else if (kind === "sync") e = num(p[({ "ΔV": "dV", "Δf": "df", "Δφ": "dphi" } as Record<string, string>)[label]]);
    else if (kind === "avr") e = num(p.T1);
    if (e === null) return [label, unit, null, null];
    return [label, unit, e, unit === "s" ? tt(e) : Math.abs(e) * tol.p_pct / 100];
  });
}

export function injectHint(code: string, p: Params, label: string): string {
  if (!complete(code, p)) return "";
  const kind = kindOf(code);
  if (kind === "idmt" && label.includes("×")) return `injeksi ${(parseFloat(label) * num(p.Is)!).toFixed(3)} A`;
  if (kind === "idmt" && label === "pickup") return `naikkan arus pelan dari ${(0.9 * num(p.Is)!).toFixed(3)} A`;
  if (kind === "dt" && label === "waktu trip" && pickupUnit(code) === "A") return `injeksi ${(2 * num(p.P)!).toFixed(3)} A (2× pickup)`;
  if (kind === "diff" && !label.startsWith("pickup")) {
    const b = parseFloat(label.split(" ")[1]);
    return `Ibias ${g(b)} In, naikkan Idiff dari ${(0.9 * diffThreshold(p, b)).toFixed(3)} In`;
  }
  if (kind === "bf" && label !== "pickup I>") return `injeksi ${(2 * num(p.I)!).toFixed(3)} A + trip relay, CB tidak membuka`;
  if (kind === "avr") {
    const v = num(p.V)!, bw = num(p.BW)!;
    const f = label.includes("atas") ? 1 + (bw + 0.5) / 100 : 1 - (bw + 0.5) / 100;
    return `injeksi ${(v * f).toFixed(2)} V (band ${(v * (1 - bw / 100)).toFixed(2)}–${(v * (1 + bw / 100)).toFixed(2)} V)`;
  }
  return "";
}

export const fmt = (x: number, unit: string) => x.toFixed(DEC[unit] ?? 3);
export const criteriaText = (unit: string, e: number | null, tol: number | null) => (e === null || tol === null ? "" : `${fmt(e, unit)} ± ${fmt(tol, unit)}`);

export function toNum(text?: string | null): number | null {
  const m = /-?\d[\d.,]*/.exec(String(text ?? ""));
  if (!m) return null;
  let t = m[0];
  t = t.includes(",") && !t.includes(".") ? t.replace(",", ".") : t.replace(/,/g, "");
  const v = parseFloat(t);
  return Number.isFinite(v) ? v : null;
}

export function judge(e: number | null, tol: number | null, actual?: string | null): "" | "OK" | "NG" {
  const a = toNum(actual);
  if (a === null || e === null || tol === null) return "";
  return Math.abs(a - e) <= tol + 1e-9 ? "OK" : "NG";
}

export type ItemDef = [section: string, description: string, criteria: string, unit: string];
export const fnDesc = (n: number, code: string) => `F${n} · ${code} · ${funcName(code)}`;
export const pointDesc = (n: number, code: string, label: string) => `F${n} · ${code} · ${label}`;

export function functionItems(sec: string, n: number, code: string, p: Params = {}, tol: Tol = DEFAULT_TOL): ItemDef[] {
  if (kindOf(code) === "check") return [[sec, pointDesc(n, code, funcName(code)), "", ""]];
  const out: ItemDef[] = [[sec, fnDesc(n, code), paramsText(p), FSET_UNIT]];
  const ex = new Map(expected(code, p, tol).map(([l, , e, t]) => [l, [e, t] as [number | null, number | null]]));
  for (const [label, unit] of points(code)) {
    const [e, t] = ex.get(label) || [null, null];
    out.push([sec, pointDesc(n, code, label), criteriaText(unit, e, t), unit]);
  }
  if (kindOf(code) === "avr") out.push([sec, pointDesc(n, code, "V di dalam band → tidak ada perintah"), "Tidak ada Raise/Lower", ""]);
  return out;
}

export function blockItems(device: string, letter: string, codes: string[], tol: Tol = { ...DEFAULT_TOL }): ItemDef[] {
  const sec = sectionName(letter, device);
  const out: ItemDef[] = [[sec, SETUP_DESC, tolText(tol), SETUP_UNIT]];
  codes.forEach((code, i) => out.push(...functionItems(sec, i + 1, code, {}, tol)));
  return out;
}

export interface Func { n: number; code: string; name: string; kind: Kind; fset: Row | null; points: [string, Row][] }
export function group(rows: Row[]): { setup: Row | null; tol: Tol; funcs: Func[] } {
  let setup: Row | null = null;
  const fs = new Map<number, Func>();
  for (const r of rows) {
    if ((r.unit || "") === SETUP_UNIT) { setup = setup || r; continue; }
    const m = DESC.exec(r.description || "");
    if (!m) continue;
    const n = Number(m[1]), code = m[2];
    if (!fs.has(n)) fs.set(n, { n, code, name: funcName(code), kind: kindOf(code), fset: null, points: [] });
    const f = fs.get(n)!;
    if ((r.unit || "") === FSET_UNIT) f.fset = f.fset || r;
    else f.points.push([m[3], r]);
  }
  return { setup, tol: setup ? parseTol(setup.criteria) : { ...DEFAULT_TOL }, funcs: [...fs.values()].sort((a, b) => a.n - b.n) };
}
