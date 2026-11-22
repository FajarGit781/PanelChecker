// Mesin sinkron HP ↔ Supabase. Aturan sama dengan desktop (app/cloud.py SyncEngine):
// pull dulu (kode punch bentrok diselesaikan), lalu push perubahan lokal, last-write-wins via updated_at.
import { Api } from "./api";
import { BATCH, PAGE } from "./config";
import { nextIssueCode, Row, stamp } from "./logic";
import { store, Table } from "./store";
import { t as tr } from "./i18n";

// kolom yang dikirim ke server per tabel (selain uuid, updated_at, deleted)
const COLS: Record<Table, string[]> = {
  projects: ["code", "name", "client", "contractor", "location", "start_date", "end_date", "description",
    "issue_prefix", "created_at"],
  sites: ["project_uuid", "name", "location", "sort", "created_at"],
  panels: ["site_uuid", "bay", "tag", "name", "panel_type", "vendor", "serial_no", "remarks", "accepted_by",
    "accepted_at", "sort", "created_at"],
  panel_checks: ["panel_uuid", "section", "description", "criteria", "unit", "sort", "result", "value", "remark",
    "checked_by", "checked_at", "created_at"],
  issues: ["project_uuid", "site_uuid", "panel_uuid", "check_uuid", "code", "title", "description", "category",
    "severity", "status", "pic", "raised_by", "raised_date", "due_date", "closed_date", "verified_by", "action",
    "created_at"],
  attachments: ["issue_uuid", "kind", "filename", "caption", "storage_path", "created_at"],
};
const ORDER: Table[] = ["projects", "sites", "panels", "panel_checks", "issues", "attachments"];
const REQUIRED: Partial<Record<Table, string>> = {
  sites: "project_uuid", panels: "site_uuid", panel_checks: "panel_uuid", issues: "project_uuid",
  attachments: "issue_uuid",
};

export interface SyncStats { pulled: number; pushed: number; photos_up: number; photos_down: number; skipped: number;
  seconds: number }

export class SyncEngine {
  constructor(private api: Api, private push = true, private progress: (m: string) => void = () => {}) {}

  async run(): Promise<SyncStats> {
    const t0 = Date.now();
    const st: SyncStats = { pulled: 0, pushed: 0, photos_up: 0, photos_down: 0, skipped: 0, seconds: 0 };
    this.progress(tr("Mengambil perubahan dari cloud…"));
    for (const t of ORDER) st.pulled += await this.pull(t);
    await this.pullTeam();
    if (this.push) {
      this.progress(tr("Mengirim perubahan lokal…"));
      for (const t of ORDER) st.pushed += await this.pushTable(t, st);
    }
    await store.setMeta("sync_last", new Date().toISOString());
    st.seconds = Math.round((Date.now() - t0) / 100) / 10;
    return st;
  }

  // ---------------------------------------------------------------- pull
  private async pull(t: Table): Promise<number> {
    const key = `cursor_${t}`;
    const cursor: string = await store.meta(key, "");
    let q = cursor;
    if (cursor) {   // mundur 2 menit untuk transaksi yang commit terlambat (aman: LWW)
      const d = new Date(cursor);
      if (!isNaN(d.getTime())) q = new Date(d.getTime() - 120000).toISOString();
    }
    let offset = 0, n = 0, maxSeen = cursor;
    for (;;) {
      const rows = await this.api.changedSince(t, q, offset);
      const apply: Row[] = [];
      for (const r of rows) {
        const row = await this.prepare(t, r);
        if (row) apply.push(row);
        const su = r.server_updated_at || "";
        if (new Date(su).getTime() > new Date(maxSeen || 0).getTime()) maxSeen = su;
      }
      await store.putRaw(t, apply);
      n += apply.length;
      if (rows.length < PAGE) break;
      offset += PAGE;
      this.progress(tr("Ambil {0}: {1}…", t, offset));
    }
    if (maxSeen && maxSeen !== cursor) await store.setMeta(key, maxSeen);
    return n;
  }

  private async prepare(t: Table, r: Row): Promise<Row | null> {
    const local = store.get(t, r.uuid);
    if (local && (local.updated_at || "") >= (r.updated_at || "")) return null;  // lokal sama/lebih baru
    const req = REQUIRED[t];
    if (req && !r[req]) return null;
    const row: Row = { uuid: r.uuid, updated_at: r.updated_at, deleted: Number(r.deleted || 0), _dirty: 0 };
    for (const c of COLS[t]) row[c] = r[c] ?? null;
    if (t === "issues" && !local) await this.resolveCodeClash(row);
    if (t === "attachments" && local && local.storage_path !== row.storage_path) await store.setPhoto(r.uuid, null);
    return row;
  }

  /** Dua perangkat membuat kode punch sama saat offline → kode lokal yang belum terkirim diganti. */
  private async resolveCodeClash(remote: Row) {
    const clash = store.all("issues", true).find((i) => i.project_uuid === remote.project_uuid &&
      i.code === remote.code && i.uuid !== remote.uuid && i._dirty);
    if (!clash) return;
    const pool = store.all("issues", true).filter((i) => i.project_uuid === remote.project_uuid);
    const code = nextIssueCode(store.get("projects", remote.project_uuid), [...pool, remote]);
    await store.edit("issues", clash.uuid, { code });
  }

  /** Pengaturan tim yang dipakai di HP (kategori temuan, target default). Logo & kop tidak perlu di HP. */
  private async pullTeam() {
    const keys = ["categories", "due_days_Critical", "due_days_Major", "due_days_Minor"];
    let rows: Row[];
    try {
      rows = await this.api.teamSettings(keys);
    } catch (e: any) {
      if (e?.status === 404) return;   // server lama tanpa tabel team_settings
      throw e;
    }
    const t: Record<string, string> = {};
    for (const r of rows) if (!r.deleted) t[r.key] = r.value ?? "";
    if (JSON.stringify(t) !== JSON.stringify(store.team)) await store.setTeam(t);
  }

  // ---------------------------------------------------------------- push
  private payload(t: Table, r: Row): Row {
    const p: Row = { uuid: r.uuid, updated_at: r.updated_at, deleted: Number(r.deleted || 0) };
    for (const c of COLS[t]) p[c] = r[c] ?? null;
    return p;
  }

  private async pushTable(t: Table, st: SyncStats): Promise<number> {
    if (t === "attachments") {
      for (const r of store.dirty(t)) {
        if (r.storage_path || r.deleted) continue;
        const blob = await store.photo(r.uuid);
        if (!blob) continue;
        const path = `${r.issue_uuid || "umum"}/${r.uuid}.jpg`;
        this.progress(tr("Upload foto {0}…", r.filename || ""));
        await this.api.upload(path, blob, blob.type === "image/png" ? "image/png" : "image/jpeg");
        // updated_at ikut diperbarui supaya perangkat lain yang sudah punya metadata ikut mengunduh foto
        await store.putRaw(t, [{ ...store.get(t, r.uuid)!, storage_path: path, updated_at: stamp(), _dirty: 1 }]);
        st.photos_up++;
      }
    }
    const rows = store.dirty(t);
    let n = 0;
    for (let i = 0; i < rows.length; i += BATCH) {
      const chunk = rows.slice(i, i + BATCH);
      const payload: Row[] = [], sent: Row[] = [];
      for (const r of chunk) {
        const req = REQUIRED[t];
        if (req && !r[req]) { st.skipped++; continue; }
        if (t === "attachments" && !r.storage_path && !r.deleted) { st.skipped++; continue; }  // foto belum terupload
        payload.push(this.payload(t, r));
        sent.push(r);
      }
      this.progress(tr("Kirim {0}: {1}/{2}", t, i + chunk.length, rows.length));
      await this.api.upsert(t, payload);
      // flag hanya dibersihkan kalau baris tidak diubah lagi selama pengiriman
      const clean: Row[] = [];
      for (const r of sent) {
        const cur = store.get(t, r.uuid);
        if (cur && cur.updated_at === r.updated_at) clean.push({ ...cur, _dirty: 0 });
      }
      await store.putRaw(t, clean);
      n += payload.length;
    }
    return n;
  }

  // ---------------------------------------------------------------- foto
  /** Unduh foto satu lampiran (dipanggil saat foto dibuka). */
  static async ensurePhoto(api: Api | null, att: Row): Promise<Blob | undefined> {
    const have = await store.photo(att.uuid);
    if (have || !att.storage_path || !api) return have;
    const blob = await api.download(att.storage_path);
    await store.setPhoto(att.uuid, blob);
    return blob;
  }

  /** Unduh semua foto yang belum ada di HP (untuk dipakai offline). */
  async downloadAll(filter?: (a: Row) => boolean): Promise<number> {
    const have = await store.photoKeys();
    const todo = store.all("attachments").filter((a) => a.storage_path && !have.has(a.uuid) && (!filter || filter(a)));
    let n = 0;
    for (const [k, a] of todo.entries()) {
      this.progress(tr("Unduh foto {0}/{1}…", k + 1, todo.length));
      try {
        await store.setPhoto(a.uuid, await this.api.download(a.storage_path));
        n++;
      } catch { /* lewati yang gagal */ }
    }
    return n;
  }
}
