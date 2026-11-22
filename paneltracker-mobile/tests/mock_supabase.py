"""Server tiruan Supabase (Auth + PostgREST subset + Storage) untuk menguji sinkron secara lokal."""
import datetime as dt
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USERS = {"a@test.id": "pass-a", "b@test.id": "pass-b", "stranger@test.id": "pass-x"}
MEMBERS = {"a@test.id": "engineer", "b@test.id": "vendor"}
TABLES = {t: {} for t in ["projects", "sites", "panels", "panel_checks", "issues", "attachments", "check_templates", "team_settings"]}
STORAGE = {}
REVOKED = set()
LOCK = threading.Lock()
_clock = [dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)]


def server_now():
    n = max(dt.datetime.now(dt.timezone.utc), _clock[0] + dt.timedelta(microseconds=1))
    _clock[0] = n
    return n.isoformat()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None):
        body = raw if raw is not None else (json.dumps(obj).encode() if obj is not None else b"")
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _user(self):
        a = self.headers.get("Authorization", "")
        if not a.startswith("Bearer tok-"):
            return None
        return a[len("Bearer tok-"):]

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if u.path == "/auth/v1/token":
            j = json.loads(body)
            gt = urllib.parse.parse_qs(u.query)["grant_type"][0]
            if gt == "password":
                if USERS.get(j["email"]) != j["password"]:
                    return self._send(400, {"error_description": "Invalid login credentials"})
                email = j["email"]
                REVOKED.discard("ref-" + email)
            else:
                if j["refresh_token"] in REVOKED:
                    return self._send(400, {"error_description": "Invalid Refresh Token: Refresh Token Not Found"})
                email = j["refresh_token"].replace("ref-", "")
            return self._send(200, {"access_token": "tok-" + email, "refresh_token": "ref-" + email,
                                    "expires_in": 3600, "user": {"id": "id-" + email, "email": email}})
        if u.path == "/auth/v1/logout":
            e = self._user()
            if e:
                REVOKED.add("ref-" + e)
            return self._send(204)
        email = self._user()
        if not email:
            return self._send(401, {"message": "JWT invalid"})
        if u.path.startswith("/storage/v1/object/panel-photos/"):
            if MEMBERS.get(email) not in ("engineer", "vendor", "admin"):
                return self._send(403, {"message": "denied"})
            STORAGE[urllib.parse.unquote(u.path.split("/panel-photos/", 1)[1])] = body
            return self._send(200, {"Key": "ok"})
        t = u.path.split("/rest/v1/")[1]
        if MEMBERS.get(email) not in ("engineer", "vendor", "admin"):
            return self._send(403, {"message": "new row violates row-level security policy"})
        rows = json.loads(body)
        with LOCK:
            for r in rows:
                old = TABLES[t].get(r["uuid"])
                if old and r["updated_at"] < old["updated_at"]:
                    continue
                nr = dict(old or {})
                nr.update(r)
                nr["server_updated_at"] = server_now()
                TABLES[t][r["uuid"]] = nr
        return self._send(201)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "authorization, apikey, content-type, prefer, x-upsert, cache-control")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_PUT(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        email = self._user()
        if not email:
            return self._send(401, {"message": "JWT invalid"})
        if u.path == "/auth/v1/user":
            USERS[email] = body["password"]
            return self._send(200, {"id": "id-" + email, "email": email})
        return self._send(404, {})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        email = self._user()
        if not email:
            return self._send(401, {"message": "JWT invalid"})
        if u.path.startswith("/storage/v1/object/authenticated/panel-photos/"):
            p = urllib.parse.unquote(u.path.split("/panel-photos/", 1)[1])
            if p not in STORAGE or email not in MEMBERS:
                return self._send(404, {"message": "not found"})
            return self._send(200, raw=STORAGE[p])  # isi gambar
        t = u.path.split("/rest/v1/")[1]
        qs = urllib.parse.parse_qs(u.query)
        if t == "app_users":
            e = qs["email"][0].split(".", 1)[1]
            return self._send(200, [{"email": e, "full_name": "", "role": MEMBERS[e]}] if e in MEMBERS else [])
        if email not in MEMBERS:
            return self._send(200, [])
        rows = sorted(TABLES[t].values(), key=lambda r: (r["server_updated_at"], r["uuid"]))
        if "server_updated_at" in qs:
            c = qs["server_updated_at"][0].split(".", 1)[1]
            cdt = dt.datetime.fromisoformat(c)
            rows = [r for r in rows if dt.datetime.fromisoformat(r["server_updated_at"]) > cdt]
        if "key" in qs and qs["key"][0].startswith("in.("):
            keys = qs["key"][0][4:-1].split(",")
            rows = [r for r in rows if r.get("key") in keys]
        off = int(qs.get("offset", ["0"])[0])
        lim = int(qs.get("limit", ["1000"])[0])
        return self._send(200, rows[off:off + lim])


def start(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
