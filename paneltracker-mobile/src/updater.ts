// Update otomatis APK tanpa install ulang (hanya Android/native; PWA sudah selalu versi terbaru).
//
// Sumber update = situs PWA yang sama (pt-panel-app). Satu deploy → PWA dan APK sama-sama terbarui.
//  1. Saat online, unduh bundle.json (daftar file + sha256 + versi APK minimum).
//  2. Versi lebih baru & APK cukup baru → unduh file yang berubah saja ke penyimpanan app
//     (file yang sama diambil dari bundle yang sedang jalan), cek sha256.
//  3. Bundle baru dipakai saat aplikasi dibuka berikutnya (atau tombol "Muat ulang") lewat API bawaan Capacitor
//     WebView.setServerBasePath; setelah tampil sehat, bundle itu sendiri memanggil persistServerBasePath.
//     Origin tetap https://localhost → data offline (IndexedDB) aman.
//  4. Pengaman: bila bundle baru tidak berhasil tampil dalam 20 detik, public/boot-guard.js kembali ke bundle bawaan
//     APK dan versi itu ditandai rusak (tidak dicoba lagi). Install APK baru otomatis kembali ke bundle bawaan.
import { Capacitor, CapacitorHttp, WebView } from "@capacitor/core";
import { App } from "@capacitor/app";
import { Directory, Filesystem } from "@capacitor/filesystem";
import { APP_VERSION, IS_TEST, UPDATE_BASE } from "./config";

interface FileEntry { p: string; h: string; s: number }
interface Manifest { version: string; minNative: string; files: FileEntry[] }

const K = { pending: "pt.bundle.pending", applied: "pt.bundle.applied", ok: "pt.bundle.ok", bad: "pt.bundle.bad" };
const DIR = "bundles";

export function cmpVer(a: string, b: string): number {
  const x = a.split(".").map((n) => parseInt(n, 10) || 0), y = b.split(".").map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] || 0) - (y[i] || 0);
    if (d) return d > 0 ? 1 : -1;
  }
  return 0;
}

const native = () => Capacitor.isNativePlatform() && !IS_TEST;
const ls = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* abaikan */ } },
  del: (k: string) => { try { localStorage.removeItem(k); } catch { /* abaikan */ } },
};

/** Dipanggil setelah aplikasi tampil: bundle ini sehat (boot-guard tidak perlu kembali ke bundle bawaan). */
export function markBundleOk() {
  if (!native()) return;
  // bundle yang sedang tampil terbukti sehat → simpan path-nya untuk start berikutnya (bundle rusak tidak pernah tersimpan)
  WebView.persistServerBasePath().catch(() => {});
  ls.set(K.ok, APP_VERSION);
  if (ls.get(K.applied) === APP_VERSION) ls.del(K.applied);
  const p = pending();
  if (p && cmpVer(p.version, APP_VERSION) <= 0) ls.del(K.pending);
}

function pending(): { version: string; path: string } | null {
  try { return JSON.parse(ls.get(K.pending) || "null"); } catch { return null; }
}

/** Saat start (sebelum tampil): pakai bundle yang sudah diunduh. True → WebView memuat ulang ke bundle baru. */
export async function applyPendingAtStart(): Promise<boolean> {
  if (!native()) return false;
  const p = pending();
  if (!p || cmpVer(p.version, APP_VERSION) <= 0 || ls.get(K.bad) === p.version) return false;
  return applyNow();
}

/** Pindah ke bundle yang sudah diunduh sekarang (WebView memuat ulang). */
export async function applyNow(): Promise<boolean> {
  const p = pending();
  if (!p) return false;
  try {
    await Filesystem.stat({ path: `${DIR}/${p.version}/index.html`, directory: Directory.Data });
  } catch {
    ls.del(K.pending);
    return false;
  }
  ls.set(K.applied, p.version);
  await WebView.setServerBasePath({ path: p.path });     // WebView memuat ulang; bundle baru menyimpan dirinya bila sehat
  return true;
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", bytes as unknown as ArrayBuffer);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function blobToB64(blob: Blob): Promise<string> {
  const buf = new Uint8Array(await blob.arrayBuffer());
  let s = "";
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(s);
}

let running = false;

/** Cek & unduh update di belakang layar. onReady(versi) saat bundle baru siap dipakai. */
export async function checkForUpdate(onReady?: (version: string) => void): Promise<string | null> {
  if (!native() || running || !navigator.onLine) return null;
  running = true;
  try {
    const r = await CapacitorHttp.get({ url: `${UPDATE_BASE}bundle.json?t=${Date.now()}`, headers: { "Cache-Control": "no-cache" } });
    if (r.status !== 200) return null;
    const m: Manifest = typeof r.data === "string" ? JSON.parse(r.data) : r.data;
    if (!m?.version || !Array.isArray(m.files)) return null;
    if (cmpVer(m.version, APP_VERSION) <= 0 || ls.get(K.bad) === m.version) return null;
    const info = await App.getInfo();
    if (cmpVer(info.version, m.minNative || "0") < 0) return null;       // butuh APK baru (plugin native berubah)
    const pend = pending();
    if (pend?.version === m.version) { onReady?.(m.version); return m.version; }

    let local: Manifest | null = null;
    try { local = await (await fetch("bundle.json", { cache: "no-store" })).json(); } catch { /* bundle lama tanpa manifest */ }
    const localHash = new Map((local?.files || []).map((f) => [f.p, f.h]));
    const dir = `${DIR}/${m.version}`;
    for (const f of m.files) {
      let b64 = "";
      if (localHash.get(f.p) === f.h) {                                  // sama dengan bundle yang sedang jalan
        try {
          const res = await fetch(f.p);
          if (res.ok) {
            const bytes = new Uint8Array(await res.arrayBuffer());
            if (await sha256Hex(bytes) === f.h) b64 = await blobToB64(new Blob([bytes]));
          }
        } catch { /* ambil dari server */ }
      }
      if (!b64) {                                                         // berubah, atau salinan lokal tidak cocok
        const res = await CapacitorHttp.get({ url: UPDATE_BASE + f.p.split("/").map(encodeURIComponent).join("/"), responseType: "arraybuffer" });
        if (res.status !== 200) throw new Error(`unduh ${f.p}: ${res.status}`);
        b64 = String(res.data);
        if (await sha256Hex(b64ToBytes(b64)) !== f.h) throw new Error(`hash ${f.p} tidak cocok`);
      }
      await Filesystem.writeFile({ path: `${dir}/${f.p}`, data: b64, directory: Directory.Data, recursive: true });
    }
    const uri = (await Filesystem.getUri({ path: dir, directory: Directory.Data })).uri;
    ls.set(K.pending, JSON.stringify({ version: m.version, path: decodeURIComponent(uri.replace(/^file:\/\//, "")) }));
    await cleanup(m.version);
    onReady?.(m.version);
    return m.version;
  } catch {
    return null;                                                          // coba lagi saat online berikutnya
  } finally {
    running = false;
  }
}

/** Hapus bundle lama (simpan yang sedang dipakai & yang menunggu). */
async function cleanup(keep: string) {
  try {
    const { files } = await Filesystem.readdir({ path: DIR, directory: Directory.Data });
    for (const f of files) {
      const name = typeof f === "string" ? f : f.name;
      if (name === keep || name === APP_VERSION) continue;
      await Filesystem.rmdir({ path: `${DIR}/${name}`, directory: Directory.Data, recursive: true }).catch(() => {});
    }
  } catch { /* folder belum ada */ }
}
