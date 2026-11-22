"""Matriks integrasi SAS: item checklist "X. SAS · <device>" → baris device × 5 kolom.

Aturan sama dengan aplikasi HP (paneltracker-mobile/src/sas.ts):
  kolom   Integrasi · IP · SNTP · CID · Setting (dicocokkan dari deskripsi item)
  tap     kosong → OK → NG → N/A → kosong
  IP      dicek format, subnet bay (dari kriteria "Subnet 172.16.9.x") dan dobel dengan device lain.
"""
from __future__ import annotations

import re

SAS_COLS = (
    ("int", "Integrasi", re.compile(r"terintegrasi", re.I)),
    ("ip", "IP", re.compile(r"^ip address", re.I)),
    ("sntp", "SNTP", re.compile(r"sntp", re.I)),
    ("cid", "CID", re.compile(r"\bcid\b", re.I)),
    ("set", "Setting", re.compile(r"^setting", re.I)),
)
_SEC = re.compile(r"^[A-Z]{1,2}\. SAS · (.+)$")
_IPV4 = re.compile(r"^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$")
NEXT = {"": "OK", "OK": "NG", "NG": "NA", "NA": ""}


def is_sas_section(section) -> bool:
    return bool(_SEC.match(section or ""))


def device_name(section) -> str:
    m = _SEC.match(section or "")
    return m.group(1) if m else (section or "")


def sas_matrix(rows, key=lambda r: r):
    """rows: item checklist (dict / sqlite Row / objek; `key` mengambil dict-nya).
    Hasil: [{"section", "name", "cells": {kolom: row}, "extra": [row, …]}] sesuai urutan muncul."""
    out, by_sec = [], {}
    for r in rows:
        d_ = key(r)
        sec = d_["section"] or ""
        m = _SEC.match(sec)
        if not m:
            continue
        dev = by_sec.get(sec)
        if dev is None:
            dev = by_sec[sec] = {"section": sec, "name": m.group(1), "cells": {}, "extra": []}
            out.append(dev)
        col = next((k for k, _, rx in SAS_COLS if rx.search(d_["description"] or "")), None)
        if col and col not in dev["cells"]:
            dev["cells"][col] = r
        else:
            dev["extra"].append(r)
    return out


def next_result(cur) -> str:
    return NEXT.get(cur or "", "")


def subnet_prefix(criteria):
    m = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3})\.x", criteria or "", re.I)
    return m.group(1) + "." if m else None


def ip_warning(ip, criteria, others: dict) -> str:
    """others: {ip: "tag · device"} milik device lain. "" = aman."""
    v = (ip or "").strip()
    if not v:
        return ""
    if not _IPV4.match(v):
        return "Format IP tidak valid"
    pre = subnet_prefix(criteria)
    if pre and not v.startswith(pre):
        return f"Di luar subnet {pre}x"
    if v in others:
        return f"Sudah dipakai: {others[v]}"
    return ""
