import { render } from "preact";
import { Capacitor, SystemBars, SystemBarsStyle, SystemBarType } from "@capacitor/core";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans-condensed/latin-500.css";
import "@fontsource/ibm-plex-sans-condensed/latin-600.css";
import "@fontsource/ibm-plex-sans-condensed/latin-700.css";
import "./styles.css";
import { DEFAULT_KEY, DEFAULT_URL, IS_TEST } from "./config";
import { session } from "./session";
import { store } from "./store";
import { App } from "./ui/App";

async function boot() {
  const root = document.getElementById("app")!;
  try {
    // build tes: server tiruan bisa diatur lewat ?server=http://127.0.0.1:port
    const q = new URLSearchParams(location.search);
    if (IS_TEST && q.get("server")) session.configure(q.get("server")!, "sb_publishable_test");
    else session.configure(DEFAULT_URL, DEFAULT_KEY);
    await store.open();
    session.load();
    render(<App />, root);
    if (!Capacitor.isNativePlatform() && !IS_TEST && "serviceWorker" in navigator && location.protocol === "https:") {
      // versi web (PWA): kulit aplikasi di-cache supaya tetap terbuka tanpa sinyal
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    }
    if (Capacitor.isNativePlatform()) {
      // status bar di atas header gelap → ikon terang; navigation bar di atas menu putih → ikon gelap
      SystemBars.setStyle({ style: SystemBarsStyle.Dark, bar: SystemBarType.StatusBar }).catch(() => {});
      SystemBars.setStyle({ style: SystemBarsStyle.Light, bar: SystemBarType.NavigationBar }).catch(() => {});
    }
  } catch (e: any) {
    root.innerHTML = `<div style="padding:24px;font-family:sans-serif"><h3>Panel Tracker</h3><p>Gagal memulai: ${String(e?.message || e).replace(/</g, "&lt;")}</p></div>`;
  }
}
boot();
