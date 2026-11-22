"""Penyimpanan rahasia lokal (token login cloud).

Di Windows, token dienkripsi dengan DPAPI (CryptProtectData) milik akun Windows yang sedang login.
Akibatnya, kalau folder PanelTracker_Data (termasuk settings.ini) dicopy ke laptop lain atau dibuka
oleh akun Windows lain, token tidak bisa dibaca dan pengguna harus login ulang.

Di macOS (aplikasi .app), token disimpan di Keychain milik user Mac; settings.ini hanya berisi rujukan
"keychain:<akun>". Folder data yang disalin ke Mac/user lain tidak membawa tokennya.

Selain itu (menjalankan dari source / pengujian), nilai disimpan dengan prefix "plain:" — sengaja, supaya tes
otomatis tidak pernah menulis ke Keychain pengguna.
"""
from __future__ import annotations

import base64
import sys

_PREFIX_DPAPI = "dpapi:"
_PREFIX_PLAIN = "plain:"
_PREFIX_KEYCHAIN = "keychain:"
_SERVICE = "PanelTracker"


def _use_keychain() -> bool:
    return sys.platform == "darwin" and bool(getattr(sys, "frozen", False))
_ENTROPY = b"PanelTracker/cloud-token/v1"


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def mk(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    src, _k1 = mk(data)
    ent, _k2 = mk(_ENTROPY)
    out = BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    if encrypt:
        ok = fn(ctypes.byref(src), "PanelTracker", ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(out))
    else:
        ok = fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
    if not ok:
        raise OSError("DPAPI gagal")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(secret: str, account: str = "cloud-token") -> str:
    """account: nama entri Keychain (macOS); dibedakan per folder data supaya tidak saling menimpa."""
    if not secret:
        if _use_keychain():
            try:
                import keyring
                keyring.delete_password(_SERVICE, account)
            except Exception:
                pass
        return ""
    if _use_keychain():
        try:
            import keyring
            keyring.set_password(_SERVICE, account, secret)
            return _PREFIX_KEYCHAIN + account
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            return _PREFIX_DPAPI + base64.b64encode(_dpapi(secret.encode("utf-8"), True)).decode("ascii")
        except Exception:
            pass
    return _PREFIX_PLAIN + secret


def unprotect(stored: str) -> str:
    """Kembalikan rahasia asli, atau "" kalau tidak bisa dibuka (mis. disalin dari laptop lain)."""
    if not stored:
        return ""
    if stored.startswith(_PREFIX_DPAPI):
        if sys.platform != "win32":
            return ""
        try:
            return _dpapi(base64.b64decode(stored[len(_PREFIX_DPAPI):]), False).decode("utf-8")
        except Exception:
            return ""
    if stored.startswith(_PREFIX_KEYCHAIN):
        if not _use_keychain():
            return ""
        try:
            import keyring
            return keyring.get_password(_SERVICE, stored[len(_PREFIX_KEYCHAIN):]) or ""
        except Exception:
            return ""
    if stored.startswith(_PREFIX_PLAIN):
        return stored[len(_PREFIX_PLAIN):]   # di .app macOS: dipindah ke Keychain oleh pemanggil (is_protected False)
    return stored  # format lama (v2.5 ke bawah): teks biasa → akan dienkripsi ulang saat dipakai


def is_protected(stored: str) -> bool:
    return bool(stored) and stored.startswith((_PREFIX_DPAPI, _PREFIX_KEYCHAIN))
