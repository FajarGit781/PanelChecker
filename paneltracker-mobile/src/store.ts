// Penyimpanan offline di HP (IndexedDB) + cache di memori.
// Setiap baris berformat sama dengan tabel server (kunci = uuid). Kolom lokal: _dirty (1 = belum terkirim).
import { openDB, IDBPDatabase } from "idb";
import { Row, stamp, uuid as newUuid } from "./logic";

export const TABLES = ["projects", "sites", "panels", "panel_checks", "issues", "attachments"] as const;
export type Table = (typeof TABLES)[number];

const DB_NAME = "panel-tracker";
const DB_VER = 1;

type Listener = () => void;

class Store {
  private db!: IDBPDatabase;
  private mem: Record<string, Map<string, Row>> = {};
  private listeners = new Set<Listener>();
  private notifyTimer: any = null;
  ready = false;
  /** Pengaturan tim dari cloud (kategori temuan, target default). Hanya dibaca di HP. */
  team: Record<string, string> = {};

  async open() {
    this.db = await openDB(DB_NAME, DB_VER, {
      upgrade(db) {
        for (const t of TABLES) db.createObjectStore(t, { keyPath: "uuid" });
        db.createObjectStore("photos");   // uuid lampiran → Blob
        db.createObjectStore("meta");     // cursor sinkron, pengaturan
      },
    });
    for (const t of TABLES) {
      const m = new Map<string, Row>();
      for (const r of await this.db.getAll(t)) m.set(r.uuid, r);
      this.mem[t] = m;
    }
    this.team = (await this.db.get("meta", "team")) || {};
    this.ready = true;
  }

  async setTeam(t: Record<string, string>) {
    this.team = t;
    await this.db.put("meta", t, "team");
    this.changed();
  }

  // ------------------------------------------------------------ baca
  all(t: Table, includeDeleted = false): Row[] {
    const out: Row[] = [];
    for (const r of this.mem[t].values()) if (includeDeleted || !r.deleted) out.push(r);
    return out;
  }

  get(t: Table, id?: string | null): Row | undefined {
    return id ? this.mem[t].get(id) : undefined;
  }

  // ------------------------------------------------------------ tulis
  async putRaw(t: Table, rows: Row[]) {
    if (!rows.length) return;
    const tx = this.db.transaction(t, "readwrite");
    for (const r of rows) {
      this.mem[t].set(r.uuid, r);
      tx.store.put(r);
    }
    await tx.done;
    this.changed();
  }

  /** Ubah data oleh pengguna: updated_at baru + tandai belum terkirim. */
  async edit(t: Table, id: string, changes: Row): Promise<Row> {
    const cur = this.mem[t].get(id);
    if (!cur) throw new Error(`${t} ${id} tidak ditemukan`);
    const row = { ...cur, ...changes, updated_at: stamp(), _dirty: 1 };
    await this.putRaw(t, [row]);
    return row;
  }

  async create(t: Table, data: Row): Promise<Row> {
    const ts = stamp();
    const row = { uuid: newUuid(), created_at: ts.slice(0, 19), deleted: 0, ...data, updated_at: ts, _dirty: 1 };
    await this.putRaw(t, [row]);
    return row;
  }

  dirty(t: Table): Row[] {
    return [...this.mem[t].values()].filter((r) => r._dirty);
  }

  pendingCount(): number {
    let n = 0;
    for (const t of TABLES) n += this.dirty(t).length;
    return n;
  }

  // ------------------------------------------------------------ foto
  async photo(id: string): Promise<Blob | undefined> {
    const v: any = await this.db.get("photos", id);
    if (!v) return undefined;
    if (v instanceof Blob) return v;                                   // format lama
    return new Blob([v.b], { type: v.t || "image/jpeg" });
  }

  /** Foto disimpan sebagai ArrayBuffer (bukan Blob): Safari/iPhone mode privat & WebKit tertentu menolak Blob di IndexedDB. */
  async setPhoto(id: string, blob: Blob | null) {
    if (blob) await this.db.put("photos", { t: blob.type || "image/jpeg", b: await blob.arrayBuffer() }, id);
    else await this.db.delete("photos", id);
  }

  async photoKeys(): Promise<Set<string>> {
    return new Set((await this.db.getAllKeys("photos")) as string[]);
  }

  // ------------------------------------------------------------ meta
  async meta<T = any>(k: string, d?: T): Promise<T> {
    const v = await this.db.get("meta", k);
    return v === undefined ? (d as T) : v;
  }

  async setMeta(k: string, v: any) {
    await this.db.put("meta", v, k);
  }

  /** Hapus semua data di HP (dipakai saat keluar akun). */
  async wipe() {
    for (const t of [...TABLES, "photos", "meta"]) await this.db.clear(t as any);
    for (const t of TABLES) this.mem[t] = new Map();
    this.team = {};
    this.changed();
  }

  // ------------------------------------------------------------ notifikasi UI
  subscribe(fn: Listener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private changed() {
    if (this.notifyTimer) return;
    this.notifyTimer = setTimeout(() => {
      this.notifyTimer = null;
      for (const l of this.listeners) l();
    }, 0);
  }
}

export const store = new Store();
