# -*- mode: python ; coding: utf-8 -*-
# Build macOS: ./build_mac.sh   (atau: pyinstaller --noconfirm --clean PanelTracker_mac.spec)
# Hasil: dist/Panel Tracker.app  (mode folder/onedir — disarankan untuk .app; start lebih cepat)
import re
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', open("app/__init__.py").read()).group(1)

datas = [("assets/icon.ico", "assets"), ("assets/icon.png", "assets"), ("assets/fonts", "assets/fonts"), ("assets/ui", "assets/ui")]
datas += collect_data_files("reportlab")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("reportlab.graphics.barcode") + ["PySide6.QtSvg"]
    + collect_submodules("keyring.backends"),
    excludes=["PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "tkinter", "matplotlib", "numpy",
              "scipy", "pandas", "IPython", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtNetwork"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PanelTracker", console=False, upx=False,
          argv_emulation=False, target_arch=None)
coll = COLLECT(exe, a.binaries, a.datas, name="PanelTracker", upx=False)
app = BUNDLE(
    coll,
    name="Panel Tracker.app",
    icon="assets/icon.icns",
    bundle_identifier="id.paneltracker.desktop",
    version=VERSION,
    info_plist={
        "CFBundleName": "Panel Tracker",
        "CFBundleDisplayName": "Panel Tracker",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHumanReadableCopyright": "Panel Tracker",
        "NSDocumentsFolderUsageDescription": "Panel Tracker menyimpan database dan pengaturan di folder Documents/PanelTracker.",
        "NSDesktopFolderUsageDescription": "Untuk menyimpan report PDF / Excel yang Anda pilih.",
        "NSDownloadsFolderUsageDescription": "Untuk membuka atau menyimpan file Excel / PDF yang Anda pilih.",
    },
)
