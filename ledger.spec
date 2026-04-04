# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for 账目配平工具.
Bundles PySide6, openpyxl, httpx and the ledger source package into a
single-file Windows executable with no console window.
"""

import sys
from pathlib import Path

block_cipher = None

# Collect all hidden imports required by PySide6 / openpyxl / httpx
hidden_imports = [
    # PySide6 platform plugin loader
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    # openpyxl uses pkg_resources / importlib.metadata internally
    "openpyxl",
    "openpyxl.cell._writer",
    # httpx optional dependencies
    "httpx",
    "anyio",
    "certifi",
    "httpcore",
    "idna",
    "sniffio",
]

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="账目配平工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed mode – no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
