"""Kompresi foto sebelum disimpan / di-upload (Supabase Storage free tier 1 GB).

Target: sisi terpanjang maks 1280 px dan ≤ 150 KB per foto (rata-rata lama ±170 KB @1600 px).
Teks di layar HMI / LED BCU tetap terbaca di 1280 px. Kalau masih terlalu besar, kualitas JPEG
diturunkan bertahap, lalu ukuran 1024 px.
"""
from __future__ import annotations

MAX_PX = 1280
TARGET = 150_000          # byte
RECOMPRESS_ABOVE = 200_000  # foto lama yang lebih besar dari ini dikompres ulang sebelum upload


def _to_image(src):
    from PySide6.QtGui import QImage, QImageReader
    if isinstance(src, QImage):
        return src
    if isinstance(src, (bytes, bytearray, memoryview)):
        img = QImage.fromData(bytes(src))
        return img
    reader = QImageReader(str(src))
    reader.setAutoTransform(True)       # rotasi EXIF dari HP
    return reader.read()


def _jpeg(img, q) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPG", q)
    return bytes(ba)


def compress(src, max_px=MAX_PX, target=TARGET) -> bytes:
    """src: path file, bytes, atau QImage → JPEG terkompresi (b"" kalau gambar tidak terbaca)."""
    from PySide6.QtCore import Qt
    img = _to_image(src)
    if img is None or img.isNull():
        return b""
    if img.hasAlphaChannel():           # PNG transparan → latar putih (JPEG tanpa alpha)
        from PySide6.QtGui import QImage, QPainter
        bg = QImage(img.size(), QImage.Format_RGB32)
        bg.fill(Qt.white)
        p = QPainter(bg)
        p.drawImage(0, 0, img)
        p.end()
        img = bg
    best = b""
    for px in (max_px, 1024):
        im = img
        if im.width() > px or im.height() > px:
            im = im.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        for q in (80, 70, 60, 50):
            data = _jpeg(im, q)
            if not best or len(data) < len(best):
                best = data
            if len(data) <= target:
                return data
    return best


def shrink_if_large(data: bytes) -> bytes:
    """Dipakai saat upload: foto lama/besar dikompres ulang; yang sudah kecil dibiarkan."""
    if not data or len(data) <= RECOMPRESS_ABOVE:
        return data
    try:
        out = compress(data)
    except Exception:
        return data
    return out if out and len(out) < len(data) else data
