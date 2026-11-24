import { useEffect, useRef, useState } from "preact/hooks";
import { DEFAULT_CATEGORIES, DUE_DAYS, ISSUE_STATUSES, SEVERITIES } from "../config";
import { attachmentsOf, categories, issuesOf, panelsOf, teamCategories, teamDueDays } from "../data";
import { statusLabel, t } from "../i18n";
import { resizeImage } from "../image";
import { defaultDue, fmtDate, isOverdue, nextIssueCode, Row, today } from "../logic";
import { session } from "../session";
import { store } from "../store";
import { SyncEngine } from "../sync";
import { projectCrumbs } from "./Home";
import { Icon, Lamp, LAMP, PunchTag, SearchBox, SEV_COLOR, STATUS_LAMP, TopBar, useNav, useSession, useStore, INK, portal } from "./common";

const SFILTERS: [string, (i: Row) => boolean, string?][] = [
  ["Belum close", (i) => i.status !== "Closed"],
  ["Open", (i) => i.status === "Open", LAMP.red],
  ["Dikerjakan", (i) => i.status === "In Progress", LAMP.amber],
  ["Siap Verifikasi", (i) => i.status === "Ready to Verify", LAMP.blue],
  ["Closed", (i) => i.status === "Closed", LAMP.green],
  ["Lewat target", (i) => isOverdue(i)],
  ["Semua", () => true],
];
const SEV_INFO: Record<string, [string, string]> = {
  Critical: ["A", "Wajib selesai sebelum energize"],
  Major: ["B", "Wajib selesai sebelum serah terima"],
  Minor: ["C", "Boleh menyusul"],
};

export function Punches({ panel }: { panel?: string }) {
  useStore();
  const s = useSession();
  const nav = useNav();
  const [q, setQ] = useState("");
  const [f, setF] = useState(0);
  const [sev, setSev] = useState("");
  const pr = store.get("projects", nav.project);
  const p = panel ? store.get("panels", panel) : undefined;
  let list = pr ? issuesOf(nav.project, panel ? null : nav.site) : [];
  if (panel) list = list.filter((i) => i.panel_uuid === panel);
  const ql = q.trim().toLowerCase();
  const base = list.filter((i) => (!sev || i.severity === sev) &&
    (!ql || [i.code, i.title, i.panel_tag, i.pic, i.category].some((x) => String(x || "").toLowerCase().includes(ql))));
  const shown = base.filter(SFILTERS[f][1]);
  return (
    <>
      <TopBar title={p ? t("Punch {0}", p.tag) : t("Punch list")} crumbs={p ? [store.get("sites", p.site_uuid)?.name || ""] : projectCrumbs(nav)}
        back={!!panel}
        right={!panel && <button class="icon-btn" aria-label={t("Pilih project / site")} onClick={nav.pickProject}><Icon name="down" /></button>} />
      <div class="content">
        <SearchBox value={q} onInput={setQ} placeholder={t("Cari kode, judul, panel, PIC")} />
        <div class="chips">{SFILTERS.map(([lab, fn, col], k) => (
          <button class={"chip" + (f === k ? " on" : "")} onClick={() => setF(k)}>
            {col && <Lamp color={col} />}{t(lab)} <span class="n">{base.filter(fn).length}</span></button>))}
        </div>
        <div class="chips">
          <button class={"chip" + (!sev ? " on" : "")} onClick={() => setSev("")}>{t("Semua kategori")}</button>
          {SEVERITIES.map((x) => <button class={"chip" + (sev === x ? " on" : "")} onClick={() => setSev(sev === x ? "" : x)}>
            <b style={{ color: sev === x ? undefined : SEV_COLOR[x] }}>{SEV_INFO[x][0]}</b> {x}</button>)}
        </div>
        {shown.length === 0 && <div class="empty"><b>{t("Tidak ada punch")}</b>{t("Tidak ada punch yang sesuai filter.")}</div>}
        {shown.map((i) => <PunchTag i={i} onClick={() => nav.go({ name: "punch", id: i.uuid })} />)}
      </div>
      {!s.readOnly && pr && <button class="fab" onClick={() => nav.go({ name: "punch", preset: panel ? { panel_uuid: panel } : {} })}>
        <Icon name="plus" />{t("Punch baru")}</button>}
    </>
  );
}

// ======================================================================= form punch
type Pending = { blob: Blob; kind: string; name: string };

export function PunchEdit({ id, preset }: { id?: string; preset?: Record<string, any> }) {
  useStore();
  const s = useSession();
  const nav = useNav();
  const ro = s.readOnly;
  const existing = id ? store.get("issues", id) : undefined;
  const pid = existing?.project_uuid || nav.project;
  const [f, setF] = useState<Row>(() => existing ? { ...existing } : {
    title: "", description: "", category: teamCategories(DEFAULT_CATEGORIES)[0], severity: "Major", status: "Open", pic: "",
    due_date: defaultDue(preset?.severity || "Major", teamDueDays(DUE_DAYS)), raised_date: today(), action: "",
    panel_uuid: "", check_uuid: null, ...preset,
  });
  const [err, setErr] = useState("");
  const [pending, setPending] = useState<Pending[]>([]);
  const [viewer, setViewer] = useState<{ blob?: Blob; att?: Row; idx?: number } | null>(null);
  const cam = useRef<HTMLInputElement>(null);
  const gal = useRef<HTMLInputElement>(null);
  const shootKind = useRef("before");
  if (id && !existing) return <><TopBar title="Punch" back /><div class="content"><div class="empty"><b>{t("Punch tidak ditemukan")}</b></div></div></>;
  const panels = panelsOf(pid);
  const cats = categories(pid, teamCategories(DEFAULT_CATEGORIES));
  const set = (k: string, v: any) => setF((o) => ({ ...o, [k]: v }));
  const atts = existing ? attachmentsOf(existing.uuid) : [];
  const stIdx = ISSUE_STATUSES.indexOf(f.status);
  const panel = f.panel_uuid ? store.get("panels", f.panel_uuid) : undefined;

  async function save() {
    if (!f.title?.trim()) { setErr(t("Isi judul temuan dulu.")); window.scrollTo(0, 0); return; }
    let siteUuid = panel?.site_uuid || existing?.site_uuid || nav.site || null;
    if (!siteUuid) siteUuid = store.all("sites").find((x) => x.project_uuid === pid)?.uuid || null;
    const data: Row = {
      title: f.title.trim(), description: (f.description || "").trim(), category: f.category, severity: f.severity,
      status: f.status, pic: (f.pic || "").trim(), due_date: f.due_date || null, raised_date: f.raised_date || null,
      action: (f.action || "").trim(), panel_uuid: f.panel_uuid || null, site_uuid: siteUuid,
      verified_by: (f.verified_by || "").trim(),
      closed_date: f.status === "Closed" ? (f.closed_date || existing?.closed_date || today()) : null,
    };
    let issue: Row;
    if (existing) issue = await store.edit("issues", existing.uuid, data);
    else {
      const who = s.info?.full_name || (s.info?.email || "").split("@")[0];
      issue = await store.create("issues", { ...data, project_uuid: pid, check_uuid: f.check_uuid || null,
        code: nextIssueCode(store.get("projects", pid), store.all("issues", true).filter((i) => i.project_uuid === pid)),
        raised_by: who });
    }
    for (const ph of pending) await addPhoto(issue.uuid, ph);
    nav.toast(existing ? t("Punch {0} disimpan.", issue.code) : t("Punch {0} dibuat.", issue.code));
    if (navigator.onLine) session.sync();
    nav.back();
  }

  async function addPhoto(issueUuid: string, ph: Pending) {
    const att = await store.create("attachments", { issue_uuid: issueUuid, kind: ph.kind, filename: ph.name, caption: "", storage_path: null });
    await store.setPhoto(att.uuid, ph.blob);
  }

  function shoot(kind: string, camera: boolean) {
    shootKind.current = kind;
    (camera ? cam : gal).current?.click();
  }

  async function onFiles(e: any) {
    const files: File[] = [...(e.currentTarget.files || [])];
    e.currentTarget.value = "";
    for (const file of files) {
      try {
        const ph = { blob: await resizeImage(file), kind: shootKind.current,
          name: `foto_${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}.jpg` };
        if (existing) await addPhoto(existing.uuid, ph);
        else setPending((p) => [...p, ph]);
      } catch {
        nav.toast(t("Foto tidak bisa dibaca. Coba ambil ulang."));
      }
    }
  }

  async function del() {
    if (!existing || !confirm(t("Hapus punch {0}? Punch ditandai terhapus dan masih bisa dipulihkan admin.", existing.code))) return;
    await store.edit("issues", existing.uuid, { deleted: 1 });
    for (const a of atts) await store.edit("attachments", a.uuid, { deleted: 1 });
    nav.toast(t("Punch {0} dihapus.", existing.code));
    nav.back();
  }

  const col = (kind: string, label: string) => {
    const mine = atts.filter((a) => (kind === "after" ? a.kind === "after" : a.kind !== "after"));
    const pend = pending.map((p, k) => ({ p, k })).filter(({ p }) => (kind === "after" ? p.kind === "after" : p.kind !== "after"));
    return (
      <div class="photo-col">
        <h4>{label} <span>{mine.length + pend.length}</span></h4>
        <div class="thumbs">
          {mine.map((a) => <Thumb key={a.uuid} att={a} onOpen={(b) => setViewer({ blob: b, att: a })} />)}
          {pend.map(({ p, k }) => <PendingThumb key={"p" + k} blob={p.blob} onOpen={() => setViewer({ blob: p.blob, idx: k })} />)}
          {!ro && <button class="shoot" onClick={() => shoot(kind, true)} aria-label={t("Ambil foto {0}", label)}><Icon name="camera" />{t("Kamera")}</button>}
          {!ro && <button class="shoot" onClick={() => shoot(kind, false)} aria-label={t("Pilih dari galeri")}><Icon name="image" />{t("Galeri")}</button>}
        </div>
      </div>
    );
  };

  return (
    <>
      <TopBar title={existing ? existing.code : t("Punch baru")} crumbs={[panel?.tag || t("Umum"), existing ? statusLabel(existing.status) : ""]}
        back sync={false} right={!ro && <button class="save-btn" onClick={save}>{t("Simpan")}</button>} />
      <div class="content">
        {err && <div class="msg err">{err}</div>}
        <div class="sheet"><div class="bd" style={{ paddingTop: 14 }}>
          <div class="field"><label>{t("Temuan")}</label>
            <textarea rows={2} readOnly={ro} value={f.title} placeholder={t("Contoh: Ferrule kabel X2:14 tidak sesuai drawing")}
              onInput={(e: any) => set("title", e.currentTarget.value)} /></div>
          <div class="field" style={{ marginBottom: 6 }}><label>{t("Status")}</label>
            <div class="flow">{ISSUE_STATUSES.map((x, k) => (
              <button class={k < stIdx ? "past" : k === stIdx ? "cur" : ""} disabled={ro} aria-pressed={k === stIdx}
                onClick={() => set("status", x)}>
                <span class="dot" style={k === stIdx ? { background: STATUS_LAMP[x], borderColor: STATUS_LAMP[x] } : {}}>{k < stIdx ? "✓" : ""}</span>
                {statusLabel(x)}</button>))}
            </div>
          </div>
        </div></div>

        <div class="sheet"><div class="bd" style={{ paddingTop: 14 }}>
          <div class="field"><label>{t("Kategori punch")}</label>
            <div class="sevpick">{SEVERITIES.map((x) => (
              <button class={f.severity === x ? "on" : ""} style={{ color: SEV_COLOR[x] }} disabled={ro} aria-pressed={f.severity === x}
                onClick={() => { set("severity", x); if (!existing) set("due_date", defaultDue(x, teamDueDays(DUE_DAYS))); }}>
                <div class="L">{SEV_INFO[x][0]}</div><div class="D">{t(SEV_INFO[x][1])}</div></button>))}
            </div></div>
          <div class="field"><label>{t("Panel")}</label>
            <select disabled={ro} value={f.panel_uuid || ""} onChange={(e: any) => set("panel_uuid", e.currentTarget.value)}>
              <option value="">{t("Umum, tidak terkait panel")}</option>
              {panels.map((p) => <option value={p.uuid}>{p.tag} ({p.site_name}{p.bay ? `, ${p.bay}` : ""})</option>)}
            </select></div>
          <div class="field"><label>{t("Kategori temuan")}</label>
            <select disabled={ro} value={f.category || ""} onChange={(e: any) => set("category", e.currentTarget.value)}>
              {cats.map((c) => <option value={c}>{t(c)}</option>)}
            </select></div>
          <div class="row" style={{ gap: 10, alignItems: "flex-start" }}>
            <div class="field grow"><label>{t("PIC")}</label>
              <input readOnly={ro} value={f.pic || ""} placeholder={t("Vendor / nama")} onInput={(e: any) => set("pic", e.currentTarget.value)} /></div>
            <div class="field grow"><label>{t("Target selesai")}</label>
              <input type="date" readOnly={ro} value={f.due_date || ""} onInput={(e: any) => set("due_date", e.currentTarget.value)} /></div>
          </div>
          {f.status === "Closed" && (
            <div class="row" style={{ gap: 10, alignItems: "flex-start" }}>
              <div class="field grow"><label>{t("Tanggal close")}</label>
                <input type="date" readOnly={ro} value={f.closed_date || today()} onInput={(e: any) => set("closed_date", e.currentTarget.value)} /></div>
              <div class="field grow"><label>{t("Diverifikasi oleh")}</label>
                <input readOnly={ro} value={f.verified_by || ""} onInput={(e: any) => set("verified_by", e.currentTarget.value)} /></div>
            </div>
          )}
        </div></div>

        <div class="sheet">
          <div class="hd"><h2>{t("Foto")}</h2></div>
          <div class="bd">
            <div class="photo-cols">{col("before", t("Sebelum"))}{col("after", t("Sesudah"))}</div>
            <input ref={cam} type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={onFiles} />
            <input ref={gal} type="file" accept="image/*" multiple style={{ display: "none" }} onChange={onFiles} />
          </div>
        </div>

        <div class="sheet"><div class="bd" style={{ paddingTop: 14 }}>
          <div class="field"><label>{t("Deskripsi")}</label>
            <textarea readOnly={ro} value={f.description || ""} onInput={(e: any) => set("description", e.currentTarget.value)} /></div>
          <div class="field" style={{ marginBottom: 0 }}><label>{t("Tindakan perbaikan")}</label>
            <textarea readOnly={ro} value={f.action || ""} onInput={(e: any) => set("action", e.currentTarget.value)} /></div>
          {existing && <div class="small muted" style={{ marginTop: 10 }}>
            {t("Ditemukan {0} oleh {1}", fmtDate(existing.raised_date) || "-", existing.raised_by || "-")}
            {existing._dirty ? <> · <span style={{ color: INK.amber, fontWeight: 600 }}>{t("belum terkirim")}</span></> : null}</div>}
        </div></div>

        {!ro && <button class="btn primary block" onClick={save}>{existing ? t("Simpan perubahan") : t("Buat punch")}</button>}
        {!ro && existing && <button class="btn danger block" style={{ marginTop: 10 }} onClick={del}>{t("Hapus punch")}</button>}
      </div>
      {viewer && <Viewer blob={viewer.blob} ro={ro} onClose={() => setViewer(null)}
        onDelete={async () => {
          if (!confirm(t("Hapus foto ini?"))) return;
          if (viewer.att) await store.edit("attachments", viewer.att.uuid, { deleted: 1 });
          else if (viewer.idx !== undefined) setPending((p) => p.filter((_, k) => k !== viewer.idx));
          setViewer(null);
        }} />}
    </>
  );
}

function useObjectUrl(blob?: Blob) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!blob) { setUrl(""); return; }
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob]);
  return url;
}

export function Thumb({ att, onOpen }: { att: Row; onOpen: (b?: Blob) => void }) {
  const [blob, setBlob] = useState<Blob | undefined>();
  const [state, setState] = useState("loading");
  useEffect(() => {
    let alive = true;
    SyncEngine.ensurePhoto(navigator.onLine ? session.api : null, att)
      .then((b) => { if (alive) { setBlob(b); setState(b ? "ok" : "none"); } })
      .catch(() => alive && setState("err"));
    return () => { alive = false; };
  }, [att.uuid, att.storage_path]);
  const url = useObjectUrl(blob);
  return (
    <button class="thumb" onClick={() => blob && onOpen(blob)}>
      {url ? <img src={url} alt="" /> : <div class="ph">{state === "loading" ? t("Memuat…") : t("Belum diunduh")}</div>}
      {!att.storage_path && <span class="up"><Lamp color={LAMP.amber} /></span>}
    </button>
  );
}

function PendingThumb({ blob, onOpen }: { blob: Blob; onOpen: () => void }) {
  const url = useObjectUrl(blob);
  return <button class="thumb" onClick={onOpen}><img src={url} alt="" /><span class="up"><Lamp color={LAMP.amber} /></span></button>;
}

export function Viewer({ blob, ro, onClose, onDelete }: { blob?: Blob; ro: boolean; onClose: () => void; onDelete: () => void }) {
  const url = useObjectUrl(blob);
  return portal(
    <div class="viewer" onClick={onClose}>
      {url && <img src={url} alt="" />}
      <div class="bar2" onClick={(e) => e.stopPropagation()}>
        <button class="btn grow" onClick={onClose}>{t("Tutup")}</button>
        {!ro && <button class="btn danger" onClick={onDelete}>{t("Hapus foto")}</button>}
      </div>
    </div>
  );
}
