import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MashCAD
Builds standalone executables for Windows, macOS, and Linux
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all necessary data files
datas = []
datas += collect_data_files('pyvista')
datas += collect_data_files('vtk')
datas += collect_data_files('vtkmodules')

# Collect hidden imports
hiddenimports = []
hiddenimports += collect_submodules('pyvista')
hiddenimports += collect_submodules('vtkmodules')
hiddenimports += collect_submodules('PySide6')
hiddenimports += [
    'numpy',
    'shapely',
    'ezdxf',
    'build123d',
    'pymeshlab',
    'meshlib',
    'pyransac3d',
    'open3d',
    'scipy',
    'scipy.spatial.transform',
    'scipy.sparse.csgraph',
    'alphashape',
    'vtkmodules.vtkRenderingOpenGL2',
    'vtkmodules.vtkInteractionStyle',
    'vtkmodules.vtkRenderingFreeType',
    'vtkmodules.vtkRenderingContextOpenGL2',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'tkinter',
        'PyQt5',
        'PyQt6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MashCAD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one: 'icon.ico' (Windows) or 'icon.icns' (macOS)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MashCAD',
)

# macOS App Bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='MashCAD.app',
        icon=None,  # Add icon path here: 'icon.icns'
        bundle_identifier='com.mashcad.app',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSHighResolutionCapable': 'True',
            'CFBundleShortVersionString': '2.5.0',
        },
    )
