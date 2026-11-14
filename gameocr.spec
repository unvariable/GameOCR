# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('config.default.toml', '.')]
binaries = []
hiddenimports = ['gameocr', 'gameocr.__main__', 'gameocr.ocr_models', 'gameocr.ui.overlay', 'gameocr.ui.settings_dialog', 'gameocr.ui.window_picker', 'gameocr.local_models', 'rapidocr_onnxruntime', 'onnxruntime', 'ctranslate2', 'sentencepiece', 'rapidfuzz', 'deepl', 'tomli_w', 'cv2', 'numpy', 'dbus_fast', 'dbus_fast.aio', 'Xlib', 'gameocr.capture.portal_backend']
datas += collect_data_files('rapidocr_onnxruntime')
hiddenimports += collect_submodules('gameocr')
tmp_ret = collect_all('ctranslate2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gameocr/__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'notebook', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='gameocr',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='gameocr',
)
