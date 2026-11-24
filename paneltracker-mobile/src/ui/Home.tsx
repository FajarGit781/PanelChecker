import { issuesOf, panelOverview, projects, sitesOf } from "../data";
import { t } from "../i18n";
import { isOverdue, Row, today } from "../logic";
import { store } from "../store";
import { Icon, Lamp, LAMP, Meter, PANEL_LAMP, PunchTag, TopBar, useNav, useStore, INK, portal } from "./common";

export function projectCrumbs(nav: { project: string; site: string }) {
  const pr = store.get("projects", nav.project);
  const site = nav.site ? store.get("sites", nav.site) : undefined;
  return [pr?.code || "", site ? site.name : t("Semua site")];
}

export function Home() {
  useStore();
  const nav = useNav();
  const pr = store.get("projects", nav.project);
  if (!pr) {
    return (
      <>
        <TopBar title="Panel Tracker" />
        <div class="content">
          <div class="empty"><b>{t("Belum ada data di HP")}</b>{t("Tekan lampu sinkron di kanan atas untuk mengambil project dari cloud.")}</div>
        </div>
      </>
    );
  }
  const ov = panelOverview(nav.project, nav.site);
  const iss = issuesOf(nav.project, nav.site);
  const td = today();
  const open = iss.filter((i) => i.status !== "Closed");
  const aOpen = open.filter((i) => i.severity === "Critical");
  const over = open.filter((i) => isOverdue(i, td));
  const items = ov.reduce((a, o) => ({ c: a.c + o.stats.checked, t: a.t + o.stats.total }), { c: 0, t: 0 });
  const started = ov.filter((o) => o.stats.checked > 0).length;
  const lastId = localStorage.getItem("pt.lastPanel");
  const last = lastId ? ov.find((o) => o.panel.uuid === lastId) : undefined;
  const urgent = open.slice().sort((a, b) =>
    ["Critical", "Major", "Minor"].indexOf(a.severity) - ["Critical", "Major", "Minor"].indexOf(b.severity) ||
    Number(isOverdue(b, td)) - Number(isOverdue(a, td)) || String(a.due_date || "9").localeCompare(String(b.due_date || "9"))).slice(0, 5);
  const sites = sitesOf(nav.project).filter((s) => !nav.site || s.uuid === nav.site);

  return (
    <>
      <TopBar title={pr.name} crumbs={projectCrumbs(nav)}
        right={<button class="icon-btn" aria-label={t("Pilih project / site")} onClick={nav.pickProject}><Icon name="down" /></button>} />
      <div class="content">
        <div class={"energize " + (aOpen.length ? "block" : "clear")}>
          <Icon name="bolt" size={30} />
          <div class="grow">
            {aOpen.length ? <>
              <div class="what">{t("{0} punch kategori A masih terbuka", aOpen.length)}</div>
              <div class="why">{t("Harus selesai sebelum energize.")}</div>
            </> : <>
              <div class="what">{t("Tidak ada punch kategori A terbuka")}</div>
              <div class="why">{t("Dari sisi punch list, tidak ada yang menahan energize.")}</div>
            </>}
          </div>
        </div>

        {last && (
          <button class="resume" onClick={() => nav.go({ name: "panel", id: last.panel.uuid })}>
            <div class="grow">
              <div class="k">{t("Lanjutkan checking")}</div>
              <div class="tg">{last.panel.tag}</div>
              <div class="k">{t("{0} dari {1} item diuji", last.stats.checked, last.stats.total)}</div>
            </div>
            <Lamp color={PANEL_LAMP[last.status]} size="lg" />
            <Icon name="chev" />
          </button>
        )}

        <div class="gauges">
          <div class="gauge"><div class="v">{started}<span class="muted" style={{ fontSize: 17 }}>/{ov.length}</span></div><div class="l">{t("panel sudah dicek")}</div></div>
          <div class="gauge"><div class="v">{items.t ? Math.round((100 * items.c) / items.t) : 0}%</div><div class="l">{t("item uji selesai")}</div></div>
          <div class="gauge"><div class="v" style={{ color: over.length ? LAMP.red : undefined }}>{over.length}</div><div class="l">{t("punch lewat target")}</div></div>
        </div>

        <div class="sheet">
          <div class="hd"><h2>{t("Progres per site")}</h2></div>
          {sites.map((s) => {
            const so = ov.filter((o) => o.panel.site_uuid === s.uuid);
            const st = so.reduce((a, o) => ({ OK: a.OK + o.stats.OK, NA: a.NA + o.stats.NA, NG: a.NG + o.stats.NG, p: a.p + o.stats.pending }),
              { OK: 0, NA: 0, NG: 0, p: 0 });
            const op = open.filter((i) => i.site_uuid === s.uuid).length;
            const done = so.filter((o) => o.status === "Lulus" || o.status === "Diterima").length;
            return (
              <button class="site-row line" style={{ display: "block" }} onClick={() => { nav.setSite(s.uuid); nav.tab({ name: "panels" }); }}>
                <div class="row"><span class="nm grow">{s.name}</span>
                  <span class="small muted">{t("{0}/{1} panel lulus", done, so.length)}{op ? <> · <b style={{ color: INK.red }}>{t("{0} punch", op)}</b></> : null}</span></div>
                <Meter parts={[[st.OK, LAMP.green], [st.NA, "#8C9396"], [st.NG, LAMP.red], [st.p, "#E6E9E6"]]} />
              </button>
            );
          })}
        </div>

        <div class="sheet">
          <div class="hd"><h2>{t("Punch perlu tindakan")}</h2><span class="aside">{t("{0} terbuka", open.length)}</span></div>
          <div class="bd">
            {urgent.length === 0 ? <div class="muted small">{t("Semua punch sudah closed.")}</div> :
              urgent.map((i) => <PunchTag i={i} onClick={() => nav.go({ name: "punch", id: i.uuid })} />)}
            {open.length > urgent.length && <button class="btn block sm" onClick={() => nav.tab({ name: "punches" })}>{t("Lihat semua punch")}</button>}
          </div>
        </div>
      </div>
    </>
  );
}

export function ProjectSheet({ onClose }: { onClose: () => void }) {
  const nav = useNav();
  const ps = projects();
  return portal(
    <div class="sheet-modal" onClick={onClose}>
      <div class="panel" onClick={(e) => e.stopPropagation()}>
        <div class="grip" />
        <h2>{t("Project")}</h2>
        {ps.map((p) => (
          <button class="line" onClick={() => { nav.setProject(p.uuid); }}>
            <Lamp color={p.uuid === nav.project ? LAMP.green : LAMP.off} />
            <div class="main"><div class="t">{p.code}</div><div class="s">{p.name}</div></div>
          </button>
        ))}
        <h2 style={{ marginTop: 14 }}>{t("Site / GI")}</h2>
        <button class="line" onClick={() => { nav.setSite(""); onClose(); }}>
          <Lamp color={!nav.site ? LAMP.green : LAMP.off} /><div class="main"><div class="t">{t("Semua site")}</div></div>
        </button>
        {sitesOf(nav.project).map((s: Row) => (
          <button class="line" onClick={() => { nav.setSite(s.uuid); onClose(); }}>
            <Lamp color={nav.site === s.uuid ? LAMP.green : LAMP.off} />
            <div class="main"><div class="t">{s.name}</div>{s.location && <div class="s">{s.location}</div>}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

