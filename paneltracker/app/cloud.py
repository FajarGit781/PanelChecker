"""Sinkronisasi ke Supabase (offline-first, last-write-wins).

- Database lokal (SQLite) tetap jadi sumber kerja utama; aplikasi jalan tanpa internet.
- PUSH: semua record lokal ber-flag `dirty=1` di-upsert ke Supabase (berdasarkan uuid).
  Server menolak versi yang lebih lama (trigger pt_touch membandingkan updated_at).
- PULL: ambil record yang berubah di server sejak cursor terakhir (server_updated_at),
  terapkan ke lokal jika lebih baru.
- Foto: diupload ke Storage bucket `panel-photos`; tabel hanya menyimpan path-nya.

Hanya memakai pustaka standar Python (urllib) supaya .exe tetap ringan.
"""
from __future__ import annotations

import base64
import datetime as dt
import http.client
import json
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .i18n import tr
from .db import Database, now, stamp

DEFAULT_URL = "https://ewwtxklxgkyflhyazueg.supabase.co"
DEFAULT_KEY = "sb_publishable_5pqbo5TleB5PgtLdYthD_w_dKoNi2-D"  # publishable key: aman di aplikasi klien
BUCKET = "panel-photos"
BATCH = 200
PAGE = 1000


class CloudError(Exception):
    def __init__(self, msg="", status=None):
        super().__init__(msg)
        self.status = status   # kode HTTP kalau ada


class AuthError(CloudError):
    pass


# ======================================================================== HTTP client
CONNECT_TIMEOUT = 6   # detik per alamat IP saat menyambung (bukan batas waktu menunggu jawaban server)


def _connect_fast(host, port, timeout):
    """Sambung ke server: IPv4 dulu, lalu IPv6, dengan batas waktu sambung pendek per alamat.

    Di jaringan dengan IPv6/NAT64 yang tidak berfungsi (DNS memberi alamat 64:ff9b::…), urllib bawaan mencoba
    alamat IPv6 lebih dulu dan menunggu sampai timeout penuh untuk SETIAP alamat (2 × 40 detik) sebelum memakai
    IPv4 — satu kali sinkron bisa belasan menit. Browser/HP tidak kena karena memakai 'Happy Eyeballs'."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    infos.sort(key=lambda i: 0 if i[0] == socket.AF_INET else 1)
    ct = min(CONNECT_TIMEOUT, timeout) if timeout else CONNECT_TIMEOUT
    last = None
    for family, stype, proto, _, addr in infos:
        sock = socket.socket(family, stype, proto)
        try:
            sock.settimeout(ct)
            sock.connect(addr)
            sock.settimeout(timeout)
            return sock
        except OSError as e:
            last = e
            sock.close()
    raise last or OSError(f"Tidak bisa terhubung ke {host}")


class _FastHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        if self._tunnel_host:            # lewat proxy: pakai cara bawaan
            return super().connect()
        sock = _connect_fast(self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _FastHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self):
        super().__init__(context=ssl.create_default_context())
        self._ctx = ssl.create_default_context()

    def https_open(self, req):
        return self.do_open(_FastHTTPSConnection, req, context=self._ctx)


_OPENER = urllib.request.build_opener(_FastHTTPSHandler())

def check_endpoint(url: str, key: str):
    """Tolak konfigurasi yang tidak aman: koneksi tanpa HTTPS atau secret/service key di aplikasi."""
    u = (url or "").strip().lower()
    local = u.startswith(("http://127.0.0.1", "http://localhost"))   # hanya untuk pengujian lokal
    if not (u.startswith("https://") or local):
        raise CloudError(tr("Alamat server harus memakai HTTPS (terenkripsi)."))
    k = (key or "").strip()
    bad = k.startswith("sb_secret_")
    if k.count(".") == 2:   # key JWT lama: cek role-nya
        try:
            import base64
            seg = k.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
            bad = bad or claims.get("role") == "service_role"
        except Exception:
            pass
    if bad:
        raise CloudError(tr("Key yang dimasukkan adalah SECRET / service key. Key ini tidak boleh dipakai di aplikasi "
                            "(bisa melewati semua pengamanan). Pakai publishable key."))


WEAK_PASSWORDS = {"password", "p@ssw0rd", "p@ssword", "passw0rd", "viewer", "admin", "qwerty", "12345678",
                  "123456789", "1234567890", "paneltracker", "supabase", "rahasia", "bismillah"}


def password_problems(pw: str, username: str = "") -> list:
    """Aturan password tim: min 10 karakter, ada huruf & angka, bukan password umum / username."""
    p = pw or ""
    out = []
    if len(p) < 10:
        out.append(tr("minimal 10 karakter"))
    if not any(c.isalpha() for c in p) or not any(c.isdigit() for c in p):
        out.append(tr("harus ada huruf dan angka"))
    low = p.lower()
    u = (username or "").split("@")[0].lower()
    if low in WEAK_PASSWORDS or (len(u) >= 3 and u in low) or len(set(p)) < 5:
        out.append(tr("terlalu mudah ditebak (password umum / mengandung username)"))
    return out


class SupabaseClient:
    def __init__(self, url: str, key: str, timeout: int = 40):
        check_endpoint(url, key)
        self.url = url.rstrip("/")
        self.key = key.strip()
        self.timeout = timeout
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0.0
        self.email = None
        self.user_id = None

    # ---------------------------------------------------------------- low level
    def _req(self, method, path, body=None, headers=None, raw=False, auth=True):
        h = {"apikey": self.key}
        if auth:
            self._ensure_token()
            h["Authorization"] = f"Bearer {self.access_token}"
        if headers:
            h.update(headers)
        data = None
        if body is not None:
            if isinstance(body, (bytes, bytearray)):
                data = bytes(body)
            else:
                data = json.dumps(body).encode("utf-8")
                h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
        try:
            with _OPENER.open(req, timeout=self.timeout) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(msg)
                msg = j.get("msg") or j.get("message") or j.get("error_description") or j.get("error") or msg
            except Exception:
                pass
            if e.code in (400, 401, 403, 422) and "/auth/" in path:
                raise AuthError(msg) from None
            if e.code == 401:
                raise AuthError(f"Sesi tidak valid ({msg}). Silakan login ulang.") from None
            raise CloudError(f"HTTP {e.code} {method} {path.split('?')[0]}: {msg}", e.code) from None
        except urllib.error.URLError as e:
            raise CloudError(f"Tidak bisa terhubung ke server cloud: {e.reason}") from None
        except TimeoutError:
            raise CloudError("Koneksi ke server cloud timeout.") from None
        if raw:
            return payload
        if not payload:
            return None
        return json.loads(payload.decode("utf-8"))

    # ---------------------------------------------------------------- auth
    def _set_session(self, j):
        self.access_token = j["access_token"]
        self.refresh_token = j.get("refresh_token")
        self.expires_at = time.time() + float(j.get("expires_in", 3600)) - 60
        user = j.get("user") or {}
        self.email = user.get("email", self.email)
        self.user_id = user.get("id", self.user_id)

    def sign_in(self, email, password):
        j = self._req("POST", "/auth/v1/token?grant_type=password", {"email": email, "password": password},
                      auth=False)
        self._set_session(j)
        return j

    def restore(self, refresh_token):
        self.refresh_token = refresh_token
        self._refresh()

    def _refresh(self):
        if not self.refresh_token:
            raise AuthError("Belum login.")
        j = self._req("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": self.refresh_token},
                      auth=False)
        self._set_session(j)

    def _ensure_token(self):
        if not self.access_token or time.time() >= self.expires_at:
            self._refresh()

    def sign_out(self):
        """Cabut sesi laptop ini di server (scope=local), lalu hapus dari memori.

        Tanpa scope, Supabase memakai "global": semua sesi akun ini di laptop/HP lain ikut dicabut."""
        try:
            if self.access_token or self.refresh_token:
                self._req("POST", "/auth/v1/logout?scope=local", {}, auth=True)
        except Exception:
            pass
        self.access_token = self.refresh_token = None

    def update_password(self, new_password):
        self._req("PUT", "/auth/v1/user", {"password": new_password})

    # ---------------------------------------------------------------- data
    def membership(self):
        q = urllib.parse.quote(self.email or "")
        rows = self._req("GET", f"/rest/v1/app_users?select=email,full_name,role&email=eq.{q}")
        if not rows:  # coba case-insensitive
            rows = self._req("GET", f"/rest/v1/app_users?select=email,full_name,role&email=ilike.{q}")
        return rows[0] if rows else None

    def upsert(self, table, rows):
        if rows:
            self._req("POST", f"/rest/v1/{table}?on_conflict=uuid", rows,
                      headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def changed_since(self, table, cursor, offset=0, limit=PAGE):
        q = f"/rest/v1/{table}?select=*&order=server_updated_at.asc,uuid.asc&limit={limit}&offset={offset}"
        if cursor:
            q += "&server_updated_at=gt." + urllib.parse.quote(cursor)
        return self._req("GET", q) or []

    def upload(self, path, data: bytes, content_type="image/jpeg"):
        self._req("POST", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(path)}", data,
                  headers={"Content-Type": content_type, "x-upsert": "true", "cache-control": "3600"})

    def download(self, path) -> bytes:
        return self._req("GET", f"/storage/v1/object/authenticated/{BUCKET}/{urllib.parse.quote(path)}", raw=True)


# ======================================================================== mapping
# local_table: (server_table, [kolom data], {kolom_fk_lokal: (tabel_parent_lokal, kolom_fk_server)})
MAP = {
    "project": ("projects", ["code", "name", "client", "contractor", "location", "start_date", "end_date",
                             "description", "issue_prefix", "created_at"], {}),
    "site": ("sites", ["name", "location", "sort", "created_at"], {"project_id": ("project", "project_uuid")}),
    "panel": ("panels", ["bay", "tag", "name", "panel_type", "vendor", "serial_no", "remarks", "accepted_by",
                         "accepted_at", "sort", "created_at"], {"site_id": ("site", "site_uuid")}),
    "check_template": ("check_templates", ["name", "description", "created_at"], {}),
    "panel_check": ("panel_checks", ["section", "description", "criteria", "unit", "sort", "result", "value",
                                     "remark", "checked_by", "checked_at", "created_at"],
                    {"panel_id": ("panel", "panel_uuid")}),
    "issue": ("issues", ["code", "title", "description", "category", "severity", "status", "pic", "raised_by",
                         "raised_date", "due_date", "closed_date", "verified_by", "action", "created_at"],
              {"project_id": ("project", "project_uuid"), "site_id": ("site", "site_uuid"),
               "panel_id": ("panel", "panel_uuid"), "check_id": ("panel_check", "check_uuid")}),
    "attachment": ("attachments", ["kind", "filename", "caption", "storage_path", "created_at"],
                   {"issue_id": ("issue", "issue_uuid"), "check_id": ("panel_check", "check_uuid")}),
}
ORDER = ["project", "site", "panel", "check_template", "panel_check", "issue", "attachment"]
REQUIRED_FK = {"site": "project_id", "panel": "site_id", "panel_check": "panel_id", "issue": "project_id"}


SETTINGS_TABLE = "team_settings"
_SETTINGS_NS = uuid.UUID("6f1c2a3e-7d4b-5e8f-9a10-2b3c4d5e6f70")


def setting_uuid(key: str) -> str:
    """uuid tetap per key → semua laptop & HP menulis baris yang sama."""
    return str(uuid.uuid5(_SETTINGS_NS, "team_setting:" + key))


LOGIN_DOMAIN = "paneltracker.local"


def login_email(user: str) -> str:
    """'Fajar' → 'fajar@paneltracker.local'; alamat email lengkap dipakai apa adanya."""
    user = (user or "").strip()
    return user.lower() if "@" in user else f"{user.lower()}@{LOGIN_DOMAIN}"


def display_user(email: str) -> str:
    email = email or ""
    return email.split("@")[0] if email.lower().endswith("@" + LOGIN_DOMAIN) else email


class SyncEngine:
    def __init__(self, db: Database, client: SupabaseClient, progress=None, push=True):
        self.push = push
        self.db = db
        self.c = client
        self.progress = progress or (lambda msg: None)
        self._id2uuid = {}
        self._uuid2id = {}

    # ---------------------------------------------------------------- helpers
    def _uuid_of(self, table, rid):
        if rid is None:
            return None
        key = (table, rid)
        if key not in self._id2uuid:
            r = self.db.q1(f"SELECT uuid FROM {table} WHERE id=?", (rid,))
            self._id2uuid[key] = r["uuid"] if r else None
        return self._id2uuid[key]

    def _id_of(self, table, uid):
        if not uid:
            return None
        key = (table, uid)
        if key not in self._uuid2id:
            r = self.db.q1(f"SELECT id FROM {table} WHERE uuid=?", (uid,))
            self._uuid2id[key] = r["id"] if r else None
        return self._uuid2id[key]

    # ---------------------------------------------------------------- run
    def run(self):
        t0 = time.time()
        stats = {"pushed": 0, "pulled": 0, "photos_up": 0, "photos_down": 0, "skipped": 0}
        # pull dulu: perubahan tim diterapkan & bentrok kode punch diselesaikan sebelum kirim
        self.progress(tr("Mengambil perubahan dari cloud…"))
        if self.db.get_setting("att_check_uuid_v1", "") != "1":
            # v2.8: lampiran punya check_uuid (foto evidence). Versi lama sudah menarik baris tanpa kolom ini →
            # tarik ulang semua lampiran sekali supaya tautan ke item checklist terisi.
            self.db.set_setting("sync_cursor_attachments", "")
            self.db.set_setting("att_check_uuid_v1", "1")
        for t in ORDER:
            stats["pulled"] += self._pull(t, stats)
        stats["pulled"] += self._pull_settings()
        if self.push:
            self.progress(tr("Mengirim perubahan lokal…"))
            for t in ORDER:
                stats["pushed"] += self._push(t, stats)
            stats["pushed"] += self._push_settings()
        self.progress(tr("Mengunduh foto…"))
        stats["photos_down"] += self._download_missing_photos()
        self.db.set_setting("sync_last", now())
        stats["seconds"] = round(time.time() - t0, 1)
        return stats

    # ---------------------------------------------------------------- push
    def _payload(self, t, r):
        server, cols, fks = MAP[t]
        d = {"uuid": r["uuid"], "updated_at": r["updated_at"], "deleted": int(r["deleted"] or 0)}
        for c in cols:
            d[c] = r[c]
        for lcol, (ptable, scol) in fks.items():
            d[scol] = self._uuid_of(ptable, r[lcol])
        if t == "check_template":
            d["items"] = [[i["section"], i["description"], i["criteria"], i["unit"]]
                          for i in self.db.template_items(r["id"])]
        return d

    def _push(self, t, stats):
        extra = " AND kind<>'logo'" if t == "attachment" else ""
        rows = self.db.q(f"SELECT * FROM {t} WHERE dirty=1{extra} ORDER BY id")
        if not rows:
            return 0
        server = MAP[t][0]
        if t == "attachment":
            for r in rows:
                if not r["storage_path"] and not r["deleted"] and r["data"]:
                    issue_uuid = self._uuid_of("issue", r["issue_id"])
                    check_uuid = self._uuid_of("panel_check", r["check_id"]) if not issue_uuid else None
                    folder = issue_uuid or (f"check/{check_uuid}" if check_uuid else "umum")
                    path = f"{folder}/{r['uuid']}.jpg"
                    self.progress(tr("Upload foto {0}…", r['filename'] or ''))
                    from .imaging import shrink_if_large
                    data = bytes(r["data"])
                    small = shrink_if_large(data)      # foto lama/besar dikompres dulu (hemat storage 1 GB)
                    if small is not data:
                        self.db.conn.execute("UPDATE attachment SET data=? WHERE id=?", (small, r["id"]))
                        data = small
                    ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
                    self.c.upload(path, data, ctype)
                    # updated_at ikut diperbarui supaya laptop lain yang sudah punya metadata ikut mengunduh foto
                    self.db.conn.execute("UPDATE attachment SET storage_path=?, updated_at=? WHERE id=?",
                                         (path, stamp(), r["id"]))
                    stats["photos_up"] += 1
            self.db.conn.commit()
            rows = self.db.q(f"SELECT * FROM {t} WHERE dirty=1{extra} ORDER BY id")
        n = 0
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            payload, sent = [], []
            for r in chunk:
                p = self._payload(t, r)
                req = REQUIRED_FK.get(t)
                if req and not p[MAP[t][2][req][1]]:
                    stats["skipped"] += 1  # parent tidak ditemukan; biarkan dirty
                    continue
                payload.append(p)
                sent.append(r)
            self.progress(tr("Kirim {0}: {1}/{2}", server, i + len(chunk), len(rows)))
            self.c.upsert(server, payload)
            for r in sent:
                # hanya bersihkan flag kalau record tidak berubah lagi selama dikirim
                self.db.conn.execute(f"UPDATE {t} SET dirty=0 WHERE id=? AND updated_at=?", (r["id"], r["updated_at"]))
            self.db.conn.commit()
            n += len(payload)
        return n

    # ---------------------------------------------------------------- pull
    def _pull(self, t, stats):
        server, cols, fks = MAP[t]
        key = f"sync_cursor_{server}"
        cursor = self.db.get_setting(key, "")
        # mundur 2 menit untuk menangkap transaksi yang commit terlambat (record ganda aman: LWW)
        q_cursor = cursor
        if cursor:
            try:
                q_cursor = (dt.datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                            - dt.timedelta(minutes=2)).isoformat()
            except ValueError:
                q_cursor = cursor
        offset, n, max_seen = 0, 0, cursor
        while True:
            rows = self.c.changed_since(server, q_cursor, offset)
            for r in rows:
                if self._apply(t, r):
                    n += 1
                su = r.get("server_updated_at") or ""
                if su > (max_seen or ""):
                    max_seen = su
            self.db.conn.commit()
            if len(rows) < PAGE:
                break
            offset += PAGE
            self.progress(tr("Ambil {0}: {1}…", server, offset))
        if max_seen and max_seen != cursor:
            self.db.set_setting(key, max_seen)
        return n

    def _apply(self, t, r) -> bool:
        server, cols, fks = MAP[t]
        local = self.db.q1(f"SELECT * FROM {t} WHERE uuid=?", (r["uuid"],))
        if local is not None:
            relink = (t == "attachment" and r.get("check_uuid") and not local["check_id"] and not local["dirty"])
            if (local["updated_at"] or "") >= (r["updated_at"] or "") and not relink:
                return False  # lokal sama / lebih baru → biarkan (akan di-push kalau dirty)
        vals = {c: r.get(c) for c in cols}
        for lcol, (ptable, scol) in fks.items():
            pid = self._id_of(ptable, r.get(scol))
            if pid is None and r.get(scol):
                pid = None  # parent belum ada / terhapus permanen
            vals[lcol] = pid
        req = REQUIRED_FK.get(t)
        if req and vals.get(req) is None:
            return False
        if t == "issue" and local is None:
            self._resolve_code_clash(vals.get("project_id"), vals.get("code"), r["uuid"])
        vals.update(uuid=r["uuid"], updated_at=r["updated_at"], deleted=int(r.get("deleted") or 0), dirty=0)
        if local is None:
            if t == "attachment":
                vals["data"] = None
            cs = ", ".join(vals)
            cur = self.db.conn.execute(f"INSERT INTO {t}({cs}) VALUES({', '.join('?' * len(vals))})",
                                       tuple(vals.values()))
            self._uuid2id[(t, r["uuid"])] = cur.lastrowid
            rid = cur.lastrowid
        else:
            if t == "attachment" and r.get("storage_path") != local["storage_path"]:
                vals["data"] = None
            cs = ", ".join(f"{k}=?" for k in vals)
            self.db.conn.execute(f"UPDATE {t} SET {cs} WHERE id=?", (*vals.values(), local["id"]))
            rid = local["id"]
        if t == "check_template":
            items = r.get("items") or []
            if isinstance(items, str):
                items = json.loads(items)
            self.db.conn.execute("DELETE FROM check_template_item WHERE template_id=?", (rid,))
            for k, it in enumerate(items):
                it = list(it) + ["", "", "", ""]
                self.db.conn.execute("INSERT INTO check_template_item(template_id,section,description,criteria,unit,"
                                     "sort) VALUES(?,?,?,?,?,?)", (rid, it[0], it[1], it[2], it[3], k))
        return True

    # ---------------------------------------------------------------- pengaturan tim
    def _pull_settings(self) -> int:
        """Kop report, logo, tanda tangan, daftar pilihan & target default dipakai bersama satu tim."""
        key = "sync_cursor_team_settings"
        cursor = self.db.get_setting(key, "")
        try:
            rows = self.c.changed_since(SETTINGS_TABLE, cursor)
        except CloudError as e:
            if e.status == 404:   # server lama tanpa tabel team_settings → lewati
                return 0
            raise
        n, max_seen = 0, cursor
        for r in rows:
            if not r.get("deleted") and self.db.apply_remote_setting(r.get("key"), r.get("value") or "",
                                                                     r.get("updated_at")):
                n += 1
            su = r.get("server_updated_at") or ""
            if su > (max_seen or ""):
                max_seen = su
        self.db.conn.commit()
        if max_seen and max_seen != cursor:
            self.db.set_setting(key, max_seen)
        return n

    def _push_settings(self) -> int:
        rows = self.db.shared_settings_dirty()
        if not rows:
            return 0
        payload = []
        for r in rows:
            val = r["value"] or ""
            if r["key"] == "logo":
                logo = self.db.get_logo()
                val = base64.b64encode(logo).decode() if logo else ""
            payload.append({"uuid": setting_uuid(r["key"]), "key": r["key"], "value": val,
                            "updated_at": r["updated_at"] or stamp(), "deleted": 0})
        self.progress(tr("Kirim pengaturan tim…"))
        try:
            self.c.upsert(SETTINGS_TABLE, payload)
        except CloudError as e:
            if e.status == 404:
                return 0
            raise
        for r in rows:
            self.db.conn.execute("UPDATE settings SET dirty=0 WHERE key=? AND COALESCE(updated_at,'')=?",
                                 (r["key"], r["updated_at"] or ""))
        self.db.conn.commit()
        return len(payload)

    def _resolve_code_clash(self, project_id, code, remote_uuid):
        """Dua laptop membuat kode punch sama saat offline → kode lokal yang belum terkirim diganti."""
        if not project_id or not code:
            return
        clash = self.db.q1("SELECT id FROM issue WHERE project_id=? AND code=? AND uuid<>? AND dirty=1",
                           (project_id, code, remote_uuid))
        if clash:
            new = self.db.next_issue_code(project_id)
            # pastikan tidak bentrok dengan kode remote yang sedang masuk
            if new == code:
                n = int(new.split("-")[-1]) + 1
                new = f"{'-'.join(new.split('-')[:-1])}-{n:04d}"
            self.db._update("issue", clash["id"], {"code": new})
            self.db.log(project_id, "issue", clash["id"], "update", f"Kode {code} bentrok saat sinkron → {new}")

    def _download_missing_photos(self) -> int:
        rows = self.db.q("SELECT id, storage_path FROM attachment WHERE data IS NULL AND storage_path IS NOT NULL "
                         "AND deleted=0 AND kind<>'logo'")
        n = 0
        for k, r in enumerate(rows, start=1):
            self.progress(tr("Unduh foto {0}/{1}…", k, len(rows)))
            try:
                data = self.c.download(r["storage_path"])
            except CloudError:
                continue
            self.db.conn.execute("UPDATE attachment SET data=? WHERE id=?", (data, r["id"]))
            n += 1
            if k % 10 == 0:
                self.db.conn.commit()
        self.db.conn.commit()
        return n
