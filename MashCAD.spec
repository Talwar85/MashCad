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

# Collect all necessary data files - MINIMAL für kleinere Bundle-Größe
datas = []
# PyVista braucht nur wenige Daten (keine Beispiel-Meshes etc.)
# datas += collect_data_files('pyvista')  # ~50MB - nicht nötig
# VTK Data-Files sind RIESIG und meist nicht nötig
# datas += collect_data_files('vtk')      # ~200MB - nicht nötig
# datas += collect_data_files('vtkmodules')
# Matplotlib: nur colormaps/stylesheets werden gebraucht
datas += collect_data_files('matplotlib', include_py_files=False, subdir='mpl-data')
# PIL braucht keine extra data files
# datas += collect_data_files('PIL')

# Lokale MashCad-Module als Source einbinden
datas += [
    ('gui', 'gui'),
    ('modeling', 'modeling'),
    ('sketcher', 'sketcher'),
    ('core', 'core'),
    ('config', 'config'),
    ('i18n', 'i18n'),
    ('icon.ico', '.'),
    ('app.png', '.'),
]

# Collect hidden imports
hiddenimports = []
# PyVista - alle Submodule
hiddenimports += collect_submodules('pyvista')
# VTK - ALLE Module (PyVista prüft sie bei Initialisierung)
# Manuelle Liste funktioniert nicht, da PyVista mehr braucht
hiddenimports += collect_submodules('vtkmodules')
# PIL - nur Basis
hiddenimports += ['PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont']
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
    # Scientific - scipy Module (optimize braucht linalg!)
    'scipy',
    'scipy.optimize',
    'scipy.spatial',
    'scipy.spatial.transform',
    'scipy.sparse',
    'scipy.sparse.csgraph',
    'scipy.interpolate',
    'scipy.linalg',  # Benötigt von scipy.optimize
    # Stdlib needed by scipy/numpy
    'unittest',  # numpy.testing braucht es
    # Mesh conversion
    'trimesh',
    # Matplotlib (minimal für PyVista colors)
    'matplotlib',
    'matplotlib.colors',
    'matplotlib.cm',
    'matplotlib.pyplot',
]

# Cross-platform binaries
binaries = []
if sys.platform == 'win32':
    lib3mf_path = os.path.join(sys.prefix, 'Library', 'bin', 'lib3mf.dll')
    if os.path.exists(lib3mf_path):
        binaries.append((lib3mf_path, os.path.join('Library', 'bin')))
elif sys.platform == 'linux':
    # Linux: lib3mf might be in different locations
    for lib_path in ['/usr/lib/lib3mf.so', '/usr/local/lib/lib3mf.so']:
        if os.path.exists(lib_path):
            binaries.append((lib_path, 'lib'))
            break

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/hook-lib3mf.py'],
    excludes=[
        # ===== GROSSE PAKETE (spart GB) =====
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'keras',
        'open3d',
        'opencv-python', 'cv2',
        'pandas',
        'sklearn', 'scikit-learn',
        'h5py', 'tables',
        'sympy',
        'dask',
        'xarray',
        'numba',
        # ===== WEB/SERVER =====
        'flask', 'django', 'fastapi',
        'dash', 'plotly',
        'tornado', 'aiohttp',
        'requests',  # nicht direkt gebraucht
        # ===== JUPYTER/NOTEBOOKS =====
        'jupyter', 'jupyterlab',
        'notebook', 'nbformat', 'nbconvert',
        'ipywidgets', 'ipykernel', 'ipython',
        # ===== GUI ALTERNATIVEN =====
        'tkinter', '_tkinter', 'Tkinter',
        'PyQt5', 'PyQt6',
        'wx', 'wxPython',
        # ===== TESTING/DEV =====
        'pytest', 'nose',  # unittest NICHT excluden - numpy.testing braucht es!
        'coverage', 'tox',
        # ===== MESH (nicht bundlebar) =====
        'meshlib', 'mrmeshpy',
        'pymeshlab',  # Oft problematisch in Bundles
        'pyransac3d',  # Optional
        # ===== SONSTIGES =====
        'gdown',
        'beautifulsoup4', 'bs4',
        'lxml',
        'sqlalchemy',
        # ===== VTK Module =====
        # NICHT excluden - PyVista prüft alle bei Initialisierung!
        # 'vtkmodules.vtkWebCore',  # etc.
        # ===== PySide6 Module die wir NICHT brauchen =====
        'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender',
        'PySide6.QtBluetooth',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets',
        'PySide6.QtLocation', 'PySide6.QtPositioning',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtNfc',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickControls2',
        'PySide6.QtQuickWidgets', 'PySide6.QtQml',
        'PySide6.QtRemoteObjects',
        'PySide6.QtSensors', 'PySide6.QtSerialPort',
        'PySide6.QtSpatialAudio', 'PySide6.QtStateMachine',
        'PySide6.QtTextToSpeech',
        'PySide6.QtWebChannel', 'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebSockets',
        'PySide6.QtDBus', 'PySide6.QtDesigner',
        'PySide6.QtHelp', 'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtConcurrent', 'PySide6.QtAxContainer',
        'PySide6.QtNetworkAuth', 'PySide6.QtNetwork',
        'PySide6.QtXml',
        # ===== Scipy =====
        # KEINE scipy Module excluden - zu viele interne Abhängigkeiten!
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
    icon='icon.ico',  # Windows icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=sys.platform != 'win32',  # strip nur auf Linux/macOS (Windows hat kein strip)
    upx=True,
    upx_exclude=[
        # Diese DLLs vertragen kein UPX
        'vcruntime140.dll',
        'msvcp140.dll',
        'python*.dll',
        'Qt*.dll',
        'PySide6*.dll',
    ],
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
            'CFBundleShortVersionString': '0.1-alpha',
        },
    )
