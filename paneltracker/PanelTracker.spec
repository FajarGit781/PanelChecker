# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller --noconfirm PanelTracker.spec
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [("assets/icon.ico", "assets"), ("assets/icon.png", "assets"), ("assets/fonts", "assets/fonts"), ("assets/ui", "assets/ui")]
datas += collect_data_files("reportlab")  # font metrics & data reportlab

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("reportlab.graphics.barcode") + ["PySide6.QtSvg"],
    excludes=["PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "tkinter", "matplotlib", "numpy", "scipy", "pandas", "IPython", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtNetwork"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PanelTracker",
    icon="assets/icon.ico",
    console=False,
    upx=False,
    version="version_info.txt" if os.path.exists("version_info.txt") else None,
)
