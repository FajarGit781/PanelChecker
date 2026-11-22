import { describe, expect, it } from "vitest";
import { ipWarning, isSasSection, nextResult, sasMatrix, subnetPrefix } from "../src/sas";

const mk = (section: string, description: string, extra: Record<string, any> = {}) =>
  ({ uuid: section + description, section, description, criteria: "", result: "", ...extra });

describe("matriks SAS", () => {
  it("item SAS dipetakan per device × 5 kolom; seksi lain diabaikan", () => {
    const rows = [
      mk("A. Visual & Mekanikal", "Kondisi fisik"),
      ...["Device terintegrasi ke SAS (online di HMI SAS 1 & 2)", "IP address sudah dikonfigurasi",
        "SNTP sudah dikonfigurasi & waktu sinkron", "File CID sudah diupload", "Setting sudah diupload"]
        .map((d) => mk("I. SAS · -F87T MiCOM P643", d)),
      mk("J. SAS · GPS Time Server", "IP address sudah dikonfigurasi"),
      mk("J. SAS · GPS Time Server", "Item tambahan lain"),
    ];
    const m = sasMatrix(rows);
    expect(m.map((d) => d.name)).toEqual(["-F87T MiCOM P643", "GPS Time Server"]);
    expect(Object.keys(m[0].cells).sort()).toEqual(["cid", "int", "ip", "set", "sntp"]);
    expect(Object.keys(m[1].cells)).toEqual(["ip"]);
    expect(m[1].extra.map((c) => c.description)).toEqual(["Item tambahan lain"]);
    expect(isSasSection("A. Visual & Mekanikal")).toBe(false);
    expect(isSasSection("M. SAS · -A30 MiCOM C264 (BCU)")).toBe(true);
  });
  it("tap sel berputar kosong → OK → NG → N/A → kosong", () => {
    expect([nextResult(""), nextResult("OK"), nextResult("NG"), nextResult("NA")]).toEqual(["OK", "NG", "NA", ""]);
  });
  it("validasi IP: format, subnet bay, dobel", () => {
    expect(subnetPrefix("Subnet 172.16.9.x")).toBe("172.16.9.");
    const used = new Map([["172.16.9.12", "=ET09+R1 · -P501 Easergy P5F30"]]);
    expect(ipWarning("", "Subnet 172.16.9.x", used)).toBe("");
    expect(ipWarning("172.16.9.11", "Subnet 172.16.9.x", used)).toBe("");
    expect(ipWarning("172.16.90.11", "Subnet 172.16.9.x", used)).toMatch(/luar subnet/);
    expect(ipWarning("172.16.9.300", "Subnet 172.16.9.x", used)).toMatch(/tidak valid/);
    expect(ipWarning("172.16.9.12", "Subnet 172.16.9.x", used)).toMatch(/Sudah dipakai/);
    expect(ipWarning("10.0.0.5", "Sesuai IP plan", used)).toBe("");
  });
});
