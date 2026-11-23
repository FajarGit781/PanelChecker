/* Pengaman update otomatis APK (lihat src/updater.ts).
   Bila bundle hasil update tidak berhasil tampil dalam 20 detik (markBundleOk tidak terpanggil), kembali ke bundle
   bawaan APK dan tandai versi itu rusak supaya tidak dicoba lagi. File terpisah karena CSP melarang script inline. */
(function () {
  try {
    var C = window.Capacitor;
    if (!C || !C.isNativePlatform || !C.isNativePlatform()) return;
    var applied = localStorage.getItem("pt.bundle.applied");
    if (!applied) return;
    setTimeout(function () {
      if (localStorage.getItem("pt.bundle.ok") === applied) return;
      localStorage.setItem("pt.bundle.bad", applied);
      localStorage.removeItem("pt.bundle.applied");
      localStorage.removeItem("pt.bundle.pending");
      var W = C.Plugins && C.Plugins.WebView;
      // bundle bawaan APK; ia menyimpan dirinya sendiri (persistServerBasePath) setelah tampil sehat
      if (W) W.setServerAssetPath({ path: "public" });
    }, 20000);
  } catch (e) { /* abaikan */ }
})();
