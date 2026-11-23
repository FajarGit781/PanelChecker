import { createContext } from "preact";
import { useContext, useEffect, useReducer, useState } from "preact/hooks";
import { session } from "../session";
import { store } from "../store";
import { statusLabel, t } from "../i18n";
import { fmtDate, isOverdue, Row } from "../logic";

// Warna lampu indikator menurut IEC 60073
export const LAMP = { red: "#D7261E", amber: "#E08A00", green: "#1E8E3E", blue: "#1F6FB2", off: "#CFD4D2" };
/** Versi lampu yang aman untuk TEKS di atas kertas/abu (kontras ≥ 4.5:1). Lampu (bulatan) tetap pakai LAMP. */
export const INK = { red: "#B51F18", amber: "#8A5200", green: "#1A7A36", blue: "#1A5F9A" };
export const STATUS_LAMP: Record<string, string> = {
  "Open": LAMP.red, "In Progress": LAMP.amber, "Ready to Verify": LAMP.blue, "Closed": LAMP.green,
};
export const PANEL_LAMP: Record<string, string> = {
  "Tanpa checklist": LAMP.off, "Belum dicek": LAMP.off, "Sedang dicek": LAMP.amber, "Ada temuan": LAMP.red,
  "Lulus": LAMP.green, "Diterima": LAMP.green,
};
export const SEV_CLASS: Record<string, string> = { Critical: "sevA", Major: "sevB", Minor: "sevC" };
export const SEV_COLOR: Record<string, string> = { Critical: "#D7261E", Major: "#B04A12", Minor: "#8A6D00" };

export function useStore() {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => { const u = store.subscribe(() => force(0)); return () => { u(); }; }, []);
}

export function useSession() {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => { const u = session.subscribe(() => force(0)); return () => { u(); }; }, []);
  return session;
}

export function useOnline() {
  const [on, setOn] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const a = () => setOn(true), b = () => setOn(false);
    addEventListener("online", a);
    addEventListener("offline", b);
    return () => { removeEventListener("online", a); removeEventListener("offline", b); };
  }, []);
  return on;
}

// ------------------------------------------------------------------ navigasi
export type Route =
  | { name: "home" } | { name: "panels" } | { name: "panel"; id: string } | { name: "punches"; panel?: string }
  | { name: "punch"; id?: string; preset?: Record<string, any> } | { name: "scan" } | { name: "account" }
  | { name: "password"; forced?: boolean };

export interface Nav { go: (r: Route) => void; back: () => void; tab: (r: Route) => void; toast: (m: string) => void;
  project: string; setProject: (id: string) => void; site: string; setSite: (id: string) => void;
  pickProject: () => void }
export const NavCtx = createContext<Nav>(null as any);
export const useNav = () => useContext(NavCtx);

// ------------------------------------------------------------------ elemen
export function Lamp({ color, size, on = true, pulse }: { color: string; size?: "lg"; on?: boolean; pulse?: boolean }) {
  return <span class={`lamp${size ? " " + size : ""}${on && color !== LAMP.off ? " on" : ""}${pulse ? " pulse" : ""}`}
    style={{ background: color, color }} aria-hidden="true" />;
}

export function StatusText({ s }: { s: string }) {
  return <span class="status-txt"><Lamp color={STATUS_LAMP[s] || LAMP.off} />{statusLabel(s)}</span>;
}

/** Pelat nama panel (traffolyte hitam, huruf putih ber-grafir, dua sekrup). */
export function Plate({ tag, name, small }: { tag: string; name?: string; small?: boolean }) {
  return (
    <div class={"plate" + (small ? " sm" : "")}>
      <div class="tag">{tag}</div>
      {name && <div class="name">{name}</div>}
    </div>
  );
}

export function Meter({ parts }: { parts: [number, string][] }) {
  const tot = parts.reduce((a, [v]) => a + v, 0) || 1;
  return <div class="meter">{parts.map(([v, c], i) => v > 0 && <i key={i} style={{ width: `${(100 * v) / tot}%`, background: c }} />)}</div>;
}

/** Lampu status sinkron di header: hijau = tersinkron, kuning = ada yang belum terkirim / sedang sinkron,
 *  merah = gagal, padam = offline. Tekan untuk sinkron sekarang. */
export function SyncLamp() {
  const s = useSession();
  const online = useOnline();
  const nav = useNav();
  useStore();
  const pend = s.readOnly ? 0 : store.pendingCount();
  const color = !online ? LAMP.off : s.lastError ? LAMP.red : (s.syncing || pend) ? LAMP.amber : LAMP.green;
  const label = !online ? t("Offline") : s.syncing ? t("Menyinkron…") : s.lastError ? t("Sinkron gagal") :
    pend ? t("{0} belum terkirim", pend) : t("Tersinkron");
  return (
    <button class="icon-btn" aria-label={label} title={label}
      onClick={() => { if (!online) nav.toast(t("Offline — perubahan disimpan di HP")); else s.sync().then((r) => r && nav.toast(t("Sinkron selesai"))); }}>
      <Lamp color={color} size="lg" pulse={s.syncing} />
    </button>
  );
}

export function TopBar({ title, crumbs, back, right, sync = true }:
  { title: string; crumbs?: string[]; back?: boolean; right?: any; sync?: boolean }) {
  const nav = useNav();
  const s = useSession();
  return (
    <div class="topbar">
      {back && <button class="back-btn" aria-label={t("Kembali")} onClick={() => nav.back()}><Icon name="back" size={24} /></button>}
      <div class="ttl">
        {crumbs && crumbs.length > 0 && (
          <div class="crumb">{crumbs.filter(Boolean).map((c, i) => <>{i > 0 && <i>›</i>}<span>{c}</span></>)}</div>
        )}
        <h1>{title}</h1>
      </div>
      {s.readOnly && <span class="viewer-tag">{t("Viewer")}</span>}
      {right}
      {sync && <SyncLamp />}
    </div>
  );
}

const P: Record<string, string> = {
  home: '<path d="M4 11.5 12 5l8 6.5"/><path d="M6 10v9.5h12V10"/><path d="M10 19.5v-5h4v5"/>',
  panel: '<rect x="5" y="3.5" width="14" height="17" rx="1"/><path d="M8 7h8"/><circle cx="9" cy="11" r="1"/><circle cx="12" cy="11" r="1"/><circle cx="15" cy="11" r="1"/><path d="M16.5 14.5v3"/>',
  punch: '<path d="M7 3.5h10l3 3v14H4v-17z"/><path d="M9 3.5V7h6V3.5"/><path d="M12 11v4M12 17.6v.2"/>',
  scan: '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><rect x="8" y="8" width="3" height="3"/><rect x="13" y="8" width="3" height="3"/><rect x="8" y="13" width="3" height="3"/><path d="M13 13h3v3"/>',
  user: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20c1.2-4 4-5.5 7.5-5.5s6.3 1.5 7.5 5.5"/>',
  camera: '<path d="M4 8h3l1.5-2.5h7L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  image: '<rect x="3.5" y="5" width="17" height="14" rx="1.5"/><circle cx="9" cy="10" r="1.6"/><path d="m4 17 5-4.5 4 3.5 3-2.5 4 3.5"/>',
  back: '<path d="M15 5 8 12l7 7"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  down: '<path d="m7 10 5 5 5-5"/>',
  shield: '<path d="M12 3 4.5 6v5.5c0 4.5 3.2 8 7.5 9.5 4.3-1.5 7.5-5 7.5-9.5V6z"/><path d="m8.8 12 2.2 2.2 4.4-4.4"/>',
  bolt: '<path d="M13 3 5 13.5h6L10 21l8-10.5h-6z"/>',
};

export function Icon({ name, size = 22 }: { name: string; size?: number }) {
  return <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" stroke-width="1.9"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: P[name] || "" }} />;
}

export function SearchBox({ value, onInput, placeholder }: { value: string; onInput: (v: string) => void; placeholder: string }) {
  return (
    <div class="search">
      <Icon name="search" size={20} />
      <input class="input" type="search" value={value} placeholder={placeholder} onInput={(e: any) => onInput(e.currentTarget.value)} />
    </div>
  );
}

/** Kartu punch bergaya label gantung: huruf kategori besar di kiri, lampu status di kanan atas. */
export function PunchTag({ i, onClick }: { i: Row; onClick: () => void }) {
  const late = isOverdue(i);
  const k = { Critical: "A", Major: "B", Minor: "C" }[i.severity as string] || "?";
  return (
    <button class="ptag" onClick={onClick}>
      <div class={"sev " + (SEV_CLASS[i.severity] || "sevB")}>{k}<small>{i.severity}</small></div>
      <div class="body">
        <div class="code"><span class="grow">{i.code}</span><StatusText s={i.status} /></div>
        <div class="t">{i.title}</div>
        <div class="s">
          {i.panel_tag || t("Umum")} <span class="muted">› {i.site_name}</span>
          {i.status !== "Closed" && i.due_date && <> · <span class={late ? "late" : ""}>{late ? t("telat, target {0}", fmtDate(i.due_date)) : t("target {0}", fmtDate(i.due_date))}</span></>}
          {i.pic ? <> · {i.pic}</> : null}
          {i._dirty ? <> · <span class="unsent">{t("belum terkirim")}</span></> : null}
        </div>
      </div>
    </button>
  );
}
