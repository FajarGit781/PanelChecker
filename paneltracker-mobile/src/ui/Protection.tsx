// Uji proteksi relay di HP: blok per relay, kartu per fungsi (setting → expected otomatis, actual → OK/NG),
// uji fungsional OK/NG, panduan injeksi sekunder, foto evidence & punch. Data = item checklist biasa (src/relaytest.ts).
import { useState } from "preact/hooks";
import * as R from "../relaytest";
import type { Func, Tol } from "../relaytest";
import { t } from "../i18n";
import { nowLocal, Row } from "../logic";
import { session } from "../session";
import { store } from "../store";
import { renameCheck } from "../sync";
import { evidenceOf } from "../data";
import { Icon, INK, Lamp, STATUS_LAMP, useNav } from "./common";
import { Evidence, punchPreset } from "./Panels";
import { ratioDevices } from "../injection";

// ----------------------------------------------------------------------- tulis data
async function addItems(panelId: string, items: R.ItemDef[], who: string) {
  const mx = Math.max(0, ...store.all("panel_checks").filter((c) => c.panel_uuid === panelId).map((c) => Number(c.sort) || 0));
  let i = 0;
  for (const [section, description, criteria, unit] of items) {
    i++;
    const setup = unit === R.SETUP_UNIT;
    await store.create("panel_checks", {
      panel_uuid: panelId, section, description, criteria, unit, sort: mx + i, value: "", remark: "",
      result: setup ? "OK" : "", checked_by: setup ? who : "", checked_at: setup ? nowLocal() : null,
    });
  }
}

async function setResult(c: Row, res: string, who: string) {
  await store.edit("panel_checks", c.uuid, res ? { result: res, checked_by: who, checked_at: nowLocal() } :
    { result: "", checked_by: "", checked_at: null });
}

async function setActual(c: Row, text: string, e: number | null, tol: number | null, who: string) {
  const v = text.trim();
  const res = R.judge(e, tol, v);
  const ch: Row = { value: v };
  if (res !== (c.result || "")) Object.assign(ch, res ? { result: res, checked_by: who, checked_at: nowLocal() } : { result: "", checked_by: "", checked_at: null });
  await store.edit("panel_checks", c.uuid, ch);
}

/** Ubah kriteria item. Online: PATCH definisi (hasil yang sedang diisi tim di perangkat lain tidak tertimpa; baris yang
 *  belum terkirim tetap _dirty sehingga ikut terkirim). Offline: hanya boleh bila semua baris memang masih menunggu
 *  dikirim dari HP ini. */
async function redefine(defs: [Row, Row][]): Promise<string | null> {
  if (!defs.length) return null;
  if (navigator.onLine && session.api) {
    for (const [c, d] of defs) await renameCheck(session.api, c, d);
    return null;
  }
  if (defs.some(([c]) => !c._dirty)) return t("Ubah setting butuh sinyal (online) supaya hasil tim tidak tertimpa.");
  for (const [c, d] of defs) await store.edit("panel_checks", c.uuid, d);
  return null;
}

/** Simpan setting satu fungsi: kriteria fset + kriteria tiap titik, lalu nilai ulang hasil yang sudah terisi. */
async function saveFunction(f: Func, p: R.Params, tol: Tol, who: string): Promise<string | null> {
  const ex = new Map(R.expected(f.code, p, tol).map(([l, , e, tt]) => [l, [e, tt] as [number | null, number | null]]));
  const defs: [Row, Row][] = [];
  if (f.fset && R.paramsText(p) !== (f.fset.criteria || "")) defs.push([f.fset, { criteria: R.paramsText(p) }]);
  for (const [label, c] of f.points) {
    if (!c.unit) continue;
    const [e, tt] = ex.get(label) || [null, null];
    const cr = R.criteriaText(c.unit, e, tt);
    if (cr !== (c.criteria || "")) defs.push([c, { criteria: cr }]);
  }
  const err = await redefine(defs);
  if (err) return err;
  for (const [label, c0] of f.points) {
    const c = store.get("panel_checks", c0.uuid);
    if (!c || !c.unit || !String(c.value || "").trim()) continue;
    const [e, tt] = ex.get(label) || [null, null];
    await setActual(c, c.value, e, tt, who);
  }
  return null;
}

// ----------------------------------------------------------------------- blok
export function ProtectionBlock({ section, rows, ro, who, panel, byCheck }: {
  section: string; rows: Row[]; ro: boolean; who: string; panel: Row; byCheck: Map<string, Row[]> }) {
  const nav = useNav();
  const [tolOpen, setTolOpen] = useState(false);
  const g = R.group(rows);
  const tests = rows.filter((c) => c.unit !== R.SETUP_UNIT);
  const done = tests.filter((c) => c.result).length, ng = tests.filter((c) => c.result === "NG").length;
  const used = tests.filter((c) => c.result || String(c.value || "").trim()).length + rows.reduce((n, c) => n + evidenceOf(c.uuid).length, 0);

  async function deleteBlock() {
    if (used) { nav.toast(t("Blok ini sudah berisi hasil uji atau foto, tidak bisa dihapus. Kosongkan nilainya dulu bila memang salah buat.")); return; }
    if (!confirm(t("Hapus blok {0}? Semua titik uji di blok ini ikut terhapus.", section))) return;
    for (const c of rows) await store.edit("panel_checks", c.uuid, { deleted: 1 });
    nav.toast(t("Blok uji proteksi dihapus."));
    if (navigator.onLine) session.sync();
  }

  return (
    <div class="inj prot">
      <div class="sec"><h3>{section}</h3>
        <span class={"cnt" + (done === tests.length && tests.length ? " done" : "")}>{done}/{tests.length}{ng ? <span style={{ color: INK.red }}> · {ng} NG</span> : null}</span></div>
      <div class="inj-setup">
        <span>{t("Toleransi: waktu ±{0}% (min {1} ms) · pickup ±{2}%", g.tol.t_pct, g.tol.t_ms, g.tol.p_pct)}</span>
        {!ro && <div class="row" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <button class="btn sm" onClick={() => setTolOpen(true)}><Icon name="edit" size={16} />{t("Toleransi…")}</button>
          {!used && <button class="btn sm danger" onClick={deleteBlock}><Icon name="close" size={16} />{t("Hapus blok")}</button>}
        </div>}
      </div>
      {g.funcs.map((f) => <FuncCard key={f.n + ":" + [f.fset, ...f.points.map((x) => x[1])].map((c) => c?.updated_at || "").join()}
        f={f} tol={g.tol} ro={ro} who={who} panel={panel} byCheck={byCheck} />)}
      {tolOpen && <TolSheet g={g} who={who} onClose={() => setTolOpen(false)} />}
    </div>
  );
}

function PunchLinks({ c, ro, panel, byCheck }: { c: Row; ro: boolean; panel: Row; byCheck: Map<string, Row[]> }) {
  const nav = useNav();
  const ps = byCheck.get(c.uuid) || [];
  const open = ps.filter((i) => i.status !== "Closed");
  return (
    <>
      {ps.map((i) => <button class="punch-chip" onClick={() => nav.go({ name: "punch", id: i.uuid })}><Lamp color={STATUS_LAMP[i.status]} />{i.code}</button>)}
      {!ro && c.result === "NG" && open.length === 0 && <button class="add-punch" onClick={() => nav.go({ name: "punch", preset: punchPreset(panel, c) })}>+ {t("Punch")}</button>}
    </>
  );
}

function ResultButtons({ c, ro, who }: { c: Row; ro: boolean; who: string }) {
  return (
    <div class="push sm">
      {(["OK", "NG", "NA"] as const).map((k) => (
        <button class={k + (c.result === k ? " on" : "")} disabled={ro} aria-pressed={c.result === k}
          onClick={() => setResult(c, c.result === k ? "" : k, who)}>{k === "NA" ? "N/A" : k}</button>
      ))}
    </div>
  );
}

function FuncCard({ f, tol, ro, who, panel, byCheck }: { f: Func; tol: Tol; ro: boolean; who: string; panel: Row; byCheck: Map<string, Row[]> }) {
  const [edit, setEdit] = useState(false);
  const p = R.parseParams(f.fset?.criteria);
  const ok = f.kind === "check" || R.complete(f.code, p);
  const tests = f.points.map(([, c]) => c);
  const nng = tests.filter((c) => c.result === "NG").length, npend = tests.filter((c) => !c.result).length;
  const ex = new Map(R.expected(f.code, p, tol).map(([l, , e, tt]) => [l, [e, tt] as [number | null, number | null]]));
  const first = tests[0];
  const [vals, setVals] = useState<Record<string, string>>(() => Object.fromEntries(tests.map((c) => [c.uuid, String(c.value || "")])));

  async function save(c: Row, label: string) {
    const v = (vals[c.uuid] || "").trim();
    if (ro || v === String(c.value || "")) return;
    const [e, tt] = ex.get(label) || [null, null];
    await setActual(c, v, e, tt, who);
  }

  return (
    <div class={"step inj-pt" + (nng ? " NG" : npend ? "" : " OK")}>
      <div class="inj-ph">
        <div class="grow"><b>F{f.n}</b> <span class="fcode">{f.code}</span> <span>{t(f.name)}</span></div>
        <span class={"pill " + (nng ? "NG" : npend ? "" : "OK")}>{nng ? t("{0} NG", nng) : npend ? t("{0} belum diisi", npend) : t("Lulus")}</span>
      </div>
      {f.kind === "check" ? (
        <div class="prot-check">
          <ResultButtons c={first} ro={ro} who={who} />
          <div class="links"><PunchLinks c={first} ro={ro} panel={panel} byCheck={byCheck} /></div>
        </div>
      ) : (
        <>
          <div class="prot-set">
            {ok ? <span>{settingSummary(f.code, p)}</span> : <span class="warn">{t("Setting belum diisi — expected muncul setelah setting diisi.")}</span>}
            {!ro && <button class="btn sm" onClick={() => setEdit(true)}><Icon name="edit" size={16} />{t("Setting…")}</button>}
          </div>
          {f.fset && ok && (
            <div class="prot-setok"><span class="small muted">{t("Setting di relay sesuai approval?")}</span><ResultButtons c={f.fset} ro={ro} who={who} /></div>
          )}
          <table class="inj-t">
            <thead><tr><th>{t("Titik uji")} · {t("Expected")}</th><th>{t("Actual")}</th><th>{t("Status")}</th></tr></thead>
            <tbody>
              {f.points.map(([label, c]) => {
                if (!c.unit) return (
                  <tr class={"chk " + (c.result || "")} key={c.uuid}>
                    <td colSpan={3}><b>{t(label)}</b> <small class="muted">· {t(c.criteria || "")}</small>
                      <div class="prot-check-row"><ResultButtons c={c} ro={ro} who={who} />
                        <div class="links"><PunchLinks c={c} ro={ro} panel={panel} byCheck={byCheck} /></div></div></td>
                  </tr>
                );
                const [e, tt] = ex.get(label) || [null, null];
                const hint = R.injectHint(f.code, p, label);
                const r = c.result || "";
                return (
                  <tr class={r} key={c.uuid}>
                    <th>{t(label)}
                      <div class="ex">{e === null ? <small>—</small> : <>{R.fmt(e, c.unit)}<small> {c.unit} ±{R.fmt(tt!, c.unit)}</small></>}</div>
                      {hint && <div class="hint">{hint}</div>}</th>
                    <td class="ac"><input inputMode="decimal" value={vals[c.uuid] || ""} readOnly={ro} aria-label={`${t("Actual")} ${label}`}
                      onInput={(ev: any) => setVals({ ...vals, [c.uuid]: ev.currentTarget.value })} onBlur={() => save(c, label)}
                      onKeyDown={(ev: any) => { if (ev.key === "Enter") ev.currentTarget.blur(); }} />
                      <div class="er">{c.unit}</div></td>
                    <td class="st"><span class={"pill " + r}>{r || t("Belum")}</span><PunchLinks c={c} ro={ro} panel={panel} byCheck={byCheck} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
      {first && <Evidence c={first} ro={ro} />}
      {edit && <SettingSheet f={f} p={p} tol={tol} who={who} onClose={() => setEdit(false)} />}
    </div>
  );
}

function settingSummary(code: string, p: R.Params): string {
  return R.PARAMS[R.kindOf(code)].map(([k, lab, u]) => {
    const unit = u === "@" ? R.pickupUnit(code) : u;
    return p[k] ? `${t(lab)} ${p[k]}${unit ? " " + unit : ""}` : "";
  }).filter(Boolean).join(" · ");
}

function SettingSheet({ f, p, tol, who, onClose }: { f: Func; p: R.Params; tol: Tol; who: string; onClose: () => void }) {
  const nav = useNav();
  const [v, setV] = useState<R.Params>(() => ({ ...(R.kindOf(f.code) === "idmt" ? { kurva: "IEC SI" } : {}), ...p }));
  const [busy, setBusy] = useState(false);
  const preview = R.expected(f.code, v, tol);
  async function save() {
    setBusy(true);
    try {
      const err = await saveFunction(f, v, tol, who);
      if (err) { nav.toast(err); return; }
      nav.toast(t("Setting disimpan."));
      if (navigator.onLine) session.sync();
      onClose();
    } catch (e: any) {
      nav.toast(t("Gagal menyimpan: {0}", e?.message || String(e)));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div class="sheet-modal" onClick={onClose}>
      <div class="panel" onClick={(e) => e.stopPropagation()}>
        <div class="grip" /><h2>F{f.n} · {f.code} · {t(f.name)}</h2>
        <div class="inj-form">
          {R.PARAMS[R.kindOf(f.code)].map(([k, lab, u]) => k === "kurva" ? (
            <label class="fld"><span>{t(lab)}</span>
              <select value={v.kurva} onChange={(e: any) => setV({ ...v, kurva: e.currentTarget.value })}>
                {Object.keys(R.CURVES).map((c) => <option value={c}>{c}</option>)}</select></label>
          ) : (
            <label class="fld"><span>{t(lab)}</span>
              <div class="in"><input inputMode="decimal" value={v[k] || ""} onInput={(e: any) => setV({ ...v, [k]: e.currentTarget.value })} />
                <i>{u === "@" ? R.pickupUnit(f.code) : (k === "TMS" && v.kurva === "DT" ? "s" : u)}</i></div></label>
          ))}
          {R.kindOf(f.code) === "dt" && <div class="small muted">{t("Waktu trip boleh kosong bila hanya uji pickup.")}</div>}
          {R.kindOf(f.code) === "idmt" && String(v.kurva).startsWith("IEEE") && <div class="small muted">{t("Kurva IEEE memakai rumus C37.112 dengan TD langsung; cek apakah relay memakai faktor skala TD.")}</div>}
        </div>
        {preview.length > 0 && (
          <div class="inj-prev">
            <div class="small muted">{t("Expected yang akan dipakai:")}</div>
            {preview.map(([l, u, e, tt]) => <div class="inj-prev-r"><b>{t(l)}</b> → {e === null ? "—" : `${R.fmt(e, u)} ${u} ±${R.fmt(tt!, u)}`}</div>)}
          </div>
        )}
        <div class="row" style={{ gap: 8, margin: "10px 16px 0" }}>
          <button class="btn grow" disabled={busy} onClick={onClose}>{t("Batal")}</button>
          <button class="btn primary grow" disabled={busy} onClick={save}>{busy ? t("Menyimpan…") : t("Simpan")}</button>
        </div>
      </div>
    </div>
  );
}

function TolSheet({ g, who, onClose }: { g: ReturnType<typeof R.group>; who: string; onClose: () => void }) {
  const nav = useNav();
  const [v, setV] = useState({ t_pct: String(g.tol.t_pct), t_ms: String(g.tol.t_ms), p_pct: String(g.tol.p_pct) });
  const [busy, setBusy] = useState(false);
  async function save() {
    const tol = { t_pct: R.num(v.t_pct)!, t_ms: R.num(v.t_ms)!, p_pct: R.num(v.p_pct)! };
    if (Object.values(tol).some((x) => x === null || x < 0)) { nav.toast(t("Isi semua angka toleransi.")); return; }
    setBusy(true);
    try {
      if (g.setup) { const err = await redefine([[g.setup, { criteria: R.tolText(tol) }]]); if (err) { nav.toast(err); return; } }
      for (const f of g.funcs) if (f.kind !== "check") {
        const err = await saveFunction(f, R.parseParams(f.fset?.criteria), tol, who);
        if (err) { nav.toast(err); return; }
      }
      nav.toast(t("Toleransi disimpan."));
      onClose();
    } catch (e: any) {
      nav.toast(t("Gagal menyimpan: {0}", e?.message || String(e)));
    } finally {
      setBusy(false);
    }
  }
  const f = (k: keyof typeof v, label: string, u: string) => (
    <label class="fld"><span>{label}</span><div class="in"><input inputMode="decimal" value={v[k]} onInput={(e: any) => setV({ ...v, [k]: e.currentTarget.value })} /><i>{u}</i></div></label>
  );
  return (
    <div class="sheet-modal" onClick={onClose}>
      <div class="panel" onClick={(e) => e.stopPropagation()}>
        <div class="grip" /><h2>{t("Toleransi uji")}</h2>
        <div class="inj-form">
          <div class="two">{f("t_pct", t("Waktu trip ±"), "%")}{f("t_ms", t("minimal"), "ms")}</div>
          {f("p_pct", t("Pickup ±"), "%")}
          <div class="small muted">{t("Standar IEC 60255-151: waktu ±5% atau ±40 ms (ambil yang lebih besar), pickup ±5%.")}</div>
        </div>
        <div class="row" style={{ gap: 8, margin: "10px 16px 0" }}>
          <button class="btn grow" disabled={busy} onClick={onClose}>{t("Batal")}</button>
          <button class="btn primary grow" disabled={busy} onClick={save}>{busy ? t("Menyimpan…") : t("Simpan")}</button>
        </div>
      </div>
    </div>
  );
}

export function CreateProtection({ panel, checks, who, onClose }: { panel: Row; checks: Row[]; who: string; onClose: () => void }) {
  const nav = useNav();
  const devs = ratioDevices(checks).filter((d) => !/C264|PM8240/.test(d));
  const [dev, setDev] = useState(devs[0] || "");
  const [sel, setSel] = useState<string[]>(() => R.presetFor(devs[0] || ""));
  function pickDev(d: string) {
    setDev(d);
    setSel(R.presetFor(d));
  }
  const all = [...sel, ...Object.keys(R.FUNCS).filter((c) => !sel.includes(c))];
  async function save() {
    if (!dev.trim()) { nav.toast(t("Isi nama device / alat baca.")); return; }
    if (!sel.length) { nav.toast(t("Pilih minimal satu fungsi.")); return; }
    const secs = checks.map((c) => c.section || "");
    if (secs.some((x) => R.isProtectionSection(x) && R.deviceOf(x) === dev.trim()) &&
      !confirm(t("Panel ini sudah punya uji proteksi untuk {0}. Buat blok kedua?", dev.trim()))) return;
    const order = Object.keys(R.FUNCS);
    const codes = [...sel].sort((a, b) => {
      const pa = R.presetFor(dev).indexOf(a), pb = R.presetFor(dev).indexOf(b);
      return (pa < 0 ? 100 + order.indexOf(a) : pa) - (pb < 0 ? 100 + order.indexOf(b) : pb);
    });
    await addItems(panel.uuid, R.blockItems(dev.trim(), R.nextLetter(secs), codes), who);
    nav.toast(t("Uji proteksi dibuat ({0} fungsi).", codes.length));
    if (navigator.onLine) session.sync();
    onClose();
  }
  return (
    <div class="sheet-modal" onClick={onClose}>
      <div class="panel" onClick={(e) => e.stopPropagation()}>
        <div class="grip" /><h2>{t("Uji proteksi relay baru")}</h2>
        <div class="inj-form">
          <label class="fld"><span>{t("Relay")}</span>
            <input list="prot-devs" value={dev} onInput={(e: any) => pickDev(e.currentTarget.value)} />
            <datalist id="prot-devs">{devs.map((d) => <option value={d} />)}</datalist></label>
          <div class="small muted">{t("Fungsi tercentang otomatis sesuai model relay. Setting bisa diisi nanti; uji fungsional bisa langsung diisi OK/NG.")}</div>
        </div>
        <div class="prot-funcs">
          {all.map((c) => (
            <label class="line inj-rv" key={c}>
              <input type="checkbox" checked={sel.includes(c)} onChange={(e: any) => setSel(e.currentTarget.checked ? [...sel, c] : sel.filter((x) => x !== c))} />
              <div class="main"><div class="t"><span class="fcode">{c}</span> {t(R.funcName(c))}</div></div>
            </label>
          ))}
        </div>
        <div class="row" style={{ gap: 8, margin: "10px 16px 0" }}>
          <button class="btn grow" onClick={onClose}>{t("Batal")}</button>
          <button class="btn primary grow" onClick={save}>{t("Buat ({0} fungsi)", sel.length)}</button>
        </div>
      </div>
    </div>
  );
}
