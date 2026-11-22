import { describe, expect, it } from "vitest";
import { tagFromQr, uuidFromQr } from "../src/logic";

describe("isi QR label panel", () => {
  it("label baru: uuid + tag", () => {
    const q = "PT:D0AB213F-7141-47e9-aff7-b9f463a375fe:ET09+R1 & ET09+W1";
    expect(uuidFromQr(q)).toBe("d0ab213f-7141-47e9-aff7-b9f463a375fe");
    expect(tagFromQr(q)).toBe("ET09+R1 & ET09+W1");
  });
  it("label lama: nomor lokal diabaikan, pakai tag", () => {
    expect(uuidFromQr("PT:12:=E00+X1")).toBeUndefined();
    expect(tagFromQr("PT:12:=E00+X1")).toBe("=E00+X1");
  });
  it("tag biasa / baris baru dirapikan", () => {
    expect(tagFromQr("  =EU01+WR1 ")).toBe("=EU01+WR1");
    expect(tagFromQr("PT:x:COMMON IED\nPANEL")).toBe("COMMON IED PANEL");
  });
  it("label v2.7.2: link viewer web", () => {
    const q = "https://panel-viewer.example.app/?p=D0AB213F-7141-47e9-aff7-b9f463a375fe";
    expect(uuidFromQr(q)).toBe("d0ab213f-7141-47e9-aff7-b9f463a375fe");
    expect(uuidFromQr("https://h.example/v?x=1&p=d0ab213f-7141-47e9-aff7-b9f463a375fe")).toBe("d0ab213f-7141-47e9-aff7-b9f463a375fe");
    expect(tagFromQr(q)).toBe("");
    expect(uuidFromQr("https://panel-viewer.example.app/")).toBeUndefined();
  });
});
