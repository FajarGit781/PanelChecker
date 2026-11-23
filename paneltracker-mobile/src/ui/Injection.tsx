// Uji injeksi sekunder CT/VT di HP: blok tabel per titik uji, actual → OK/NG otomatis, baca foto layar HMI (OCR di HP).
// Data = item checklist biasa (lihat src/injection.ts), sama dengan aplikasi laptop.
import { useRef, useState } from "preact/hooks";
import * as I from "../injection";
import type { Key, PointGroup, Setup } from "../injection";
import { resizeImage } from "../image";
import { t } from "../i18n";
import { nowLocal, Row } from "../logic";
import { session } from "../session";
import { store } from "../store";
import { renameCheck } from "../sync";
import { Icon, INK, Lamp, STATUS_LAMP, useNav } from "./common";
import { Evidence, punchPreset } from "./Panels";

const keyLabel = (k: Key) => (k === "f" ? t("Frekuensi") : k);
const unitLabel = (k: Key) => (k === "PF" ? "" : I.UNIT[k]);

// ----------------------------------------------------------------------- tulis data
async function addItems(panelId: string, items: I.ItemDef[], who: string) {
  const mx = Math.max(0, ...store.all("panel_checks").filter((c) => c.panel_uuid === panelId).map((c) => Number(c.sort) || 0));
  let i = 0;
  for (const [section, description, criteria, unit] of items) {
    i++;
    const setup = unit === I.SETUP_UNIT;   // item setup langsung OK (rasio sudah dikonfigurasi)
    await store.create("panel_checks", {
      panel_uuid: panelId, section, description, criteria, unit, sort: mx + i, value: "", remark: "",
      result: setup ? "OK" : "", checked_by: setup ? who : "", checked_at: setup ? nowLocal() : null,
    });
  }
}

async function setActual(c: Row, text: string, exp: number, tol: number, who: string) {
  const v = text.trim();
  const res = I.judge(exp, tol, v);
  const ch: Row = { value: v };
  if (res !== (c.result || "")) Object.assign(ch, res ? { result: res, checked_by: who, checked_at: nowLocal() } : { result: "", checked_by: "", checked_at: null });
  await store.edit("panel_checks", c.uuid, ch);
}

// ----------------------------------------------------------------------- blok
export function InjectionBlock({ section, rows, ro, who, panel, byCheck }: {
  section: string; rows: Row[]; ro: boolean; who: string; panel: Row; byCheck: Map<string, Row[]> }) {
  const nav = useNav();
  const [sheet, setSheet] = useState<"" | "setup" | "point">("");
  const g = I.group(rows);
  const s = g.setup ? I.parseSetup(g.setup.criteria) : null;
  const all = g.points.flatMap((p) => Object.values(p.rows)) as Row[];
  const done = all.filter((c) => c.result).length, ng = all.filter((c) => c.result === "NG").length;

  async function deletePoint(p: PointGroup) {
    const rs = Object.values(p.rows) as Row[];
    if (rs.some((c) => c.result || String(c.value || "").trim())) {
      nav.toast(t("T{0} sudah berisi hasil uji, tidak bisa dihapus. Kosongkan nilainya dulu bila memang salah buat.", p.n));
      return;
    }
    if (!confirm(t("Hapus titik uji T{0}?", p.n))) return;
    for (const c of rs) await store.edit("panel_checks", c.uuid, { deleted: 1 });
  }

  return (
    <div class="inj">
      <div class="sec"><h3>{section}</h3>
        <span class={"cnt" + (done === all.length && all.length ? " done" : "")}>{done}/{all.length}{ng ? <span style={{ color: INK.red }}> · {ng} NG</span> : null}</span></div>
      <div class="inj-setup">
        {s ? <span>{t("CT {0}/{1} A · VT {2} kV/{3} V · toleransi {4}% (P, Q terhadap S) · PF ±{5} · f ±{6} Hz",
          I.g(s.ct_p), I.g(s.ct_s), I.g(s.vt_p), I.g(s.vt_s), I.g(s.tol), I.g(s.tol_pf), I.g(s.tol_f))}</span>
          : <span style={{ color: INK.red }}>{t("Setup rasio CT/VT belum terbaca. Klik Setup… untuk mengisi rasio; sementara expected diambil dari kriteria item.")}</span>}
        {!ro && <div class="row" style={{ gap: 8, marginTop: 8 }}>
          <button class="btn sm" onClick={() => setSheet("setup")}><Icon name="edit" size={16} />{t("Setup…")}</button>
          <button class="btn sm" disabled={!s} onClick={() => setSheet("point")}><Icon name="plus" size={16} />{t("Titik uji")}</button>
        </div>}
      </div>
      {g.points.map((p) => <PointCard key={p.n + ":" + Object.values(p.rows).map((c) => c!.updated_at).join()} p={p} s={s}
        ro={ro} who={who} panel={panel} byCheck={byCheck} onDelete={() => deletePoint(p)} />)}
      {g.points.length === 0 && <div class="empty small">{t("Belum ada titik uji. Klik + Titik uji.")}</div>}
      {sheet === "setup" && <SetupSheet g={g} s={s || I.DEFAULT_SETUP} section={section} panel={panel} who={who} onClose={() => setSheet("")} />}
      {sheet === "point" && s && <PointSheet g={g} s={s} section={section} panel={panel} who={who} onClose={() => setSheet("")} />}
    </div>
  );
}

function PointCard({ p, s, ro, who, panel, byCheck, onDelete }: { p: PointGroup; s: Setup | null; ro: boolean; who: string;
  panel: Row; byCheck: Map<string, Row[]>; onDelete: () => void }) {
  const nav = useNav();
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(p.rows).map(([k, c]) => [k, String(c!.value || "")])));
  const [ocr, setOcr] = useState<{ stage: string; pct: number } | null>(null);
  const [review, setReview] = useState<{ found: Partial<Record<Key, I.OcrHit>>; raw: string; url: string } | null>(null);
  const cam = useRef<HTMLInputElement>(null);
  const gal = useRef<HTMLInputElement>(null);
  const keys = I.KEYS.filter((k) => p.rows[k]);
  const res = keys.map((k) => p.rows[k]!.result || "");
  const nng = res.filter((r) => r === "NG").length, npend = res.filter((r) => !r).length;
  const first = (p.rows.IA || p.rows[keys[0]])!;
  const exp = (k: Key) => I.expOf(s, p, k, p.rows[k]!);
  const sec = s ? I.secondary(s, p) : null;

  async function save(k: Key) {
    const c = p.rows[k]!;
    if (ro || (vals[k] || "").trim() === String(c.value || "")) return;
    const [e, tol] = exp(k);
    await setActual(c, vals[k] || "", e, tol, who);
  }

  async function onPhoto(ev: any) {
    const file: File | undefined = ev.currentTarget.files?.[0];
    ev.currentTarget.value = "";
    if (!file) return;
    try {   // simpan sebagai foto evidence titik ini
      const blob = await resizeImage(file);
      const att = await store.create("attachments", { check_uuid: first.uuid, issue_uuid: null, kind: "evidence",
        filename: `hmi_T${p.n}_${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}.jpg`, caption: t("Foto HMI T{0}", p.n), storage_path: null });
      await store.setPhoto(att.uuid, blob);
    } catch { /* foto evidence gagal disimpan tidak menggagalkan baca nilai */ }
    setOcr({ stage: t("Menyiapkan OCR"), pct: 0 });
    try {
      const { recognize } = await import("../ocr");
      const raw = await recognize(file, (stage, pct) => setOcr({ stage: stage ? t(stage) : "", pct }));
      setReview({ found: I.parseHmi(raw), raw, url: URL.createObjectURL(file) });
    } catch {
      nav.toast(t("Mesin OCR gagal berjalan. Isi nilai secara manual."));
    } finally {
      setOcr(null);
    }
  }

  async function apply(sel: Partial<Record<Key, number>>) {
    let n = 0;
    const next = { ...vals };
    for (const k of keys) {
      if (sel[k] === undefined) continue;
      const text = I.valueText(k, sel[k]!);
      const [e, tol] = exp(k);
      await setActual(p.rows[k]!, text, e, tol, who);
      next[k] = text;
      n++;
    }
    setVals(next);
    if (review) URL.revokeObjectURL(review.url);
    setReview(null);
    nav.toast(t("{0} nilai dimasukkan dari foto", n));
    if (navigator.onLine) session.sync();
  }

  return (
    <div class={"step inj-pt" + (nng ? " NG" : npend ? "" : " OK")}>
      <div class="inj-ph">
        <div class="grow">
          <b>T{p.n}</b> <span>{t("I {0}% · V {1}% · φ {2}° · {3} Hz", I.g(p.pi), I.g(p.pv), I.g(p.phi), I.g(p.hz))}</span>
          {sec && <div class="small muted">{t("Injeksi: {0} A ∠{1}° · {2} V L-N · {3} Hz", sec.i.toFixed(3), I.g(-p.phi), sec.v_ln.toFixed(2), I.g(p.hz))}</div>}
        </div>
        <span class={"pill " + (nng ? "NG" : npend ? "" : "OK")}>{nng ? t("{0} NG", nng) : npend ? t("{0} belum diisi", npend) : t("Lulus")}</span>
        {!ro && <button class="inj-del" aria-label={t("Hapus titik uji T{0}", p.n)} onClick={onDelete}><Icon name="close" size={16} /></button>}
      </div>
      {!ro && (
        <div class="inj-ocr">
          <button class="btn sm primary grow" disabled={!!ocr} onClick={() => cam.current?.click()}><Icon name="camera" size={18} />{t("Foto HMI → isi Actual")}</button>
          <button class="btn sm" disabled={!!ocr} aria-label={t("Pilih dari galeri")} onClick={() => gal.current?.click()}><Icon name="image" size={18} /></button>
          <input ref={cam} type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={onPhoto} />
          <input ref={gal} type="file" accept="image/*" style={{ display: "none" }} onChange={onPhoto} />
        </div>
      )}
      {ocr && <div class="msg warn" role="status" style={{ margin: "0 12px 10px" }}>{t("Membaca foto…")} {ocr.stage} {ocr.pct ? `${ocr.pct}%` : ""}
        <div class="small">{t("Diproses di HP ini, gratis, foto tidak dikirim ke mana pun. Pertama kali ±10 detik untuk memuat mesin OCR.")}</div></div>}
      <table class="inj-t">
        <thead><tr><th>{t("Besaran")} · {t("Expected")}</th><th>{t("Actual")}</th><th>{t("Status")}</th></tr></thead>
        <tbody>
          {keys.map((k) => {
            const c = p.rows[k]!;
            const [e, tol] = exp(k);
            const r = c.result || "";
            const ps = byCheck.get(c.uuid) || [];
            const openP = ps.filter((i) => i.status !== "Closed");
            return (
              <tr class={r} key={k}>
                <th>{keyLabel(k)}<div class="ex">{I.fmt(e, I.DEC[k])}<small> {unitLabel(k)} ±{I.fmt(tol, I.DEC[k])}</small></div></th>
                <td class="ac"><input inputMode="decimal" value={vals[k] || ""} readOnly={ro} aria-label={t("Actual {0}", keyLabel(k))}
                  onInput={(ev: any) => setVals({ ...vals, [k]: ev.currentTarget.value })} onBlur={() => save(k)}
                  onKeyDown={(ev: any) => { if (ev.key === "Enter") ev.currentTarget.blur(); }} />
                  {vals[k] && <div class="er">{I.errorText(k, e, tol, vals[k], s)}</div>}</td>
                <td class="st">
                  <span class={"pill " + r}>{r || t("Belum")}</span>
                  {ps.map((i) => <button class="punch-chip" onClick={() => nav.go({ name: "punch", id: i.uuid })}><Lamp color={STATUS_LAMP[i.status]} />{i.code}</button>)}
                  {!ro && r === "NG" && openP.length === 0 && <button class="add-punch" onClick={() => nav.go({ name: "punch", preset: punchPreset(panel, c) })}>+ {t("Punch")}</button>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Evidence c={first} ro={ro} />
      {review && <ReviewSheet review={review} keys={keys} exp={exp} current={vals}
        onApply={apply} onClose={() => { URL.revokeObjectURL(review.url); setReview(null); }} />}
    </div>
  );
}

function ReviewSheet({ review, keys, exp, current, onApply, onClose }: {
  review: { found: Partial<Record<Key, I.OcrHit>>; raw: string; url: string }; keys: Key[]; exp: (k: Key) => [number, number];
  current: Record<string, string>; onApply: (sel: Partial<Record<Key, number>>) => void; onClose: () => void }) {
  const hits = keys.filter((k) => review.found[k]);
  const [use, setUse] = useState<Record<string, boolean>>(() => Object.fromEntries(hits.map((k) => [k, review.found[k]!.conf !== "low"])));
  const n = hits.filter((k) => use[k]).length;
  const CONF = { high: [t("Jelas"), INK.green], medium: [t("Agak ragu"), INK.amber], low: [t("Ragu"), INK.red] } as const;
  return (
    <div class="sheet-modal" onClick={onClose}>
      <div class="panel" onClick={(e) => e.stopPropagation()}>
        <div class="grip" />
        <h2>{t("Hasil baca foto HMI")}</h2>
        <img src={review.url} alt={t("Foto HMI")} class="inj-photo" />
        {hits.length === 0 ? <div class="msg warn" style={{ margin: "8px 16px" }}>{t("Tidak ada nilai yang terbaca. Coba foto yang lebih dekat, tegak lurus, dan tidak silau.")}</div> : (
          <>
            <div class="small muted" style={{ margin: "8px 16px" }}>{t("Cek setiap nilai dengan foto sebelum dimasukkan. Nilai yang ragu tidak dicentang otomatis.")}</div>
            {hits.map((k) => {
              const h = review.found[k]!;
              const old = (current[k] || "").trim();
              return (
                <label class="line inj-rv" key={k}>
                  <input type="checkbox" checked={!!use[k]} onChange={(e: any) => setUse({ ...use, [k]: e.currentTarget.checked })} />
                  <div class="main">
                    <div class="t">{keyLabel(k)}: <b>{I.fmt(h.value, I.DEC[k])} {unitLabel(k)}</b>
                      {old && <span class="muted small"> ({t("ganti {0}", old)})</span>}</div>
                    <div class="s">{t("Terbaca di foto")}: “{h.seen}” · {t("Expected")} {I.fmt(exp(k)[0], I.DEC[k])}</div>
                  </div>
                  <span class="small" style={{ color: CONF[h.conf][1] }}>{CONF[h.conf][0]}</span>
                </label>
              );
            })}
          </>
        )}
        {hits.length > 0 && hits.length < keys.length && <div class="small muted" style={{ margin: "6px 16px" }}>
          {t("Tidak terbaca: {0}. Isi manual atau coba foto lain.", keys.filter((k) => !review.found[k]).map(keyLabel).join(", "))}</div>}
        <details style={{ margin: "6px 16px" }}><summary class="small muted">{t("Teks mentah hasil OCR")}</summary>
          <pre class="inj-raw">{review.raw}</pre></details>
        <div class="row" style={{ gap: 8, margin: "10px 16px 0" }}>
          <button class="btn grow" onClick={onClose}>{t("Batal")}</button>
          <button class="btn primary grow" disabled={!n} onClick={() => onApply(Object.fromEntries(hits.filter((k) => use[k]).map((k) => [k, review.found[k]!.value])))}>
            {t("Masukkan {0} nilai ke Actual", n)}</button>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------- form setup / titik / blok baru
function num(v: string): number { const x = parseFloat(String(v).replace(",", ".")); return Number.isFinite(x) ? x : NaN; }

function SetupFields({ v, set }: { v: Record<string, string>; set: (v: Record<string, string>) => void }) {
  const inp = (k: string, label: string) => (
    <input inputMode="decimal" aria-label={label} value={v[k]} onInput={(e: any) => set({ ...v, [k]: e.currentTarget.value })} />
  );
  const f = (k: string, label: string, suffix = "") => (
    <label class="fld"><span>{label}</span>
      <div class="in">{inp(k, label)}{suffix && <i>{suffix}</i>}</div>
    </label>
  );
  return (
    <div class="inj-form">
      <div class="fld"><span>{t("Rasio CT")}</span>
        <div class="ratio">{inp("ct_p", t("CT primer"))}<i>A /</i>{inp("ct_s", t("CT sekunder"))}<i>A</i></div></div>
      <div class="fld"><span>{t("Rasio VT")}</span>
        <div class="ratio">{inp("vt_p", t("VT primer"))}<i>kV /</i>{inp("vt_s", t("VT sekunder"))}<i>V</i></div></div>
      {f("tol", t("Toleransi I, V, P, Q"), "%")}
      <div class="two">{f("tol_pf", t("Toleransi PF (±)"))}{f("tol_f", t("Toleransi frekuensi (±)"), "Hz")}</div>
      <div class="small muted">{t("P dan Q dinilai terhadap daya semu S (MVA), supaya Q≈0 pada φ = 0° tidak menghasilkan error % tak hingga.")}</div>
    </div>
  );
}

const setupStr = (s: Setup): Record<string, string> => Object.fromEntries(Object.entries(s).map(([k, x]) => [k, I.g(x)]));
function readSetup(v: Record<string, string>): Setup | null {
  const s = { ct_p: num(v.ct_p), ct_s: num(v.ct_s), vt_p: num(v.vt_p), vt_s: num(v.vt_s), tol: num(v.tol), tol_pf: num(v.tol_pf), tol_f: num(v.tol_f) };
  if (Object.values(s).some((x) => !Number.isFinite(x)) || s.ct_p <= 0 || s.ct_s <= 0 || s.vt_p <= 0 || s.vt_s <= 0) return null;
  return s;
}

function SetupSheet({ g, s, section, panel, who, onClose }: { g: ReturnType<typeof I.group>; s: Setup; section: string; panel: Row; who: string; onClose: () => void }) {
  const nav = useNav();
  const [v, setV] = useState(() => setupStr(s));
  const [busy, setBusy] = useState(false);
  async function save() {
    const ns = readSetup(v);
    if (!ns) { nav.toast(t("Rasio CT/VT belum benar.")); return; }
    const defs: [Row, Row][] = [];
    if (g.setup) defs.push([g.setup, { criteria: I.setupText(ns) }]);
    for (const p of g.points) {
      const ex = I.expected(ns, p);
      for (const [k, c] of Object.entries(p.rows)) {
        const cr = I.criteriaText(k as Key, ex[k as Key][0], ex[k as Key][1]);
        if (cr !== c!.criteria) defs.push([c!, { criteria: cr }]);
      }
    }
    const filled = g.points.flatMap((p) => Object.values(p.rows)).filter((c) => String(c!.value || "").trim()).length;
    if (filled && !confirm(t("{0} nilai actual sudah terisi. Expected dan status OK/NG akan dihitung ulang dengan rasio baru. Lanjutkan?", filled))) return;
    if (defs.length && (!navigator.onLine || !session.api)) {
      nav.toast(t("Ubah setup butuh sinyal (online) supaya hasil tim tidak tertimpa."));
      return;
    }
    setBusy(true);
    try {
      for (const [c, d] of defs) await renameCheck(session.api!, c, d);
      if (!g.setup) await addItems(panel.uuid, [[section, I.SETUP_DESC, I.setupText(ns), I.SETUP_UNIT]], who);
      for (const p of g.points) {
        const ex = I.expected(ns, p);
        for (const [k, c0] of Object.entries(p.rows)) {
          const c = store.get("panel_checks", c0!.uuid)!;
          if (String(c.value || "").trim()) await setActual(c, c.value, ex[k as Key][0], ex[k as Key][1], who);
        }
      }
      nav.toast(t("Setup disimpan."));
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
        <div class="grip" /><h2>{t("Setup uji injeksi")}</h2>
        <SetupFields v={v} set={setV} />
        <div class="row" style={{ gap: 8, margin: "10px 16px 0" }}>
          <button class="btn grow" disabled={busy} onClick={onClose}>{t("Batal")}</button>
          <button class="btn primary grow" disabled={busy} onClick={save}>{busy ? t("Menyimpan…") : t("Simpan")}</button>
        </div>
      </div>
    </div>
  );
}

function PointSheet({ g, s, section, panel, who, onClose }: { g: ReturnType<typeof I.group>; s: Setup; section: string; panel: Row; who: string; onClose: () => void }) {
  const nav = useNav();
  const last = g.points[g.points.length - 1];
  const [v, setV] = useState({ pi: I.g(Math.min(200, (last?.pi ?? 0) + 10)), pv: I.g(last?.pv ?? 100), phi: I.g(last?.phi ?? 30), hz: I.g(last?.hz ?? 50) });
  async function save() {
    const [pi, pv, phi, hz] = [num(v.pi), num(v.pv), num(v.phi), num(v.hz)];
    if ([pi, pv, phi, hz].some((x) => !Number.isFinite(x))) { nav.toast(t("Isi semua angka titik uji.")); return; }
    const n = Math.max(0, ...g.points.map((p) => p.n)) + 1;
    await addItems(panel.uuid, I.pointItems(section, s, n, pi, pv, phi, hz), who);
    onClose();
  }
  return (
    <div class="sheet-modal" onClick={onClose}>
      <div class="panel" onClick={(e) => e.stopPropagation()}>
        <div class="grip" /><h2>{t("Tambah titik uji")}</h2>
        <PointFields v={v} set={setV as any} />
        <div class="row" style={{ gap: 8, margin: "10px 16px 0" }}>
          <button class="btn grow" onClick={onClose}>{t("Batal")}</button>
          <button class="btn primary grow" onClick={save}>{t("Tambah")}</button>
        </div>
      </div>
    </div>
  );
}

function PointFields({ v, set, list }: { v: Record<string, string>; set: (v: Record<string, string>) => void; list?: boolean }) {
  const f = (k: string, label: string, suffix: string, mode = "decimal") => (
    <label class="fld"><span>{label}</span>
      <div class="in"><input inputMode={mode as any} value={v[k]} onInput={(e: any) => set({ ...v, [k]: e.currentTarget.value })} /><i>{suffix}</i></div>
    </label>
  );
  return (
    <div class="inj-form">
      {f("pi", t("Injeksi arus (% In)"), "%", list ? "text" : "decimal")}
      {list && <div class="small muted" style={{ marginTop: -4 }}>{t("Satu titik uji per angka, dipisah koma")}</div>}
      <div class="two">{f("pv", t("Injeksi tegangan (% Vn)"), "%")}{f("phi", t("Sudut φ (+ = lagging)"), "°", "text")}</div>
      {f("hz", t("Frekuensi"), "Hz")}
    </div>
  );
}

export function CreateInjection({ panel, checks, who, onClose }: { panel: Row; checks: Row[]; who: string; onClose: () => void }) {
  const nav = useNav();
  const devs = I.ratioDevices(checks);
  const [dev, setDev] = useState(devs.find((d) => d.includes("BCU")) || devs[0] || "BCU");
  const [v, setV] = useState(() => setupStr(I.prefillFromRatio(checks, dev)));
  const [pt, setPt] = useState({ pi: "10, 50, 100", pv: "100", phi: "30", hz: "50" });
  function pickDev(d: string) {
    setDev(d);
    const s = I.prefillFromRatio(checks, d);
    if (JSON.stringify(s) !== JSON.stringify(I.DEFAULT_SETUP)) setV(setupStr(s));
  }
  async function save() {
    const s = readSetup(v);
    if (!dev.trim()) { nav.toast(t("Isi nama device / alat baca.")); return; }
    if (!s) { nav.toast(t("Rasio CT/VT belum benar.")); return; }
    const pis = pt.pi.split(/[;\s]+|,(?=\s)|,(?!\d)/).map((x) => x.trim()).filter(Boolean).map(num);
    const [pv, phi, hz] = [num(pt.pv), num(pt.phi), num(pt.hz)];
    if (!pis.length || pis.some((x) => !Number.isFinite(x)) || [pv, phi, hz].some((x) => !Number.isFinite(x))) {
      nav.toast(t("Isi % injeksi arus, contoh: 10, 50, 100"));
      return;
    }
    const secs = checks.map((c) => c.section || "");
    if (secs.some((x) => I.isInjectionSection(x) && I.deviceOf(x) === dev.trim()) &&
      !confirm(t("Panel ini sudah punya uji injeksi untuk {0}. Buat blok kedua?", dev.trim()))) return;
    await addItems(panel.uuid, I.blockItems(dev.trim(), I.nextLetter(secs), s, pis.map((pi) => [pi, pv, phi, hz])), who);
    nav.toast(t("Uji injeksi CT/VT dibuat ({0} titik).", pis.length));
    if (navigator.onLine) session.sync();
    onClose();
  }
  return (
    <div class="sheet-modal" onClick={onClose}>
      <div class="panel" onClick={(e) => e.stopPropagation()}>
        <div class="grip" /><h2>{t("Uji injeksi CT/VT baru")}</h2>
        <div class="inj-form">
          <label class="fld"><span>{t("Device / alat baca")}</span>
            <input list="inj-devs" value={dev} onInput={(e: any) => pickDev(e.currentTarget.value)} />
            <datalist id="inj-devs">{devs.map((d) => <option value={d} />)}</datalist>
          </label>
          <div class="small muted">{t("Alat yang dibaca nilainya (BCU, meter, relay). Rasio diambil dari item Rasio CT/VT bila sudah diisi.")}</div>
        </div>
        <SetupFields v={v} set={setV} />
        <PointFields v={pt} set={setPt as any} list />
        <div class="row" style={{ gap: 8, margin: "10px 16px 0" }}>
          <button class="btn grow" onClick={onClose}>{t("Batal")}</button>
          <button class="btn primary grow" onClick={save}>{t("Buat")}</button>
        </div>
      </div>
    </div>
  );
}
