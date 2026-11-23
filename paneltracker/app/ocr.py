"""OCR foto layar HMI/BCU/meter memakai OCR bawaan sistem operasi (gratis, offline, tanpa API):
macOS → Apple Vision (pyobjc), Windows 10/11 → Windows.Media.Ocr (winrt).

recognize(image_bytes) → teks per baris (potongan teks di baris yang sama digabung kiri→kanan),
siap diurai `injection.parse_hmi`. available() False bila mesin OCR tidak ada (fitur disembunyikan).
"""
from __future__ import annotations

import sys


def _join_lines(boxes):
    """boxes: [(x, y_center, height, text)] dengan sumbu y ke ATAS (0..1). Gabung jadi baris teks."""
    rows = []
    for b in sorted(boxes, key=lambda b: -b[1]):
        for r in rows:
            if abs(r["y"] - b[1]) < 0.5 * max(r["h"], b[2]):
                r["items"].append(b)
                break
        else:
            rows.append(dict(y=b[1], h=b[2], items=[b]))
    return "\n".join(" ".join(t for _, _, _, t in sorted(r["items"], key=lambda b: b[0])) for r in rows)


# ---------------------------------------------------------------- macOS
def _mac_available():
    try:
        import Vision  # noqa: F401
        from Foundation import NSData  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _mac_recognize(data: bytes) -> str:
    import Vision
    from Foundation import NSData
    nsd = NSData.dataWithBytes_length_(data, len(data))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(nsd, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)          # angka & kode (IA, VAB) jangan "dikoreksi" jadi kata
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(str(err))
    boxes = []
    for o in req.results() or []:
        c = o.topCandidates_(1)
        if not c:
            continue
        bb = o.boundingBox()
        boxes.append((bb.origin.x, bb.origin.y + bb.size.height / 2, bb.size.height, str(c[0].string())))
    return _join_lines(boxes)


# ---------------------------------------------------------------- Windows
def _win_available():
    try:
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
        return OcrEngine.try_create_from_user_profile_languages() is not None
    except Exception:  # noqa: BLE001
        return False


def _win_recognize(data: bytes) -> str:
    import asyncio
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    async def run():
        stream = InMemoryRandomAccessStream()
        w = DataWriter(stream)
        w.write_bytes(list(data))
        await w.store_async()
        await w.flush_async()
        w.detach_stream()
        stream.seek(0)
        dec = await BitmapDecoder.create_async(stream)
        bmp = await dec.get_software_bitmap_async()
        eng = OcrEngine.try_create_from_user_profile_languages()
        res = await eng.recognize_async(bmp)
        H = float(dec.pixel_height) or 1.0
        boxes = []
        for line in res.lines:
            for word in line.words:
                r = word.bounding_rect
                yc = 1 - (r.y + r.height / 2) / H          # sumbu y ke atas, sama dengan Vision
                boxes.append((r.x / (float(dec.pixel_width) or 1.0), yc, r.height / H, word.text))
        return _join_lines(boxes)

    return asyncio.run(run())


def available() -> bool:
    if sys.platform == "darwin":
        return _mac_available()
    if sys.platform.startswith("win"):
        return _win_available()
    return False


def recognize(data: bytes) -> str:
    if sys.platform == "darwin":
        return _mac_recognize(data)
    if sys.platform.startswith("win"):
        return _win_recognize(data)
    raise RuntimeError("OCR tidak tersedia di sistem ini")
