import { useState } from "preact/hooks";
import { APP_VERSION } from "../config";
import { getLang, setLang, t } from "../i18n";
import { displayUser } from "../logic";
import { store } from "../store";
import { Icon, Lamp, LAMP, TopBar, useNav, useOnline, useSession, useStore, INK } from "./common";

export function Account() {
  useStore();
  const s = useSession();
  const nav = useNav();
  const online = useOnline();
  const [busy, setBusy] = useState(false);
  const pend = s.readOnly ? 0 : store.pendingCount();
  const atts = store.all("attachments").filter((a) => a.storage_path).length;
  const last = s.lastSync ? new Date(s.lastSync).toLocaleTimeString().slice(0, 5) : "";
  const lamp = !online ? LAMP.off : s.lastError ? LAMP.red : (s.syncing || pend) ? LAMP.amber : LAMP.green;

  async function logout() {
    const msg = pend > 0
      ? t("{0} perubahan belum terkirim ke cloud dan akan hilang. Tetap keluar?", pend)
      : t("Keluar dari akun? Data di HP ini dihapus; data di cloud tetap aman.");
    if (!confirm(msg)) return;
    setBusy(true);
    await s.logout();
    setBusy(false);
  }

  return (
    <>
      <TopBar title={t("Akun")} />
      <div class="content">
        <div class="sheet">
          <div class="hd" style={{ paddingBottom: 12 }}>
            <div class="grow">
              <h2>{s.info?.full_name || displayUser(s.info?.email || "")}</h2>
              <div class="small muted">{t("Login sebagai {0}, peran {1}", displayUser(s.info?.email || ""), s.info?.role || "-")}</div>
            </div>
          </div>
          {s.readOnly && <div class="bd"><div class="msg warn" style={{ margin: 0 }}>{t("Akun viewer hanya bisa melihat data dan mencetak di laptop.")}</div></div>}
        </div>

        <div class="sheet">
          <div class="hd"><h2>{t("Sinkron")}</h2></div>
          <div class="line" style={{ cursor: "default" }}>
            <Lamp color={lamp} size="lg" pulse={s.syncing} />
            <div class="main">
              <div class="t">{!online ? t("Offline") : s.syncing ? (s.syncMsg || t("Menyinkron…")) : s.lastError ? t("Sinkron gagal") :
                pend ? t("{0} perubahan menunggu dikirim", pend) : t("Semua data tersinkron")}</div>
              <div class="s">{s.lastError ? s.lastError : last ? t("Terakhir sinkron pukul {0}", last) : t("Belum sinkron sejak aplikasi dibuka")}</div>
            </div>
            <button class="btn sm primary" disabled={s.syncing || !online} onClick={() => s.sync()}>{t("Sinkron")}</button>
          </div>
          <div class="line" style={{ cursor: "default" }}>
            <Icon name="image" />
            <div class="main">
              <div class="t">{t("Foto untuk kerja tanpa sinyal")}</div>
              <div class="s">{t("Foto diunduh saat punch dibuka. Unduh semua ({0}) sebelum masuk area tanpa sinyal.", atts)}</div>
            </div>
            <button class="btn sm" disabled={s.syncing || !online}
              onClick={async () => nav.toast(t("{0} foto diunduh.", await s.downloadAllPhotos()))}>{t("Unduh")}</button>
          </div>
        </div>

        <div class="sheet">
          <div class="hd"><h2>{t("Bahasa")}</h2></div>
          {(["id", "en"] as const).map((l) => (
            <button class="line" onClick={() => { setLang(l); location.reload(); }}>
              <Lamp color={getLang() === l ? LAMP.green : LAMP.off} />
              <div class="main"><div class="t">{l === "id" ? "Bahasa Indonesia" : "English"}</div></div>
            </button>
          ))}
        </div>

        <div class="sheet">
          <div class="hd"><h2>{t("Keamanan")}</h2></div>
          <button class="line" onClick={() => nav.go({ name: "password" })}>
            <Icon name="shield" /><div class="main"><div class="t">{t("Ganti password")}</div>
              <div class="s">{t("Min. 10 karakter, huruf dan angka")}</div></div><span class="chev"><Icon name="chev" /></span>
          </button>
          <button class="line" disabled={busy} onClick={logout} style={{ color: INK.red }}>
            <Icon name="close" /><div class="main"><div class="t">{t("Keluar dan hapus data di HP")}</div>
              <div class="s">{t("Sesi dicabut di server")}</div></div>
          </button>
        </div>
        <p class="small muted" style={{ textAlign: "center" }}>Panel Tracker Mobile {APP_VERSION}</p>
      </div>
    </>
  );
}
