// Matriks integrasi SAS: item checklist "X. SAS · <device>" dipetakan ke baris device × 5 kolom.
// Sama dengan aplikasi laptop (app/sas_matrix.py).
import type { Row } from "./logic";

export const SAS_COLS = [
  { key: "int", label: "Integrasi", re: /terintegrasi/i },
  { key: "ip", label: "IP", re: /^ip address/i },
  { key: "sntp", label: "SNTP", re: /sntp/i },
  { key: "cid", label: "CID", re: /\bcid\b/i },
  { key: "set", label: "Setting", re: /^setting/i },
] as const;
export type SasCol = typeof SAS_COLS[number]["key"];

const SEC_RE = /^[A-Z]{1,2}\. SAS · (.+)$/;

export function isSasSection(section: string): boolean {
  return SEC_RE.test(section || "");
}

/** Seksi uji DI/DO ("X. SAS · DI/DO <device>"): report & foto evidence terpisah. */
export function isDidoSection(section: string): boolean {
  return /^[A-Z]{1,2}\. SAS · DI\/DO /.test(section || "");
}

const NOT_MEASURE = new Set(["ip", "rev", "rev cid"]);
/** Item measurement test = punya satuan ukur (VDC, VAC, MΩ, ms, rasio, …), bukan IP / revisi file. */
export function isMeasurement(unit: string): boolean {
  const u = (unit || "").trim().toLowerCase();
  return !!u && !NOT_MEASURE.has(u);
}

/** Item yang diberi foto evidence: uji DI/DO & measurement test (sama dengan desktop). */
export function needsEvidence(section: string, unit: string): boolean {
  return isDidoSection(section) || isMeasurement(unit);
}

export interface SasDevice {
  section: string;
  name: string;
  cells: Partial<Record<SasCol, Row>>;
  extra: Row[];          // item SAS lain yang tidak masuk 5 kolom (tetap ditampilkan sebagai daftar)
}

export function sasMatrix(checks: Row[]): SasDevice[] {
  const out: SasDevice[] = [];
  const bySec = new Map<string, SasDevice>();
  for (const c of checks) {
    const m = SEC_RE.exec(c.section || "");
    if (!m) continue;
    let d = bySec.get(c.section);
    if (!d) {
      d = { section: c.section, name: m[1], cells: {}, extra: [] };
      bySec.set(c.section, d);
      out.push(d);
    }
    const col = SAS_COLS.find((k) => k.re.test(c.description || ""));
    if (col && !d.cells[col.key]) d.cells[col.key] = c;
    else d.extra.push(c);
  }
  // blok tanpa kolom matriks (Rasio CT/VT, DI/DO …) bukan device → tetap tampil di daftar
  return out.filter((d) => Object.keys(d.cells).length > 0);
}

/** Tap sel: kosong → OK → NG → N/A → kosong. */
export function nextResult(cur: string): string {
  return ({ "": "OK", OK: "NG", NG: "NA", NA: "" } as Record<string, string>)[cur || ""] ?? "";
}

const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;

/** Subnet bay dari kriteria item, mis. "Subnet 172.16.9.x" → "172.16.9." */
export function subnetPrefix(criteria: string): string | null {
  const m = /(\d{1,3}\.\d{1,3}\.\d{1,3})\.x/i.exec(criteria || "");
  return m ? m[1] + "." : null;
}

/** Pesan peringatan IP ("" = aman). others = IP yang sudah dipakai device lain → {ip: "tag · device"}. */
export function ipWarning(ip: string, criteria: string, others: Map<string, string>): string {
  const v = (ip || "").trim();
  if (!v) return "";
  if (!IPV4.test(v)) return "Format IP tidak valid";
  const pre = subnetPrefix(criteria);
  if (pre && !v.startsWith(pre)) return `Di luar subnet ${pre}x`;
  const dup = others.get(v);
  if (dup) return `Sudah dipakai: ${dup}`;
  return "";
}
