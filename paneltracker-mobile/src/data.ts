// Query data untuk tampilan (dari cache memori store).
import { checkStats, isOverdue, panelStatus, PunchCount, Row, Stats, today } from "./logic";
import { store } from "./store";

export function projects(): Row[] {
  return store.all("projects").sort((a, b) => String(a.code).localeCompare(String(b.code)));
}

export function sitesOf(pid: string): Row[] {
  return store.all("sites").filter((s) => s.project_uuid === pid)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0) || String(a.name).localeCompare(String(b.name)));
}

export function panelsOf(pid: string, siteId?: string | null): Row[] {
  const sites = new Map(sitesOf(pid).map((s) => [s.uuid, s]));
  return store.all("panels").filter((p) => sites.has(p.site_uuid) && (!siteId || p.site_uuid === siteId))
    .map((p): Row => ({ ...p, site_name: sites.get(p.site_uuid)!.name }))
    .sort((a, b) => String(a.site_name).localeCompare(String(b.site_name)) || (a.sort ?? 0) - (b.sort ?? 0) ||
      String(a.tag).localeCompare(String(b.tag)));
}

export function checksOf(panelId: string): Row[] {
  return store.all("panel_checks").filter((c) => c.panel_uuid === panelId)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0) || String(a.created_at).localeCompare(String(b.created_at)));
}

export function issuesOf(pid: string, siteId?: string | null): Row[] {
  const panels = new Map(store.all("panels").map((p) => [p.uuid, p]));
  const sites = new Map(store.all("sites").map((s) => [s.uuid, s]));
  return store.all("issues").filter((i) => i.project_uuid === pid && (!siteId || i.site_uuid === siteId))
    .map((i): Row => ({ ...i, panel_tag: panels.get(i.panel_uuid)?.tag || "", site_name: sites.get(i.site_uuid)?.name || "" }))
    .sort((a, b) => String(b.code).localeCompare(String(a.code), undefined, { numeric: true }));
}

export function attachmentsOf(issueId: string): Row[] {
  return store.all("attachments").filter((a) => a.issue_uuid === issueId)
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
}

export interface PanelOv { panel: Row; stats: Stats; punch: PunchCount; status: string }

export function panelOverview(pid: string, siteId?: string | null): PanelOv[] {
  const checks = new Map<string, Row[]>();
  for (const c of store.all("panel_checks")) {
    if (!checks.has(c.panel_uuid)) checks.set(c.panel_uuid, []);
    checks.get(c.panel_uuid)!.push(c);
  }
  const t = today();
  const pu = new Map<string, PunchCount>();
  for (const i of store.all("issues")) {
    if (!i.panel_uuid) continue;
    const c = pu.get(i.panel_uuid) || { open: 0, total: 0, Critical: 0, overdue: 0 };
    c.total++;
    if (i.status !== "Closed") {
      c.open++;
      if (i.severity === "Critical") c.Critical++;
      if (isOverdue(i, t)) c.overdue++;
    }
    pu.set(i.panel_uuid, c);
  }
  return panelsOf(pid, siteId).map((p) => {
    const st = checkStats(checks.get(p.uuid) || []);
    const c = pu.get(p.uuid) || { open: 0, total: 0, Critical: 0, overdue: 0 };
    return { panel: p, stats: st, punch: c, status: panelStatus(p, st, c) };
  });
}

/** Kategori temuan & target default: pakai pengaturan tim dari laptop (Pengaturan → Daftar Pilihan) kalau ada. */
export function teamCategories(fallback: string[]): string[] {
  try {
    const v = JSON.parse(store.team.categories || "null");
    if (Array.isArray(v) && v.length) return v.map(String);
  } catch { /* abaikan nilai rusak */ }
  return fallback;
}

export function teamDueDays(fallback: Record<string, number>): Record<string, number> {
  const out = { ...fallback };
  for (const s of Object.keys(fallback)) {
    const n = parseInt(store.team[`due_days_${s}`] ?? "", 10);
    if (!isNaN(n) && n >= 0) out[s] = n;
  }
  return out;
}

export function categories(pid: string, base: string[]): string[] {
  const out = [...base];
  for (const i of store.all("issues")) if (i.project_uuid === pid && i.category && !out.includes(i.category)) out.push(i.category);
  return out;
}
