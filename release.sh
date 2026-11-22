#!/bin/bash
# ============================================================
#  release.sh: naikkan versi, test, build, zip, (opsional) deploy.
#
#  ./release.sh desktop <versi>                 mis. 2.7.5  → .dmg + source zip
#  ./release.sh mobile  <versi> [--deploy]      mis. 1.1.6  → test, build, Android Studio zip,
#                                                --deploy: upload PWA ke pt-panel-app
#  ./release.sh viewer    [--deploy]            zip web-viewer, --deploy ke pt-panel-viewer
#  ./release.sh dashboard [--deploy]            zip pm-dashboard, --deploy ke pt-panel-dashboard
#
#  Opsi umum:
#    --dry-run      hanya tampilkan apa yang akan dilakukan
#    --allow-dirty  izinkan rilis walau ada perubahan belum di-commit
#
#  Aturan:
#  - File hasil di root TIDAK PERNAH ditimpa: kalau nama sudah ada → _r2, _r3, …
#  - Kalau test/build gagal, perubahan versi dibatalkan (git checkout).
#  - Kalau berhasil: commit "release <app> v<versi>" + tag <app>-v<versi>.
# ============================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

APP="${1:-}"; shift || true
VER=""; DEPLOY=0; DRY=0; DIRTY_OK=0
for a in "$@"; do
  case "$a" in
    --deploy) DEPLOY=1 ;;
    --dry-run) DRY=1 ;;
    --allow-dirty) DIRTY_OK=1 ;;
    [0-9]*.[0-9]*.[0-9]*) VER="$a" ;;
    *) echo "[X] Argumen tidak dikenal: $a"; exit 1 ;;
  esac
done

SITE_APP="390f620b-ff0d-4ea9-a710-d47d5c4c62f8"      # pt-panel-app
SITE_VIEWER="d895392a-16dc-49c0-8caa-387e305c164d"   # pt-panel-viewer
SITE_DASH="pt-panel-dashboard"                       # site ID belum tercatat → pakai nama

say()  { echo "==> $*"; }
run()  { if [ "$DRY" = 1 ]; then echo "    [dry] $*"; else "$@"; fi; }
die()  { echo "[X] $*"; exit 1; }

# Nama file bebas di root: base.ext → base_r2.ext → base_r3.ext …
free_name() {
  local base="$1" ext="$2" n=2 f="$ROOT/$1.$2"
  while [ -e "$f" ]; do f="$ROOT/${base}_r$n.$ext"; n=$((n+1)); done
  echo "$f"
}

need_version() { [ -n "$VER" ] || die "Versi wajib diisi, mis: ./release.sh $APP 1.2.3"; }

check_clean() {
  [ "$DIRTY_OK" = 1 ] && return
  if [ -n "$(git status --porcelain)" ]; then
    git status --short
    die "Ada perubahan belum di-commit. Commit dulu, atau pakai --allow-dirty."
  fi
}

check_tag() { git rev-parse -q --verify "refs/tags/$1" >/dev/null && die "Tag $1 sudah ada. Pakai versi lain." || true; }

# Batalkan perubahan versi kalau gagal di tengah jalan
REVERT_FILES=()
on_fail() {
  if [ ${#REVERT_FILES[@]} -gt 0 ] && [ "$DRY" = 0 ]; then
    echo "[!] Gagal: perubahan versi dibatalkan."
    git checkout -- "${REVERT_FILES[@]}" 2>/dev/null || true
  fi
}
trap on_fail ERR

# Ganti teks versi dengan regex (python3 bawaan Mac cukup)
bump() {  # bump <file> <regex> <replacement>
  if [ "$DRY" = 1 ]; then echo "    [dry] versi → $VER di $1"; return; fi
  python3 - "$@" <<'PY'
import re, sys
path, pat, rep = sys.argv[1:4]
s = open(path, encoding="utf-8").read()
new, n = re.subn(pat, rep, s, count=1, flags=re.M)
if n == 0:
    sys.exit(f"[X] pola versi tidak ditemukan di {path}: {pat}")
open(path, "w", encoding="utf-8").write(new)
PY
}

commit_and_tag() {  # commit_and_tag <app> <files…>
  local app="$1"; shift
  run git add "$@"
  run git commit -q -m "release $app v$VER" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  run git tag "$app-v$VER"
  say "Commit + tag $app-v$VER"
}

# ------------------------------------------------------------ desktop
release_desktop() {
  need_version; check_clean; check_tag "desktop-v$VER"
  local D=paneltracker
  local IFS_VER; IFS_VER="${VER//./, }"
  REVERT_FILES=("$D/app/__init__.py" "$D/version_info.txt" "$D/installer/PanelTracker.iss" "$D/README.md")

  say "Versi desktop → $VER"
  bump "$D/app/__init__.py"            '^__version__ = "[^"]+"'            "__version__ = \"$VER\""
  bump "$D/version_info.txt"           'filevers=\([0-9, ]+\)'             "filevers=($IFS_VER, 0)"
  bump "$D/version_info.txt"           'prodvers=\([0-9, ]+\)'             "prodvers=($IFS_VER, 0)"
  bump "$D/version_info.txt"           "'FileVersion', '[^']+'"            "'FileVersion', '$VER'"
  bump "$D/version_info.txt"           "'ProductVersion', '[^']+'"         "'ProductVersion', '$VER'"
  bump "$D/installer/PanelTracker.iss" '^#define AppVersion "[^"]+"'       "#define AppVersion \"$VER\""
  bump "$D/README.md"                  '^# Panel Tracker v[0-9.]+'         "# Panel Tracker v$VER"

  say "Build .app + .dmg (termasuk self-test)"
  run "$D/build_mac.sh"

  local DMG; DMG="$(free_name "PanelTracker_${VER}_mac" dmg)"
  run cp "$D/dist/PanelTracker_${VER}_mac.dmg" "$DMG"

  commit_and_tag desktop "${REVERT_FILES[@]}"
  REVERT_FILES=()

  local SRC; SRC="$(free_name "PanelTracker_v${VER}_source" zip)"
  run git archive --format=zip -o "$SRC" HEAD "$D"

  say "Selesai:"; echo "    $DMG"; echo "    $SRC"
  echo "    Windows .exe: jalankan paneltracker/build.bat di Windows (versi sudah $VER)."
}

# ------------------------------------------------------------ mobile
release_mobile() {
  need_version; check_clean; check_tag "mobile-v$VER"
  local M=paneltracker-mobile
  REVERT_FILES=("$M/package.json" "$M/package-lock.json" "$M/src/config.ts" "$M/public/sw.js"
                "$M/android/app/build.gradle" "$M/README.md")

  local CODE; CODE=$(sed -n 's/^ *versionCode \([0-9]*\).*/\1/p' "$M/android/app/build.gradle" | head -1)
  [ -n "$CODE" ] || die "versionCode tidak ditemukan di build.gradle"
  say "Versi mobile → $VER (versionCode $CODE → $((CODE+1)))"
  if [ "$DRY" = 1 ]; then echo "    [dry] npm version $VER"; else
    (cd "$M" && npm version "$VER" --no-git-tag-version --allow-same-version >/dev/null); fi
  bump "$M/src/config.ts"              '^export const APP_VERSION = "[^"]+"' "export const APP_VERSION = \"$VER\""
  bump "$M/public/sw.js"               'const CACHE = "pt-web-v[^"]+"'       "const CACHE = \"pt-web-v$VER\""
  bump "$M/android/app/build.gradle"   'versionCode [0-9]+'                  "versionCode $((CODE+1))"
  bump "$M/android/app/build.gradle"   'versionName "[^"]+"'                 "versionName \"$VER\""
  bump "$M/README.md"                  '^# Panel Tracker Mobile \(Android\) v[0-9.]+' "# Panel Tracker Mobile (Android) v$VER"

  say "Test + build"
  (cd "$M" && run npm test --silent && run npm run build --silent && run npx cap sync android)

  commit_and_tag mobile "${REVERT_FILES[@]}"
  REVERT_FILES=()

  local Z; Z="$(free_name "PanelTracker_Mobile_v${VER}_AndroidStudio" zip)"
  say "Zip Android Studio → $(basename "$Z")"
  run zip -qr "$Z" "$M" \
      -x "$M/node_modules/*" "$M/dist/*" "$M/android/app/build/*" "$M/android/build/*" \
         "$M/android/.gradle/*" "$M/android/local.properties" "*/.DS_Store"
  # Gradle hanya butuh 2 modul ini (lihat android/capacitor.settings.gradle)
  run zip -qr "$Z" "$M/node_modules/@capacitor/android" "$M/node_modules/@capacitor/app" \
      -x "*/.DS_Store" "*/build/*" "*/ios/*" "*/node_modules/@capacitor/*/node_modules/*"

  if [ "$DEPLOY" = 1 ]; then
    say "Deploy PWA → pt-panel-app (public/_headers sudah ikut ke dist/)"
    run npx --yes netlify-cli deploy --prod --dir "$M/dist" --site "$SITE_APP"
  fi
  say "Selesai:"; echo "    $Z"
  [ "$DEPLOY" = 1 ] && echo "    PWA: https://pt-panel-app.netlify.app" || echo "    PWA belum di-deploy (tambahkan --deploy)."
}

# ------------------------------------------------------------ static sites
release_static() {  # release_static <folder> <zipbase> <site> <url>
  local F="$1" ZB="$2" SITE="$3" URL="$4"
  local Z; Z="$(free_name "$ZB" zip)"
  run zip -qr "$Z" "$F" -x "*/.DS_Store"
  say "Zip → $Z"
  if [ "$DEPLOY" = 1 ]; then
    local TMP; TMP="$(mktemp -d)"
    run cp "$F/index.html" "$F/_headers" "$TMP/"
    [ -f "$F/dashboard.js" ] && run cp "$F/dashboard.js" "$TMP/"
    say "Deploy → $URL"
    run npx --yes netlify-cli deploy --prod --dir "$TMP" --site "$SITE"
    rm -rf "$TMP"
  fi
}

case "$APP" in
  desktop)   release_desktop ;;
  mobile)    release_mobile ;;
  viewer)    release_static web-viewer   PanelTracker_WebViewer   "$SITE_VIEWER" https://pt-panel-viewer.netlify.app ;;
  dashboard) release_static pm-dashboard PanelTracker_PMDashboard "$SITE_DASH"   https://pt-panel-dashboard.netlify.app ;;
  *) sed -n '2,19p' "$0" | sed 's/^#  \{0,1\}//'; exit 1 ;;
esac
