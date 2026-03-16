# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

# 收集 PyPDF2 的所有模块 - 使用更可靠的方式
pyPDF2_datas, pyPDF2_binaries, pyPDF2_hiddenimports = collect_all('PyPDF2')
pil_datas, pil_binaries, pil_hiddenimports = collect_all('PIL')

# 确保 PyPDF2 的元数据被包含（某些包需要）
pyPDF2_datas += copy_metadata('PyPDF2')

# 手动添加 PyPDF2 的所有子模块（备用方案）
pyPDF2_hiddenimports += [
    'PyPDF2',
    'PyPDF2._cmap',
    'PyPDF2._codecs', 
    'PyPDF2._encryption',
    'PyPDF2._merger',
    'PyPDF2._page',
    'PyPDF2._protocols',
    'PyPDF2._reader',
    'PyPDF2._security',
    'PyPDF2._utils',
    'PyPDF2._version',
    'PyPDF2._writer',
    'PyPDF2.constants',
    'PyPDF2.errors',
    'PyPDF2.filters',
    'PyPDF2.generic',
    'PyPDF2.pagerange',
    'PyPDF2.papersizes',
    'PyPDF2.types',
    'PyPDF2.xmp',
]

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=pyPDF2_binaries + pil_binaries,
    datas=pyPDF2_datas + pil_datas,
    hiddenimports=list(set(pyPDF2_hiddenimports + pil_hiddenimports + ['numpy'])),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Mac 和 Windows 使用不同的图标
if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='PDFMerger',
        debug=False,
        bootloader_ignore_signals=True,
        strip=False,
        upx=False,
        console=False,
    )
    app = BUNDLE(exe, name='PDFMerger.app', icon=None)
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='PDFMerger',
        debug=False,
        bootloader_ignore_signals=True,
        strip=False,
        upx=False,
        console=False,
        icon=['pdf_icon.ico'],
    )