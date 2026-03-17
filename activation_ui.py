#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
激活界面模块 - 独立模块化组件
提供统一的激活界面，可以集成到任何需要激活功能的软件中
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading
import time
import os
import sys
import logging
from typing import Tuple, Dict

# 导入激活模块
from simple_activation_client import SimpleActivationClient, get_hardware_id

# 配置日志
logger = logging.getLogger(__name__)



class ActivationUI:
    """激活界面模块 - 独立可复用的UI组件"""
    
    def __init__(self, root_window, activation_client, on_activation_success=None):
        """
        初始化激活界面
        
        Args:
            root_window: Tkinter根窗口
            activation_client: SimpleActivationClient实例
            on_activation_success: 激活成功后的回调函数
        """
        self.root = root_window
        self.client = activation_client
        self.on_activation_success = on_activation_success
        
        # 清理现有窗口内容
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # 调整窗口大小以适应激活界面
        self.root.geometry("800x840")
        
        # 创建激活界面
        self.create_activation_ui()
        
        # 设置样式
        self.setup_styles()
    
    def setup_styles(self):
        """设置UI样式"""
        style = ttk.Style()
        
        # 设置主题
        try:
            style.theme_use('clam')
        except:
            try:
                style.theme_use('alt')
            except:
                pass  # 使用默认主题
        
        # 自定义样式 - 文字和按钮放大20%
        style.configure('Title.TLabel', font=('Arial', 14, 'bold'))
        style.configure('Heading.TLabel', font=('Arial', 12, 'bold'))
        
        # 按钮样式 - 放大20%
        style.configure('Big.TButton', font=('Arial', 11), padding=8)
        style.configure('Big.TLabel', font=('Arial', 11))
        
        # 配置所有按钮默认使用大按钮样式
        style.configure('TButton', font=('Arial', 11), padding=8)
        
        # 标签字体放大
        style.configure('TLabel', font=('Arial', 11))
    
    def create_activation_ui(self):
        """创建激活界面"""
        # 主框架
        activation_frame = ttk.Frame(self.root, padding="20")
        activation_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置网格布局权重，使列均匀分布
        activation_frame.grid_columnconfigure(0, weight=1)
        activation_frame.grid_columnconfigure(1, weight=1)
        
        # 标题
        title_label = ttk.Label(activation_frame, text="软件激活", font=("Arial", 22, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(20, 10))
        

        
        # 获取产品价格信息并缓存
        try:
            trial_price = self.client.get_server_product_price(f"{self.client.product_id}_test")
            monthly_price = self.client.get_server_product_price(f"{self.client.product_id}_yue")
            year_price = self.client.get_server_product_price(f"{self.client.product_id}_nian")
            official_price = self.client.get_server_product_price(self.client.product_id)

            # 缓存价格到client中，避免重复请求
            self.client.cached_prices = {
                f"{self.client.product_id}_test": trial_price,
                f"{self.client.product_id}_yue": monthly_price,
                f"{self.client.product_id}_nian": year_price,
                self.client.product_id: official_price
            }
        except Exception as e:
            # 如果获取价格失败，使用默认价格，并简化错误提示
            error_msg = str(e)
            if "无法连接到服务器" in error_msg or "网络" in error_msg or "连接" in error_msg or "Timeout" in error_msg:
                # 网络连接失败，检查全局变量判断是否真的网络错误
                try:
                    from simple_activation_client import _last_server_status
                    # 如果最后一次服务器验证失败，说明是真正的网络错误
                    if _last_server_status and not _last_server_status.get('success', False):
                        import sys
                        messagebox.showerror(
                            "网络连接失败",
                            f"网络连接失败，无法完成激活验证！\n\n"
                            "请检查网络连接后重新启动软件。\n\n"
                            "如果您使用的是月卡版，必须联网才能正常使用"
                        )
                        sys.exit(1)
                    else:
                        # 获取价格失败，但不是真正的网络错误，使用默认价格
                        trial_price = 1.0
                        monthly_price = 20.0
                        year_price = 50.0
                        official_price = 100.0
                        print("获取产品价格失败，使用默认价格: 激活过期或非网络错误")
                except:
                    # 无法获取服务器状态，使用默认价格
                    trial_price = 1.0
                    monthly_price = 20.0
                    year_price = 50.0
                    official_price = 100.0
                    print("获取产品价格失败，使用默认价格: 无法判断错误类型")
            else:
                # 其他错误（如激活过期），使用默认价格并继续
                trial_price = 1.0
                monthly_price = 20.0
                year_price = 50.0
                official_price = 100.0
                print(f"获取产品价格失败，使用默认价格: {error_msg}")
        
        # 激活选项标题
        option_label = ttk.Label(activation_frame, text="请选择激活方式：", font=("Arial", 14, "bold"))
        option_label.grid(row=2, column=0, columnspan=2, pady=(20, 10), sticky="ew")
        
        # 激活按钮回调函数
        def start_trial_activation():
            self._start_activation_flow("试用版", self.client.start_trial_activation_flow, trial_btn)
        
        def start_monthly_activation():
            self._start_activation_flow("月卡版", self.client.start_monthly_activation_flow, monthly_btn)
        
        def start_year_activation():
            self._start_activation_flow("年费版", self.client.start_year_activation_flow, year_btn)
        
        def start_official_activation():
            self._start_activation_flow("正式版", self.client.start_official_activation_flow, official_btn)
        
        # 第一行：试用版和月卡版
        # 试用版价格显示 - 第1列
        trial_price_label = ttk.Label(activation_frame, text=f"试用版价格：¥{trial_price}",
                                    font=("Arial", 13, "bold"), foreground="blue")
        trial_price_label.grid(row=3, column=0, pady=(10, 5), padx=(0, 10))

        # 试用版激活按钮
        trial_btn = ttk.Button(activation_frame, text="激活试用版",
                              command=start_trial_activation, width=20, style='Big.TButton')
        trial_btn.grid(row=4, column=0, pady=5, padx=(0, 10))

        # 试用版说明
        trial_desc = ttk.Label(activation_frame, text="试用版：支付试用费用，试用完整功能",
                              font=("Arial", 11), foreground="blue")
        trial_desc.grid(row=5, column=0, pady=(0, 15), padx=(0, 10))

        # 月卡版价格显示 - 第2列
        monthly_price_label = ttk.Label(activation_frame, text=f"月卡版价格：¥{monthly_price}",
                                      font=("Arial", 13, "bold"), foreground="orange")
        monthly_price_label.grid(row=3, column=1, pady=(10, 5), padx=(10, 0))

        # 月卡版激活按钮
        monthly_btn = ttk.Button(activation_frame, text="激活月卡版",
                               command=start_monthly_activation, width=20, style='Big.TButton')
        monthly_btn.grid(row=4, column=1, pady=5, padx=(10, 0))

        # 月卡版说明
        monthly_desc = ttk.Label(activation_frame, text="月卡版：按月付费，享受一个月完整功能",
                               font=("Arial", 11), foreground="orange")
        monthly_desc.grid(row=5, column=1, pady=(0, 15), padx=(10, 0))

        # 第二行：年费版和正式版
        # 年费版价格显示 - 第1列
        year_price_label = ttk.Label(activation_frame, text=f"年费版价格：¥{year_price}",
                                   font=("Arial", 13, "bold"), foreground="purple")
        year_price_label.grid(row=6, column=0, pady=(10, 5), padx=(0, 10))

        # 年费版激活按钮
        year_btn = ttk.Button(activation_frame, text="激活年费版",
                             command=start_year_activation, width=20, style='Big.TButton')
        year_btn.grid(row=7, column=0, pady=5, padx=(0, 10))

        # 年费版说明
        year_desc = ttk.Label(activation_frame, text="年费版：按年付费，享受一年完整功能",
                            font=("Arial", 11), foreground="purple")
        year_desc.grid(row=8, column=0, pady=(0, 15), padx=(0, 10))

        # 正式版价格显示 - 第2列
        official_price_label = ttk.Label(activation_frame, text=f"正式版价格：¥{official_price}",
                                       font=("Arial", 13, "bold"), foreground="green")
        official_price_label.grid(row=6, column=1, pady=(10, 5), padx=(10, 0))

        # 正式版激活按钮
        official_btn = ttk.Button(activation_frame, text="激活正式版",
                                 command=start_official_activation, width=20, style='Big.TButton')
        official_btn.grid(row=7, column=1, pady=5, padx=(10, 0))

        # 正式版说明
        official_desc = ttk.Label(activation_frame, text="正式版：购买完整授权，享受全部功能",
                                 font=("Arial", 11), foreground="green")
        official_desc.grid(row=8, column=1, pady=(0, 20), padx=(10, 0))

        # 重要提示
        warning_label = ttk.Label(activation_frame,
                                text="本产品购买后自动激活，不支持退款，请您悉知！",
                                font=("Arial", 12), foreground="red")
        warning_label.grid(row=9, column=0, columnspan=2, pady=(0, 10))

        # 退出按钮
        quit_btn = ttk.Button(activation_frame, text="退出",
                            command=self.root.quit, style='Big.TButton')
        quit_btn.grid(row=10, column=0, columnspan=2, pady=(0, 20))
        
        # 保存按钮引用用于后续操作
        self.trial_btn = trial_btn
        self.monthly_btn = monthly_btn
        self.year_btn = year_btn
        self.official_btn = official_btn
        self.activation_frame = activation_frame
    
    def _start_activation_flow(self, version_type, activation_func, button):
        """启动激活流程"""
        # 禁用所有按钮
        self.trial_btn.config(state='disabled')
        self.year_btn.config(state='disabled')
        self.official_btn.config(state='disabled')
        button.config(state='disabled', text=f'正在创建{version_type}订单...')
        
        def activation_thread():
            try:
                success, result = activation_func()
                
                if success:
                    # 激活成功，显示二维码
                    order_id, qr_file = result
                    if qr_file:
                        self.root.after(0, lambda: self._show_qr_code(qr_file, order_id, version_type))
                else:
                    # 激活失败，显示错误信息
                    error_msg = result
                    self.root.after(0, lambda: self._activation_failed(version_type, error_msg))
            except Exception as e:
                self.root.after(0, lambda: self._activation_failed(version_type, f"激活过程异常: {str(e)}"))
        
        threading.Thread(target=activation_thread, daemon=True).start()
    
    def _show_qr_code(self, qr_file, order_id, version_type):
        """显示二维码并开始监控支付状态"""
        # 清除激活按钮
        self.trial_btn.grid_forget()
        self.monthly_btn.grid_forget()
        self.year_btn.grid_forget()
        self.official_btn.grid_forget()
        
        # 清除其他元素
        for widget in self.activation_frame.grid_slaves():
            if widget not in [self.trial_btn, self.monthly_btn, self.year_btn, self.official_btn]:
                widget.grid_forget()
        
        # 显示版本信息
        version_label = ttk.Label(self.activation_frame, text=f"{version_type}激活", font=("Arial", 14, "bold"))
        version_label.grid(row=0, column=0, columnspan=2, pady=(20, 0))
        
        # 显示二维码
        try:
            pil_image = Image.open(qr_file)
            pil_image = pil_image.resize((250, 250), Image.LANCZOS)
            qr_photo = ImageTk.PhotoImage(pil_image)
            
            qr_label = ttk.Label(self.activation_frame, image=qr_photo)
            qr_label.grid(row=1, column=0, columnspan=2, pady=20)
            qr_label.image = qr_photo
            
            # 显示支付提示
            info_label = ttk.Label(self.activation_frame, text="请使用微信扫描二维码完成支付", 
                                  font=("Arial", 10))
            info_label.grid(row=2, column=0, columnspan=2, pady=(0, 10))
            
            # 开始监控支付状态
            self._monitor_payment(order_id, version_type)
            
        except Exception as e:
            messagebox.showerror("错误", f"二维码显示失败：{e}")
    
    def _monitor_payment(self, order_id, version_type):
        """监控支付状态"""
        def check_thread():
            for i in range(60):  # 最多等待5分钟
                time.sleep(5)  # 每5秒检查一次
                
                # 检查支付状态
                activation_code = self.client.check_payment_status(order_id)
                
                if activation_code:
                    # 支付成功，获得激活码
                    print(f"收到激活码: {activation_code}")
                    
                    # 验证激活码
                    if self.client.decrypt_activation_code(activation_code, order_id):
                        self.root.after(0, lambda: self._activation_success(version_type))
                        return
                    else:
                        print("激活码验证失败")
                        return
            
            # 超时
            self.root.after(0, lambda: messagebox.showwarning("超时", "支付检查超时，请稍后手动检查支付状态"))
        
        threading.Thread(target=check_thread, daemon=True).start()
    
    def _activation_success(self, version_type):
        """激活成功"""
        messagebox.showinfo("成功", f"{version_type}激活成功！")
        
        # 调用成功回调函数
        if self.on_activation_success:
            self.on_activation_success()
    
    def _activation_failed(self, version_type, error_msg):
        """激活失败"""
        # 恢复按钮状态
        self.trial_btn.config(state='normal', text='激活试用版')
        self.monthly_btn.config(state='normal', text='激活月卡版')
        self.year_btn.config(state='normal', text='激活年费版')
        self.official_btn.config(state='normal', text='激活正式版')
        
        messagebox.showerror(f"{version_type}激活失败", error_msg)


def create_activation_ui(root_window, product_id="pdf_merger", server_url="https://wfnlj520.com", 
                        on_activation_success=None):
    """
    创建激活界面的便捷函数
    
    Args:
        root_window: Tkinter根窗口
        product_id: 产品ID
        server_url: 服务器URL
        on_activation_success: 激活成功回调
    
    Returns:
        ActivationUI实例
    """
    # 创建激活客户端
    client = SimpleActivationClient(product_id, server_url)
    
    # 创建激活界面
    activation_ui = ActivationUI(root_window, client, on_activation_success)
    
    return activation_ui


def check_and_show_activation(root_window, product_id="pdf_merger", server_url="https://wfnlj520.com",
                             on_activation_success=None, on_already_activated=None):
    """
    检查激活状态并显示相应界面的便捷函数 - 按照新逻辑实现

    Args:
        root_window: Tkinter根窗口
        product_id: 产品ID
        server_url: 服务器URL
        on_activation_success: 激活成功回调
        on_already_activated: 已激活时的回调

    Returns:
        tuple: (ActivationUI实例, 激活客户端实例) 或 (None, 激活客户端实例)
    """
    try:
        # 创建激活客户端
        client = SimpleActivationClient(product_id, server_url)

        # 检查激活状态
        if client.activated:
            # 已激活，返回客户端实例
            logger.info("✅ 激活验证通过")
            # 不在这里调用回调，让调用方根据返回值决定
            return None, client
        else:
            # 未激活，需要进入激活界面
            logger.info("❌ 激活验证失败，显示激活界面")
            activation_ui = ActivationUI(root_window, client, on_activation_success)
            return activation_ui, client

    except Exception as e:
        logger.error(f"❌ 检查激活状态异常: {e}")
        # 显示激活界面，确保返回有效的客户端实例
        try:
            error_client = SimpleActivationClient(product_id, server_url)
            activation_ui = ActivationUI(root_window, error_client, on_activation_success)
            return activation_ui, error_client
        except Exception as e2:
            logger.error(f"❌ 创建错误激活界面失败: {e2}")
            # 再次失败，返回空的激活界面和None
            return None, None


class OfflineModeUI:
    """离线模式界面 - 处理网络连接失败的情况"""
    
    def __init__(self, root_window, product_id, server_url, on_activation_success=None, on_already_activated=None):
        """
        初始化离线模式界面
        
        Args:
            root_window: Tkinter根窗口
            product_id: 产品ID
            server_url: 服务器URL
            on_activation_success: 激活成功回调
            on_already_activated: 已激活时的回调
        """
        self.root = root_window
        self.product_id = product_id
        self.server_url = server_url
        self.on_activation_success = on_activation_success
        self.on_already_activated = on_already_activated
        
        # 清除当前窗口内容
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # 创建离线模式界面
        self.create_offline_ui()
    
    def create_offline_ui(self):
        """创建离线模式界面"""
        offline_frame = ttk.Frame(self.root, padding="20")
        offline_frame.pack(expand=True, fill='both')
        
        # 标题
        title_label = ttk.Label(offline_frame, text="PDF合并工具 - 离线模式",
                               font=("Arial", 19, "bold"))
        title_label.pack(pady=(20, 10))

        # 离线模式说明
        info_text = """
⚠️  网络连接失败，无法连接到激活服务器

💡 如果您已经激活过软件：
   • 可以继续使用软件，但会有使用次数限制
   • 每启动60次需要联网验证一次激活状态
   • 建议尽快恢复网络连接完成激活验证

🔧 如果您尚未激活软件：
   • 请检查网络连接后重启软件
   • 或联系客服获取离线激活帮助

📱 当前状态：需要激活才能正常使用
        """

        info_label = ttk.Label(offline_frame, text=info_text.strip(),
                               font=("Arial", 12), justify='left',
                               foreground="orange")
        info_label.pack(pady=(20, 30))

        # 重试按钮
        retry_btn = ttk.Button(offline_frame, text="重试网络连接",
                              command=self.retry_network_connection, style='Big.TButton')
        retry_btn.pack(pady=10)

        # 退出按钮
        exit_btn = ttk.Button(offline_frame, text="退出程序",
                             command=self.root.quit, style='Big.TButton')
        exit_btn.pack(pady=5)
    
    def retry_network_connection(self):
        """重试网络连接"""
        try:
            # 重新创建激活客户端
            client = SimpleActivationClient(self.product_id, self.server_url)
            
            # 检查是否激活成功
            if client.activated:
                # 激活成功，调用回调函数
                if self.on_activation_success:
                    self.on_activation_success()
            else:
                # 仍需要激活，显示激活界面
                for widget in self.root.winfo_children():
                    widget.destroy()
                
                activation_ui = ActivationUI(self.root, client, self.on_activation_success)
                activation_ui.create_activation_ui()
                
        except Exception as e:
            error_msg = str(e)
            if "无法从服务器获取产品价格" in error_msg or "ConnectionError" in error_msg:
                messagebox.showwarning("网络仍然不可用", 
                                    "网络连接仍然失败，请检查网络设置后重试\n\n如果已激活，软件可以离线使用")
            else:
                messagebox.showerror("重试失败", f"重试时发生错误：{error_msg}")