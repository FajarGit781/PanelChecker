import { App as CapApp } from "@capacitor/app";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { applyNow } from "../updater";
import { projects } from "../data";
import { t } from "../i18n";
import { session } from "../session";
import { store } from "../store";
import { Account } from "./Account";
import { Home, ProjectSheet } from "./Home";
import { ChangePassword, Login, Relogin } from "./Login";
import { PanelDetail, Panels } from "./Panels";
import { PunchEdit, Punches } from "./Punches";
import { Scan } from "./Scan";
import { Icon, Nav, NavCtx, Route, useOnline, useSession, useStore } from "./common";

const TABS: { r: Route; label: string; icon: string }[] = [
  { r: { name: "home" }, label: "Ringkasan", icon: "home" },
  { r: { name: "panels" }, label: "Panel", icon: "panel" },
  { r: { name: "scan" }, label: "Scan", icon: "scan" },
  { r: { name: "punches" }, label: "Punch", icon: "punch" },
  { r: { name: "account" }, label: "Akun", icon: "user" },
];

export function App() {
  const s = useSession();
  useStore();
  const online = useOnline();
  const [stack, setStack] = useState<Route[]>([{ name: "home" }]);
  const [toastMsg, setToast] = useState("");
  const toastTimer = useRef<any>(null);
  const [project, setProjectState] = useState<string>(() => localStorage.getItem("pt.project") || "");
  const [site, setSiteState] = useState<string>("");
  const [picker, setPicker] = useState(false);
  const [upd, setUpd] = useState<string>(() => (window as any).__ptUpdate || "");
  useEffect(() => {
    const h = (e: any) => setUpd(String(e.detail || ""));
    addEventListener("pt-update", h);
    return () => removeEventListener("pt-update", h);
  }, []);
  const stackRef = useRef(stack);
  stackRef.current = stack;

  // project aktif: yang terakhir dipilih, atau project pertama
  const ps = projects();
  const effProject = ps.some((p) => p.uuid === project) ? project : (ps[0]?.uuid || "");

  const nav: Nav = useMemo(() => ({
    go: (r) => setStack((st) => [...st, r]),
    back: () => setStack((st) => (st.length > 1 ? st.slice(0, -1) : st[0].name !== "home" ? [{ name: "home" }] : st)),
    tab: (r) => setStack([r]),
    toast: (m) => {
      setToast(m);
      clearTimeout(toastTimer.current);
      toastTimer.current = setTimeout(() => setToast(""), 2600);
    },
    project: effProject,
    setProject: (id) => { localStorage.setItem("pt.project", id); setProjectState(id); setSiteState(""); },
    site,
    setSite: (id) => setSiteState(id),
    pickProject: () => setPicker(true),
  }), [effProject, site]);

  // tombol back Android & sinkron saat aplikasi dibuka kembali
  useEffect(() => {
    const subs: any[] = [];
    CapApp.addListener("backButton", () => {
      if (stackRef.current.length > 1) setStack((st) => st.slice(0, -1));
      else if (stackRef.current[0].name !== "home") setStack([{ name: "home" }]);
      else CapApp.minimizeApp().catch(() => {});
    }).then((h) => subs.push(h)).catch(() => {});
    CapApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive && session.loggedIn && navigator.onLine) session.sync();
    }).then((h) => subs.push(h)).catch(() => {});
    return () => subs.forEach((h) => h.remove());
  }, []);

  useEffect(() => {
    if (!s.loggedIn) return;
    if (navigator.onLine) session.sync();
    session.startAuto(10);
    const on = () => session.sync();
    addEventListener("online", on);
    return () => { session.stopAuto(); removeEventListener("online", on); };
  }, [s.loggedIn]);

  if (!s.loggedIn) return <Login onDone={() => setStack([{ name: "home" }])} />;
  if (s.expired) return <Relogin />;

  const r = stack[stack.length - 1];
  const root = stack[0].name;
  const openPunch = store.all("issues").filter((i) => i.project_uuid === effProject && i.status !== "Closed").length;
  let screen;
  switch (r.name) {
    case "home": screen = <Home />; break;
    case "panels": screen = <Panels />; break;
    case "panel": screen = <PanelDetail key={r.id} id={r.id} />; break;
    case "punches": screen = <Punches key={r.panel || "all"} panel={r.panel} />; break;
    case "punch": screen = <PunchEdit key={(r.id || "new") + stack.length} id={r.id} preset={r.preset} />; break;
    case "scan": screen = <Scan />; break;
    case "account": screen = <Account />; break;
    case "password": screen = <ChangePassword onDone={() => { nav.toast(t("Password berhasil diganti.")); nav.back(); }}
      onCancel={() => nav.back()} />; break;
  }
  return (
    <NavCtx.Provider value={nav}>
      <div class="shell">
        {!online && <div class="offline-strip">{t("Tanpa sinyal — perubahan disimpan di HP dan dikirim otomatis nanti")}</div>}
        {upd && (
          <div class="update-strip">{t("Versi baru {0} siap dipakai.", upd)}
            <button onClick={async () => { if (!(await applyNow())) setUpd(""); }}>{t("Muat ulang")}</button>
            <button class="x" aria-label={t("Nanti")} onClick={() => setUpd("")}>✕</button>
          </div>
        )}
        {screen}
      </div>
      {r.name !== "scan" && (
        <nav class="nav">
          {TABS.map((tb) => tb.r.name === "scan" ? (
            <button class="scan" aria-label={t("Scan label panel")} onClick={() => nav.go({ name: "scan" })}>
              <span class="knob"><Icon name="scan" size={28} /></span>
            </button>
          ) : (
            <button class={root === tb.r.name ? "on" : ""} aria-current={root === tb.r.name ? "page" : undefined} onClick={() => nav.tab(tb.r)}>
              <Icon name={tb.icon} />
              {t(tb.label)}
              {tb.r.name === "punches" && openPunch > 0 && <span class="count">{openPunch}</span>}
            </button>
          ))}
        </nav>
      )}
      {picker && <ProjectSheet onClose={() => setPicker(false)} />}
      {toastMsg && <div class="toast">{toastMsg}</div>}
    </NavCtx.Provider>
  );
}
