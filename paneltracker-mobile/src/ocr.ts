// OCR foto layar HMI/BCU di HP (Tesseract, jalan di perangkat: gratis, tanpa API, foto tidak dikirim ke mana pun).
// Mesin & data bahasa ikut di dalam aplikasi (folder ocr/, disalin saat build) → tetap jalan tanpa sinyal.
// Dimuat hanya saat dipakai pertama kali (±10 MB), supaya aplikasi tetap ringan saat dibuka.

type Progress = (stage: string, pct: number) => void;
let worker: any = null;
let loading: Promise<any> | null = null;

const STAGE: Record<string, string> = {
  "loading tesseract core": "Memuat mesin OCR", "initializing tesseract": "Menyiapkan OCR",
  "loading language traineddata": "Memuat data bahasa", "initializing api": "Menyiapkan OCR", "recognizing text": "Membaca teks",
};
let onProg: Progress | undefined;

async function getWorker() {
  if (worker) return worker;
  if (!loading) {
    loading = (async () => {
      const T: any = (await import("tesseract.js")).default;
      const base = new URL("ocr/", document.baseURI).href;
      // workerBlobURL:false → worker dari file sendiri (CSP script-src 'self' tidak mengizinkan blob:)
      return T.createWorker("eng", 1, {
        workerPath: base + "worker.min.js", corePath: base.replace(/\/$/, ""), langPath: base.replace(/\/$/, ""),
        workerBlobURL: false, gzip: true, cacheMethod: "none",
        logger: (m: any) => onProg?.(STAGE[m.status] || "", Math.round((m.progress || 0) * 100)),
      });
    })();
  }
  try {
    worker = await loading;
  } catch (e) {
    loading = null;
    throw e;
  }
  return worker;
}

/** Pra-proses: skala ±1800 px, grayscale, balik warna bila latar gelap (LCD), naikkan kontras. */
async function prep(blob: Blob): Promise<HTMLCanvasElement> {
  const url = URL.createObjectURL(blob);
  try {
    const img = await new Promise<HTMLImageElement>((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
    const k = Math.min(2.5, 1800 / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * k);
    c.height = Math.round(img.naturalHeight * k);
    const g = c.getContext("2d", { willReadFrequently: true })!;
    g.drawImage(img, 0, 0, c.width, c.height);
    const d = g.getImageData(0, 0, c.width, c.height), px = d.data;
    let sum = 0;
    for (let i = 0; i < px.length; i += 4) { const y = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]; px[i] = y; sum += y; }
    const dark = sum / (px.length / 4) < 110;
    for (let i = 0; i < px.length; i += 4) {
      let y = px[i];
      if (dark) y = 255 - y;
      y = Math.max(0, Math.min(255, (y - 128) * 1.6 + 128));
      px[i] = px[i + 1] = px[i + 2] = y;
    }
    g.putImageData(d, 0, 0);
    return c;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Foto → teks per baris. onProgress dipanggil selama memuat mesin & membaca. */
export async function recognize(blob: Blob, onProgress?: Progress): Promise<string> {
  onProg = onProgress;
  try {
    const w = await getWorker();
    const canvas = await prep(blob);
    const { data } = await w.recognize(canvas);
    return data.text || "";
  } finally {
    onProg = undefined;
  }
}
