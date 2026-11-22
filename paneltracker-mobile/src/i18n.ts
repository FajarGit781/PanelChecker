// Bahasa: teks sumber Bahasa Indonesia, terjemahan English di kamus EN.
import { EN } from "./i18n_en";

let lang: "id" | "en" = (typeof localStorage !== "undefined" && localStorage.getItem("pt.lang") === "en") ? "en" : "id";

export function getLang() { return lang; }

export function setLang(l: "id" | "en") {
  lang = l;
  try { localStorage.setItem("pt.lang", l); } catch { /* abaikan */ }
}

export function t(s: string, ...args: any[]): string {
  let out = lang === "en" ? (EN[s] ?? s) : s;
  args.forEach((a, i) => { out = out.split(`{${i}}`).join(String(a)); });
  return out;
}

const STATUS_ID: Record<string, string> = {
  "Open": "Open", "In Progress": "Dikerjakan", "Ready to Verify": "Siap Verifikasi", "Closed": "Closed",
};
export function statusLabel(s: string) { return t(STATUS_ID[s] ?? s); }
