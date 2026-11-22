# PanelChecker: Panel Tracker

Commissioning GI GAIA 2 150kV SAS: checking panel + punch list. Arsitektur, keputusan, dan aturan data lengkap ada di ADR codebase-memory-mcp (`manage_adr`, project `Users-jarbook-PanelChecker`). Baca ADR dulu, jangan membaca ulang README untuk konteks.

## Aturan wajib
- **Jangan timpa file build yang sudah diserahkan** (.dmg/.exe/.apk/.zip di root). Rebuild ke nama baru (`_r2`) atau naikkan versi. Cek `hdiutil info` sebelum menyentuh .dmg.
- **Jangan jalankan app GUI user** (`Panel Tracker.app`, `PanelTracker.exe`) dengan flag tebakan, karena itu membuka data asli. Hanya `--selftest <folder>` yang aman.
- **Supabase (`ewwtxklxgkyflhyazueg`) = data produksi.** Perubahan harus additive/idempotent (uuid5, `on conflict do nothing`, soft delete hanya untuk baris yang belum diisi). Jangan pernah menimpa hasil checking.
- Netlify: tanya dulu sebelum mengubah visitor access / login situs.
- Jawab dalam Bahasa Indonesia, ringkas.
- Git (lokal, branch `main`, tanpa remote): cek `git diff` alih-alih membaca ulang file. Commit setelah tiap perubahan selesai dan teruji. File build (.dmg/.zip/.apk) sengaja tidak masuk git.

## Struktur
| Folder | Isi | Stack |
|---|---|---|
| `paneltracker/` | Desktop app | Python 3.10–3.13, PySide6, SQLite, PyInstaller |
| `paneltracker-mobile/` | Android APK + PWA | React + TS + Vite + Capacitor |
| `web-viewer/` | Viewer QR publik read-only + edge function `panel-view` | HTML statis + Supabase Edge Function |
| `pm-dashboard/` | Dashboard PM (login) | HTML + `dashboard.js` |
| `kas-ca/` | App terpisah: Kas CA Proyek (bukan Supabase Panel Tracker) | Netlify Functions + Blobs |

File kunci desktop: `app/db.py` (SQLite), `app/cloud.py` (sinkron Supabase), `app/reports.py` (PDF), `app/i18n.py` + `app/i18n_en.py` (teks ID/EN), `app/ui/`.
Mobile: `src/sync.ts`, `src/api.ts`, `src/data.ts`, `src/i18n.ts` + `src/i18n_en.ts`, `src/ui/`.

## Versi: naikkan di semua tempat
- **Desktop:** `paneltracker/app/__init__.py` (`__version__`), `paneltracker/version_info.txt`, judul README.
- **Mobile:** `paneltracker-mobile/package.json`, `src/config.ts` (`APP_VERSION`), `public/sw.js` (`CACHE = "pt-web-vX"`), `android/app/build.gradle` (`versionCode` +1, `versionName`), judul README.

## Build
- **Desktop Mac:** `cd paneltracker && ./build_mac.sh` → `dist/PanelTracker_<versi>_mac.dmg` (sudah termasuk self-test). Pakai `SKIP_VENV=1` kalau venv sudah siap. Salin hasil ke root dengan nama yang belum ada.
- **Desktop Windows:** `paneltracker/build.bat`, hanya bisa dijalankan di Windows (oleh user).
- **Source zip:** `PanelTracker_v<versi>_source.zip` di root (tanpa `dist/`, `build/`, `.venv*`).
- **Mobile PWA:** `cd paneltracker-mobile && npm run build`, lalu deploy `dist/` + `_headers`:
  `npx netlify-cli deploy --prod --dir <folder> --site 390f620b-ff0d-4ea9-a710-d47d5c4c62f8` (pt-panel-app)
- **Mobile Android:** `npm run build && npx cap sync android` → zip project untuk Android Studio: `PanelTracker_Mobile_v<versi>_AndroidStudio.zip` (tanpa `node_modules`).
- **Web viewer:** `npx netlify-cli deploy --prod --dir <folder index.html & _headers> --site d895392a-16dc-49c0-8caa-387e305c164d` (pt-panel-viewer)
- **PM dashboard:** situs pt-panel-dashboard.netlify.app. Site ID belum tercatat, jadi cek dengan `npx netlify-cli sites:list` sebelum deploy.

## Test
- **Mobile:** `cd paneltracker-mobile && npm test` (vitest), `npm run build` (sudah termasuk `tsc`).
- **Desktop:** skrip di `paneltracker/tests/` dijalankan langsung dengan `python tests/<file>.py` dari folder mana saja (path relatif ke file test). Output `ALL OK` berarti lulus. Butuh Python 3.10–3.13 + `requirements.txt` (Python bawaan Mac 3.9 tidak cukup). Sinkron diuji dengan `tests/mock_supabase.py`, jangan pakai Supabase asli.
- Test import FAT butuh `Punchlist_GI_GAIA_2_13112026.xlsx` di `paneltracker/tests/data/` atau lewat env `PT_FAT_XLSX=<path>`. Kalau file tidak ada, bagian itu di-SKIP.
- Perubahan kecil (teks/warna): cukup self-test bawaan build.
