# Panel Tracker v2.9.1: Checking Panel & Punch List + Cloud Sync (ID / EN)

Aplikasi desktop Windows (.exe portable) untuk **checking panel per item uji fungsi** dan **mengelola punch list temuan**. Report PDF siap tanda tangan, dalam bahasa Indonesia atau English.

## Alur kerja
1. **Template checklist**: item uji standar per tipe panel. Tersedia 3 template bawaan (Panel Proteksi & Kontrol 35 item, RTU/Gateway 16 item, Umum), masing-masing juga dalam versi English. Semua bisa diedit, diduplikat, atau di-import/export Excel.
2. **Panel**: saat panel dibuat atau di-import dari Excel, template diterapkan otomatis sesuai tipe panelnya.
3. **Checking**: tiap item diberi hasil **OK / NG / N/A**, bisa ditambah nilai ukur (VDC, MΩ, dll.) dan catatan. Semua tersimpan otomatis, termasuk siapa yang mengecek dan kapan.
4. **NG → Punch**: begitu item diklik NG, form punch langsung terbuka dengan judul, deskripsi, kriteria, dan hasil ukur yang sudah terisi. Punch-nya otomatis terhubung ke item cek tersebut.
5. **Punch board**: Open → Dikerjakan → Siap Verifikasi → Closed. Status diubah dengan menyeret kartu antar kolom. Kategori punch:
   - **A · Critical**: wajib selesai sebelum energize
   - **B · Major**: wajib selesai sebelum serah terima
   - **C · Minor**: bisa menyusul

   Target selesai terisi otomatis per kategori (default 3/7/14 hari, bisa diatur di Pengaturan).
6. **Re-test & sign-off**: setelah perbaikan, ubah hasil item ke OK lalu **Terima panel** (menu ⋯ di panel). Penerimaan dicatat beserta nama dan tanggal.

Status panel ditentukan otomatis: *Belum dicek → Sedang dicek → Ada temuan → Lulus → Diterima*.

## Halaman
| Halaman | Isi |
|---|---|
| Beranda | KPI (panel dicek, % item diuji, item NG, punch open A/B/C, lewat target), donut status panel, tren punch dibuka vs ditutup, daftar panel yang perlu perhatian, punch terbaru, aktivitas terakhir |
| Checking Panel | Daftar kartu panel (cari/filter status) di kiri, checklist panel di kanan. Ada filter Belum/NG/Catatan, tombol "Semua OK" per section, dan "Sisa item = OK" |
| Punch List | Board kanban (drag & drop) atau tabel yang bisa disortir; filter panel, kategori, PIC, lewat target |
| Laporan & Data | PDF punch list (+foto, filter cetak), lembar uji per panel (+QR & tanda tangan), ringkasan checking, label QR, import FAT, export/import Excel |
| Template Checklist | Editor template |

**Scan QR**: tempel label QR di panel, lalu scan dengan scanner USB ke kotak di sidebar (atau ketik tag + Enter). Checklist panel tersebut langsung terbuka. Pintasan: `Ctrl+F` untuk scan/cari, `Ctrl+N` untuk punch baru.

## Cetak punch list dengan filter
Dialog **Cetak Punch List** memilih punch yang dicetak:
- Preset cepat: Semua / Belum close / Open saja / Closed saja / Kategori A aktif.
- Filter status, kategori A/B/C, lewat target, panel/bay (dengan pilih cepat per bay, misalnya Trafo atau UGC), kategori temuan, dan PIC.
- Pengaturan layout: urutan, kelompok per panel (dengan subtotal), lampiran foto, judul, dan bahasa report.
- Warna status di report: **Open merah**, **In Progress oranye**, **Ready to Verify biru**, **Closed hijau**.
- Layout report: teks kop panjang (nama perusahaan, alamat, nama project) otomatis diperkecil atau dipotong agar tidak menabrak judul. Kotak KPI menyesuaikan tinggi isinya, judul grup panel tidak tertinggal sendirian di bawah halaman, dan teks yang sangat panjang di satu sel dibatasi.
- Lampiran foto disusun 2 kartu per baris (4 punch per halaman), sehingga lebih hemat kertas.

## Bahasa / Language (v2.4)
- Tombol **ID / EN** di sidebar mengganti bahasa tampilan langsung. Window dibuka ulang di halaman yang sama; data tidak berubah.
- **Pengaturan** punya dua pilihan: **Bahasa tampilan** dan **Bahasa report PDF**. Report bisa berbeda bahasa dengan tampilan, misalnya UI Indonesia tapi report English untuk owner/vendor asing.
- Dialog **Cetak Punch List** punya pilihan bahasa per cetakan. Judul otomatis dan keterangan filter ikut bahasa tersebut.
- Yang diterjemahkan: menu, dialog, status (Dikerjakan → In Progress, Lulus → Passed, Diterima → Accepted), kategori bawaan (Mekanikal → Mechanical, dst.), serta header/legend/kolom PDF.
- Yang tidak diterjemahkan: data yang diketik user (judul temuan, remark, item checklist yang sudah ada).
- Template checklist bawaan versi English (`… — EN`) ikut tersedia. Saat UI English, panel baru otomatis memakai template EN.
- Kamus terjemahan ada di `app/i18n_en.py`. Teks yang belum ada di kamus tampil dalam bahasa Indonesia, jadi tidak pernah error.

## Tampilan (v2.7, sama dengan app Android)
- Gaya "ruang relay": latar abu RAL 7035, sidebar hitam seperti pelat traffolyte, lampu indikator IEC 60073 (merah = temuan/open, kuning = sedang dikerjakan, hijau = lulus/closed, biru = siap verifikasi). Kuning sinyal hanya untuk tombol aksi utama (Simpan, + Punch, Buat PDF). Font IBM Plex Sans dibundel di `assets/fonts` (lisensi OFL).
- Kartu panel: lampu status + pelat nama tag. Kartu punch: blok huruf A/B/C di kiri.
- Warna tidak lagi ikut mode gelap Windows. Palet terang dipasang paksa, dan kalender pemilih tanggal, daftar combo, menu, tooltip, kotak pesan serta centang diberi warna eksplisit. Teks putih di atas latar putih tidak terjadi lagi.
- Kontras dicek otomatis (`tests/shots_all.py`): setiap teks yang terlihat di semua halaman, dialog dan popup diukur terhadap latarnya, dengan Windows disimulasikan dalam mode gelap.

## Layar kecil (v2.5)
- Tata letak menyesuaikan laptop kecil (mis. 1366×768 dengan scaling 125%):
  - kartu Beranda dan Laporan pindah ke 2 kolom;
  - tombol checklist menjadi ikon saja (teks ada di tooltip);
  - filter punch list pindah ke 2 baris;
  - dialog yang lebih tinggi dari layar otomatis diperkecil sehingga tombol Simpan / Buat PDF tetap terlihat.
- Error tak terduga tidak menutup aplikasi. Pesannya ditampilkan, dan detailnya dicatat di `error.log` di folder data.

## Portable
`PanelTracker.exe` adalah satu file yang bisa dijalankan dari folder mana saja, termasuk flashdisk. Data (`paneltracker.db` + `settings.ini`) disimpan di folder **`PanelTracker_Data`** di samping exe. Jadi kalau folder ini dicopy, seluruh data ikut terbawa. Kalau folder exe tidak bisa ditulis (misalnya di Program Files setelah memakai installer), data otomatis disimpan di `Documents\PanelTracker`.

## Versi macOS (v2.7.3)
**Install:** buka `PanelTracker_<versi>_mac.dmg`, lalu seret **Panel Tracker** ke folder **Applications**.

**Saat pertama kali dibuka:** aplikasi ini belum ditandatangani dengan Apple Developer ID, jadi macOS memunculkan peringatan "developer tidak dikenal". Klik kanan aplikasi lalu pilih **Open**, atau buka **System Settings → Privacy & Security → Open Anyway**. Cukup sekali per Mac.

**Perbedaan dengan versi Windows:**
- Data (`paneltracker.db` + `settings.ini`) disimpan di **~/Documents/PanelTracker**, bukan di samping aplikasi, karena isi .app tidak boleh diubah.
- Token login cloud disimpan di **Keychain** macOS, bukan DPAPI. `settings.ini` hanya berisi rujukan, jadi menyalin folder data ke Mac lain tidak ikut membawa token login.
- Data yang disinkron sama dengan laptop Windows dan HP (Supabase yang sama).

**Jenis Mac:** build hanya jalan di jenis Mac yang sama dengan Mac yang dipakai untuk build: Apple Silicon (M1/M2/M3/…) atau Intel.

**Build sendiri:** butuh Python 3.10–3.13 dari python.org atau Homebrew. Jalankan `./build_mac.sh`, lalu ambil hasilnya di `dist/Panel Tracker.app` dan `dist/PanelTracker_<versi>_mac.dmg`. Script ini sekaligus menjalankan self-test seperti `build.bat`.

## Build .exe (Windows)
1. Install Python 3.12 (64-bit) dari python.org dan centang **Add python.exe to PATH**.
2. Double-click **`build.bat`**. Prosesnya ±3–5 menit dan diakhiri self-test otomatis (termasuk report English).
3. Hasilnya: `dist\PanelTracker.exe`.

Alternatif tanpa Windows: push ke GitHub, lalu jalankan workflow `.github/workflows/build.yml`.

**Installer (tahap berikutnya):** `installer/PanelTracker.iss` adalah draft untuk Inno Setup 6. Build exe dulu, lalu compile file .iss tersebut untuk menghasilkan `PanelTracker_Setup_2.7.4.exe`.

## Import punch list FAT (Excel)
Menu **Laporan & Data → Import Punch List FAT** membaca workbook dengan format satu sheet per panel dan kolom *No · Deskripsi Temuan · Dokumentasi Temuan · Rencana Tindakan · Dokumentasi Penyelesaian · Status · Remark*.

- Foto yang ditempel di dalam sel ikut diimpor: kolom Dokumentasi Temuan menjadi foto **sebelum**, kolom Dokumentasi Penyelesaian menjadi foto **sesudah**. Ukuran foto otomatis diperkecil.
- Status Close/Open/Proses dipetakan ke Closed/Open/Dikerjakan.
- Kategori A/B/C dan kategori temuan ditebak dari deskripsi, jadi sebaiknya dicek ulang.
- Sheet "General" menjadi punch umum (tidak terkait panel). Sheet lainnya masing-masing menjadi satu panel.
- ID dibuat deterministik, jadi import ulang file yang sama tidak membuat data dobel, termasuk di laptop lain dan di cloud.
- Kotak penanda merah yang digambar di atas foto di Excel tidak ikut terimpor, karena itu objek gambar terpisah dari fotonya.

## Sinkronisasi cloud (Supabase)
Aplikasi tetap bekerja **offline**: semua data tersimpan di SQLite lokal. Saat ada internet, tombol **Cloud sync** di sidebar (atau sinkron otomatis tiap 5/10/30 menit) akan:
1. **Mengambil** perubahan dari anggota tim lain.
2. **Mengirim** perubahan lokal, termasuk mengupload foto ke Storage bucket `panel-photos` (privat).
3. **Mengunduh** foto yang belum ada di laptop.

Detail cara kerjanya:
- **Konflik** (dua orang mengubah item yang sama saat offline): perubahan yang terakhir menang (*last-write-wins*). Aturan ini dijaga oleh server.
- **Kode punch bentrok** (dua laptop sama-sama membuat PL-0023 saat offline): punch yang belum terkirim otomatis diberi nomor berikutnya.
- **Hapus** bersifat *soft delete*, sehingga penghapusan ikut tersinkron ke laptop lain.
- **Keamanan:** hanya email yang terdaftar di tabel `app_users` yang bisa membaca data (Row Level Security). Peran `viewer` hanya bisa membaca, sedangkan `admin`/`engineer`/`vendor` bisa menulis. Aplikasi hanya memakai *publishable key*; secret key tidak pernah ada di exe.

**Akun tim (v2.5):** login cukup pakai **username**. Di belakang layar, username `Fajar` dipetakan ke email internal `fajar@paneltracker.local`. Email lengkap tetap bisa dipakai.

| Username | Peran | Hak |
|---|---|---|
| Fajar, Azaly, Ahnaf, Mirza | engineer | lihat & ubah semua data |
| Viewer | viewer | hanya lihat |

**Mode viewer:** setelah login sebagai viewer, sidebar menampilkan label *MODE VIEWER · hanya lihat*. Dalam mode ini:
- Tombol tambah/ubah disembunyikan dan tombol OK/NG/N/A terkunci.
- Viewer tetap bisa membuka punch, melihat foto, mencetak semua report, dan mengganti bahasa.
- Sinkron hanya mengambil data dari cloud; tidak ada yang dikirim.
- Server juga menolak perubahan dari viewer (Row Level Security), jadi aturan ini tidak bisa diakali dari aplikasi.

**Menambah anggota tim:**
1. Di dashboard Supabase buka **Authentication → Users → Add user**. Isi email `username@paneltracker.local` (huruf kecil) dan password, lalu centang *Auto confirm*.
2. Daftarkan email tersebut di tabel tim (SQL Editor), dengan peran `engineer` atau `viewer`:
   `insert into public.app_users(email, full_name, role) values ('budi@paneltracker.local','Budi','engineer');`
3. Disarankan: **Authentication → Sign In / Providers → matikan "Allow new users to sign up"**.

Skema lengkap ada di `supabase/schema.sql`. Kuota gratis Supabase: database 500 MB, foto 1 GB. Project free akan di-pause setelah 7 hari tanpa aktivitas; aktifkan lagi dari dashboard bila perlu (data tidak hilang).

## Keamanan (v2.6)
Supabase API memang bisa dihubungi dari internet, karena dari situlah semua laptop sinkron. Tapi datanya tidak bisa dibaca atau diubah siapa pun tanpa akun tim. Pengamanannya berlapis:

**Server (Supabase)**
- *Publishable key* yang ada di exe **tidak memberi akses apa pun**. Tanpa login, semua tabel menolak (`permission denied`). Key ini memang dirancang untuk boleh diketahui; yang melindungi data adalah login + Row Level Security.
- Hanya akun yang terdaftar di `app_users` yang bisa melihat data. Viewer hanya bisa baca. Tidak ada yang bisa mengubah perannya sendiri.
- Tidak ada hapus permanen dari aplikasi (tabel maupun foto). "Hapus" hanya menandai data, jadi masih bisa dipulihkan.
- **Audit log** (`private.pt_audit`) mencatat setiap perubahan: siapa, kapan, data lama dan baru. Log ini hanya bisa dibaca admin lewat SQL Editor.
- Jam laptop yang salah atau dimanipulasi tidak bisa "mengunci" data, karena tanggal di masa depan dikoreksi ke jam server.
- Foto disimpan di bucket privat: maks 5 MB, hanya JPEG/PNG.
- Secret / service key tidak pernah ada di aplikasi. Aplikasi bahkan menolak kalau secret key atau alamat `http://` dimasukkan di pengaturan server.

**Aplikasi**
- Password bawaan/lemah **wajib diganti** saat login pertama. Aturannya: min. 10 karakter, ada huruf dan angka, bukan password umum, tidak mengandung username. Ganti password kapan saja lewat **Akun cloud → Ganti password…**.
- Token login di `settings.ini` dienkripsi dengan **Windows DPAPI**. Kalau folder data disalin ke laptop atau akun Windows lain, token tidak bisa dipakai dan harus login ulang.
- **Keluar** juga mencabut sesi di server, bukan hanya menghapus di laptop.
- Koneksi selalu HTTPS dengan verifikasi sertifikat.

**Yang perlu diatur admin di dashboard Supabase** (tidak bisa dari aplikasi/SQL):
1. **Authentication → Sign In / Providers**: matikan *Allow new users to sign up* dan *Allow anonymous sign-ins*.
2. **Authentication → Policies / Passwords**: *Minimum password length* = 10, *Password requirements* = huruf + angka.
3. Akun Supabase (dashboard) aktifkan **MFA / 2FA**. Akun dashboard adalah kunci utama seluruh data.
4. **Database → Settings → SSL**: aktifkan *Enforce SSL on incoming connections*.

**Di laptop:** aktifkan BitLocker (Windows Pro) atau simpan folder data di drive terenkripsi, karena database lokal berisi semua data dan foto. Jangan bagikan folder `PanelTracker_Data` lewat chat/flashdisk ke orang luar.

**Pengaturan tim ikut sinkron (v2.7.1):** isi kop report (nama perusahaan, alamat, logo), tanda tangan report, daftar kategori temuan & tipe panel, dan target selesai default **cukup sekali** di satu laptop. Setelah disimpan, langsung dikirim ke cloud dan laptop lain mendapatkannya saat sinkron berikutnya. Kategori dan target default juga dipakai di aplikasi HP. Nama user dan bahasa tetap per laptop. Kalau dua orang mengubah pengaturan yang sama saat offline, perubahan yang terakhir yang dipakai. Viewer hanya bisa melihat pengaturan ini.

**Label QR (v2.7.1):** QR berisi `PT:<uuid panel>:<tag>`. uuid sama di semua laptop dan HP, jadi label yang dicetak di laptop mana pun membuka panel yang benar. Label lama (berisi nomor urut laptop pencetak) tetap bisa di-scan: aplikasi memakai tag-nya, bukan nomornya. Disarankan cetak ulang label lama. Teks label dibungkus maksimal 2 baris dan tidak pernah saling menimpa; baris baru dari data Excel tidak lagi muncul sebagai kotak hitam.

**Viewer web tanpa login (v2.7.2):** isi **Pengaturan → Alamat viewer web (link label QR)** dengan alamat https halaman viewer (folder `web-viewer`). Setelah itu, label QR berisi `https://<viewer>/?p=<uuid panel>`. Scan dengan kamera HP biasa, dan halaman progress & punch list panel itu langsung terbuka tanpa login dan hanya bisa dilihat. Scanner USB di aplikasi ini tetap mengenali label baru maupun label lama. Kalau alamat dikosongkan, label kembali ke format `PT:<uuid>:<tag>`. Detail keamanan ada di `web-viewer/README.md`.

**Printer label (v2.7.2):** saat **Cetak label QR**, pilih **Printer label (1 label per halaman, mis. Xprinter)** lalu pilih ukuran label. Tersedia preset 40×30 sampai 100×100 mm, atau isi ukuran sendiri. Setiap panel dicetak menjadi satu halaman PDF seukuran label, hitam pekat tanpa garis putus, supaya tajam di printer thermal 203 dpi.
- Label melebar: QR di kiri, teks di kanan.
- Label persegi atau tegak: QR di atas, tag di bawah.

Ukuran yang dipilih diingat per laptop. Di driver printer, set ukuran kertas yang sama, lalu cetak PDF dengan skala **100% / Actual size**. Pilihan lama **Kertas A4 (24 label)** tetap ada.

**Keluar dari akun (v2.7.3):** **Keluar** hanya mencabut sesi laptop ini. Laptop dan HP lain yang memakai akun yang sama tetap login. Sebelumnya, keluar di satu perangkat ikut memutus semua perangkat lain.

**Checksheet integrasi SAS GAIA 2:** dibuat dari drawing *E2010-96564-BD-01-SAD rev A2*. Setiap panel GAIA2 mendapat satu seksi per device (C264, P643, P841, P143, P746, PCS-931, P5F30, PM8240, RTF), masing-masing 5 item:
1. Terintegrasi ke SAS
2. IP sudah dikonfigurasi (kriteria subnet bay 172.16.n.x; IP aktual diisi di kolom nilai)
3. SNTP sudah sinkron
4. CID sudah diupload
5. Setting sudah diupload. Approval setting baru keluar saat SAT, jadi tidak dicek di sini.

Perangkat panel SAS 1/2 (GPS, Gateway, SAS Server, Workstation) cukup 3 item: terintegrasi, IP, dan SNTP. Template **SAS · …** per tipe panel tersedia untuk panel baru. Generator ada di `tools/sas_checksheet_gaia2.py`, dan SQL yang diterapkan ada di `supabase/sas_checksheet_gaia2.sql`.

**Cetak check sheet dengan filter (v2.7.3):** buka **Laporan & Data → Lembar Uji Panel → Pilih panel & cetak…**, atau **⋯ → Cetak check sheet** di panel.
- **Panel:** cari tag/nama/bay; saring tipe, bay, dan status (Belum dicek / Sedang dicek / Ada temuan / Lulus / Diterima); lalu centang panel yang dicetak. Tombol cepat: Semua panel, Belum selesai, Ada temuan.
- **Isi:** pilih seksi (**Hanya SAS** / **Tanpa SAS** / pilih sendiri) dan item (semua / belum dicek / NG / belum dicek + NG). Panel tanpa item yang cocok otomatis dilewati.
- **Opsi:** **form kosong** untuk diisi tangan di lapangan (hasil, nilai, dan catatan dikosongkan; ada isian tanggal uji dan penguji), punch list panel, kolom tanda tangan, judul, dan bahasa report.

**Matriks SAS (v2.7.4):** di panel yang punya checksheet integrasi SAS, tombol **Matriks SAS** (bar filter checklist) menampilkan tabel device × Integrasi · IP · SNTP · CID · Setting.
- Klik sel untuk mengganti status: kosong → ✓ → ✗ → N/A.
- IP bisa diketik langsung di sel. Item IP otomatis OK kalau IP valid, masih di subnet bay, dan tidak dobel dengan device lain di panel mana pun.
- Matriks dan daftar memakai item yang sama, jadi selalu sinkron.
- Aturannya sama dengan aplikasi HP (`app/sas_matrix.py`).

**Koneksi cloud (v2.7.4):** aplikasi mencoba IPv4 lebih dulu, dengan batas waktu sambung pendek. Dulu di jaringan dengan IPv6/NAT64 yang tidak berfungsi, setiap permintaan tertunda sekitar 80 detik.

**Pemulihan & reset password:** lihat contoh SQL di akhir `supabase/schema.sql`.

## Struktur kode
```
main.py                      entry point, mode portable, --selftest <folder>
app/db.py                    skema SQLite & logika (status panel, statistik, punch)
app/templates_default.py     template checklist bawaan (ID + EN)
app/reports.py               PDF: punch list, lembar uji, ringkasan, label QR
app/excel_io.py              import/export Excel (panel, template, data)
app/import_fat.py            import punch list FAT (+ foto di dalam sel)
app/cloud.py                 klien Supabase (Auth/REST/Storage) + mesin sinkron, aturan password
app/secure_store.py          enkripsi token login (Windows DPAPI)
app/i18n.py, app/i18n_en.py  bahasa (tr(), kamus Indonesia → English)
app/ui/cloud_ui.py           dialog akun cloud, sinkron background, status sidebar
supabase/schema.sql          skema cloud (referensi)
app/ui/theme.py              warna, stylesheet, ikon SVG
app/ui/widgets.py            komponen: KPI card, donut, bar chart, tombol OK/NG/NA, kartu panel & punch
app/ui/page_*.py             halaman Beranda, Checking, Punch, Laporan, Template
app/ui/dialogs.py            form project/site/panel/punch/pengaturan
app/ui/report_dialogs.py     dialog filter cetak punch list
```
