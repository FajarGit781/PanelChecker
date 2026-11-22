"""Sinkron tetap cepat di jaringan dengan IPv6 / NAT64 yang tidak berfungsi.

DNS memberi alamat IPv6 (mis. 64:ff9b::…) lebih dulu, tetapi alamat itu tidak bisa dihubungi. Sebelumnya urllib
menunggu timeout penuh per alamat (2 × 40 detik) untuk SETIAP permintaan. Sekarang IPv4 dicoba dulu dan batas
waktu sambung per alamat pendek."""
import os, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from app import cloud

# 1. urutan: IPv4 dulu walau DNS memberi IPv6 lebih dulu
srv = HTTPServer(("127.0.0.1", 0), type("H", (BaseHTTPRequestHandler,), {"do_GET": lambda s: (s.send_response(204), s.end_headers()), "log_message": lambda *a: None}))
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
real = socket.getaddrinfo
DEAD6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("100::1", port, 0, 0))   # 100::/64 = discard-only, tidak bisa dihubungi


def fake_getaddrinfo(host, p, *a, **k):
    return [DEAD6, DEAD6] + [i for i in real("127.0.0.1", p, *a, **k) if i[0] == socket.AF_INET]


socket.getaddrinfo = fake_getaddrinfo
try:
    t = time.time()
    s = cloud._connect_fast("contoh.supabase.co", port, 40)
    dt = time.time() - t
    assert s.family == socket.AF_INET, s.family
    s.close()
    assert dt < 1.0, f"terlalu lama: {dt:.1f}s"
    print(f"IPv4 dipakai lebih dulu: OK ({dt * 1000:.0f} ms)")

    # 2. hanya IPv6 mati → gagal cepat (batas sambung per alamat), bukan 2 × 40 detik
    cloud.CONNECT_TIMEOUT = 1
    socket.getaddrinfo = lambda *a, **k: [DEAD6, DEAD6]
    t = time.time()
    try:
        cloud._connect_fast("contoh.supabase.co", port, 40)
        raise AssertionError("seharusnya gagal")
    except OSError:
        pass
    dt = time.time() - t
    assert dt < 2.5, f"menunggu terlalu lama: {dt:.1f}s"
    print(f"alamat mati tidak ditunggu lama: OK ({dt:.1f} s untuk 2 alamat)")
finally:
    socket.getaddrinfo = real
    srv.shutdown()

# 3. klien HTTPS memakai opener cepat
assert any(isinstance(h, cloud._FastHTTPSHandler) for h in cloud._OPENER.handlers)
print("klien HTTPS memakai koneksi cepat: OK")
print("SEMUA OK")
