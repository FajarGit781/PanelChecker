#!/bin/bash
# ============================================================
#  Build "Panel Tracker.app" + installer .dmg untuk macOS
#  Jalankan di Terminal:   ./build_mac.sh
#  Syarat: Python 3.10 – 3.13 (python.org atau Homebrew). Python bawaan macOS (3.9) terlalu lama.
#  Hasil:  dist/Panel Tracker.app  dan  dist/PanelTracker_<versi>_mac.dmg
#  Catatan: hasil build hanya jalan di jenis Mac yang sama (Apple Silicon ↔ Intel).
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

PY="${PY:-}"
if [ -z "$PY" ]; then
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "[X] Python 3.10–3.13 tidak ditemukan. Install dari https://www.python.org/downloads/macos/ lalu jalankan lagi."
  exit 1
fi
VERSION=$("$PY" -c 'import re;print(re.search(r"__version__\s*=\s*\"([^\"]+)\"", open("app/__init__.py").read()).group(1))')
echo "[1/5] Python: $("$PY" --version)  ·  Panel Tracker v$VERSION"

if [ -z "${SKIP_VENV:-}" ]; then
  echo "[2/5] Virtual environment & library…"
  [ -d .venv-mac ] || "$PY" -m venv .venv-mac
  # shellcheck disable=SC1091
  source .venv-mac/bin/activate
  python -m pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
else
  echo "[2/5] Memakai Python yang sudah ada (SKIP_VENV)"
  python() { "$PY" "$@"; }
  pyinstaller() { "$PY" -m PyInstaller "$@"; }
fi

echo "[3/5] Build .app (2–5 menit)…"
rm -rf "dist/Panel Tracker.app" dist/PanelTracker
pyinstaller --noconfirm --clean PanelTracker_mac.spec

APP="dist/Panel Tracker.app"
echo "[4/5] Self-test…"
rm -rf build/selftest_mac
"$APP/Contents/MacOS/PanelTracker" --selftest "$PWD/build/selftest_mac"
ls build/selftest_mac/*.pdf >/dev/null

echo "[5/5] Installer .dmg…"
# ad-hoc signature supaya Gatekeeper bisa mengenali bundle utuh (bukan Developer ID)
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
DMG="dist/PanelTracker_${VERSION}_mac.dmg"
STAGE="build/dmg"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Panel Tracker $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
echo
echo "Selesai:"
echo "  $APP"
echo "  $DMG"
echo "Buka .dmg, seret 'Panel Tracker' ke Applications. Pertama kali dibuka: klik kanan → Open."
