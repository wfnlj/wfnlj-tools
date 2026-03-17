# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all

# 收集所有第三方库
pyPDF2_datas, pyPDF2_binaries, pyPDF2_hiddenimports = collect_all('PyPDF2')
pil_datas, pil_binaries, pil_hiddenimports = collect_all('PIL')
requests_datas, requests_binaries, requests_hiddenimports = collect_all('requests')
schedule_datas, schedule_binaries, schedule_hiddenimports = collect_all('schedule')
crypto_datas, crypto_binaries, crypto_hiddenimports = collect_all('cryptography')

# 合并所有数据
all_datas = pyPDF2_datas + pil_datas + requests_datas + schedule_datas + crypto_datas
all_binaries = pyPDF2_binaries + pil_binaries + requests_binaries + schedule_binaries + crypto_binaries
all_hiddenimports = list(set(
    pyPDF2_hiddenimports + pil_hiddenimports + 
    requests_hiddenimports + schedule_hiddenimports + crypto_hiddenimports + 
    ['numpy']
))

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
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
    # 修复 Mac app 架构问题
    app = BUNDLE(
        exe,
        name='PDFMerger.app',
        icon=None,
        info_plist={
            'CFBundleName': 'PDFMerger',
            'CFBundleDisplayName': 'PDFMerger',
            'CFBundleIdentifier': 'com.wfnlj.pdfmerger',
            'CFBundleVersion': '1.1.3',
            'CFBundleShortVersionString': '1.1.3',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.13.0',
        }
    )
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