import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// Build produksi: CSP hanya mengizinkan koneksi ke Supabase (HTTPS).
// Build tes (PT_TEST=1): tambah server tiruan lokal.
const testConnect = process.env.PT_TEST ? "http://127.0.0.1:* http://localhost:*" : "";

export default defineConfig({
  plugins: [
    preact(),
    {
      name: "pt-csp",
      transformIndexHtml: (html: string) => html.replace("%PT_TEST_CONNECT%", testConnect),
    },
  ],
  base: "./",
  define: { __PT_TEST__: JSON.stringify(!!process.env.PT_TEST) },
  build: { outDir: "dist", target: "es2020", sourcemap: false },
  test: { environment: "node", testTimeout: 60000 },
} as any);
