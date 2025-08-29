# -*- mode: python ; coding: utf-8 -*-

options = [
    ("O", None, "OPTION"),
    ("hash_seed=0", None, "OPTION")
]


a = Analysis(['build_exec.py'],
    pathex=[],
    binaries=None,
    datas=None,
    hiddenimports=['pyspecan.view.tk_gui', 'pyspecan.controller.tk_gui'],
    hookspath=None,
    hooksconfig={},
    runtime_hooks=None,
    excludes=None,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    options,
    name='pyspecan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
