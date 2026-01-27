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

# Lokale MashCad-Module als Source einbinden
datas += [
    ('gui', 'gui'),
    ('modeling', 'modeling'),
    ('sketcher', 'sketcher'),
    ('core', 'core'),
    ('i18n', 'i18n'),
]

# Collect hidden imports — only what MashCad actually uses
hiddenimports = []
hiddenimports += collect_submodules('pyvista')
hiddenimports += collect_submodules('vtkmodules')
hiddenimports += [
    # Qt — nur die tatsächlich genutzten Module
    'PySide6.QtWidgets',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    # Core
    'numpy',
    'shapely',
    'shapely.geometry',
    'shapely.ops',
    'ezdxf',
    'build123d',
    'lib3mf',
    'loguru',
    # Visualization
    'pyvistaqt',
    'ocp_tessellate',
    # Scientific
    'scipy',
    'scipy.optimize',
    'scipy.spatial',
    'scipy.spatial.transform',
    'scipy.sparse.csgraph',
    'scipy.interpolate',
    'scipy.cluster.hierarchy',
    'scipy.ndimage',
    # Mesh conversion (optional — meshlib excluded: native DLL issues in bundled env)
    'pymeshlab',
    'pyransac3d',
    'trimesh',
    # VTK specifics
    'vtkmodules.vtkRenderingOpenGL2',
    'vtkmodules.vtkInteractionStyle',
    'vtkmodules.vtkRenderingFreeType',
    'vtkmodules.vtkRenderingContextOpenGL2',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[
        (os.path.join(sys.prefix, 'Library', 'bin', 'lib3mf.dll'), os.path.join('Library', 'bin')),
    ],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/hook-lib3mf.py'],
    excludes=[
        # Nicht benutzt — spart GB an Speicher
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'keras',
        'open3d',
        'opencv-python', 'cv2',
        'matplotlib',
        'pandas',
        'PIL', 'pillow',
        'tkinter',
        'PyQt5', 'PyQt6',
        'ipywidgets', 'jupyter',
        'notebook', 'nbformat',
        'dash', 'plotly', 'flask',
        'sympy',
        'h5py',
        'sklearn', 'scikit-learn',
        'gdown',
        'beautifulsoup4', 'bs4',
        'meshlib', 'mrmeshpy',  # Native DLL nicht bundlebar
        # PySide6-Module die MashCad nicht braucht
        'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickControls2',
        'PySide6.QtQuickWidgets', 'PySide6.QtQml',
        'PySide6.QtSpatialAudio',
        'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
        'PySide6.QtDBus', 'PySide6.QtDesigner',
        'PySide6.QtHelp', 'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtConcurrent', 'PySide6.QtAxContainer',
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
            'CFBundleShortVersionString': '2.6.0',
        },
    )
