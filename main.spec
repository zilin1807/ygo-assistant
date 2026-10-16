# PyInstaller spec for YGO Assistant
# Build with: pyinstaller main.spec --clean --noconfirm
# 输出：dist/main.exe（单文件，无需 Python 环境）

import os
import sys
from pathlib import Path

block_cipher = None

# 打包工程根目录（spec 所在目录）
ROOT = Path(SPECPATH).resolve()

a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 把桌宠 PNG 一起打包
        ('assets/*.png', 'assets'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # === mss 动态分发：PyInstaller 静态分析扫不到 ===
        # mss.base.MSS.from_mss() 用 platform.system() 判断后
        # 动态 import mss.windows / mss.linux / mss.darwin,
        # 同时 mss.windows.choose_impl() 又动态 import mss.windows.gdi
        # 所以这四个必须显式声明。
        'mss',
        'mss.base',
        'mss.exception',
        'mss.factory',
        'mss.models',
        'mss.screenshot',
        'mss.tools',
        'mss.windows',
        'mss.windows.gdi',
        'mss.linux',
        'mss.darwin',
        # === 其它动态依赖 ===
        'dashscope',
        'PIL',
        'PIL._tkinter_finder',  # 防 matplotlib_compat 引
        'pkg_resources.py2_warn',
        # Windows-only：ctypes 装的 callback 才能跑
        'win32gui',
        'win32con',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy',
        'pandas', 'IPython', 'jupyter',
        'tornado', 'zmq', 'pytest',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ygo-assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # 用 UPX 压缩
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # 桌面应用，不开 console（要开调试改 True）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'assets' / 'desktop_pet.png') if (ROOT / 'assets' / 'desktop_pet.png').exists() else None,
)
