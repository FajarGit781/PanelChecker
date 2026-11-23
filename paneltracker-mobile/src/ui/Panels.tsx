import { useEffect, useState } from "preact/hooks";
import { checksOf, issuesOf, panelOverview, sitesOf } from "../data";
import { t } from "../i18n";
import { checkStats, nowLocal, panelStatus, Row, today } from "../logic";
import { store } from "../store";
import { ipWarning, isSasSection, nextResult, SAS_COLS, SasDevice, sasMatrix } from "../sas";
import { projectCrumbs } from "./Home";
import { Icon, Lamp, LAMP, Meter, PANEL_LAMP, Plate, SearchBox, STATUS_LAMP, TopBar, useNav, useSession, useStore, INK } from "./common";

const FILTERS = ["Semua", "Ada temuan", "Sedang dicek", "Belum dicek", "Lulus", "Diterima"];

/** Daftar panel ditampilkan seperti deretan kubikel di ruang relay, dikelompokkan per site. */
export function Panels() {
  useStore();
  const nav = useNav();
  const [q, setQ] = useState("");
  const [f, setF] = useState("Semua");
  const pr = store.get("projects", nav.project);
  const ov = pr ? panelOverview(nav.project, nav.site) : [];
  const ql = q.trim().toLowerCase();
  const list = ov.filter((o) => (f === "Semua" || o.status === f) &&
    (!ql || [o.panel.tag, o.panel.name, o.panel.bay, o.panel.site_name].some((x) => String(x || "").toLowerCase().includes(ql))));
  const count = (x: string) => x === "Semua" ? ov.length : ov.filter((o) => o.status === x).length;
  const sites = sitesOf(nav.project).filter((s) => list.some((o) => o.panel.site_uuid === s.uuid));
  return (
    <>
      <TopBar title={t("Panel")} crumbs={projectCrumbs(nav)}
        right={<button class="icon-btn" aria-label={t("Pilih project / site")} onClick={nav.pickProject}><Icon name="down" /></button>} />
      <div class="content">
        <SearchBox value={q} onInput={setQ} placeholder={t("Cari tag, bay, nama panel")} />
        <div class="chips">{FILTERS.map((x) => (
          <button class={"chip" + (f === x ? " on" : "")} onClick={() => setF(x)}>
            {x !== "Semua" && <Lamp color={PANEL_LAMP[x]} />}{t(x)} <span class="n">{count(x)}</span>
          </button>))}
        </div>
        {list.length === 0 && <div class="empty"><b>{t("Tidak ada panel")}</b>{q || f !== "Semua" ? t("Ubah pencarian atau filter.") : t("Panel ditambahkan dari aplikasi laptop.")}</div>}
        {sites.map((s) => {
          const items = list.filter((o) => o.panel.site_uuid === s.uuid);
          return (
            <div key={s.uuid}>
              <div class="bay-head"><h3>{s.name}</h3><span class="aside">{t("{0} panel", items.length)}</span></div>
              <div class="lineup">
                {items.map((o) => (
                  <button class={"cubicle" + (o.status === "Diterima" ? " accepted" : "")} aria-label={o.panel.tag}
                    onClick={() => nav.go({ name: "panel", id: o.panel.uuid })}>
                    <div class="lamps"><Lamp color={PANEL_LAMP[o.status]} />{o.punch.open > 0 && <Lamp color={LAMP.amber} />}</div>
                    <Plate tag={o.panel.tag} small />
                    <div class="bay">{o.panel.bay || o.panel.name || "-"}</div>
                    <div class="lvl">
                      <i style={{ width: `${o.stats.total ? (100 * o.stats.OK) / o.stats.total : 0}%`, background: LAMP.green }} />
                      <i style={{ width: `${o.stats.total ? (100 * o.stats.NA) / o.stats.total : 0}%`, background: "#8C9396" }} />
                      <i style={{ width: `${o.stats.total ? (100 * o.stats.NG) / o.stats.total : 0}%`, background: LAMP.red }} />
                    </div>
                    <div class="foot"><span>{o.stats.total ? `${Math.round(o.stats.pct)}%` : t("tanpa cek")}</span>
                      {o.punch.open > 0 && <b>{t("{0} punch", o.punch.open)}</b>}{o.status === "Diterima" && <span style={{ color: "#1F5C4A" }}>{t("Diterima")}</span>}</div>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
        {list.length > 0 && (
          <div class="legend">
            <span><Lamp color={LAMP.red} />{t("Ada temuan")}</span><span><Lamp color={LAMP.amber} />{t("Sedang dicek / ada punch")}</span>
            <span><Lamp color={LAMP.green} />{t("Lulus / diterima")}</span><span><Lamp color={LAMP.off} />{t("Belum dicek")}</span>
          </div>
        )}
      </div>
    </>
  );
}

// ======================================================================= detail panel = lembar uji
const CFILTERS = ["Semua", "Belum dicek", "NG", "Ada catatan"];
const VIEW_KEY = "pt.sasView";

export function PanelDetail({ id }: { id: string }) {
  useStore();
  const s = useSession();
  const nav = useNav();
  const [f, setF] = useState("Semua");
  useEffect(() => { localStorage.setItem("pt.lastPanel", id); }, [id]);
  const p = store.get("panels", id);
  if (!p) return <><TopBar title={t("Panel")} back /><div class="content"><div class="empty"><b>{t("Panel tidak ditemukan")}</b></div></div></>;
  const site = store.get("sites", p.site_uuid);
  const checks = checksOf(id);
  const st = checkStats(checks);
  const punches = issuesOf(site?.project_uuid || nav.project).filter((i) => i.panel_uuid === id);
  const byCheck = new Map<string, Row[]>();
  for (const i of punches) if (i.check_uuid) byCheck.set(i.check_uuid, [...(byCheck.get(i.check_uuid) || []), i]);
  const open = punches.filter((i) => i.status !== "Closed").length;
  const status = panelStatus(p, st, { open, total: punches.length, Critical: 0, overdue: 0 });
  const sas = sasMatrix(checks);
  const [view, setViewState] = useState<string>(() => localStorage.getItem(VIEW_KEY) || "matrix");
  const setView = (v: string) => { localStorage.setItem(VIEW_KEY, v); setViewState(v); };
  const matrix = sas.length > 0 && view === "matrix";
  const inMatrix = new Set<string>();
  if (matrix) for (const d of sas) for (const c of Object.values(d.cells)) if (c) inMatrix.add(c.uuid);
  const numbered = checks.map((c, k) => ({ c, no: k + 1 }));
  const shown = numbered.filter(({ c }) => !inMatrix.has(c.uuid)).filter(({ c }) => f === "Semua" || (f === "Belum dicek" && !c.result) || (f === "NG" && c.result === "NG") ||
    (f === "Ada catatan" && (c.remark || c.value)));
  const sections: [string, { c: Row; no: number }[]][] = [];
  for (const x of shown) {
    const last = sections[sections.length - 1];
    if (last && last[0] === (x.c.section || "")) last[1].push(x);
    else sections.push([x.c.section || "", [x]]);
  }
  const ro = s.readOnly;
  const who = s.info?.full_name || (s.info?.email || "").split("@")[0];
  const fcount = (x: string) => x === "Semua" ? checks.length : x === "Belum dicek" ? st.pending : x === "NG" ? st.NG :
    checks.filter((c) => c.remark || c.value).length;

  async function setResult(c: Row, v: string) {
    if (ro) return;
    const val = c.result === v ? "" : v;
    await store.edit("panel_checks", c.uuid, val ? { result: val, checked_by: who, checked_at: nowLocal() } :
      { result: "", checked_by: "", checked_at: null });
    if (val === "NG" && !(byCheck.get(c.uuid) || []).some((i) => i.status !== "Closed")) {
      nav.toast(t("Item NG dicatat. Lengkapi punch untuk temuan ini."));
      nav.go({ name: "punch", preset: punchPreset(p!, c) });
    }
  }

  async function markRestOk() {
    const rest = checks.filter((c) => !c.result);
    if (!rest.length || !confirm(t("Tandai {0} item yang belum dicek sebagai OK?", rest.length))) return;
    for (const c of rest) await store.edit("panel_checks", c.uuid, { result: "OK", checked_by: who, checked_at: nowLocal() });
    nav.toast(t("{0} item ditandai OK.", rest.length));
  }

  async function accept() {
    const dirty = st.pending || st.NG || open;
    if (!confirm(dirty ? t("Panel belum bersih: {0} belum dicek, {1} NG, {2} punch terbuka. Tetap terima panel?", st.pending, st.NG, open)
      : t("Terima panel {0}?", p!.tag))) return;
    await store.edit("panels", id, { accepted_by: who, accepted_at: today() });
    nav.toast(t("Panel {0} diterima.", p!.tag));
  }

  return (
    <>
      <TopBar title={p.tag} crumbs={[site?.name || "", p.bay || ""]} back />
      <div class="content">
        <div class="panel-hero">
          <Plate tag={p.tag} name={p.name || ""} />
          <dl class="facts">
            <div><dt>{t("Status")}</dt><dd class="row" style={{ gap: 6 }}><Lamp color={PANEL_LAMP[status]} />{t(status)}</dd></div>
            <div><dt>{t("Tipe")}</dt><dd>{p.panel_type || "-"}</dd></div>
            <div><dt>{t("Vendor")}</dt><dd>{p.vendor || "-"}</dd></div>
            <div><dt>{t("Serial number")}</dt><dd>{p.serial_no || "-"}</dd></div>
          </dl>
          <Meter parts={[[st.OK, LAMP.green], [st.NA, "#8C9396"], [st.NG, LAMP.red], [st.pending, "#E6E9E6"]]} />
          <div class="tally">
            <span>{st.checked}/{st.total} {t("diuji")}</span>
            <span style={{ color: INK.green }}>{st.OK} OK</span>
            <span style={{ color: INK.red }}>{st.NG} NG</span>
            <span class="muted">{st.NA} N/A</span>
          </div>
          {p.accepted_at && <div class="msg ok" style={{ margin: "10px 0 0" }}>{t("Diterima oleh {0} pada {1}", p.accepted_by || "-", p.accepted_at)}</div>}
          <div class="acts">
            <button class="btn sm" onClick={() => nav.go({ name: "punches", panel: id })}>
              <Lamp color={open ? LAMP.red : LAMP.off} />{t("Punch panel")} ({open}/{punches.length})</button>
            {!ro && <button class="btn sm primary" onClick={() => nav.go({ name: "punch", preset: { panel_uuid: id } })}><Icon name="plus" size={18} />{t("Punch")}</button>}
            {!ro && st.pending > 0 && <button class="btn sm" onClick={markRestOk}>{t("Sisa item OK")}</button>}
            {!ro && !p.accepted_at && st.total > 0 && <button class="btn sm dark" onClick={accept}><Icon name="shield" size={18} />{t("Terima panel")}</button>}
          </div>
        </div>

        {sas.length > 0 && (
          <div class="seg" role="tablist">
            <button class={matrix ? "on" : ""} aria-selected={matrix} onClick={() => setView("matrix")}>{t("Matriks SAS")}</button>
            <button class={!matrix ? "on" : ""} aria-selected={!matrix} onClick={() => setView("list")}>{t("Daftar")}</button>
          </div>
        )}
        {matrix && <SasMatrix devices={sas} ro={ro} who={who} panel={p} byCheck={byCheck} />}
        <div class="chips">{CFILTERS.map((x) => <button class={"chip" + (f === x ? " on" : "")} onClick={() => setF(x)}>{t(x)} <span class="n">{fcount(x)}</span></button>)}</div>
        {checks.length === 0 && <div class="empty"><b>{t("Belum ada checklist")}</b>{t("Terapkan template checklist ke panel ini dari aplikasi laptop.")}</div>}
        {checks.length > 0 && shown.length === 0 && <div class="empty"><b>{t("Tidak ada item")}</b>{t("Tidak ada item untuk filter ini.")}</div>}
        {sections.map(([sec, rows]) => {
          const all = checks.filter((c) => (c.section || "") === sec);
          const ss = checkStats(all);
          return (
            <div key={sec}>
              <div class="sec"><h3>{sec || t("Umum")}</h3>
                <span class={"cnt" + (ss.pending === 0 ? " done" : "")}>{ss.checked}/{ss.total}{ss.NG ? <span style={{ color: INK.red }}> · {ss.NG} NG</span> : null}</span></div>
              {rows.map(({ c, no }) => <Step key={c.uuid + c.updated_at} c={c} no={no} ro={ro} punches={byCheck.get(c.uuid) || []}
                onResult={setResult} panel={p!} />)}
            </div>
          );
        })}
      </div>
    </>
  );
}

// ======================================================================= matriks SAS
function usedIps(panelId: string): Map<string, Map<string, string>> {
  // ip → (uuid item → "tag · device") untuk deteksi IP dobel antar device / panel
  const out = new Map<string, Map<string, string>>();
  for (const c of store.all("panel_checks")) {
    if (c.deleted || !c.value || !isSasSection(c.section) || !/^ip address/i.test(c.description || "")) continue;
    const p = store.get("panels", c.panel_uuid);
    if (!p || p.deleted) continue;
    const who = (p.uuid === panelId ? "" : `${String(p.tag).replace(/\s+/g, " ")} · `) + String(c.section).replace(/^[A-Z]{1,2}\. SAS · /, "");
    const ip = String(c.value).trim();
    if (!out.has(ip)) out.set(ip, new Map());
    out.get(ip)!.set(c.uuid, who);
  }
  return out;
}

const MARK: Record<string, string> = { OK: "✓", NG: "✗", NA: "N/A" };

function SasMatrix({ devices, ro, who, panel, byCheck }: { devices: SasDevice[]; ro: boolean; who: string; panel: Row;
  byCheck: Map<string, Row[]> }) {
  const nav = useNav();
  const ips = usedIps(panel.uuid);
  const set = async (c: Row, result: string) => {
    if (ro) return;
    await store.edit("panel_checks", c.uuid, result ? { result, checked_by: who, checked_at: nowLocal() } :
      { result: "", checked_by: "", checked_at: null });
  };
  const allOk = async (d: SasDevice) => {
    for (const c of Object.values(d.cells)) if (c && !c.result) await set(c, "OK");
  };
  const total = devices.reduce((n, d) => n + Object.keys(d.cells).length, 0);
  const done = devices.reduce((n, d) => n + Object.values(d.cells).filter((c) => c && c.result).length, 0);
  const ng = devices.reduce((n, d) => n + Object.values(d.cells).filter((c) => c && c.result === "NG").length, 0);
  return (
    <div class="mx-wrap">
      <div class="sec"><h3>{t("Integrasi SAS")}</h3>
        <span class={"cnt" + (done === total ? " done" : "")}>{done}/{total}{ng ? <span style={{ color: INK.red }}> · {ng} NG</span> : null}</span></div>
      <div class="mx-scroll">
        <table class="mx">
          <thead><tr>{SAS_COLS.map((k) => <th class={k.key}>{t(k.label)}</th>)}</tr></thead>
          <tbody>
            {devices.map((d) => {
              const ngNoPunch = Object.values(d.cells).find((c) => c && c.result === "NG" &&
                !(byCheck.get(c.uuid) || []).some((i) => i.status !== "Closed"));
              const pending = Object.values(d.cells).some((c) => c && !c.result);
              const cnt = Object.values(d.cells).filter((c) => c && c.result).length;
              return [
                <tr class="devrow" key={d.section + ":h"}>
                  <th colSpan={SAS_COLS.length}>
                    <span class="n">{d.name}</span>
                    <span class="dc">{cnt}/{Object.keys(d.cells).length}</span>
                    {!ro && ngNoPunch && <button class="mini red" onClick={() => nav.go({ name: "punch", preset: punchPreset(panel, ngNoPunch) })}>+ {t("Punch")}</button>}
                    {!ro && pending && <button class="mini" onClick={() => allOk(d)}>{t("Semua OK")}</button>}
                  </th>
                </tr>,
                <tr key={d.section}>
                  {SAS_COLS.map((k) => {
                    const c = d.cells[k.key];
                    if (!c) return <td class="na-cell">—</td>;
                    if (k.key === "ip") return <IpCell key={c.uuid + c.updated_at} c={c} ro={ro} ips={ips} onSet={set} />;
                    return (
                      <td><button class={"mx-c " + (c.result || "")} disabled={ro} aria-label={`${d.name} ${k.label}: ${c.result || t("belum")}`}
                        title={c.checked_by ? t("Dicek {0}, {1}", c.checked_by, String(c.checked_at || "").slice(0, 10)) : ""}
                        onClick={() => set(c, nextResult(c.result))}>{MARK[c.result] || "·"}</button></td>
                    );
                  })}
                </tr>,
              ];
            })}
          </tbody>
        </table>
      </div>
      <div class="mx-hint">{t("Tap sel: kosong → ✓ OK → ✗ NG → N/A. Ketik IP langsung; item IP otomatis OK bila IP valid & tidak dobel.")}</div>
    </div>
  );
}

function IpCell({ c, ro, ips, onSet }: { c: Row; ro: boolean; ips: Map<string, Map<string, string>>;
  onSet: (c: Row, r: string) => Promise<void> }) {
  const [v, setV] = useState<string>(c.value || "");
  const others = new Map<string, string>();
  for (const [ip, m] of ips) for (const [uuid, who] of m) if (uuid !== c.uuid) others.set(ip, who);
  const warn = ipWarning(v, c.criteria || "", others);
  const save = async () => {
    const val = v.trim();
    if (ro || val === (c.value || "")) return;
    await store.edit("panel_checks", c.uuid, { value: val });
    // otomatis OK hanya kalau IP valid, di subnet bay, dan tidak dobel; kalau bermasalah, biarkan teknisi memutuskan
    if (val && !c.result && !ipWarning(val, c.criteria || "", others)) await onSet({ ...c, value: val }, "OK");
  };
  return (
    <td class="ip">
      <div class="ipbox">
        <input inputMode="decimal" placeholder={(c.criteria || "").replace(/^Subnet /, "")} value={v} readOnly={ro}
          class={warn ? "bad" : ""} onInput={(e: any) => setV(e.currentTarget.value)} onBlur={save}
          onKeyDown={(e: any) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
        <button class={"mx-c sm " + (c.result || "")} disabled={ro} onClick={() => onSet(c, nextResult(c.result))}>{MARK[c.result] || "·"}</button>
      </div>
      {warn && <div class="ipwarn">{t(warn)}</div>}
    </td>
  );
}

export function punchPreset(p: Row, c: Row): Record<string, any> {
  let desc = t("Item cek: {0} — {1}.", c.section || "", c.description || "");
  if (c.criteria) desc += "\n" + t("Kriteria: {0} {1}", c.criteria, c.unit || "").trim();
  if (c.value) desc += "\n" + t("Hasil ukur: {0} {1}", c.value, c.unit || "").trim();
  if (c.remark) desc += "\n" + t("Catatan: {0}", c.remark);
  return { panel_uuid: p.uuid, check_uuid: c.uuid, title: `${c.description} — ${t("tidak sesuai")}`, description: desc, severity: "Major" };
}

function Step({ c, no, ro, punches, onResult, panel }: { c: Row; no: number; ro: boolean; punches: Row[]; panel: Row;
  onResult: (c: Row, v: string) => void }) {
  const nav = useNav();
  const [remark, setRemark] = useState<string>(c.remark || "");
  const [value, setValue] = useState<string>(c.value || "");
  const save = async (k: string, v: string) => {
    if (ro || (c[k] || "") === v.trim()) return;
    await store.edit("panel_checks", c.uuid, { [k]: v.trim() });
  };
  const open = punches.filter((i) => i.status !== "Closed");
  const showNotes = !ro || c.value || c.remark;
  return (
    <div class={"step " + (c.result || "")}>
      <div class="top">
        <div class="no">{no}</div>
        <div class="grow">
          <div class="d">{c.description}</div>
          {c.criteria && <div class="crit">{t("Kriteria")}: <b>{c.criteria}{c.unit ? ` ${c.unit}` : ""}</b></div>}
          {c.checked_by && <div class="by">{t("Dicek {0}, {1}", c.checked_by, String(c.checked_at || "").slice(0, 10))}</div>}
        </div>
      </div>
      <div class="push">
        {(["OK", "NG", "NA"] as const).map((k) => (
          <button class={k + (c.result === k ? " on" : "")} disabled={ro} aria-pressed={c.result === k} onClick={() => onResult(c, k)}>
            {k === "NA" ? "N/A" : k}</button>
        ))}
      </div>
      {showNotes && (
        <div class="notes">
          {(c.unit || c.value) && <input class="val" inputMode={c.unit === "rasio" ? "text" : "decimal"} placeholder={c.unit ? t("Nilai ({0})", c.unit) : t("Nilai")} value={value} readOnly={ro}
            onInput={(e: any) => setValue(e.currentTarget.value)} onBlur={() => save("value", value)} />}
          <input placeholder={ro ? "" : t("Catatan")} value={remark} readOnly={ro}
            onInput={(e: any) => setRemark(e.currentTarget.value)} onBlur={() => save("remark", remark)} />
        </div>
      )}
      {(punches.length > 0 || (!ro && c.result === "NG" && open.length === 0)) && (
        <div class="links">
          {punches.map((i) => (
            <button class="punch-chip" onClick={() => nav.go({ name: "punch", id: i.uuid })}>
              <Lamp color={STATUS_LAMP[i.status]} />{i.code}</button>
          ))}
          {!ro && c.result === "NG" && open.length === 0 && (
            <button class="add-punch" onClick={() => nav.go({ name: "punch", preset: punchPreset(panel, c) })}>+ {t("Buat punch")}</button>
          )}
        </div>
      )}
    </div>
  );
}
