// Foto dari kamera/galeri: diputar sesuai EXIF, diperkecil maks 1600 px, disimpan JPEG 85% (sama dengan desktop).
export async function resizeImage(file: Blob, maxPx = 1600, quality = 0.85): Promise<Blob> {
  let bmp: ImageBitmap | null = null;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: "from-image" } as any);
  } catch {
    bmp = null;
  }
  let w: number, h: number, src: CanvasImageSource;
  if (bmp) {
    w = bmp.width; h = bmp.height; src = bmp;
  } else {
    const url = URL.createObjectURL(file);
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
    URL.revokeObjectURL(url);
    w = img.naturalWidth; h = img.naturalHeight; src = img;
  }
  const k = Math.min(1, maxPx / Math.max(w, h));
  const cw = Math.max(1, Math.round(w * k)), ch = Math.max(1, Math.round(h * k));
  const c = document.createElement("canvas");
  c.width = cw;
  c.height = ch;
  c.getContext("2d")!.drawImage(src, 0, 0, cw, ch);
  bmp?.close();
  return await new Promise<Blob>((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("gagal"))), "image/jpeg", quality));
}
