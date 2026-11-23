// Foto dari kamera/galeri: diputar sesuai EXIF lalu dikompres sebelum disimpan/di-upload, supaya storage
// cloud 1 GB muat banyak foto. Aturan sama dengan desktop (app/imaging.py): sisi terpanjang maks 1280 px,
// target ≤ 150 KB; kualitas JPEG diturunkan bertahap (80→50%), lalu 1024 px bila masih terlalu besar.
export const MAX_PX = 1280;
export const TARGET = 150_000;
export const RECOMPRESS_ABOVE = 200_000;

async function decode(file: Blob): Promise<{ src: CanvasImageSource; w: number; h: number; close: () => void }> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" } as any);
    return { src: bmp, w: bmp.width, h: bmp.height, close: () => bmp.close() };
  } catch {
    const url = URL.createObjectURL(file);
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
    URL.revokeObjectURL(url);
    return { src: img, w: img.naturalWidth, h: img.naturalHeight, close: () => {} };
  }
}

function encode(src: CanvasImageSource, w: number, h: number, maxPx: number, quality: number): Promise<Blob> {
  const k = Math.min(1, maxPx / Math.max(w, h));
  const cw = Math.max(1, Math.round(w * k)), ch = Math.max(1, Math.round(h * k));
  const c = document.createElement("canvas");
  c.width = cw;
  c.height = ch;
  const g = c.getContext("2d")!;
  g.fillStyle = "#fff";                 // PNG transparan → latar putih
  g.fillRect(0, 0, cw, ch);
  g.drawImage(src, 0, 0, cw, ch);
  return new Promise<Blob>((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("gagal"))), "image/jpeg", quality));
}

export async function resizeImage(file: Blob, maxPx = MAX_PX, target = TARGET): Promise<Blob> {
  const d = await decode(file);
  try {
    let best: Blob | null = null;
    for (const px of [maxPx, 1024]) {
      for (const q of [0.8, 0.7, 0.6, 0.5]) {
        const b = await encode(d.src, d.w, d.h, px, q);
        if (!best || b.size < best.size) best = b;
        if (b.size <= target) return b;
      }
    }
    return best!;
  } finally {
    d.close();
  }
}

/** Sebelum upload: foto lama/besar dikompres ulang; yang sudah kecil (atau gagal diproses) dibiarkan. */
export async function shrinkIfLarge(blob: Blob): Promise<Blob> {
  if (blob.size <= RECOMPRESS_ABOVE) return blob;
  try {
    const out = await resizeImage(blob);
    return out.size < blob.size ? out : blob;
  } catch {
    return blob;
  }
}
