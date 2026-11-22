import { useState } from "preact/hooks";
import { APP_VERSION } from "../config";
import { getLang, setLang, t } from "../i18n";
import { displayUser, passwordProblems } from "../logic";
import { store } from "../store";
import { session } from "../session";
import { Lamp, LAMP } from "./common";

export function Login({ onDone }: { onDone: () => void }) {
  const [user, setUser] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [weak, setWeak] = useState(false);

  async function submit(e: Event) {
    e.preventDefault();
    if (!user.trim() || !pw) { setErr(t("Isi username dan password.")); return; }
    setBusy(true);
    setErr("");
    try {
      const r = await session.login(user, pw);
      setPw("");
      if (r === "weak") setWeak(true);
      else onDone();
    } catch (ex: any) {
      setErr(ex.message || String(ex));
    } finally {
      setBusy(false);
    }
  }

  if (weak) return <ChangePassword forced onDone={onDone} onCancel={async () => { await session.cancelPending(); setWeak(false); }} />;

  return (
    <div class="login">
      <div class="head">
        <div class="plate"><div class="tag" style={{ fontSize: 22 }}>PANEL TRACKER</div><div class="name">{t("Checklist & punch list commissioning")}</div></div>
        <h1>{t("Masuk ke tim")}</h1>
        <p>{t("Pakai username dan password dari admin.")}</p>
      </div>
      <form onSubmit={submit}>
        {err && <div class="msg err">{err}</div>}
        <div class="field">
          <label for="u">{t("Username")}</label>
          <input id="u" autoCapitalize="none" autoCorrect="off" autoComplete="username" value={user}
            placeholder={t("mis. Fajar")} onInput={(e: any) => setUser(e.currentTarget.value)} />
        </div>
        <div class="field">
          <label for="p">{t("Password")}</label>
          <input id="p" type="password" autoComplete="current-password" value={pw} onInput={(e: any) => setPw(e.currentTarget.value)} />
        </div>
        <button class="btn primary block" disabled={busy}>{busy ? t("Memeriksa…") : t("Masuk")}</button>
        <p class="small muted" style={{ marginTop: 16 }}>
          {t("Data disimpan di HP supaya tetap bisa dipakai tanpa sinyal, dan dihapus saat keluar akun.")}
        </p>
      </form>
      <div class="foot">
        <span>v{APP_VERSION}</span>
        <button class="btn sm" type="button" onClick={() => { setLang(getLang() === "id" ? "en" : "id"); location.reload(); }}>
          {getLang() === "id" ? "English" : "Bahasa Indonesia"}
        </button>
      </div>
    </div>
  );
}

export function ChangePassword({ forced, onDone, onCancel }: { forced?: boolean; onDone: () => void; onCancel: () => void }) {
  const [old, setOld] = useState("");
  const [n1, setN1] = useState("");
  const [n2, setN2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const email = session.pendingApi?.email || session.info?.email || "";
  const rules: [string, boolean][] = [
    [t("Minimal 10 karakter"), n1.length >= 10],
    [t("Ada huruf dan angka"), /[A-Za-z]/.test(n1) && /[0-9]/.test(n1)],
    [t("Bukan password umum, tidak memuat username"), !!n1 && !passwordProblems(n1, email).some((p) => p.startsWith("terlalu"))],
    [t("Kedua isian sama"), !!n1 && n1 === n2],
  ];
  const ok = rules.every(([, v]) => v);

  async function save(e: Event) {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    setErr("");
    try {
      await session.changePassword(n1, forced ? undefined : old);
      onDone();
    } catch (ex: any) {
      setErr(ex.message || String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div class="login">
      <div class="head">
        <h1>{t("Ganti password")}</h1>
        <p>{forced ? t("Password bawaan dari admin terlalu mudah ditebak. Buat password pribadi sebelum mulai bekerja.")
          : t("Password baru berlaku di HP dan laptop.")}</p>
      </div>
      <form onSubmit={save}>
        {err && <div class="msg err">{err}</div>}
        {!forced && <div class="field"><label for="o">{t("Password sekarang")}</label>
          <input id="o" type="password" autoComplete="current-password" value={old} onInput={(e: any) => setOld(e.currentTarget.value)} /></div>}
        <div class="field"><label for="n1">{t("Password baru")}</label>
          <input id="n1" type="password" autoComplete="new-password" value={n1} onInput={(e: any) => setN1(e.currentTarget.value)} /></div>
        <div class="field"><label for="n2">{t("Ulangi password baru")}</label>
          <input id="n2" type="password" autoComplete="new-password" value={n2} onInput={(e: any) => setN2(e.currentTarget.value)} /></div>
        <div class="sheet" style={{ padding: "6px 0" }}>
          {rules.map(([lab, v]) => (
            <div class="row" style={{ padding: "6px 14px", fontSize: 14 }}><Lamp color={v ? LAMP.green : LAMP.off} />{lab}</div>
          ))}
        </div>
        <div class="row">
          <button type="button" class="btn grow" onClick={onCancel}>{t("Batal")}</button>
          <button class="btn primary grow" disabled={busy || !ok}>{busy ? t("Menyimpan…") : t("Simpan password")}</button>
        </div>
      </form>
    </div>
  );
}

/** Sesi berakhir (akun yang sama keluar di perangkat lain / password diganti). Data di HP tetap disimpan. */
export function Relogin() {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const user = displayUser(session.info?.email || "");
  const pend = session.readOnly ? 0 : store.pendingCount();

  async function submit(e: Event) {
    e.preventDefault();
    if (!pw) { setErr(t("Isi password.")); return; }
    setBusy(true);
    setErr("");
    try {
      await session.relogin(pw);
      setPw("");
    } catch (ex: any) {
      setErr(ex.message || String(ex));
    } finally {
      setBusy(false);
    }
  }

  async function other() {
    const msg = pend > 0
      ? t("{0} perubahan belum terkirim ke cloud dan akan hilang. Tetap keluar?", pend)
      : t("Keluar dari akun? Data di HP ini dihapus; data di cloud tetap aman.");
    if (confirm(msg)) await session.logout();
  }

  return (
    <div class="login">
      <div class="head">
        <div class="plate"><div class="tag" style={{ fontSize: 22 }}>PANEL TRACKER</div><div class="name">{t("Checklist & punch list commissioning")}</div></div>
        <h1>{t("Login ulang")}</h1>
        <p>{t("Sesi akun {0} berakhir, mis. karena akun yang sama keluar di perangkat lain atau password diganti.", user)}</p>
      </div>
      <form onSubmit={submit}>
        {err && <div class="msg err">{err}</div>}
        <div class={pend ? "msg warn" : "msg ok"} style={{ marginTop: 0 }}>
          {pend > 0
            ? t("{0} perubahan belum terkirim tetap aman di HP ini dan langsung dikirim setelah login.", pend)
            : t("Data di HP ini tetap disimpan.")}
        </div>
        <div class="field">
          <label for="u">{t("Username")}</label>
          <input id="u" value={user} disabled autoComplete="username" />
        </div>
        <div class="field">
          <label for="p">{t("Password")}</label>
          <input id="p" type="password" autoComplete="current-password" value={pw} autoFocus
            onInput={(e: any) => setPw(e.currentTarget.value)} />
        </div>
        <button class="btn primary block" disabled={busy}>{busy ? t("Memeriksa…") : t("Masuk lagi")}</button>
        <button class="btn block" type="button" disabled={busy} onClick={other} style={{ marginTop: 10 }}>
          {t("Pakai akun lain (hapus data di HP ini)")}
        </button>
      </form>
      <div class="foot"><span>v{APP_VERSION}</span></div>
    </div>
  );
}
