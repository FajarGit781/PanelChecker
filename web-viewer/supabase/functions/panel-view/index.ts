// Panel Tracker — endpoint publik HANYA BACA untuk viewer web (tanpa login).
//
// GET /functions/v1/panel-view?id=<uuid panel>
//   → data satu panel: info panel, checklist, punch list, dan link foto bertanda tangan (berlaku 1 jam).
//
// Keamanan:
// - Panel hanya bisa dibuka dengan uuid-nya (dari label QR). Tidak ada pencarian tag / daftar panel.
// - Data diambil lewat fungsi database public.pt_panel_view (security definer, hanya service_role yang boleh
//   memanggil). service_role tetap TIDAK punya hak SELECT tabel (hardening v2.6 tidak dibuka).
// - Service key hanya ada di server ini, tidak pernah dikirim ke browser. Tidak ada operasi tulis.

const URL_ = Deno.env.get("SUPABASE_URL")!;
const KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const BUCKET = "panel-photos";
const PHOTO_TTL = 3600;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
};
const H = { apikey: KEY, Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" };

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

type Att = { kind: string; caption: string; storage_path: string };
type Issue = Record<string, unknown> & { attachments: Att[] };

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "GET") return json(405, { error: "method_not_allowed" });

  const id = (new URL(req.url).searchParams.get("id") || "").trim().toLowerCase();
  if (!UUID_RE.test(id)) return json(404, { error: "not_found" });

  try {
    const r = await fetch(`${URL_}/rest/v1/rpc/pt_panel_view`, {
      method: "POST", headers: H, body: JSON.stringify({ p_id: id }),
    });
    if (!r.ok) throw new Error(`rpc HTTP ${r.status}: ${await r.text()}`);
    const data = await r.json();
    if (!data) return json(404, { error: "not_found" });

    // foto punch → signed URL (bucket tetap privat)
    const issues: Issue[] = data.issues || [];
    const paths = issues.flatMap((i) => i.attachments.map((a) => a.storage_path));
    const byPath = new Map<string, string>();
    if (paths.length) {
      const s = await fetch(`${URL_}/storage/v1/object/sign/${BUCKET}`, {
        method: "POST", headers: H, body: JSON.stringify({ expiresIn: PHOTO_TTL, paths }),
      });
      if (s.ok) {
        for (const x of await s.json()) if (x.signedURL && !x.error) byPath.set(x.path, `${URL_}/storage/v1${x.signedURL}`);
      } else {
        console.error("sign", s.status, await s.text());
      }
    }
    data.issues = issues.map(({ attachments, ...i }) => ({
      ...i,
      photos: attachments.filter((a) => byPath.has(a.storage_path))
        .map((a) => ({ kind: a.kind, caption: a.caption || "", url: byPath.get(a.storage_path) })),
    }));
    data.generated_at = new Date().toISOString();
    return json(200, data);
  } catch (e) {
    console.error(e);
    return json(500, { error: "server_error" });
  }
});
