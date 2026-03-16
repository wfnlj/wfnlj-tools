# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all

# 收集 PyPDF2 的所有模块
pyPDF2_datas, pyPDF2_binaries, pyPDF2_hiddenimports = collect_all('PyPDF2')
pil_datas, pil_binaries, pil_hiddenimports = collect_all('PIL')

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