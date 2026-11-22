"use strict";
/* Dashboard PM — Panel Tracker. Hanya baca; data langsung dari Supabase dengan login akun tim (RLS). */
const SUPABASE_URL = "https://ewwtxklxgkyflhyazueg.supabase.co";
const SUPABASE_KEY = "sb_publishable_5pqbo5TleB5PgtLdYthD_w_dKoNi2-D";   // publishable: aman di klien, data tetap butuh login
const LOGIN_DOMAIN = "paneltracker.local";
const LS_SESSION = "pt_dash_session", LS_PROJECT = "pt_dash_project", LS_GRAN = "pt_dash_gran";
const AUTO_REFRESH_MS = 5 * 60 * 1000;

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const oneLine = (s) => String(s ?? "").split(/\s+/).filter(Boolean).join(" ");
const pad = (n) => String(n).padStart(2, "0");
const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const today = () => isoDay(new Date());
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const fmtDate = (s) => { if (!s) return "-"; const [y, m, d] = String(s).slice(0, 10).split("-"); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
const daysBetween = (a, b) => Math.round((new Date(b + "T00:00:00") - new Date(a + "T00:00:00")) / 864e5);
function store(k, v) { try { v === undefined ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* abaikan */ } }
function load(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }

/* ------------------------------------------------------------------ Supabase */
let session = load(LS_SESSION, null);
class AuthError extends Error {}

async function authToken(body, grant) {
  const r = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=${grant}`, {
    method: "POST", headers: { apikey: SUPABASE_KEY, "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new AuthError(j.msg || j.error_description || j.message || j.error || `HTTP ${r.status}`);
  session = { access_token: j.access_token, refresh_token: j.refresh_token, email: (j.user || {}).email || session?.email,
    expires_at: Date.now() + (Number(j.expires_in || 3600) - 60) * 1000 };
  store(LS_SESSION, session);
}
async function token() {
  if (!session?.refresh_token) throw new AuthError("Belum login.");
  if (!session.access_token || Date.now() >= session.expires_at) {
    try { await authToken({ refresh_token: session.refresh_token }, "refresh_token"); }
    catch (e) { if (e instanceof AuthError) { session = null; store(LS_SESSION); throw new AuthError("Sesi berakhir, silakan login lagi."); } throw e; }
  }
  return session.access_token;
}
async function rest(path) {
  const t = await token();
  let r;
  try { r = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${t}` }, cache: "no-store" }); }
  catch (e) { throw new Error("Tidak bisa terhubung ke server. Periksa koneksi internet."); }
  if (r.status === 401) { session = null; store(LS_SESSION); throw new AuthError("Sesi berakhir, silakan login lagi."); }
  if (!r.ok) throw new Error(`Server menolak (${r.status}): ${(await r.text()).slice(0, 200)}`);
  return r.json();
}
async function restAll(table, query) {   // PostgREST membatasi 1000 baris per permintaan
  const out = [];
  for (let off = 0; ; off += 1000) {
    const rows = await rest(`${table}?${query}&limit=1000&offset=${off}`);
    out.push(...rows);
    if (rows.length < 1000) return out;
  }
}
const eq = (v) => "eq." + encodeURIComponent(v);
const inList = (vs) => "in.(" + vs.map(encodeURIComponent).join(",") + ")";

/* ------------------------------------------------------------------ tampilan dasar */
function show(id) {
  for (const v of ["vLogin", "vLoading", "vErr", "vDash"]) $("#" + v).classList.toggle("hidden", v !== id);
  const on = !!session && id !== "vLogin";
  for (const v of ["#refresh", "#logout", "#proj"]) $(v).classList.toggle("hidden", !on || (v === "#proj" && $("#proj").options.length < 2));
  $("#who").textContent = on && session?.email ? session.email.replace("@" + LOGIN_DOMAIN, "") : "";
}
function fail(e) {
  if (e instanceof AuthError) { show("vLogin"); err($("#lgErr"), e.message); return; }
  $("#errText").textContent = e.message || String(e); show("vErr");
}
function err(el, msg) { el.textContent = msg || ""; el.classList.toggle("hidden", !msg); }

$("#loginForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const u = $("#u").value.trim(), p = $("#p").value;
  const email = u.includes("@") ? u.toLowerCase() : `${u.toLowerCase()}@${LOGIN_DOMAIN}`;
  $("#lgBtn").disabled = true; err($("#lgErr"), "");
  try {
    session = { email };
    await authToken({ email, password: p }, "password");
    const m = await rest("app_users?select=email&email=" + eq(session.email));
    if (!m.length) { await logout(true); throw new AuthError("Akun ini belum terdaftar di tim Panel Tracker."); }
    $("#p").value = "";
    start();
  } catch (e) {
    session = null; store(LS_SESSION);
    err($("#lgErr"), /invalid login|credentials/i.test(e.message) ? "Username atau password salah." : e.message);
  } finally { $("#lgBtn").disabled = false; }
});
async function logout(silent) {
  if (session?.access_token) {   // scope=local: hanya sesi browser ini, perangkat lain tetap login
    try { await fetch(`${SUPABASE_URL}/auth/v1/logout?scope=local`, { method: "POST", headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${session.access_token}` } }); } catch (e) { /* abaikan */ }
  }
  session = null; store(LS_SESSION);
  if (!silent) show("vLogin");
}
$("#logout").addEventListener("click", () => { if (confirm("Keluar dari dashboard di browser ini?")) logout(); });
$("#refresh").addEventListener("click", () => refresh());
$("#proj").addEventListener("change", () => { store(LS_PROJECT, $("#proj").value); refresh(); });

/* ------------------------------------------------------------------ data */
let projects = [], data = null, baySort = "bay", gran = load(LS_GRAN, "week"), timer = null;

async function start() {
  show("vLoading");
  try {
    projects = await rest("projects?select=uuid,code,name&deleted=eq.0&order=code.asc");
    if (!projects.length) throw new Error("Belum ada project di cloud.");
    const saved = load(LS_PROJECT, "");
    $("#proj").innerHTML = projects.map((p) => `<option value="${esc(p.uuid)}">${esc(p.code)} — ${esc(p.name)}</option>`).join("");
    $("#proj").value = projects.some((p) => p.uuid === saved) ? saved : projects[0].uuid;
    await refresh();
    clearInterval(timer);
    timer = setInterval(() => { if (!document.hidden) refresh(true); }, AUTO_REFRESH_MS);
  } catch (e) { fail(e); }
}

async function refresh(quiet) {
  if (!quiet) show("vLoading");
  try {
    const pid = $("#proj").value;
    const sites = await rest("sites?select=uuid,name&deleted=eq.0&project_uuid=" + eq(pid));
    const panels = sites.length ? await restAll("panels", "select=uuid,site_uuid,tag,name,bay,panel_type,accepted_at,accepted_by&deleted=eq.0&site_uuid=" + inList(sites.map((s) => s.uuid))) : [];
    const checks = panels.length ? await restAll("panel_checks", "select=panel_uuid,section,result&deleted=eq.0&panel_uuid=" + inList(panels.map((p) => p.uuid))) : [];
    const issues = await restAll("issues", "select=uuid,panel_uuid,code,title,severity,status,pic,raised_date,due_date,closed_date&deleted=eq.0&project_uuid=" + eq(pid));
    data = compute(projects.find((p) => p.uuid === pid), sites, panels, checks, issues);
    render();
    show("vDash");
  } catch (e) { if (!quiet) fail(e); }
}

/* ------------------------------------------------------------------ hitung */
const isSas = (sec) => /^[A-Z]{1,2}\. SAS · /.test(sec || "");

function bayOf(p) {
  const t = oneLine(p.tag).replace(/\s/g, "").toUpperCase();
  let m;
  const KIND = { T: [0, "Trafo"], U: [1, "UGC"], C: [2, "Bus Coupler"], S: [3, "Bus Section"] };
  if ((m = /E([TUCS])(\d\d)\+/.exec(t))) { const [g, n] = KIND[m[1]]; return { key: m[1] + m[2], label: `${n} ${+m[2]}`, order: g * 100 + +m[2] }; }
  if ((m = /E00\+R(\d)/.exec(t))) return { key: "BB" + m[1], label: `Busbar Protection ${m[1]}`, order: 400 + +m[1] };
  if ((m = /E00\+X([12])/.exec(t))) return { key: "IO" + m[1], label: `Common I/O ${m[1]}`, order: 500 + +m[1] };
  if ((m = /E00\+X([34])/.exec(t))) return { key: "SAS" + m[1], label: `SAS ${+m[1] - 2}`, order: 600 + +m[1] };
  const b = oneLine(p.bay) || oneLine(p.tag);
  return { key: "X:" + b, label: b, order: 900 };
}

function compute(project, sites, panels, checks, issues) {
  const t = today();
  const byPanel = new Map(panels.map((p) => [p.uuid, { p, ok: 0, ng: 0, na: 0, todo: 0, sasDone: 0, sasTot: 0, open: 0, aOpen: 0 }]));
  for (const c of checks) {
    const x = byPanel.get(c.panel_uuid); if (!x) continue;
    const r = c.result || "";
    if (r === "OK") x.ok++; else if (r === "NG") x.ng++; else if (r === "NA") x.na++; else x.todo++;
    if (isSas(c.section)) { x.sasTot++; if (r) x.sasDone++; }
  }
  const open = issues.filter((i) => i.status !== "Closed");
  for (const i of open) { const x = byPanel.get(i.panel_uuid); if (x) { x.open++; if (i.severity === "Critical") x.aOpen++; } }
  const status = (x) => x.p.accepted_at ? "Diterima" : (x.ng || x.open) ? "Ada temuan" : !(x.ok + x.ng + x.na + x.todo) ? "Tanpa checklist"
    : !(x.ok + x.ng + x.na) ? "Belum dicek" : x.todo ? "Sedang dicek" : "Lulus";
  const bays = new Map();
  for (const x of byPanel.values()) {
    x.status = status(x);
    const b = bayOf(x.p);
    if (!bays.has(b.key)) bays.set(b.key, { ...b, panels: [], ok: 0, ng: 0, na: 0, todo: 0, sasDone: 0, sasTot: 0, open: 0, aOpen: 0 });
    const B = bays.get(b.key);
    B.panels.push(x);
    for (const k of ["ok", "ng", "na", "todo", "sasDone", "sasTot", "open", "aOpen"]) B[k] += x[k];
  }
  const all = [...byPanel.values()];
  const sum = (k) => all.reduce((n, x) => n + x[k], 0);
  const tot = sum("ok") + sum("ng") + sum("na") + sum("todo");
  const sev = (s) => open.filter((i) => i.severity === s).length;
  const panelTag = new Map(panels.map((p) => [p.uuid, oneLine(p.tag)]));
  const crit = open.filter((i) => i.severity === "Critical").map((i) => ({ ...i, tag: panelTag.get(i.panel_uuid) || "Umum",
    late: !!(i.due_date && i.due_date < t) })).sort((a, b) => (b.late - a.late) || String(a.due_date || "9").localeCompare(String(b.due_date || "9")) || String(a.code).localeCompare(String(b.code), undefined, { numeric: true }));
  return {
    project, sites, issues, bays: [...bays.values()], crit, today: t,
    kpi: {
      panels: all.length, done: all.filter((x) => x.status === "Lulus" || x.status === "Diterima").length,
      accepted: all.filter((x) => x.status === "Diterima").length, withNG: all.filter((x) => x.status === "Ada temuan").length,
      items: tot, checked: tot - sum("todo"), ng: sum("ng"),
      open: open.length, A: sev("Critical"), B: sev("Major"), C: sev("Minor"),
      late: open.filter((i) => i.due_date && i.due_date < t).length, aLate: crit.filter((i) => i.late).length,
      sasTot: sum("sasTot"), sasDone: sum("sasDone"),
    },
  };
}

/* ------------------------------------------------------------------ render */
const pct = (a, b) => b ? Math.round((100 * a) / b) : 0;

function render() {
  const k = data.kpi;
  const tile = (l, v, s, o = {}) => `<div class="kpi${o.alert ? " alert" : ""}"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div>${
    o.meter !== undefined ? `<div class="meter" role="img" aria-label="${o.meter}%"><i style="width:${o.meter}%"></i></div>` : ""}</div>`;
  $("#kpis").innerHTML = [
    tile("Panel selesai", `${k.done}<small>/${k.panels}</small>`, `${k.accepted} diterima · ${k.withNG} ada temuan`, { meter: pct(k.done, k.panels) }),
    tile("Item diuji", `${pct(k.checked, k.items)}<small>%</small>`, `${k.checked.toLocaleString("id-ID")} dari ${k.items.toLocaleString("id-ID")} · ${k.ng} NG`, { meter: pct(k.checked, k.items) }),
    tile("Punch open", `${k.open}`, `A ${k.A} · B ${k.B} · C ${k.C}`),
    tile("Kategori A open", `${k.A}`, k.A ? `menahan energize · ${k.aLate} lewat target` : "tidak ada yang menahan energize", { alert: k.A > 0 }),
    tile("Lewat target", `${k.late}`, k.late ? "punch open melewati target" : "semua masih dalam target", { alert: k.late > 0 }),
    tile("Integrasi SAS", k.sasTot ? `${pct(k.sasDone, k.sasTot)}<small>%</small>` : "–", k.sasTot ? `${k.sasDone} dari ${k.sasTot} item SAS` : "belum ada checksheet SAS", { meter: k.sasTot ? pct(k.sasDone, k.sasTot) : undefined }),
  ].join("");
  renderBays();
  renderTrend();
  renderCrit();
  const now = new Date();
  $("#foot").textContent = `${data.project.code} — ${data.project.name} · data cloud per ${pad(now.getHours())}:${pad(now.getMinutes())} · otomatis diperbarui tiap 5 menit · perubahan yang belum di-sync dari laptop/HP belum terlihat`;
}

function renderBays() {
  const rows = [...data.bays];
  const p = (b) => (b.ok + b.ng + b.na) / Math.max(1, b.ok + b.ng + b.na + b.todo);
  if (baySort === "pct") rows.sort((a, b) => p(a) - p(b) || a.order - b.order);
  else if (baySort === "punch") rows.sort((a, b) => b.aOpen - a.aOpen || b.open - a.open || a.order - b.order);
  else rows.sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
  $("#baySub").textContent = `${rows.length} bay · ${data.kpi.panels} panel`;
  const seg = (n, tot, color, label, b) => n ? `<span style="width:${(100 * n) / tot}%;background:${color}" title="${esc(b.label)} · ${label}: ${n} item (${pct(n, tot)}%)"></span>` : "";
  $("#bays").innerHTML = `<thead><tr><th>Bay</th><th>Progress item</th><th class="num" style="text-align:right">Diuji</th><th class="hide-sm" style="text-align:right">SAS</th><th style="text-align:right">Punch open</th></tr></thead><tbody>${
    rows.map((b) => {
      const tot = b.ok + b.ng + b.na + b.todo;
      const tags = b.panels.map((x) => oneLine(x.p.tag)).join(", ");
      return `<tr>
        <td class="name">${esc(b.label)}<small title="${esc(tags)}">${b.panels.length} panel · ${esc(tags.length > 34 ? tags.slice(0, 33) + "…" : tags)}</small></td>
        <td class="bar">${tot ? `<div class="stack" role="img" aria-label="${esc(b.label)}: ${b.ok} OK, ${b.ng} NG, ${b.na} N/A, ${b.todo} belum">${
          seg(b.ok, tot, "var(--ok)", "OK", b)}${seg(b.ng, tot, "var(--ng)", "NG", b)}${seg(b.na, tot, "var(--na)", "N/A", b)}${seg(b.todo, tot, "var(--todo)", "Belum dicek", b)}</div>` : `<span style="color:var(--faint)">tanpa checklist</span>`}</td>
        <td class="num"><b>${pct(b.ok + b.ng + b.na, tot)}%</b>${b.ng ? ` <span class="c-ng">· ${b.ng} NG</span>` : ""}</td>
        <td class="num hide-sm">${b.sasTot ? `${pct(b.sasDone, b.sasTot)}%` : "–"}</td>
        <td class="num">${b.open ? `<span class="pill ${b.aOpen ? "c-ng" : ""}"><span class="lamp" style="background:${b.aOpen ? "var(--ng)" : "var(--warn)"}"></span>${b.open}${b.aOpen ? ` (A ${b.aOpen})` : ""}</span>` : `<span class="pill c-ok"><span class="lamp" style="background:var(--ok)"></span>0</span>`}</td>
      </tr>`;
    }).join("")}</tbody>`;
}
document.querySelectorAll("[data-sort]").forEach((b) => b.addEventListener("click", () => {
  baySort = b.dataset.sort;
  document.querySelectorAll("[data-sort]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderBays();
}));

/* ---- grafik punch dibuka vs ditutup (batang berkelompok, satu sumbu) */
function weekStart(iso) {   // Senin
  const d = new Date(iso + "T00:00:00"); const wd = (d.getDay() + 6) % 7; d.setDate(d.getDate() - wd); return isoDay(d);
}
function buckets() {
  const opened = data.issues.map((i) => i.raised_date).filter(Boolean).map((s) => s.slice(0, 10));
  const closed = data.issues.filter((i) => i.status === "Closed" && i.closed_date).map((i) => i.closed_date.slice(0, 10));
  const key = gran === "week" ? weekStart : (s) => s;
  const end = data.today;
  const first = [...opened, ...closed].sort()[0] || end;
  const out = [];
  const d = new Date(key(first) + "T00:00:00");
  const stepDays = gran === "week" ? 7 : 1;
  const cap = gran === "week" ? 12 : 30;
  while (isoDay(d) <= end) { out.push({ k: isoDay(d), open: 0, closed: 0 }); d.setDate(d.getDate() + stepDays); }
  const idx = new Map(out.map((b, i) => [b.k, i]));
  for (const s of opened) { const i = idx.get(key(s)); if (i !== undefined) out[i].open++; }
  for (const s of closed) { const i = idx.get(key(s)); if (i !== undefined) out[i].closed++; }
  return out.slice(-cap);
}
const bLabel = (k) => { const [, m, d] = k.split("-"); return gran === "week" ? `${+d} ${MONTHS[+m - 1]}` : `${+d}/${+m}`; };
const bTitle = (k) => { if (gran === "day") return fmtDate(k); const e = new Date(k + "T00:00:00"); e.setDate(e.getDate() + 6); return `Minggu ${fmtDate(k)} – ${fmtDate(isoDay(e))}`; };

function niceMax(v) { if (v <= 5) return 5; const p = 10 ** Math.floor(Math.log10(v)); for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p; return 10 * p; }
function barPath(x, y, w, h) {   // ujung data membulat 4px, menempel di baseline
  if (h <= 0) return "";
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
function renderTrend() {
  document.querySelectorAll("[data-gran]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.gran === gran)));
  const B = buckets();
  const W = Math.max(300, Math.round($("#trend").clientWidth || 600)), H = 240, L = 34, R = 8, T = 10, Bt = 30;
  const max = niceMax(Math.max(1, ...B.map((b) => Math.max(b.open, b.closed))));
  const pw = W - L - R, ph = H - T - Bt, n = B.length || 1;
  const gw = pw / n, bw = Math.max(2, Math.min(26, (gw - Math.min(10, gw * 0.3)) / 2 - 1));
  const y = (v) => T + ph - (v / max) * ph;
  const ticks = 4;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Punch dibuka dan ditutup per ${gran === "week" ? "minggu" : "hari"}">`;
  for (let i = 0; i <= ticks; i++) {
    const v = (max / ticks) * i, yy = y(v);
    s += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="${i ? "#e6e9e6" : "#b3b9b5"}" stroke-width="1"/>`;
    s += `<text x="${L - 6}" y="${yy + 4}" text-anchor="end" font-size="11" fill="#656c6f">${Math.round(v)}</text>`;
  }
  const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(pw / 56))));   // label sumbu-x tidak bertabrakan
  B.forEach((b, i) => {
    const cx = L + gw * i + gw / 2;
    s += `<path d="${barPath(cx - bw - 1, y(b.open), bw, y(0) - y(b.open))}" fill="var(--series-1)"/>`;
    s += `<path d="${barPath(cx + 1, y(b.closed), bw, y(0) - y(b.closed))}" fill="var(--series-2)"/>`;
    if ((n - 1 - i) % every === 0) s += `<text x="${cx}" y="${H - Bt + 16}" text-anchor="middle" font-size="11" fill="#656c6f">${bLabel(b.k)}</text>`;
    s += `<rect class="hit" data-i="${i}" x="${L + gw * i}" y="${T}" width="${gw}" height="${ph}" fill="transparent"/>`;
  });
  s += `</svg><div class="tip hidden" id="tip"></div>`;
  $("#trend").innerHTML = s;
  const tip = $("#tip"), svg = $("#trend svg");
  svg.querySelectorAll(".hit").forEach((r) => {
    const on = () => {
      const b = B[+r.dataset.i];
      tip.innerHTML = `<b>${bTitle(b.k)}</b><div class="row"><i style="background:var(--series-1)"></i>Dibuka: ${b.open}</div><div class="row"><i style="background:var(--series-2)"></i>Ditutup: ${b.closed}</div>`;
      const box = svg.getBoundingClientRect(), rb = r.getBoundingClientRect();
      tip.style.left = `${Math.min(box.width - 70, Math.max(70, rb.left - box.left + rb.width / 2))}px`;
      tip.style.top = `${Math.max(20, (y(Math.max(b.open, b.closed)) / H) * box.height)}px`;
      tip.classList.remove("hidden");
      r.setAttribute("fill", "rgba(30,34,37,.05)");
    };
    const off = () => { tip.classList.add("hidden"); r.setAttribute("fill", "transparent"); };
    r.addEventListener("mouseenter", on); r.addEventListener("mouseleave", off);
    r.addEventListener("touchstart", on, { passive: true });
  });
  const tO = B.reduce((a, b) => a + b.open, 0), tC = B.reduce((a, b) => a + b.closed, 0);
  $("#trendNote").textContent = `Dalam rentang ini: ${tO} dibuka, ${tC} ditutup. Punch open saat ini: ${data.kpi.open}.`;
  $("#trendTable").innerHTML = `<table class="list"><thead><tr><th>${gran === "week" ? "Minggu" : "Tanggal"}</th><th style="text-align:right">Dibuka</th><th style="text-align:right">Ditutup</th></tr></thead><tbody>${
    B.map((b) => `<tr><td>${bTitle(b.k)}</td><td style="text-align:right">${b.open}</td><td style="text-align:right">${b.closed}</td></tr>`).join("")}</tbody></table>`;
}
document.querySelectorAll("[data-gran]").forEach((b) => b.addEventListener("click", () => { gran = b.dataset.gran; store(LS_GRAN, gran); renderTrend(); }));
$("#trendTableBtn").addEventListener("click", () => {
  const t = $("#trendTable").classList.toggle("hidden");
  $("#trend").classList.toggle("hidden", !t);
  $("#trendTableBtn").textContent = t ? "Tabel" : "Grafik";
});

/* ---- tabel Kategori A */
const STATUS = { Open: ["Open", "var(--ng)"], "In Progress": ["Dikerjakan", "var(--warn)"], "Ready to Verify": ["Siap verifikasi", "var(--blue)"] };
function renderCrit() {
  const c = data.crit, t = data.today;
  $("#critSub").textContent = c.length ? `${c.length} punch · ${c.filter((i) => i.late).length} lewat target` : "";
  if (!c.length) { $("#crit").innerHTML = `<tbody><tr><td class="empty">Tidak ada punch Kategori A yang terbuka — tidak ada yang menahan energize.</td></tr></tbody>`; return; }
  $("#crit").innerHTML = `<thead><tr><th></th><th>Kode</th><th>Panel</th><th>Temuan</th><th>Status</th><th>PIC</th><th>Target</th><th style="text-align:right">Umur</th></tr></thead><tbody>${
    c.map((i) => {
      const [lab, col] = STATUS[i.status] || [i.status, "var(--na)"];
      const age = i.raised_date ? daysBetween(i.raised_date.slice(0, 10), t) : null;
      const lateBy = i.late ? daysBetween(i.due_date.slice(0, 10), t) : 0;
      return `<tr>
        <td><span class="sev" title="Kategori A · Critical">A</span></td>
        <td class="code">${esc(i.code)}</td>
        <td class="nowrap">${esc(i.tag)}</td>
        <td>${esc(i.title)}</td>
        <td class="nowrap"><span class="pill"><span class="lamp" style="background:${col}"></span>${esc(lab)}</span></td>
        <td>${esc(i.pic || "-")}</td>
        <td class="nowrap ${i.late ? "c-ng" : ""}">${i.due_date ? fmtDate(i.due_date) : "-"}${i.late ? `<br><b>lewat ${lateBy} hari</b>` : ""}</td>
        <td class="nowrap" style="text-align:right">${age !== null ? `${age} hari` : "-"}</td>
      </tr>`;
    }).join("")}</tbody>`;
}

let rz = 0;
window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (data && !$("#trend").classList.contains("hidden")) renderTrend(); }, 150); });
if (session?.refresh_token) start(); else show("vLogin");
