// Dijalankan oleh tests/run_interop.py (server tiruan + aplikasi desktop di sisi Python).
import "fake-indexeddb/auto";
import { describe, expect, it } from "vitest";
import { Api } from "../src/api";
import { checkStats, nextIssueCode, passwordProblems, stamp } from "../src/logic";
import { store } from "../src/store";
import { SyncEngine } from "../src/sync";
import { panelOverview } from "../src/data";

const URL_ = process.env.MOCK_URL!;
const PHASE = process.env.PHASE!;

async function login(email: string, pw: string) {
  const api = new Api(URL_, "sb_publishable_test");
  await api.signIn(email, pw);
  return api;
}

describe("mobile ↔ desktop", () => {
  it("phase " + PHASE, async () => {
    await store.open();
    if (PHASE === "edit") {
      const api = await login("a@test.id", "Kuat-Sekali-123a");
      const st = await new SyncEngine(api).run();
      console.log("pull:", JSON.stringify(st));
      const pr = store.all("projects")[0];
      expect(pr).toBeTruthy();
      const ov = panelOverview(pr.uuid);
      expect(ov.length).toBe(18);
      // ubah hasil cek item pertama yang belum dicek di panel pertama yang masih ada item kosong
      const tgt = ov.find((o) => o.stats.pending > 0)!;
      const check = store.all("panel_checks").filter((c) => c.panel_uuid === tgt.panel.uuid && !c.result)[0];
      await store.edit("panel_checks", check.uuid, { result: "NG", checked_by: "HP-Tes", checked_at: "2026-11-19T10:00:00", remark: "dari HP" });
      // punch baru dengan foto
      const issues = store.all("issues", true).filter((i) => i.project_uuid === pr.uuid);
      const code = nextIssueCode(pr, issues);
      const iss = await store.create("issues", { project_uuid: pr.uuid, site_uuid: tgt.panel.site_uuid, panel_uuid: tgt.panel.uuid,
        check_uuid: check.uuid, code, title: "Temuan dari HP", severity: "Critical", status: "Open", category: "Wiring",
        raised_by: "HP-Tes", raised_date: "2026-11-19", due_date: "2026-11-22" });
      const att = await store.create("attachments", { issue_uuid: iss.uuid, kind: "before", filename: "hp.jpg", caption: "", storage_path: null });
      const jpg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 0xff, 0xd9]);
      await store.setPhoto(att.uuid, new Blob([jpg], { type: "image/jpeg" }));
      // ubah status punch yang sudah ada
      const old = issues.find((i) => i.status === "Open" && !i.deleted)!;
      await store.edit("issues", old.uuid, { status: "In Progress", action: "dikerjakan dari HP" });
      expect(store.pendingCount()).toBe(4);
      const st2 = await new SyncEngine(api).run();
      console.log("push:", JSON.stringify(st2));
      expect(st2.photos_up).toBe(1);
      expect(store.pendingCount()).toBe(0);
      // foto dari desktop bisa diunduh
      const withPath = store.all("attachments").filter((a) => a.storage_path && a.uuid !== att.uuid);
      const blob = await SyncEngine.ensurePhoto(api, withPath[0]);
      expect(blob && blob.size).toBeGreaterThan(100);
      console.log(JSON.stringify({ code, issue: iss.uuid, check: check.uuid, old: old.uuid, panel: tgt.panel.tag }));
    }
    if (PHASE === "viewer") {
      await store.wipe();
      const api = await login("v@test.id", "Lihat-Saja-77x");
      const st = await new SyncEngine(api, false).run();
      expect(st.pulled).toBeGreaterThan(100);
      expect(store.all("issues").some((i) => i.title === "Temuan dari HP")).toBe(true);
      expect(store.all("issues").some((i) => i.title === "Diubah di laptop")).toBe(true);
      console.log("viewer ok", JSON.stringify(st));
    }
    if (PHASE === "unit") {
      expect(passwordProblems("P@ssw0rd", "fajar@paneltracker.local").length).toBeGreaterThan(0);
      expect(passwordProblems("Gardu-Induk-2026x", "fajar@paneltracker.local")).toEqual([]);
      expect(stamp()).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$/);
      expect(nextIssueCode({ issue_prefix: "GA2" }, [{ code: "GA2-0009" }, { code: "GA2-0110" }])).toBe("GA2-0111");
      expect(checkStats([{ result: "OK" }, { result: "NG" }, { result: "" }]).pending).toBe(1);
      expect(() => new Api("http://evil.com", "sb_publishable_x")).toThrow();
      expect(() => new Api("https://x.supabase.co", "sb_secret_x")).toThrow();
    }
  });
});
