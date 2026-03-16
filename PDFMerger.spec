# -*- mode: python ; coding: utf-8 -*-
import sys

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyPDF2',
        'PyPDF2.PdfReader',
        'PyPDF2.PdfWriter',
        'PyPDF2.pager',
        'PyPDF2.utils',
        'PyPDF2.generic',
        'PyPDF2.filters',
        'PyPDF2.xmp',
        'PIL',
        'PIL.Image',
        'numpy',
    ],
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
    # Mac 不使用图标
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
    # Windows
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