"""Panel Tracker v2 — entry point.

Mode portable: data (database + settings.ini) disimpan di folder `PanelTracker_Data`
di samping .exe. Kalau folder itu tidak bisa ditulis (mis. exe di Program Files),
otomatis pindah ke Documents\\PanelTracker. Di macOS (.app), data selalu di ~/Documents/PanelTracker.
"""
import os
import sys


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(rel):
    return os.path.join(getattr(sys, "_MEIPASS", base_dir()), rel)


def data_dir():
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        # macOS: isi Panel Tracker.app tidak boleh diubah (dan hilang saat update) → data di Documents
        docs = os.path.join(os.path.expanduser("~"), "Documents", "PanelTracker")
        os.makedirs(docs, exist_ok=True)
        return docs
    cand = os.path.join(base_dir(), "PanelTracker_Data")
    try:
        os.makedirs(cand, exist_ok=True)
        test = os.path.join(cand, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return cand
    except OSError:
        docs = os.path.join(os.path.expanduser("~"), "Documents", "PanelTracker")
        os.makedirs(docs, exist_ok=True)
        return docs


def selftest(out_dir):
    """Uji build: DB demo + semua report + render semua halaman, tanpa interaksi."""
    from PySide6.QtCore import QSettings
    from app.db import Database
    from app.demo import create_demo
    from app.excel_io import export_project, import_panels, write_panel_template, export_template, import_template
    from app.reports import ReportBuilder
    from app.ui.main_window import MainWindow
    os.makedirs(out_dir, exist_ok=True)
    dbp = os.path.join(out_dir, "selftest.db")
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(dbp + ext):
            os.remove(dbp + ext)
    db = Database(dbp)
    pid = create_demo(db)
    rb = ReportBuilder(db, pid)
    rb.punchlist_report(os.path.join(out_dir, "punchlist.pdf"))
    ids = [p["id"] for p in db.panels(pid)]
    rb.check_sheets(os.path.join(out_dir, "lembar_uji.pdf"), ids[:3])
    rb.summary_report(os.path.join(out_dir, "ringkasan.pdf"))
    rb.qr_labels(os.path.join(out_dir, "qr.pdf"), ids)
    from app.i18n import using
    with using("en"):
        rb.punchlist_report(os.path.join(out_dir, "punchlist_en.pdf"), group_by_panel=True, sort="status")
        rb.check_sheets(os.path.join(out_dir, "lembar_uji_en.pdf"), ids[:2])
        rb.summary_report(os.path.join(out_dir, "ringkasan_en.pdf"))
    export_project(db, pid, os.path.join(out_dir, "export.xlsx"))
    write_panel_template(db, os.path.join(out_dir, "template_panel.xlsx"))
    import_panels(db, pid, os.path.join(out_dir, "template_panel.xlsx"))
    tid = db.templates()[0]["id"]
    export_template(db, tid, os.path.join(out_dir, "template_checklist.xlsx"))
    import_template(db, os.path.join(out_dir, "template_checklist.xlsx"))
    db.close()
    st = QSettings(os.path.join(out_dir, "selftest.ini"), QSettings.IniFormat)
    w = MainWindow(dbp, remember=False, settings=st)
    w.resize(1440, 880)
    w.show()
    from PySide6.QtWidgets import QApplication
    for i in range(len(w.pages)):
        w.nav_to(i)
        for _ in range(3):
            QApplication.processEvents()
        w.grab().save(os.path.join(out_dir, f"page_{i}.png"))
    w.close()
    print("SELFTEST OK")
    return 0


def install_excepthook(log_dir):
    """Error tak terduga: tampilkan pesan & tulis ke error.log — aplikasi tetap jalan."""
    import traceback
    import datetime as _dt

    def hook(etype, value, tb):
        from PySide6.QtWidgets import QApplication, QMessageBox
        from app.db import ReadOnlyError
        from app.i18n import tr
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        parent = QApplication.activeWindow()
        if isinstance(value, ReadOnlyError):
            QMessageBox.information(parent, "Panel Tracker",
                                    tr('Akun viewer hanya bisa melihat data. Login sebagai engineer untuk mengubah.'))
            return
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            with open(os.path.join(log_dir, "error.log"), "a", encoding="utf-8") as f:
                f.write(f"\n===== {_dt.datetime.now():%Y-%m-%d %H:%M:%S} =====\n{text}")
        except OSError:
            pass
        sys.__stderr__ and sys.__stderr__.write(text)
        QMessageBox.warning(parent, "Panel Tracker",
                            tr('Terjadi kesalahan, tapi data aman dan aplikasi tetap jalan.\n\n{0}: {1}\n\n'
                               'Detail tersimpan di error.log (folder data).', etype.__name__, value))

    sys.excepthook = hook


def main():
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication
    from app.ui.theme import STYLE

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PanelTracker.App.2")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Panel Tracker")
    app.setOrganizationName("PanelTracker")
    from app.ui.theme import setup_app
    setup_app(app, resource_path(""))   # font IBM Plex, palet terang (tidak ikut mode gelap Windows), stylesheet
    ic = resource_path(os.path.join("assets", "icon.ico"))
    if os.path.exists(ic):
        app.setWindowIcon(QIcon(ic))
    if "--selftest" in sys.argv:
        rc = selftest(sys.argv[sys.argv.index("--selftest") + 1])
        sys.stdout.flush()
        os._exit(rc)   # sama seperti keluar normal: hindari crash Qt saat Python membereskan objek

    from app import i18n
    from app.ui.main_window import MainWindow
    if sys.platform == "darwin" and getattr(sys, "frozen", False) and \
            os.path.abspath(sys.executable).startswith("/Volumes/"):
        # Dijalankan langsung dari disk image (.dmg). Kalau .dmg di-eject/diganti saat aplikasi jalan, macOS tidak
        # bisa lagi membaca kode aplikasi → crash (SIGBUS). Minta pengguna memakai salinan di Applications.
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(QMessageBox.Warning, "Panel Tracker",
                          "Panel Tracker sedang dijalankan langsung dari file installer (.dmg).\n\n"
                          "Seret 'Panel Tracker' ke folder Applications, eject installer-nya, lalu buka dari "
                          "Applications. Kalau installer di-eject atau diganti saat aplikasi berjalan, aplikasi "
                          "bisa tertutup mendadak.")
        quit_btn = box.addButton("Tutup", QMessageBox.AcceptRole)
        box.addButton("Tetap jalankan", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is quit_btn:
            os._exit(0)
    ddir = data_dir()
    install_excepthook(ddir)
    settings = QSettings(os.path.join(ddir, "settings.ini"), QSettings.IniFormat)
    i18n.set_lang(settings.value("ui/lang", "id") or "id")
    db_arg = next((a for a in sys.argv[1:] if a.lower().endswith(".db")), None)
    w = MainWindow(db_arg, settings=settings, default_db=os.path.join(ddir, "paneltracker.db"))
    w.show()
    ret = app.exec()
    # semua jendela sudah menutup database di closeEvent; simpan pengaturan lalu keluar langsung
    # (menghindari crash Qt saat Python membereskan objek di akhir proses)
    try:
        settings.sync()
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(ret)


if __name__ == "__main__":
    main()
