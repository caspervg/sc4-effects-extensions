# -*- mode: python ; coding: utf-8 -*-
import os as _os, re as _re, sys as _sys

_ver = _re.search(r'VERSION = "([^"]+)"', open('src/effdir_editor/version.py').read()).group(1)
_ver_m = _re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', _ver)
_ver_tuple = (
    (int(_ver_m.group(1)), int(_ver_m.group(2)), int(_ver_m.group(3)), 0)
    if _ver_m
    else (0, 0, 0, 0)
)

_win_ver_file = None
if _sys.platform == 'win32':
    _os.makedirs('build', exist_ok=True)
    _win_ver_file = 'build/version_info.txt'
    open(_win_ver_file, 'w').write(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_ver_tuple},
    prodvers={_ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', ''),
         StringStruct('FileDescription', 'EFFDIR Editor'),
         StringStruct('FileVersion', '{_ver}'),
         StringStruct('InternalName', 'EFFDIR-Editor'),
         StringStruct('LegalCopyright', ''),
         StringStruct('OriginalFilename', 'EFFDIR-Editor.exe'),
         StringStruct('ProductName', 'EFFDIR Editor'),
         StringStruct('ProductVersion', '{_ver}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""")

a = Analysis(
    ['run_effdir_editor.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EFFDIR-Editor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_win_ver_file,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='EFFDIR-Editor',
)
if _sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='EFFDIR-Editor.app',
        bundle_identifier='com.caspervg.effdir-editor',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': _ver,
        },
    )
