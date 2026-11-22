# Panel Tracker Viewer (web, tanpa login)

Scan label QR di pintu panel dengan **kamera HP biasa**. Halaman progress panel itu langsung terbuka: status, % pengecekan, punch list (dengan foto), dan checklist. Tidak perlu login dan tidak perlu install aplikasi. Halaman ini hanya untuk melihat; tidak ada data yang bisa diubah dari sini.

```
web-viewer/
  index.html                               halaman viewer (satu file, statis)
  supabase/functions/panel-view/index.ts   Edge Function publik hanya-baca (sudah di-deploy)
```

## Cara kerja
1. Label QR berisi link `https://<alamat viewer>/?p=<uuid panel>`.
2. `index.html` memanggil `https://ewwtxklxgkyflhyazueg.supabase.co/functions/v1/panel-view?id=<uuid>`.
3. Edge Function memanggil fungsi database `public.pt_panel_view(uuid)`. Hasilnya hanya data **satu panel itu**, ditambah link foto yang berlaku 1 jam.

Halaman juga punya tombol **Buka kamera**. Tombol ini untuk HP yang membuka viewer tanpa link, atau untuk scan label v2.7.1 (`PT:<uuid>:<tag>`) dari dalam halaman.

## Keamanan
- Panel hanya bisa dibuka dengan uuid acak yang ada di label QR. **Tidak ada pencarian tag dan tidak ada daftar panel**, jadi orang luar tidak bisa mencoba-coba "Trafo 1, Trafo 2, …".
- Siapa pun yang memegang link atau foto label bisa melihat panel itu. Ini disengaja: setara dengan berdiri di depan panelnya.
- Pengamanan v2.6 tidak dibuka:
  - tabel tetap tertutup untuk anon;
  - `service_role` tetap tanpa hak SELECT tabel;
  - `pt_panel_view` hanya bisa dipanggil oleh `service_role`, yaitu oleh Edge Function, bukan oleh browser;
  - bucket foto tetap privat.
- Data yang dikembalikan tidak memuat kolom internal (`updated_by`, `server_updated_at`, dll.) dan tidak memuat data panel lain.
- **Mematikan akses publik kapan saja:** Supabase dashboard → Edge Functions → `panel-view` → Delete. Label tetap berisi link, tetapi halaman akan menampilkan "Panel tidak ditemukan".

> **Catatan uuid:** panel hasil *Import Punch List FAT* memakai uuid deterministik, yang dihitung dari nama file/sheet dengan kunci yang ada di aplikasi. Orang yang memegang exe Panel Tracker **dan** tahu nama sheet-nya secara teori bisa menghitung uuid tersebut. Untuk data internal proyek risiko ini kecil. Panel yang dibuat manual memakai uuid acak penuh.

## Langkah setelah ini
1. **Online-kan halaman** (wajib https). Pilih salah satu cara berikut, semuanya gratis:
   - Netlify Drop: buka https://app.netlify.com/drop, lalu seret folder `web-viewer`;
   - GitHub Pages;
   - Cloudflare Pages.

   **Sudah online:** `https://pt-panel-viewer.netlify.app/` (Netlify, tim fajar-surya-ramadhani; visitor access situs ini = publik, pengaturan tim tidak diubah). Update halaman: `npx netlify-cli deploy --prod --dir <folder berisi index.html & _headers> --site d895392a-16dc-49c0-8caa-387e305c164d`.
2. Di aplikasi desktop **Panel Tracker 2.7.2**, buka **Pengaturan → Umum & Kop Report → Alamat viewer web (link label QR)** dan isi alamat tadi. Pengaturan ini ikut sinkron ke laptop tim lain.
3. **Cetak ulang label QR** (Laporan & Data → Label QR Panel). Mulai sekarang label berisi link.
4. Scan dengan kamera HP mana pun.

Label baru tetap bisa di-scan di:
- aplikasi desktop (scanner USB atau ketik);
- aplikasi Android, setelah di-build ulang dengan perubahan di `paneltracker-mobile/src/logic.ts`.

## Data yang tampil
Data diambil **dari cloud**. Perubahan yang belum di-*Cloud sync* dari laptop atau HP belum muncul. Tekan **↻ Muat ulang** untuk mengambil data terbaru.
