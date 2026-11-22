// Akun & sinkron: login, sesi tersimpan, peran (viewer = baca saja), jadwal sinkron otomatis.
import { Api, ApiError } from "./api";
import { DEFAULT_KEY, DEFAULT_URL } from "./config";
import { t } from "./i18n";
import { loginEmail, passwordProblems } from "./logic";
import { store } from "./store";
import { SyncEngine, SyncStats } from "./sync";

const SESSION_KEY = "pt.session";

export interface SessionInfo { email: string; role: string; full_name: string; refresh_token: string }

type Listener = () => void;

class SessionManager {
  info: SessionInfo | null = null;
  api: Api | null = null;
  syncing = false;
  syncMsg = "";
  lastError = "";
  lastSync = "";
  /** Sesi dicabut di server (mis. akun yang sama keluar di perangkat lain / password diganti).
   *  Data di HP TIDAK dihapus; pengguna cukup login ulang dan perubahan yang tertunda langsung dikirim. */
  expired = false;
  private listeners = new Set<Listener>();
  private timer: any = null;

  url = DEFAULT_URL;
  key = DEFAULT_KEY;

  get loggedIn() { return !!this.info; }
  get readOnly() { return this.info?.role === "viewer"; }

  subscribe(fn: Listener) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  private emit() { for (const l of this.listeners) l(); }

  configure(url: string, key: string) { this.url = url; this.key = key; }

  private makeApi(): Api {
    const api = new Api(this.url, this.key);
    api.onSession = (s) => {
      if (this.info && s.refresh_token) {
        this.info = { ...this.info, refresh_token: s.refresh_token };
        this.save();
      }
    };
    return api;
  }

  load() {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      this.info = raw ? JSON.parse(raw) : null;
    } catch { this.info = null; }
    if (this.info) {
      this.api = this.makeApi();
      this.api.refresh = this.info.refresh_token;
      this.api.email = this.info.email;
    }
  }

  private save() {
    if (this.info) localStorage.setItem(SESSION_KEY, JSON.stringify(this.info));
    else localStorage.removeItem(SESSION_KEY);
  }

  /**
   * Login. Mengembalikan "weak" kalau password harus diganti dulu (api disimpan sementara di pendingApi).
   */
  pendingApi: Api | null = null;
  pendingMember: any = null;

  async login(username: string, password: string): Promise<"ok" | "weak"> {
    const api = this.makeApi();
    const email = loginEmail(username);
    try {
      await api.signIn(email, password);
    } catch (e: any) {
      if (e instanceof ApiError && e.auth && /invalid/i.test(e.message)) throw new Error(t("Username atau password salah."));
      throw e;
    }
    const mem = await api.membership();
    if (!mem) {
      await api.signOut();
      throw new Error(t("Akun ini belum terdaftar di tim. Hubungi admin."));
    }
    if (passwordProblems(password, email).length) {
      this.pendingApi = api;
      this.pendingMember = mem;
      return "weak";
    }
    this.finishLogin(api, mem);
    return "ok";
  }

  /** Login ulang setelah sesi berakhir: akun yang sama, data di HP (termasuk yang belum terkirim) tetap utuh. */
  async relogin(password: string) {
    if (!this.info) throw new Error(t("Belum login."));
    const api = this.makeApi();
    try {
      await api.signIn(this.info.email, password);
    } catch (e: any) {
      if (e instanceof ApiError && e.auth && /invalid/i.test(e.message)) throw new Error(t("Password salah."));
      throw e;
    }
    const mem = await api.membership();
    if (!mem) {
      await api.signOut();
      throw new Error(t("Akun ini belum terdaftar di tim. Hubungi admin."));
    }
    this.expired = false;
    this.finishLogin(api, mem);
    this.sync();
  }

  async changePassword(newPw: string, oldPw?: string) {
    const api = this.pendingApi || this.api;
    if (!api) throw new Error(t("Belum login."));
    if (oldPw !== undefined) {   // verifikasi pemilik akun
      const chk = new Api(this.url, this.key);
      try {
        await chk.signIn(api.email, oldPw);
      } catch {
        throw new Error(t("Password sekarang salah."));
      }
      await chk.signOut();
    }
    await api.updatePassword(newPw);
    if (this.pendingApi) {
      this.finishLogin(this.pendingApi, this.pendingMember);
      this.pendingApi = this.pendingMember = null;
    }
  }

  async cancelPending() {
    if (this.pendingApi) await this.pendingApi.signOut();
    this.pendingApi = this.pendingMember = null;
  }

  private finishLogin(api: Api, mem: any) {
    this.api = api;
    this.info = { email: api.email, role: mem.role || "", full_name: mem.full_name || "", refresh_token: api.refresh };
    api.onSession = (s) => {
      if (this.info && s.refresh_token) { this.info = { ...this.info, refresh_token: s.refresh_token }; this.save(); }
    };
    this.save();
    this.lastError = "";
    this.expired = false;
    this.emit();
  }

  /** Keluar: cabut sesi di server dan hapus semua data di HP. */
  async logout() {
    this.stopAuto();
    if (this.api) await this.api.signOut();
    this.api = null;
    this.info = null;
    this.expired = false;
    this.save();
    for (const k of ["pt.lastPanel", "pt.project"]) localStorage.removeItem(k);
    await store.wipe();
    this.emit();
  }

  // ------------------------------------------------------------ sinkron
  async sync(): Promise<SyncStats | null> {
    if (this.syncing || !this.api || !this.info) return null;
    this.syncing = true;
    this.lastError = "";
    this.emit();
    try {
      const st = await new SyncEngine(this.api, !this.readOnly, (m) => { this.syncMsg = m; this.emit(); }).run();
      this.lastSync = new Date().toISOString();
      return st;
    } catch (e: any) {
      this.lastError = e?.message || String(e);
      if (e instanceof ApiError && e.auth && (e.status === 401 || (e.status === 400 && /refresh/i.test(e.message)))) {
        // sesi dicabut (mis. password diganti / akun yang sama keluar di perangkat lain) → minta login ulang,
        // data di HP dibiarkan utuh
        this.lastError = t("Sesi berakhir. Silakan login ulang.");
        this.expired = true;
      }
      return null;
    } finally {
      this.syncing = false;
      this.syncMsg = "";
      this.emit();
    }
  }

  async downloadAllPhotos(filter?: (a: any) => boolean): Promise<number> {
    if (!this.api) return 0;
    this.syncing = true;
    this.emit();
    try {
      return await new SyncEngine(this.api, false, (m) => { this.syncMsg = m; this.emit(); }).downloadAll(filter);
    } finally {
      this.syncing = false;
      this.syncMsg = "";
      this.emit();
    }
  }

  startAuto(minutes = 10) {
    this.stopAuto();
    this.timer = setInterval(() => { if (navigator.onLine) this.sync(); }, minutes * 60000);
  }

  stopAuto() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

export const session = new SessionManager();
