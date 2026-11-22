import jsQR from "jsqr";
import { useEffect, useRef, useState } from "preact/hooks";
import { panelsOf } from "../data";
import { t } from "../i18n";
import { tagFromQr, uuidFromQr } from "../logic";
import { store } from "../store";
import { Icon, useNav } from "./common";

/** Cari panel dari isi QR / tag (di project aktif dulu, lalu semua project). */
export function findPanel(project: string, text: string) {
  const id = uuidFromQr(text);
  if (id) {
    const p = store.get("panels", id);
    if (p && !p.deleted) return p;
  }
  const tag = tagFromQr(text).toLowerCase();
  if (!tag) return undefined;
  const inProject = project ? panelsOf(project) : [];
  const norm = (x: any) => String(x || "").replace(/\s+/g, " ").trim().toLowerCase();
  return inProject.find((p) => norm(p.tag) === tag) ||
    store.all("panels").find((p) => !p.deleted && norm(p.tag) === tag);
}

export function Scan() {
  const nav = useNav();
  const video = useRef<HTMLVideoElement>(null);
  const [err, setErr] = useState("");
  const [manual, setManual] = useState("");
  const [active, setActive] = useState(true);

  function open(text: string) {
    const p = findPanel(nav.project, text);
    if (!p) { setErr(t("Panel {0} tidak ada di data HP. Cek tag-nya, atau sinkron dulu.", tagFromQr(text))); return false; }
    const site = store.get("sites", p.site_uuid);
    if (site && site.project_uuid !== nav.project) nav.setProject(site.project_uuid);
    nav.go({ name: "panel", id: p.uuid });
    return true;
  }

  useEffect(() => {
    if (!active) return;
    let stream: MediaStream | null = null, raf = 0, stopped = false;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true } as any) as CanvasRenderingContext2D;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
        if (stopped) { stream.getTracks().forEach((x) => x.stop()); return; }
        const v = video.current!;
        v.srcObject = stream;
        await v.play();
        const tick = () => {
          if (stopped) return;
          if (v.readyState >= 2 && v.videoWidth) {
            const k = Math.min(1, 640 / v.videoWidth);
            canvas.width = Math.round(v.videoWidth * k);
            canvas.height = Math.round(v.videoHeight * k);
            ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
            const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const code = jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" });
            if (code && code.data) {
              if (navigator.vibrate) navigator.vibrate(80);
              if (open(code.data)) { stopped = true; return; }
            }
          }
          raf = requestAnimationFrame(tick);
        };
        tick();
      } catch (e: any) {
        setErr(t("Kamera tidak bisa dibuka. Izinkan akses kamera di pengaturan HP, atau ketik tag panel."));
      }
    })();
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((x) => x.stop());
    };
  }, [active]);

  return (
    <div class="scan-wrap">
      <video ref={video} playsInline muted />
      <div class="scan-top">
        <button class="back-btn" aria-label={t("Kembali")} onClick={() => nav.back()}><Icon name="back" size={26} /></button>
        <h1>{t("Scan label panel")}</h1>
      </div>
      <div class="viewfinder"><i /><i /><i /><i /><div class="laser" /></div>
      <div class="scan-bottom">
        <p>{t("Arahkan kamera ke label QR di pintu panel. Checklist panel langsung terbuka.")}</p>
        {err && <div class="msg err">{err}</div>}
        <form class="row" onSubmit={(e) => { e.preventDefault(); setErr(""); open(manual); }}>
          <input class="input grow" placeholder={t("Atau ketik tag, mis. TRAFO-9")} autoCapitalize="characters" value={manual}
            style={{ fontFamily: "var(--cond)", fontWeight: 600, letterSpacing: ".5px" }}
            onInput={(e: any) => setManual(e.currentTarget.value)} />
          <button class="btn primary">{t("Buka panel")}</button>
        </form>
        {!active && <button class="btn block" style={{ marginTop: 10 }} onClick={() => setActive(true)}>{t("Nyalakan kamera")}</button>}
      </div>
    </div>
  );
}
