#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PDF合并工具启动脚本
"""

import sys
import os

# 在导入任何其他模块之前设置窗口化选项
if sys.platform == 'win32':
    import ctypes
    # 设置控制台窗口隐藏
    ctypes.windll.kernel32.FreeConsole()
    
    import locale
    import io
    
    # 安全处理sys.stdout和sys.stderr
    if sys.stdout is not None:
        # 检查sys.stdout是否有buffer属性
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        else:
            sys.stdout = io.TextIOWrapper(sys.stdout, encoding='utf-8')
    
    if sys.stderr is not None:
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        else:
            sys.stderr = io.TextIOWrapper(sys.stderr, encoding='utf-8')
    
    locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from main import main
    
    if __name__ == "__main__":
        main()
except ImportError as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("启动错误", f"导入错误：{e}\n\n请重新下载程序")
    root.destroy()
except Exception as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("启动错误", f"程序启动失败：{e}")
    root.destroy()