"""Terjemahan sederhana Indonesia → English.

Teks sumber di kode berbahasa Indonesia. `tr("teks {0}", x)` mengembalikan terjemahan
sesuai bahasa aktif lalu memformat argumen. Bahasa report bisa berbeda dari bahasa UI
dengan `with using("en"): ...`.
"""
from __future__ import annotations

import contextlib

from .i18n_en import EN

LANGS = {"id": "Bahasa Indonesia", "en": "English"}
_lang = "id"


def set_lang(code: str):
    global _lang
    _lang = code if code in LANGS else "id"


def lang() -> str:
    return _lang


@contextlib.contextmanager
def using(code: str | None):
    global _lang
    old = _lang
    if code:
        set_lang(code)
    try:
        yield
    finally:
        _lang = old


def tr(text: str, *args, **kw) -> str:
    s = EN.get(text, text) if _lang == "en" else text
    if args or kw:
        try:
            return s.format(*args, **kw)
        except (IndexError, KeyError, ValueError):
            return text.format(*args, **kw)
    return s


class TrDict(dict):
    """dict yang nilainya otomatis diterjemahkan saat diakses."""

    def __getitem__(self, k):
        return tr(super().__getitem__(k))

    def get(self, k, d=None):
        return tr(super().get(k, d)) if k in self else d
