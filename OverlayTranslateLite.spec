# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec File for OverlayTranslate Lite
------------------------------------------------
Builds standalone executable for Windows

Build command:
    pyinstaller OverlayTranslateLite.spec --clean --noconfirm
"""

import sys
import os
from pathlib import Path

# Platform detection
IS_WINDOWS = sys.platform.startswith('win')
IS_MAC = sys.platform == 'darwin'
IS_LINUX = sys.platform.startswith('linux')

# Project root directory (lite folder)
PROJECT_ROOT = Path(SPECPATH)

# Version info
APP_NAME = "OverlayTranslateLite"
APP_DISPLAY_NAME = "Overlay Translate Lite"
__version__ = "1.0.0"

# Collect paddle and paddleocr using PyInstaller utilities
from PyInstaller.utils.hooks import collect_all

paddleocr_datas, paddleocr_binaries, paddleocr_hiddenimports = collect_all('paddleocr')
paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all('paddle')
sklearn_datas, sklearn_binaries, sklearn_hiddenimports = collect_all('sklearn')

# Binaries
binaries = []
binaries += paddleocr_binaries
binaries += paddle_binaries
binaries += sklearn_binaries

# Data files
datas = [
    ('assets', 'assets'),
    ('static', 'static'),
    ('templates', 'templates'),
    ('translations', 'translations'),
    ('config.ini', '.'),
    ('__version__.py', '.'),
    ('app.py', '.'),
    ('README.md', '.'),
]

# Add collected data
datas += paddleocr_datas
datas += paddle_datas
datas += sklearn_datas

# Hidden imports
hiddenimports = [
    # Flask and server
    'waitress',
    'flask',
    'flask.json',
    'werkzeug',
    'werkzeug.security',
    'jinja2',
    'jinja2.ext',
    'app',

    # Utils modules
    'utils',
    'utils.config',
    'utils.validators',
    'utils.helpers',
    'utils.settings_manager',
    'utils.ocr_utils',
    'utils.logging_config',
    'utils.image_optimizer',
    'utils.image_comparison',
    'utils.model_downloader',
    'utils.retry_utils',
    'utils.translation_manager',

    # GUI modules
    'gui',
    'gui.control_window',
    'gui.dialogs',
    'gui.custom_widgets',
    'gui.capture_widget',
    'gui.snipping_tool',
    'gui.enhanced_image_viewer',

    # Workers
    'workers',

    # PaddleOCR
    'paddleocr',
    'paddleocr.paddleocr',
    'paddleocr.tools',
    'paddleocr.tools.infer',
    'paddleocr.tools.infer.predict_system',
    'paddleocr.tools.infer.predict_rec',
    'paddleocr.tools.infer.predict_det',
    'paddleocr.tools.infer.predict_cls',
    'paddleocr.tools.infer.utility',
    'paddleocr.ppocr',
    'paddleocr.ppocr.utils',
    'paddleocr.ppstructure',
    'paddlepaddle',
    'paddle',
    'paddle.fluid',
    'paddle.nn',
    'paddle.vision',
    'shapely',
    'pyclipper',
    'lmdb',
    'imgaug',
    'Polygon',
    'lanms',
    'cv2',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',

    # Translation engines
    'argostranslate',
    'argostranslate.package',
    'argostranslate.translate',

    # Qt6 modules
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',

    # Utilities
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',

    # Data processing
    'numpy',
    'scipy',
    'sklearn',
    'sklearn.utils',
    'sklearn.utils._typedefs',
    'yaml',
    'json',
    'pickle',

    # Standard library
    'xml',
    'xml.etree',
    'xml.etree.ElementTree',
    'xml.dom',
    'xml.dom.minidom',
    'xml.parsers',
    'xml.parsers.expat',
    'xml.sax',
]

# Add collected hidden imports
hiddenimports += paddleocr_hiddenimports
hiddenimports += paddle_hiddenimports
hiddenimports += sklearn_hiddenimports

# Analysis
a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/rthook-paddle.py'],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'matplotlib',
        'tkinter',
        'tcl',
        'tk',
        'nltk',
        # Lite exclusions - not needed
        'openai',
        'anthropic',
        'google.generativeai',
        'google.ai.generativelanguage',
        'sseclient',
        'keyring',
        'markdown',
        'pygments',
        'psutil',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Remove duplicate binaries
a.binaries = [x for x in a.binaries if x[0] not in [y[0] for y in binaries]]

# PYZ archive
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Icon path
icon_path = str(PROJECT_ROOT / 'assets' / 'icons' / 'app_icon.ico')
if not (PROJECT_ROOT / 'assets' / 'icons' / 'app_icon.ico').exists():
    # Try alternative icon
    icon_path = str(PROJECT_ROOT / 'assets' / 'Icon.ico')
    if not (PROJECT_ROOT / 'assets' / 'Icon.ico').exists():
        icon_path = None

if IS_WINDOWS:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
        version_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )

elif IS_MAC:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch='universal2',
        codesign_identity=None,
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )

else:
    # Linux
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )
