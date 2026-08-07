# PyInstaller spec for the PDF to Markdown converter.
#
# Build with:   pyinstaller app.spec
#
# Notes:
#  * opendataloader_pdf ships a Java jar inside its wheel; collect_all pulls
#    the jar in as a data file, which a plain module scan would miss.
#  * onedir, not onefile: onefile unpacks the whole bundle to a temp folder on
#    every launch, which adds seconds of startup for no benefit here.

import os

from PyInstaller.utils.hooks import collect_all

# Optional: drop a 256x256 icon.ico next to this spec to brand the executable.
ICON = "icon.ico" if os.path.exists("icon.ico") else None

odl_datas, odl_binaries, odl_hidden = collect_all("opendataloader_pdf")

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=odl_binaries,
    datas=odl_datas,
    hiddenimports=odl_hidden,
    hookspath=[],
    runtime_hooks=[],
    # Qt modules the app never touches; excluding them saves ~60 MB.
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtNetworkAuth",
        "PySide6.QtPdf",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDF to Markdown",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no console window for non-technical users
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PDF to Markdown",
)
