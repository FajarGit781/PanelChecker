// Klien Supabase minimal (Auth + PostgREST + Storage) — format request sama dengan desktop (app/cloud.py).
import { BUCKET, PAGE } from "./config";
import { checkEndpoint, Row } from "./logic";

export class ApiError extends Error {
  constructor(message: string, public status = 0, public auth = false, public offline = false) {
    super(message);
  }
}

export interface Session { refresh_token: string; email: string; user_id?: string }

export class Api {
  url: string;
  key: string;
  access = "";
  refresh = "";
  expiresAt = 0;
  email = "";
  userId = "";
  onSession?: (s: Session) => void;   // dipanggil setiap refresh token berganti (untuk disimpan)

  constructor(url: string, key: string, public timeoutMs = 40000) {
    checkEndpoint(url, key);
    this.url = url.replace(/\/+$/, "");
    this.key = key.trim();
  }

  private async req(method: string, path: string, body?: any,
                    opts: { auth?: boolean; raw?: boolean; headers?: Record<string, string> } = {}): Promise<any> {
    const auth = opts.auth !== false;
    const h: Record<string, string> = { apikey: this.key, ...(opts.headers || {}) };
    if (auth) {
      await this.ensure();
      h.Authorization = `Bearer ${this.access}`;
    }
    let data: BodyInit | undefined;
    if (body !== undefined) {
      if (body instanceof Blob || body instanceof ArrayBuffer || body instanceof Uint8Array) data = body as any;
      else {
        data = JSON.stringify(body);
        if (!h["Content-Type"]) h["Content-Type"] = "application/json";
      }
    }
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), this.timeoutMs);
    let r: Response;
    try {
      r = await fetch(this.url + path, { method, headers: h, body: data, signal: ctl.signal, cache: "no-store" });
    } catch (e: any) {
      throw new ApiError(e?.name === "AbortError" ? "Koneksi ke server cloud timeout." :
        "Tidak bisa terhubung ke server cloud (cek internet).", 0, false, true);
    } finally {
      clearTimeout(timer);
    }
    if (!r.ok) {
      let msg = await r.text();
      try {
        const j = JSON.parse(msg);
        msg = j.msg || j.message || j.error_description || j.error || msg;
      } catch { /* teks biasa */ }
      if ([400, 401, 403, 422].includes(r.status) && path.startsWith("/auth/")) throw new ApiError(msg, r.status, true);
      if (r.status === 401) throw new ApiError(`Sesi tidak valid (${msg}). Silakan login ulang.`, 401, true);
      throw new ApiError(`HTTP ${r.status} ${method} ${path.split("?")[0]}: ${msg}`, r.status);
    }
    if (opts.raw) return await r.blob();
    const txt = await r.text();
    return txt ? JSON.parse(txt) : null;
  }

  // ------------------------------------------------------------ auth
  private setSession(j: Row) {
    this.access = j.access_token;
    this.refresh = j.refresh_token || this.refresh;
    this.expiresAt = Date.now() + (Number(j.expires_in || 3600) - 60) * 1000;
    const u = j.user || {};
    this.email = u.email || this.email;
    this.userId = u.id || this.userId;
    this.onSession?.({ refresh_token: this.refresh, email: this.email, user_id: this.userId });
  }

  async signIn(email: string, password: string) {
    this.setSession(await this.req("POST", "/auth/v1/token?grant_type=password", { email, password }, { auth: false }));
  }

  async restore(refresh: string, email = "") {
    this.refresh = refresh;
    this.email = email;
    await this.refreshToken();
  }

  async refreshToken() {
    if (!this.refresh) throw new ApiError("Belum login.", 0, true);
    this.setSession(await this.req("POST", "/auth/v1/token?grant_type=refresh_token",
      { refresh_token: this.refresh }, { auth: false }));
  }

  async ensure() {
    if (!this.access || Date.now() >= this.expiresAt) await this.refreshToken();
  }

  /** Cabut sesi INI saja di server (scope=local). Tanpa scope, Supabase mencabut semua sesi akun ini di semua
   *  perangkat (default "global") — satu orang keluar di satu HP membuat HP/laptop lain dengan akun sama putus. */
  async signOut() {
    try {
      if (this.access || this.refresh) await this.req("POST", "/auth/v1/logout?scope=local", {});
    } catch { /* tetap keluar di HP */ }
    this.access = this.refresh = "";
  }

  async updatePassword(pw: string) {
    await this.req("PUT", "/auth/v1/user", { password: pw });
  }

  async membership(): Promise<Row | null> {
    const q = encodeURIComponent(this.email || "");
    let rows = await this.req("GET", `/rest/v1/app_users?select=email,full_name,role&email=eq.${q}`);
    if (!rows || !rows.length) rows = await this.req("GET", `/rest/v1/app_users?select=email,full_name,role&email=ilike.${q}`);
    return rows && rows.length ? rows[0] : null;
  }

  // ------------------------------------------------------------ data
  async upsert(table: string, rows: Row[]) {
    if (rows.length)
      await this.req("POST", `/rest/v1/${table}?on_conflict=uuid`, rows,
        { headers: { Prefer: "resolution=merge-duplicates,return=minimal" } });
  }

  /** Update sebagian kolom satu baris tanpa updated_at → kolom lain di server (hasil cek) tidak tersentuh. */
  async patch(table: string, uuid: string, fields: Row) {
    await this.req("PATCH", `/rest/v1/${table}?uuid=eq.${encodeURIComponent(uuid)}`, fields,
      { headers: { Prefer: "return=minimal" } });
  }

  async teamSettings(keys: string[]): Promise<Row[]> {
    return (await this.req("GET", `/rest/v1/team_settings?select=key,value,updated_at,deleted&key=in.(${keys.join(",")})`)) || [];
  }

  async changedSince(table: string, cursor: string, offset = 0, limit = PAGE): Promise<Row[]> {
    let q = `/rest/v1/${table}?select=*&order=server_updated_at.asc,uuid.asc&limit=${limit}&offset=${offset}`;
    if (cursor) q += "&server_updated_at=gt." + encodeURIComponent(cursor);
    return (await this.req("GET", q)) || [];
  }

  async upload(path: string, data: Blob, contentType = "image/jpeg") {
    await this.req("POST", `/storage/v1/object/${BUCKET}/${encodeURI(path)}`, data,
      { headers: { "Content-Type": contentType, "x-upsert": "true", "cache-control": "3600" } });
  }

  async download(path: string): Promise<Blob> {
    return await this.req("GET", `/storage/v1/object/authenticated/${BUCKET}/${encodeURI(path)}`, undefined,
      { raw: true });
  }
}
