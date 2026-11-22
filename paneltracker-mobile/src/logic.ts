// Aturan bisnis yang sama dengan aplikasi desktop (app/db.py & app/cloud.py).
import { DUE_DAYS, LOGIN_DOMAIN } from "./config";

export type Row = Record<string, any>;

/** Timestamp UTC presisi mikrodetik, format sama dengan desktop: 2026-11-19T03:04:05.123000Z */
export function stamp(): string {
  return new Date().toISOString().replace(/\.(\d{3})Z$/, ".$1000Z");
}

function pad(n: number) {
  return String(n).padStart(2, "0");
}

/** Tanggal lokal YYYY-MM-DD */
export function today(d = new Date()): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Waktu lokal tanpa zona (format checked_at desktop) */
export function nowLocal(d = new Date()): string {
  return `${today(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function addDays(n: number, d = new Date()): string {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return today(x);
}

export function defaultDue(sev: string, days: Record<string, number> = DUE_DAYS): string {
  return addDays(days[sev] ?? DUE_DAYS[sev] ?? 7);
}

export function fmtDate(s?: string | null): string {
  if (!s) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : s;
}

export function uuid(): string {
  const c: any = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  const b = new Uint8Array(16);
  c.getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// ------------------------------------------------------------------ akun
export function loginEmail(user: string): string {
  const u = (user || "").trim().toLowerCase();
  return u.includes("@") ? u : `${u}@${LOGIN_DOMAIN}`;
}

export function displayUser(email: string): string {
  const e = email || "";
  return e.toLowerCase().endsWith("@" + LOGIN_DOMAIN) ? e.split("@")[0] : e;
}

const WEAK = new Set(["password", "p@ssw0rd", "p@ssword", "passw0rd", "viewer", "admin", "qwerty", "12345678",
  "123456789", "1234567890", "paneltracker", "supabase", "rahasia", "bismillah"]);

/** Aturan password tim (sama dengan desktop). Mengembalikan daftar kunci masalah (untuk diterjemahkan). */
export function passwordProblems(pw: string, username = ""): string[] {
  const p = pw || "";
  const out: string[] = [];
  if (p.length < 10) out.push("minimal 10 karakter");
  if (!/[A-Za-z]/.test(p) || !/[0-9]/.test(p)) out.push("harus ada huruf dan angka");
  const low = p.toLowerCase();
  const u = (username || "").split("@")[0].toLowerCase();
  if (WEAK.has(low) || (u.length >= 3 && low.includes(u)) || new Set(p).size < 5)
    out.push("terlalu mudah ditebak (password umum / mengandung username)");
  return out;
}

export function checkEndpoint(url: string, key: string) {
  const u = (url || "").trim().toLowerCase();
  const local = u.startsWith("http://127.0.0.1") || u.startsWith("http://localhost");
  if (!u.startsWith("https://") && !local) throw new Error("Alamat server harus memakai HTTPS (terenkripsi).");
  const k = (key || "").trim();
  let bad = k.startsWith("sb_secret_");
  if (k.split(".").length === 3) {
    try {
      const seg = k.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      bad = bad || JSON.parse(atob(seg + "=".repeat((4 - (seg.length % 4)) % 4))).role === "service_role";
    } catch { /* abaikan */ }
  }
  if (bad) throw new Error("Key yang dimasukkan adalah SECRET / service key. Pakai publishable key.");
}

// ------------------------------------------------------------------ checklist & panel
export interface Stats { total: number; OK: number; NG: number; NA: number; checked: number; pending: number; pct: number }

export function checkStats(rows: Row[]): Stats {
  const s: Stats = { total: rows.length, OK: 0, NG: 0, NA: 0, checked: 0, pending: 0, pct: 0 };
  for (const r of rows) if (r.result === "OK" || r.result === "NG" || r.result === "NA") (s as any)[r.result]++;
  s.checked = s.OK + s.NG + s.NA;
  s.pending = s.total - s.checked;
  s.pct = s.total ? (100 * s.checked) / s.total : 0;
  return s;
}

export interface PunchCount { open: number; total: number; Critical: number; overdue: number }

export function panelStatus(panel: Row, st: Stats, pu: PunchCount): string {
  if (panel.accepted_at) return "Diterima";
  if (st.NG > 0 || pu.open > 0) return "Ada temuan";
  if (st.total === 0) return "Tanpa checklist";
  if (st.checked === 0) return "Belum dicek";
  if (st.pending > 0) return "Sedang dicek";
  return "Lulus";
}

export function isOverdue(i: Row, t = today()): boolean {
  return i.status !== "Closed" && !!i.due_date && i.due_date < t;
}

export function nextIssueCode(project: Row | undefined, issues: Row[]): string {
  const prefix = ((project && project.issue_prefix) || "PL").trim();
  let mx = 0;
  for (const i of issues) {
    const tail = String(i.code || "").split("-").pop() || "";
    if (/^\d+$/.test(tail)) mx = Math.max(mx, parseInt(tail, 10));
  }
  return `${prefix}-${String(mx + 1).padStart(4, "0")}`;
}

/** QR label desktop berisi "PT:<uuid>:<tag>" (label lama: "PT:<nomor lokal>:<tag>"); scanner juga bisa berisi tag saja. */
/** Label v2.7.2+: link viewer web "https://<viewer>/?p=<uuid>" (tanpa tag). */
function uuidFromLink(t: string): string | undefined {
  if (!/^https?:\/\//i.test(t)) return undefined;
  const m = /[?&](?:p|panel)=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i.exec(t);
  return m ? m[1].toLowerCase() : undefined;
}

export function tagFromQr(text: string): string {
  const t = (text || "").trim();
  if (/^https?:\/\//i.test(t)) return "";   // link viewer: panel dicari lewat uuid saja
  const m = /^PT:[^:]*:(.+)$/is.exec(t);
  return (m ? m[1] : t).replace(/\s+/g, " ").trim();
}

/** uuid panel dari QR baru; undefined untuk label lama / tag biasa. */
export function uuidFromQr(text: string): string | undefined {
  const link = uuidFromLink((text || "").trim());
  if (link) return link;
  const m = /^PT:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}):/i.exec((text || "").trim());
  return m ? m[1].toLowerCase() : undefined;
}
