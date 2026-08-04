# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置。本地打包见 build.bat;CI 打包见 .github/workflows/build.yml。
# 生成单文件、无控制台窗口的 exe,并内置默认模板。

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/templates/default', 'templates/default'),  # 内置默认模板
    ],
    hiddenimports=[
        'win32gui', 'win32con', 'win32api',
        'pyperclip', 'PIL.ImageTk', 'cv2', 'numpy',
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WxWorkBatchAdd',      # exe 文件名(ASCII,避免中文名兼容问题)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # GUI 程序,不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/app.ico',    # 如有图标可取消注释
)
