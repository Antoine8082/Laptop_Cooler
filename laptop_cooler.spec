# -*- mode: python ; coding: utf-8 -*-
"""
laptop_cooler.spec — PyInstaller spec file for Laptop Cooler.

Build command:
    pyinstaller laptop_cooler.spec

Output:
    dist/Laptop_Cooler.exe (single file, windowed, UAC admin)
"""

import os

block_cipher = None

# ─── Chemins ─────────────────────────────────────────────────────────────────

PROJECT_DIR = os.path.abspath('.')
SRC_DIR = os.path.join(PROJECT_DIR, 'src')
DLL_DIR = os.path.join(PROJECT_DIR, 'DLL')
ASSETS_DIR = os.path.join(PROJECT_DIR, 'assets')

# ─── Analysis ────────────────────────────────────────────────────────────────

a = Analysis(
    [os.path.join(SRC_DIR, 'laptop_cooler.py')],
    pathex=[SRC_DIR],
    binaries=[
        # Toutes les DLLs LibreHardwareMonitor + dépendances → sous-dossier DLL/
        *[(os.path.join(DLL_DIR, f), 'DLL') for f in os.listdir(DLL_DIR) if f.endswith('.dll')],
    ],
    datas=[
        # Configuration par défaut
        (os.path.join(PROJECT_DIR, 'config.json'), '.'),
        # Icône
        (os.path.join(ASSETS_DIR, 'icon.ico'), 'assets'),
    ],
    hiddenimports=[
        'clr',                   # pythonnet
        'pystray._win32',        # Backend pystray Windows
        'PIL._tkinter_finder',   # Pillow + tkinter
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ─── PYZ (archive Python) ───────────────────────────────────────────────────

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ─── EXE ─────────────────────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Laptop_Cooler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # Mode windowless (pas de console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ASSETS_DIR, 'icon.ico'),
    uac_admin=True,             # Élévation UAC requise (pour LibreHardwareMonitor)
)
