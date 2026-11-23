# Panel Tracker Mobile (Android) v1.2.2

Aplikasi HP pendamping lapangan untuk Panel Tracker. Data sama dengan aplikasi laptop karena keduanya sinkron ke Supabase yang sama.

## Versi web / iPhone (gratis)
Aplikasi yang sama juga tersedia sebagai web app di **https://pt-panel-app.netlify.app**. Versi ini cocok untuk iPhone dan HP apa pun, tanpa APK dan tanpa App Store. Login, data, sinkron, dan fiturnya sama dengan aplikasi Android.

Cara memasang di HP:
- **iPhone:** buka link di **Safari**, tekan **Bagikan**, lalu pilih **Tambah ke Layar Utama**.
- **Android:** buka link di Chrome, buka menu **⋮**, lalu pilih **Instal aplikasi** atau **Tambahkan ke layar utama**.

Setelah dipasang, aplikasi terbuka layar penuh seperti aplikasi biasa dan tetap bisa dibuka tanpa sinyal, karena `public/sw.js` menyimpan file aplikasinya di HP. Datanya tersimpan di HP, sama seperti versi Android.

> iPhone bisa menghapus data situs yang tidak dibuka lebih dari 7 hari **kalau web dibuka dari Safari biasa**. Pasang lewat **Tambah ke Layar Utama** dan rutin sinkron supaya data aman.

Update versi web: jalankan `npm run build`, lalu upload isi `dist/` beserta file `_headers` ke Netlify, situs `pt-panel-app` (`npx netlify-cli deploy --prod --dir <folder> --site 390f620b-ff0d-4ea9-a710-d47d5c4c62f8`).

## Tampilan (v1.1)
Bahasa visualnya diambil dari ruang relay:
- latar abu-abu cat panel (RAL 7035);
- tag panel tampil seperti **pelat nama traffolyte** hitam ber-grafir putih;
- status memakai **lampu indikator** warna IEC 60073: merah = temuan / open, kuning = sedang dicek / dikerjakan, biru = siap verifikasi, hijau = lulus / closed, padam = belum dicek;
- kuning sinyal hanya untuk aksi utama (Masuk, Simpan, tombol Scan di tengah).

Layarnya:
- **Ringkasan** dibuka dengan status energize: berapa punch kategori A yang masih menahan energize. Lalu ada tombol lanjutkan panel terakhir, progres per site, dan punch yang perlu tindakan.
- **Panel** tampil sebagai deretan kubikel per site.
- **Lembar uji** memakai nomor langkah dan tombol OK/NG/N/A besar yang tetap mudah ditekan pakai sarung tangan.
- **Punch** memakai alur status 4 langkah, pilihan kategori A/B/C beserta artinya, dan foto Sebelum/Sesudah terpisah.
- Lampu di kanan atas menunjukkan status sinkron; tekan untuk sinkron sekarang.

**v1.1.5, matriks SAS:** panel yang punya checksheet integrasi SAS bisa ditampilkan sebagai tabel **device × Integrasi · IP · SNTP · CID · Setting**.
- Tap sel untuk mengganti status: kosong → ✓ OK → ✗ NG → N/A.
- IP bisa diketik langsung di sel. Item IP otomatis OK kalau IP valid, masih di subnet bay, dan tidak dobel dengan device lain di panel mana pun. Kalau ada masalah, muncul peringatan dan item tidak otomatis OK.
- Tombol "Semua OK" per device, dan tombol "+ Punch" untuk sel NG.
- Pilihan tampilan Matriks/Daftar diingat.

**v1.1.4, sesi login:**
- **Keluar** sekarang hanya mencabut sesi di HP itu. Sebelumnya, satu orang keluar dari akun (mis. Fajar) di satu HP membuat semua HP dan laptop lain yang memakai akun yang sama ikut putus, sehingga perubahan tidak terkirim lagi.
- Kalau sesi berakhir (akun keluar di perangkat versi lama atau password diganti), muncul layar **Login ulang**. Data di HP, termasuk yang belum terkirim, tetap disimpan dan langsung dikirim setelah login.

**v1.1.3:** scan QR juga mengenali label baru dari desktop v2.7.2 yang berisi link viewer web (`https://…/?p=<uuid>`). Label `PT:` lama tetap bisa di-scan.

**v1.1.2:** kategori temuan dan target selesai default sekarang mengikuti pengaturan tim yang diisi di laptop (Pengaturan → Daftar Pilihan), jadi tidak perlu diatur di HP. Scan QR memakai uuid panel dari label baru, sehingga label yang dicetak di laptop mana pun membuka panel yang benar. Label lama tetap bisa di-scan lewat tag-nya.

**v1.1.1, warna & kontras:** aplikasi selalu tampil terang walau HP memakai mode gelap (`color-scheme: light` dan `forceDarkAllowed=false`), sehingga pemilih tanggal dan isian tidak berubah jadi teks putih di atas latar putih. Teks berwarna memakai versi lampu yang lebih gelap, dan teks samar dibuat lebih tebal kontrasnya. Semua layar dicek otomatis: setiap teks minimal 4.5:1 terhadap latarnya, diuji dengan Chrome dalam mode gelap.

## Fitur
- **Login** pakai username tim (Fajar, Azaly, Ahnaf, Mirza, Viewer). Password lemah/bawaan wajib diganti saat login pertama.
- **Ringkasan**: status energize (punch kategori A terbuka), lanjutkan panel terakhir, panel dicek, % item uji, punch lewat target, progres per site, dan punch yang perlu tindakan. Project dan site dipilih lewat tombol di kanan atas.
- **Checking panel**: daftar panel dengan status dan progres. Checklist per section dengan tombol **OK / NG / N/A**, nilai ukur, dan catatan.
  - Klik **NG** langsung membuka form punch yang sudah terisi dan terhubung ke item cek.
  - Panel bisa diterima (sign-off) dari HP.
- **Punch list**: filter status, A/B/C, dan pencarian. Form punch lengkap: status, kategori, panel, PIC, target, deskripsi, tindakan.
  - **Foto langsung dari kamera** atau galeri, otomatis diperkecil ke maks 1600 px.
  - Foto dipisah kolom **Sebelum** dan **Sesudah**; pilih kolomnya saat memotret.
- **Scan QR** label panel (label dari menu *Label QR* di laptop), atau ketik tag panel.
- **Offline**: semua data tersimpan di HP. Perubahan dikirim otomatis saat ada sinyal, saat aplikasi dibuka, dan tiap 10 menit. Foto diunduh saat punch dibuka, atau sekaligus lewat *Akun → Unduh semua foto*.
- **Bahasa Indonesia / English** (menu Akun).
- **Viewer**: hanya bisa melihat. Tombol ubah disembunyikan, dan server juga menolak perubahan.

Cetak PDF, import Excel/FAT, dan edit template checklist tetap dilakukan di laptop.

## Build APK di Android Studio (Windows / Parallels)
Folder `android/` sudah berisi aplikasi web yang siap pakai, jadi **tidak perlu Node.js** untuk build.

1. Install **Android Studio** versi terbaru dari developer.android.com/studio. Ikuti setup default; Android SDK ikut terpasang (±5 GB).
2. Ekstrak zip, lalu di Android Studio pilih **File → Open** → folder **`paneltracker-mobile/android`**.
3. Tunggu **Gradle sync** selesai (pertama kali ±5–15 menit, butuh internet). Kalau diminta, pilih **Gradle JDK = jbr-21** (JDK bawaan Android Studio).
4. **Build → Build App Bundle(s) / APK(s) → Build APK(s)**. Hasilnya ada di `android/app/build/outputs/apk/debug/app-debug.apk`.
5. Pasang di HP dengan salah satu cara:
   - Copy `app-debug.apk` ke HP, buka, lalu izinkan *Install unknown apps*.
   - Atau colok HP lewat USB (aktifkan *Developer options → USB debugging*), lalu tekan **Run ▶**. Di Parallels, pastikan USB HP diarahkan ke Windows VM.

Minimal Android 7.0. Saat pertama memotret atau scan QR, aplikasi meminta izin kamera.

### Untuk dibagikan ke tim (disarankan)
Pakai APK **release bertanda tangan** supaya update berikutnya bisa dipasang di atas versi lama:
1. **Build → Generate Signed App Bundle / APK → APK → Create new…** (buat keystore).
2. **Simpan file keystore dan passwordnya baik-baik.** Tanpa keystore yang sama, update tidak bisa dipasang di atas versi lama dan aplikasi harus di-uninstall dulu (data yang belum sinkron hilang).
3. Pilih *release*, lalu Finish. Hasilnya ada di `android/app/release/app-release.apk`.

Setiap rilis baru: naikkan `versionCode` (dan `versionName`) di `android/app/build.gradle`.

## Keamanan
- Koneksi hanya HTTPS ke Supabase. Content-Security-Policy memblokir alamat lain, dan cleartext HTTP dimatikan di Android.
- Publishable key di aplikasi tidak memberi akses tanpa login. Hak akses dijaga Row Level Security di server, sama dengan aplikasi laptop.
- Sesi login dan data offline disimpan di penyimpanan privat aplikasi, **tidak ikut backup** Google atau transfer ke HP lain (`allowBackup=false`, `data_extraction_rules.xml`).
- **Keluar** mencabut sesi di server dan **menghapus semua data di HP**. Kalau masih ada perubahan yang belum terkirim, aplikasi memberi peringatan dulu.
- Debugging WebView dimatikan di build ini.
- Saran: aktifkan kunci layar (PIN/sidik jari) di HP. Kalau HP hilang, segera ganti password akun tersebut dari laptop (Akun cloud → Ganti password).

## Mengubah kode (developer)
Butuh Node.js 22.
```
npm install --legacy-peer-deps
npm run dev            # coba di browser
npm run build          # cek TypeScript + build ke dist/
npx cap sync android   # salin hasil build ke project Android
```
Struktur:
```
src/config.ts        alamat server, konstanta
src/api.ts           klien Supabase (Auth/REST/Storage), format sama dengan desktop
src/store.ts         penyimpanan offline (IndexedDB) + cache memori
src/sync.ts          mesin sinkron (pull → push, last-write-wins, kode punch bentrok, foto)
src/session.ts       login, ganti password, viewer, sinkron otomatis
src/logic.ts         aturan bisnis (status panel, kode punch, aturan password)
src/ui/*.tsx         layar: Login, Beranda, Panel, Punch, Scan, Akun
android/             project Android Studio (Capacitor 8)
tests/               uji interoperabilitas HP ↔ laptop
```
