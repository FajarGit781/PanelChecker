"""Checksheet integrasi SAS per panel GAIA 2 (ringkas), berdasarkan drawing E2010-96564-BD-01-SAD rev A2.

Per device cukup 5 item:
  1. Terintegrasi ke SAS (online di HMI SAS 1 & 2)
  2. IP address sudah dikonfigurasi (subnet bay dari drawing, IP aktual diisi di kolom nilai)
  3. SNTP sudah dikonfigurasi & waktu sinkron
  4. File CID sudah diupload
  5. Setting sudah diupload (approval setting baru keluar saat SAT, jadi tidak dicek di sini)
Perangkat panel SAS 1/2 (GPS, Gateway, SAS Server, Workstation) tidak punya CID/setting relay → item 1–3 saja.
Blok terakhir "Rasio CT/VT": per IED yang punya input analog, 2 item (CT ratio & VT ratio) — rasio aktual
diisi di kolom nilai (mis. "2000/1 A", "150000/110 V"); N/A bila device tidak memakai CT/VT.

Menghasilkan SQL ringkas yang:
  - menambah item ke setiap panel GAIA2 (panel_checks) dan memperbarui template "SAS · …" (check_templates);
  - menandai terhapus (soft delete) item SAS versi sebelumnya yang BELUM diisi.
Checklist & hasil checking lainnya tidak disentuh. uuid deterministik (uuid5) → aman dijalankan ulang.

Pemakaian:
  python tools/sas_checksheet_gaia2.py panels.json > sas_gaia2.sql
  (panels.json = [{"uuid","tag","max_sort"}...]; max_sort = sort terbesar checklist non-SAS panel tsb)
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import uuid

NS = uuid.UUID("7d2b9a40-5c1e-4f63-9d8a-3e1b2c4d5f60")   # namespace checksheet SAS GAIA 2
DRAWING = "E2010-96564-BD-01-SAD rev A2"
LETTERS = "IJKLMNOPQRSTUVWXYZ"


# ------------------------------------------------------------------------------------------- item
def ied_items():
    """5 item per IED / device bay. {net} = kriteria subnet bay, diganti per panel."""
    return [
        ("Device terintegrasi ke SAS (online di HMI SAS 1 & 2)", "Online", ""),
        ("IP address sudah dikonfigurasi", "{net}", "IP"),
        ("SNTP sudah dikonfigurasi & waktu sinkron", "Sync OK", ""),
        ("File CID sudah diupload", "Terupload", "rev CID"),
        ("Setting sudah diupload", "Terupload", "rev"),
    ]


def sas_items():
    """Perangkat panel SAS: tanpa CID / setting relay."""
    return [
        ("Device terintegrasi ke SAS (terhubung & online)", "Online", ""),
        ("IP address sudah dikonfigurasi", "{net}", "IP"),
        ("SNTP sudah dikonfigurasi & waktu sinkron", "Sync OK", ""),
    ]


RATIO_UNIT = "rasio"
RATIO_SECTION = "Rasio CT/VT"


def ratio_items(devs):
    """CT & VT ratio untuk setiap device yang punya input analog (bukan Common I/O)."""
    out = []
    for name in devs:
        out.append((f"{name} · CT ratio", "Sesuai drawing (prim/sek)", RATIO_UNIT))
        out.append((f"{name} · VT ratio", "Sesuai drawing (prim/sek)", RATIO_UNIT))
    return out


# ------------------------------------------------------------------------------------------- device per tipe panel
DEV = {
    "C264": "-A30 MiCOM C264 (BCU)",
    "C264IO": "MiCOM C264 Common I/O",
    "P643": "-F87T MiCOM P643",
    "P501": "-P501 Easergy P5F30",
    "P502": "-P502 Easergy P5F30",
    "P5": "-P5 Easergy P5F30",
    "P841": "-F50BF MiCOM P841",
    "P143": "-F50 MiCOM P143",
    "PCS931": "-F87L NR PCS-931",
    "P746_1": "-F87B1 MiCOM P746",
    "P746_2": "-F87B2 MiCOM P746",
    "P746_3": "-F87B3 MiCOM P746",
    "PM8240": "-PM PM8240",
    "RTF": "-N90 RTF",
}
NO_RATIO = {"C264IO"}   # tanpa input CT/VT
TYPES = {
    "TR_PROT": dict(title="Trafo Protection (=ETxx+R1)", devs=["P643", "P501", "P502", "P841"]),
    "TR_CTRL": dict(title="Trafo Control (=ETxx+W1)", devs=["C264", "PM8240", "RTF"]),
    "UGC": dict(title="UGC Control & Protection (=EUxx+WR1)", devs=["C264", "PCS931", "P5", "PM8240", "P841"]),
    "BCS": dict(title="Bus Coupler / Bus Section (=ECxx/ESxx+WR1)", devs=["C264", "P143", "P841"]),
    "BB": dict(title="Busbar Protection (=E00+R1/R2)", devs=["P746_1", "P746_2", "P746_3"]),
    "CIO": dict(title="Common IED I/O (=E00+X1/X2)", devs=["C264IO"]),
}
SAS_DEV = {
    "X3": ["GPS Time Server", "Gateway RCC (IEC 104)", "SAS Server 1", "Workstation 1"],
    "X4": ["Gateway ECMS (Modbus TCP)", "SAS Server 2", "Workstation 2"],
}


def classify(tag: str):
    """Tag panel → (tipe-tipe, subnet, panel SAS). Subnet dari label drawing: 172.16.<n>.x."""
    t = tag.replace(" ", "").upper()
    if (m := re.search(r"ET(\d\d)\+R1&=?ET\d\d\+W1", t)):
        return ["TR_PROT", "TR_CTRL"], f"172.16.{int(m.group(1))}.x", None
    if (m := re.fullmatch(r"=?ET(\d\d)\+R1", t)):
        return ["TR_PROT"], f"172.16.{int(m.group(1))}.x", None
    if (m := re.fullmatch(r"=?ET(\d\d)\+W1", t)):
        return ["TR_CTRL"], f"172.16.{int(m.group(1))}.x", None
    if (m := re.fullmatch(r"=?EU(\d\d)\+WR1", t)):
        return ["UGC"], f"172.16.{10 + int(m.group(1))}.x", None
    if (m := re.fullmatch(r"=?EC(\d\d)\+WR1", t)):
        return ["BCS"], f"172.16.{12 + int(m.group(1))}.x", None
    if (m := re.fullmatch(r"=?ES(\d\d)\+WR1", t)):
        return ["BCS"], f"172.16.{14 + int(m.group(1))}.x", None
    if (m := re.fullmatch(r"=?E00\+R([12])", t)):
        return ["BB"], f"172.16.{12 + int(m.group(1))}.x", None
    if re.fullmatch(r"=?E00\+X[12]", t):
        return ["CIO"], "", None
    if (m := re.fullmatch(r"=?E00\+(X[34])", t)):
        return [], "", m.group(1)
    return None, "", None


def blocks_for(types, sas=None):
    """[(nama device, items)] dengan {net} belum diganti."""
    if sas:
        return [(n, sas_items()) for n in SAS_DEV[sas]]
    out, seen = [], set()
    for ty in types:
        for dv in TYPES[ty]["devs"]:
            if dv not in seen:
                seen.add(dv)
                out.append((DEV[dv], ied_items()))
    ratio = [DEV[d] for ty in types for d in TYPES[ty]["devs"] if d not in NO_RATIO]
    ratio = list(dict.fromkeys(ratio))
    if ratio:   # blok terakhir → sort-nya setelah semua item SAS yang sudah ada
        out.append((RATIO_SECTION, ratio_items(ratio)))
    return out


def net_text(subnet):
    return f"Subnet {subnet}" if subnet else "Sesuai IP plan"


def sections_for(types, subnet, sas=None):
    """[(section, [(desc, criteria, unit)])] — huruf I, J, K, …"""
    net = net_text(subnet)
    return [(f"{LETTERS[i]}. SAS · {name}", [(d, c.replace("{net}", net), u) for d, c, u in its])
            for i, (name, its) in enumerate(blocks_for(types, sas))]


def template_defs():
    defs = []
    for key, ty in TYPES.items():
        defs.append((f"SAS · {ty['title']}", sections_for([key], "172.16.<no. bay>.x")))
    for x in ("X3", "X4"):
        defs.append((f"SAS · SAS {'1' if x == 'X3' else '2'} Panel / Gateway (=E00+{x})", sections_for([], "", x)))
    return defs


# ------------------------------------------------------------------------------------------- SQL
def compact_sql(panels):
    """SQL ringkas: definisi blok dikirim sekali sebagai JSON, item dibuat di database
    (extensions.uuid_generate_v5 — hasil uuid identik dengan uuid.uuid5 di sini)."""
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    local = (now + dt.timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S")
    blocks = {}

    def bid(name, items):
        k = json.dumps([name, items], ensure_ascii=False)
        if k not in blocks:
            blocks[k] = {"id": len(blocks), "name": name, "items": [list(i) for i in items]}
        return blocks[k]["id"]

    plist = []
    for p in panels:
        types, subnet, sas = classify(p["tag"])
        if types is None:
            continue
        plist.append({"uuid": p["uuid"], "max_sort": int(p.get("max_sort") or 0), "net": net_text(subnet),
                      "blocks": [bid(n, its) for n, its in blocks_for(types, sas)]})
    tpls = []
    for key, ty in TYPES.items():
        n = f"SAS · {ty['title']}"
        tpls.append({"uuid": str(uuid.uuid5(NS, "template:" + n)), "name": n, "net": net_text("172.16.<no. bay>.x"),
                     "blocks": [bid(nm, its) for nm, its in blocks_for([key])]})
    for x in ("X3", "X4"):
        n = f"SAS · SAS {'1' if x == 'X3' else '2'} Panel / Gateway (=E00+{x})"
        tpls.append({"uuid": str(uuid.uuid5(NS, "template:" + n)), "name": n, "net": net_text(""),
                     "blocks": [bid(nm, its) for nm, its in blocks_for([], x)]})
    data = {"ns": str(NS), "stamp": stamp, "local": local, "letters": LETTERS,
            "desc": "Integrasi SAS: terintegrasi, IP, SNTP, CID & setting terupload, rasio CT/VT. Ref " + DRAWING,
            "blocks": sorted(blocks.values(), key=lambda b: b["id"]), "panels": plist, "templates": tpls}
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"""-- Checksheet integrasi SAS GAIA 2 (ringkas, {DRAWING}). Dibuat {stamp}. Aman dijalankan ulang.
with d as (select $sas${js}$sas$::jsonb j),
titems as (
  select t->>'uuid' tu, t->>'name' tn,
         jsonb_agg(jsonb_build_array(substr(d.j->>'letters', bo::int, 1) || '. SAS · ' || (d.j->'blocks'->(b::int)->>'name'),
                   it->>0, replace(it->>1, '{{net}}', t->>'net'), it->>2) order by bo, io) items
  from d, jsonb_array_elements(d.j->'templates') t,
       jsonb_array_elements_text(t->'blocks') with ordinality as bl(b, bo),
       jsonb_array_elements(d.j->'blocks'->(b::int)->'items') with ordinality as its(it, io)
  group by 1, 2),
tpl as (
  insert into public.check_templates(uuid,name,description,items,created_at,updated_at,deleted)
  select tu::uuid, tn, (select j->>'desc' from d), items, (select j->>'local' from d), (select j->>'stamp' from d), 0
  from titems
  on conflict (uuid) do update set items = excluded.items, description = excluded.description,
                                   updated_at = excluded.updated_at, deleted = 0
  returning 1),
rows as (
  select p->>'uuid' pu, (p->>'max_sort')::int ms, p->>'net' net,
         substr(d.j->>'letters', bo::int, 1) || '. SAS · ' || (d.j->'blocks'->(b::int)->>'name') sec, it, bo, io
  from d, jsonb_array_elements(d.j->'panels') p,
       jsonb_array_elements_text(p->'blocks') with ordinality as bl(b, bo),
       jsonb_array_elements(d.j->'blocks'->(b::int)->'items') with ordinality as its(it, io)),
newrows as (
  select extensions.uuid_generate_v5((select (j->>'ns')::uuid from d), pu || '|' || sec || '|' || (it->>0)) cu, *
  from rows),
old as (
  update public.panel_checks c set deleted = 1, updated_at = (select j->>'stamp' from d)
  where c.section like '_. SAS · %' and c.deleted = 0
    and coalesce(c.result,'') = '' and coalesce(c.value,'') = '' and coalesce(c.remark,'') = ''
    and c.uuid not in (select cu from newrows)
    and c.panel_uuid in (select (p->>'uuid')::uuid from d, jsonb_array_elements(d.j->'panels') p)
  returning 1),
ins as (
  insert into public.panel_checks(uuid,panel_uuid,section,description,criteria,unit,sort,result,value,remark,
                                  checked_by,checked_at,created_at,updated_at,deleted)
  select cu, pu::uuid, sec, it->>0, replace(it->>1, '{{net}}', net), it->>2,
         ms + row_number() over (partition by pu order by bo, io), '', '', '', '', null,
         (select j->>'local' from d), (select j->>'stamp' from d), 0
  from newrows
  on conflict (uuid) do nothing returning 1)
select (select count(*) from tpl) template_diperbarui, (select count(*) from old) item_lama_dihapus,
       (select count(*) from ins) item_baru;"""


def expected_rows(panels):
    """Daftar (uuid, panel_uuid, section, desc, criteria, unit, sort) yang seharusnya dibuat — untuk verifikasi."""
    out = []
    for p in panels:
        types, subnet, sas = classify(p["tag"])
        if types is None:
            continue
        srt = int(p.get("max_sort") or 0)
        for s, its in sections_for(types, subnet, sas):
            for d, c, u in its:
                srt += 1
                out.append((str(uuid.uuid5(NS, f"{p['uuid']}|{s}|{d}")), p["uuid"], s, d, c, u, srt))
    return out


if __name__ == "__main__":
    pan = json.load(open(sys.argv[1]))
    print(compact_sql(pan))
    for p in pan:
        types, subnet, sas = classify(p["tag"])
        n = sum(len(i) for _, i in sections_for(types, subnet, sas)) if types is not None else 0
        print(f"-- {p['tag']!r}: {n} item ({subnet or sas or 'IP plan'})", file=sys.stderr)
