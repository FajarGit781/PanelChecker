// Uji injeksi sekunder CT/VT — sama persis dengan aplikasi laptop (paneltracker/app/injection.py).
//
// Disimpan sebagai item checklist biasa (tanpa tabel baru):
//   seksi  "<huruf>. SAS · Injeksi CT/VT <device>"
//   setup  unit "setup", kriteria "CT 2000/1 A · VT 150 kV/110 V · tol 1% · PF ±0.01 · f ±0.02 Hz"
//   titik  deskripsi "T1 · I 10% · V 100% · φ 0° · 50 Hz · IA", unit "A", kriteria "200.0 ± 2.0"
//          nilai = actual, hasil OK/NG otomatis.
// Toleransi I/V = tol% dari expected; P/Q = tol% dari S (MVA); PF/f = selisih absolut.
// Foto evidence satu titik uji ditempel di item pertamanya (IA).
import type { Row } from "./logic";

export const KEYS = ["IA", "IB", "IC", "VAB", "VBC", "VCA", "P", "Q", "PF", "f"] as const;
export type Key = (typeof KEYS)[number];
export const UNIT: Record<Key, string> = { IA: "A", IB: "A", IC: "A", VAB: "kV", VBC: "kV", VCA: "kV", P: "MW", Q: "MVAR", PF: "PF", f: "Hz" };
export const DEC: Record<Key, number> = { IA: 1, IB: 1, IC: 1, VAB: 3, VBC: 3, VCA: 3, P: 3, Q: 3, PF: 3, f: 2 };
export const SETUP_UNIT = "setup";
export const SETUP_DESC = "Setup injeksi";
const SQ3 = Math.sqrt(3);

export interface Setup { ct_p: number; ct_s: number; vt_p: number; vt_s: number; tol: number; tol_pf: number; tol_f: number }
export interface Point { n: number; pi: number; pv: number; phi: number; hz: number }
export interface PointGroup extends Point { rows: Partial<Record<Key, Row>> }
export const DEFAULT_SETUP: Setup = { ct_p: 2000, ct_s: 1, vt_p: 150, vt_s: 110, tol: 1, tol_pf: 0.01, tol_f: 0.02 };

const SEC = /^([A-Z]{1,2})\. SAS · Injeksi CT\/VT (.+)$/;
const N = "(-?\\d+(?:\\.\\d+)?)";
const SETUP_RE = new RegExp(`CT ${N}/${N} A · VT ${N} kV/${N} V · tol ${N}% · PF ±${N} · f ±${N} Hz`);
const POINT_RE = new RegExp(`^T(\\d+) · I ${N}% · V ${N}% · φ ${N}° · ${N} Hz · (${KEYS.join("|")})$`);

export const isInjectionSection = (s?: string | null) => SEC.test(s || "");
export const deviceOf = (s?: string | null) => (SEC.exec(s || "") || [])[2] || "";
export const sectionName = (letter: string, device: string) => `${letter}. SAS · Injeksi CT/VT ${device.trim()}`;

/** Angka ringkas untuk teks tersimpan: 2000 → "2000", 0.01 → "0.01" (sama dengan _g di Python). */
export function g(x: number): string {
  if (Number.isInteger(x)) return String(x);
  return String(Number(x.toPrecision(6)));
}

export const setupText = (s: Setup) =>
  `CT ${g(s.ct_p)}/${g(s.ct_s)} A · VT ${g(s.vt_p)} kV/${g(s.vt_s)} V · tol ${g(s.tol)}% · PF ±${g(s.tol_pf)} · f ±${g(s.tol_f)} Hz`;

export function parseSetup(text?: string | null): Setup | null {
  const m = SETUP_RE.exec(text || "");
  if (!m) return null;
  const [ct_p, ct_s, vt_p, vt_s, tol, tol_pf, tol_f] = m.slice(1).map(Number);
  if (ct_p <= 0 || ct_s <= 0 || vt_p <= 0 || vt_s <= 0) return null;
  return { ct_p, ct_s, vt_p, vt_s, tol, tol_pf, tol_f };
}

export const pointDesc = (n: number, pi: number, pv: number, phi: number, hz: number, key: Key) =>
  `T${n} · I ${g(pi)}% · V ${g(pv)}% · φ ${g(phi)}° · ${g(hz)} Hz · ${key}`;

export function parsePoint(desc?: string | null): (Point & { key: Key }) | null {
  const m = POINT_RE.exec(desc || "");
  if (!m) return null;
  return { n: Number(m[1]), pi: Number(m[2]), pv: Number(m[3]), phi: Number(m[4]), hz: Number(m[5]), key: m[6] as Key };
}

/** key → [expected, toleransi absolut] */
export function expected(s: Setup, p: { pi: number; pv: number; phi: number; hz: number }): Record<Key, [number, number]> {
  const ctr = s.ct_p / s.ct_s, vtr = (s.vt_p * 1000) / s.vt_s;
  const iPri = s.ct_s * p.pi / 100 * ctr;
  const vLL = s.vt_s * p.pv / 100 * vtr / 1000;
  const S = SQ3 * vLL * iPri / 1000;
  const phi = p.phi * Math.PI / 180;
  const t = s.tol / 100;
  return {
    IA: [iPri, Math.abs(iPri) * t], IB: [iPri, Math.abs(iPri) * t], IC: [iPri, Math.abs(iPri) * t],
    VAB: [vLL, Math.abs(vLL) * t], VBC: [vLL, Math.abs(vLL) * t], VCA: [vLL, Math.abs(vLL) * t],
    P: [S * Math.cos(phi), S * t], Q: [S * Math.sin(phi), S * t], PF: [Math.cos(phi), s.tol_pf], f: [p.hz, s.tol_f],
  };
}

export function secondary(s: Setup, p: { pi: number; pv: number; phi: number; hz: number }) {
  const vll = s.vt_s * p.pv / 100;
  return { i: s.ct_s * p.pi / 100, v_ln: vll / SQ3, v_ll: vll, phi: p.phi, hz: p.hz };
}

export const fmt = (x: number, d: number) => x.toFixed(d);

export function criteriaText(key: Key, exp: number, tol: number): string {
  const d = DEC[key];
  const e = Math.abs(exp) < 0.5 * 10 ** -d ? 0 : exp;
  return `${fmt(e, d)} ± ${fmt(tol, d)}`;
}

/** Angka dari isian lapangan: '1.001,5', '1001,5', '1001.5', ' 200 A'. */
export function toNum(text?: string | null): number | null {
  const m = /-?\d[\d.,]*/.exec(String(text ?? "").trim());
  if (!m) return null;
  let s = m[0];
  if (/^-?\d{1,3}(\.\d{3})+,\d+$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
  else if (s.includes(",") && !s.includes(".")) s = s.replace(",", ".");
  else s = s.replace(/,/g, "");
  const v = parseFloat(s);
  return Number.isFinite(v) ? v : null;
}

/** "OK" bila |actual − expected| ≤ toleransi, "NG" bila di luar, "" bila actual kosong/bukan angka. */
export function judge(exp: number, tol: number, actual?: string | null): "" | "OK" | "NG" {
  const a = toNum(actual);
  if (a === null) return "";
  return Math.abs(a - exp) <= tol + 1e-9 ? "OK" : "NG";
}

function signed(x: number, d: number) {
  if (Math.abs(x) < 0.5 * 10 ** -d) x = 0;
  return (x >= 0 ? "+" : "") + x.toFixed(d);
}

export function errorText(key: Key, exp: number, tol: number, actual?: string | null, s?: Setup | null): string {
  const a = toNum(actual);
  if (a === null) return "";
  if (key === "PF") return signed(a - exp, 3);
  if (key === "f") return signed(a - exp, 2) + " Hz";
  const base = key === "P" || key === "Q" ? (s && s.tol ? tol / (s.tol / 100) : 0) : Math.abs(exp);
  if (!base) return "";
  return signed((a - exp) / base * 100, 2) + " %";
}

export type ItemDef = [section: string, description: string, criteria: string, unit: string];

export function pointItems(sec: string, s: Setup, n: number, pi: number, pv: number, phi: number, hz: number): ItemDef[] {
  const ex = expected(s, { pi, pv, phi, hz });
  return KEYS.map((k) => [sec, pointDesc(n, pi, pv, phi, hz, k), criteriaText(k, ex[k][0], ex[k][1]), UNIT[k]] as ItemDef);
}

export function blockItems(device: string, letter: string, s: Setup, points: [number, number, number, number][]): ItemDef[] {
  const sec = sectionName(letter, device);
  const out: ItemDef[] = [[sec, SETUP_DESC, setupText(s), SETUP_UNIT]];
  points.forEach(([pi, pv, phi, hz], i) => out.push(...pointItems(sec, s, i + 1, pi, pv, phi, hz)));
  return out;
}

/** Huruf seksi berikutnya setelah huruf terbesar yang dipakai panel (A..Z, AA..). */
export function nextLetter(sections: string[]): string {
  let best = 0;
  for (const s of sections) {
    const m = /^([A-Z]{1,2})\. /.exec(s || "");
    if (!m) continue;
    const t = m[1];
    const v = t.length === 1 ? t.charCodeAt(0) - 64 : 26 * (t.charCodeAt(0) - 64) + (t.charCodeAt(1) - 64);
    best = Math.max(best, v);
  }
  const v = best + 1;
  return v <= 26 ? String.fromCharCode(64 + v) : String.fromCharCode(64 + Math.floor((v - 1) / 26)) + String.fromCharCode(65 + ((v - 1) % 26));
}

export function group(rows: Row[]): { setup: Row | null; points: PointGroup[] } {
  let setup: Row | null = null;
  const pts = new Map<number, PointGroup>();
  for (const r of rows) {
    if ((r.unit || "") === SETUP_UNIT) { setup = setup || r; continue; }
    const p = parsePoint(r.description);
    if (!p) continue;
    if (!pts.has(p.n)) pts.set(p.n, { n: p.n, pi: p.pi, pv: p.pv, phi: p.phi, hz: p.hz, rows: {} });
    const gp = pts.get(p.n)!;
    if (!gp.rows[p.key]) gp.rows[p.key] = r;
  }
  return { setup, points: [...pts.values()].sort((a, b) => a.n - b.n) };
}

/** Expected untuk satu baris: dari setup, atau (setup rusak) dari kriteria "x ± y". */
export function expOf(s: Setup | null, p: Point, key: Key, r: Row): [number, number] {
  if (s) return expected(s, p)[key];
  const m = /^\s*(-?\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)/.exec(r.criteria || "");
  return m ? [Number(m[1]), Number(m[2])] : [0, 0];
}

/** Rasio dari item "… · Rasio CT/VT" (nilai teks bebas, mis. '2000/1 A', '150/0.11 kV', '150000/110 V'). */
export function prefillFromRatio(rows: Row[], device: string): Setup {
  const s = { ...DEFAULT_SETUP };
  for (const r of rows) {
    if (!(r.section || "").includes("Rasio CT/VT") || !String(r.value || "").trim()) continue;
    const d = String(r.description || "");
    if (!d.startsWith(device + " · ")) continue;
    const m = /(\d+(?:[.,]\d+)?)\s*(k?V|A)?\s*\/\s*(\d+(?:[.,]\d+)?)\s*(k?V|A)?/i.exec(r.value);
    if (!m) continue;
    const a = Number(m[1].replace(",", ".")), ua = (m[2] || "").toLowerCase();
    const b = Number(m[3].replace(",", ".")), ub = (m[4] || "").toLowerCase();
    if (d.endsWith("CT ratio")) { s.ct_p = a; s.ct_s = b; }
    else if (d.endsWith("VT ratio")) {
      s.vt_p = ua === "v" || (!ua && a > 1000) ? a / 1000 : a;
      s.vt_s = ub === "kv" || (!ub && b < 5) ? b * 1000 : b;
    }
  }
  return s;
}

export function ratioDevices(rows: Row[]): string[] {
  const out: string[] = [];
  for (const r of rows) {
    if (!(r.section || "").includes("Rasio CT/VT")) continue;
    const dev = String(r.description || "").split(" · ")[0].trim();
    if (dev && !out.includes(dev)) out.push(dev);
  }
  return out;
}

// ======================================================================= baca foto HMI (teks OCR → nilai)
const NUMRE = "(-?\\d{1,6}(?:[.,]\\d{1,4})?)";
const UNITRE = "(MVAR|Mvar|MVAr|kvar|kVAR|kA|kV|kW|MW|Hz|HZ|A|V)?(?![A-Za-z])";
const OCR_LABELS: Record<Key, string[]> = {
  IA: ["I\\s*[-_.]?\\s*(?:A|R|L1|1)(?![A-Z0-9])", "Ia(?![a-z])"],
  IB: ["I\\s*[-_.]?\\s*(?:B|S|L2|2)(?![A-Z0-9])", "Ib(?![a-z])"],
  IC: ["I\\s*[-_.]?\\s*(?:C|T|L3|3)(?![A-Z0-9])", "Ic(?![a-z])"],
  VAB: ["[VU]\\s*[-_.]?\\s*(?:AB|RS|L1\\s*-?\\s*L2|12)(?![A-Z0-9])"],
  VBC: ["[VU]\\s*[-_.]?\\s*(?:BC|ST|L2\\s*-?\\s*L3|23)(?![A-Z0-9])"],
  VCA: ["[VU]\\s*[-_.]?\\s*(?:CA|TR|L3\\s*-?\\s*L1|31)(?![A-Z0-9])"],
  P: ["(?<![A-Z])P(?:\\s*(?:tot|total|3ph))?(?![A-Z])", "Active\\s*Power", "Daya\\s*Aktif"],
  Q: ["(?<![A-Z])Q(?:\\s*(?:tot|total|3ph))?(?![A-Z])", "Reactive\\s*Power", "Daya\\s*Reaktif"],
  PF: ["P\\.?\\s*F\\.?(?![A-Z])", "cos\\s*(?:φ|phi|ϕ|0|o)?", "Power\\s*Factor"],
  f: ["(?<![A-Z])f(?![A-Z])", "Freq(?:uency|uensi)?"],
};
const OCR_UNITS: Record<Key, Record<string, number>> = {
  IA: { A: 1, kA: 1000 }, IB: { A: 1, kA: 1000 }, IC: { A: 1, kA: 1000 },
  VAB: { kV: 1, V: 0.001 }, VBC: { kV: 1, V: 0.001 }, VCA: { kV: 1, V: 0.001 },
  P: { MW: 1, kW: 0.001 }, Q: { MVAR: 1, kvar: 0.001 }, PF: { "": 1 }, f: { Hz: 1 },
};

function normUnit(u?: string): string {
  if (!u) return "";
  const l = u.toLowerCase();
  if (l === "mvar") return "MVAR";
  if (l === "kvar") return "kvar";
  if (l === "hz") return "Hz";
  if (l === "ka" || l === "kv" || l === "kw") return "k" + u[1].toUpperCase();
  if (l === "mw") return "MW";
  return u;
}

function ocrNum(s: string): number | null {
  s = s.trim();
  if (/^-?\d{1,3}(\.\d{3})+,\d+$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
  else s = s.replace(",", ".");
  const v = parseFloat(s);
  return Number.isFinite(v) ? v : null;
}

export interface OcrHit { value: number; seen: string; conf: "high" | "medium" | "low" }

/** Teks hasil OCR layar HMI/BCU/meter → nilai per besaran (hanya angka berlabel, atau satuan khas MW/MVAR/Hz). */
export function parseHmi(text: string): Partial<Record<Key, OcrHit>> {
  const lines = String(text || "").split(/\r?\n/).map((l) => l.replace(/\|/g, " ").replace(/\s+/g, " ").trim()).filter(Boolean);
  const found: Partial<Record<Key, OcrHit>> = {};
  for (const line of lines) {
    for (const k of KEYS) {
      if (found[k]?.conf === "high") continue;
      for (const lab of OCR_LABELS[k]) {
        const re = new RegExp(`(${lab})\\s*[:=]?\\s*${NUMRE}\\s*${UNITRE}`, "gi");
        let m: RegExpExecArray | null, hit = false;
        while ((m = re.exec(line))) {
          const unit = normUnit(m[3]);
          const conv = OCR_UNITS[k];
          if (unit && !(unit in conv)) continue;
          let v = ocrNum(m[2]);
          if (v === null) continue;
          v *= unit ? conv[unit] : 1;
          if (k === "PF" && Math.abs(v) > 1) continue;
          if (k === "f" && (v < 40 || v > 70)) continue;
          const conf = unit || k === "PF" ? "high" : "medium";
          if (!found[k] || (conf === "high" && found[k]!.conf !== "high")) {
            let seen = m[0].trim();
            if (unit && conv[unit] !== 1) seen += ` (→ ${Object.keys(conv)[0]})`;
            found[k] = { value: v, seen, conf };
          }
          hit = true;
          break;
        }
        if (hit) break;
      }
    }
  }
  const all = lines.join(" ");
  const loose: [Key, RegExp][] = [["P", /(-?\d+(?:[.,]\d+)?)\s*MW\b/i], ["Q", /(-?\d+(?:[.,]\d+)?)\s*M?var\b/i], ["f", /(\d{2}(?:[.,]\d+)?)\s*Hz\b/i]];
  for (const [k, rx] of loose) {
    if (found[k]) continue;
    const m = rx.exec(all);
    if (m) { const v = ocrNum(m[1]); if (v !== null) found[k] = { value: v, seen: m[0], conf: "low" }; }
  }
  return found;
}

/** Teks nilai yang disimpan dari angka hasil baca foto. */
export function valueText(key: Key, v: number): string {
  if (key === "PF") return v.toFixed(3);
  return String(Number(v.toFixed(Math.max(DEC[key], 1))));
}
