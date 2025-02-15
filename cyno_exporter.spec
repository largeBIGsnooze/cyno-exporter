# -*- mode: python ; coding: utf-8 -*-

import os, shutil


def copy_folders(folder):
    for icon in os.listdir(folder):
        src = os.path.join(folder, icon)
        dst = os.path.join(f"./dist/{folder}", icon)
        if os.path.isdir(src):
            if "__pycache__" in src:
                continue
            os.makedirs(dst, exist_ok=True)
            copy_folders(src)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)


copy_folders("./icons")
copy_folders("./tools")
shutil.copy("./icon.ico", "./dist/icon.ico")

a = Analysis(
    ["cyno_exporter.py"],
    pathex=[],
    binaries=[],
    datas=[("style.qss", ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Cyno Exporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["dist/icon.ico"],
)
