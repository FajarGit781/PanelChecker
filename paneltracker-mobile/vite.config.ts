import { defineConfig } from "vite";
import preact from "@preact/preset-vite";
import { createHash } from "node:crypto";
import { gunzipSync } from "node:zlib";
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

// Build produksi: CSP hanya mengizinkan koneksi ke Supabase (HTTPS).
// Build tes (PT_TEST=1): tambah server tiruan lokal.
const testConnect = process.env.PT_TEST ? "http://127.0.0.1:* http://localhost:*" : "";
const pkg = JSON.parse(readFileSync("package.json", "utf8"));

// Versi APK minimum yang bisa memakai bundle web ini lewat update otomatis (lihat src/updater.ts).
// Naikkan hanya bila bundle butuh plugin native baru (APK harus di-install ulang).
const MIN_NATIVE = "1.3.0";

// Mesin OCR (Tesseract) + data bahasa Inggris, disajikan dari aplikasi sendiri (offline, CSP 'self').
const OCR_FILES: [string, string][] = [
  ["ocr/worker.min.js", "node_modules/tesseract.js/dist/worker.min.js"],
  ["ocr/tesseract-core-simd-lstm.wasm.js", "node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm.js"],
  ["ocr/tesseract-core-lstm.wasm.js", "node_modules/tesseract.js-core/tesseract-core-lstm.wasm.js"],
];
// Data bahasa disajikan TANPA .gz: build Android (aapt) men-decompress aset *.gz dan membuang akhiran .gz,
// sehingga di APK file .gz tidak ada → OCR gagal. Tanpa kompresi, nama file sama di PWA dan APK.
const OCR_LANG: [string, string] = ["ocr/eng.traineddata", "node_modules/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz"];

const outDirRef = { dir: "dist" };

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

export default defineConfig({
  plugins: [
    preact(),
    {
      name: "pt-csp",
      transformIndexHtml: (html: string) => html.replace("%PT_TEST_CONNECT%", testConnect),
    },
    {
      name: "pt-ocr-assets",
      generateBundle() {
        for (const [fileName, src] of OCR_FILES) this.emitFile({ type: "asset", fileName, source: readFileSync(src) });
        this.emitFile({ type: "asset", fileName: OCR_LANG[0], source: gunzipSync(readFileSync(OCR_LANG[1])) });
      },
    },
    {
      // bundle.json: daftar file + sha256 → APK mengunduh hanya file yang berubah dari situs PWA (update otomatis)
      name: "pt-bundle-manifest",
      apply: "build",
      configResolved(c: any) { outDirRef.dir = c.build.outDir.startsWith("/") ? c.build.outDir : join(c.root, c.build.outDir); },
      closeBundle: {
        order: "post",
        sequential: true,
        handler() {
          const out = outDirRef.dir;
          const files = walk(out).map((p) => relative(out, p).split("\\").join("/"))
            .filter((p) => !["bundle.json", "_headers", "sw.js"].includes(p))
            .sort()
            .map((p) => ({ p, h: createHash("sha256").update(readFileSync(join(out, p))).digest("hex"), s: statSync(join(out, p)).size }));
          writeFileSync(join(out, "bundle.json"), JSON.stringify({ version: pkg.version, minNative: MIN_NATIVE, files }));
        },
      },
    } as any,
  ],
  base: "./",
  define: { __PT_TEST__: JSON.stringify(!!process.env.PT_TEST) },
  build: { outDir: "dist", target: "es2020", sourcemap: false },
  test: { environment: "node", testTimeout: 60000 },
} as any);
