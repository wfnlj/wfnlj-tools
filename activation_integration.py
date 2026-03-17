# 激活集成补丁
# 将以下代码添加到 main.py 的开头

# 替换原来的导入
# from activation_ui import check_and_show_activation
# from simple_activation_client import SimpleActivationClient

# 使用新的激活系统
from local_activation_system import (
    check_activation, 
    get_hardware_id,
    activate_with_code,
    activate_online,
    check_payment_status,
    get_all_hardware_features
)


def check_and_show_activation_new(root, on_success=None):
    """
    新版激活检查和显示
    """
    # 检查激活状态
    success, error_msg, activation_info = check_activation()
    
    if success:
        # 已激活，显示状态
        type_names = {'trial': '试用版', 'monthly': '月卡版', 'yearly': '年卡版', 'lifetime': '长期版'}
        type_name = type_names.get(activation_info.get('activation_type'), '未知')
        
        # 创建激活信息显示窗口
        info_window = tk.Toplevel(root)
        info_window.title("激活状态")
        info_window.geometry("400x200")
        
        ttk.Label(info_window, text=f"已激活: {type_name}", font=("Arial", 14, "bold")).pack(pady=10)
        
        if activation_info.get('activation_type') != 'lifetime':
            ttk.Label(info_window, text=f"有效期至: {activation_info.get('expire_date', '')[:10]}").pack(pady=5)
            ttk.Label(info_window, text=f"剩余天数: {activation_info.get('days_remaining', 0)} 天").pack(pady=5)
        else:
            ttk.Label(info_window, text="永久有效").pack(pady=5)
        
        ttk.Label(info_window, text=f"硬件ID: {activation_info.get('hardware_id', '')}").pack(pady=5)
        
        def continue_app():
            info_window.destroy()
            if on_success:
                on_success()
        
        ttk.Button(info_window, text="继续使用", command=continue_app).pack(pady=20)
        
        return True
    else:
        # 未激活，显示激活界面
        show_activation_dialog(root, on_success)
        return False


def show_activation_dialog(root, on_success=None):
    """
    显示激活对话框
    """
    dialog = tk.Toplevel(root)
    dialog.title("软件激活")
    dialog.geometry("500x400")
    
    # 获取硬件ID
    hwid = get_hardware_id()
    
    # 标题
    ttk.Label(dialog, text="软件激活", font=("Arial", 18, "bold")).pack(pady=20)
    
    # 硬件ID显示
    hwid_frame = ttk.Frame(dialog)
    hwid_frame.pack(fill=tk.X, padx=20, pady=10)
    ttk.Label(hwid_frame, text="设备ID:").pack(side=tk.LEFT)
    ttk.Label(hwid_frame, text=hwid, font=("Consolas", 10)).pack(side=tk.LEFT, padx=10)
    
    # 激活类型选择
    type_frame = ttk.LabelFrame(dialog, text="选择激活类型", padding=10)
    type_frame.pack(fill=tk.X, padx=20, pady=10)
    
    type_var = tk.StringVar(value="yearly")
    types = [
        ("试用版 (7天)", "trial"),
        ("月卡版 (30天)", "monthly"),
        ("年卡版 (365天)", "yearly"),
        ("长期版", "lifetime")
    ]
    
    for text, value in types:
        ttk.Radiobutton(type_frame, text=text, variable=type_var, value=value).pack(anchor=tk.W)
    
    # 激活码输入
    code_frame = ttk.LabelFrame(dialog, text="或输入激活码", padding=10)
    code_frame.pack(fill=tk.X, padx=20, pady=10)
    
    code_entry = ttk.Entry(code_frame, width=50)
    code_entry.pack(fill=tk.X)
    
    # 状态显示
    status_label = ttk.Label(dialog, text="", foreground="blue")
    status_label.pack(pady=10)
    
    # 按钮
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=20)
    
    def do_online_activate():
        """在线激活"""
        activation_type = type_var.get()
        status_label.config(text="正在创建订单...", foreground="blue")
        dialog.update()
        
        success, msg, qr_url = activate_online(activation_type)
        
        if success:
            # 显示二维码
            show_payment_dialog(dialog, msg, qr_url, on_success)
        else:
            status_label.config(text=msg, foreground="red")
    
    def do_code_activate():
        """激活码激活"""
        code = code_entry.get().strip()
        if not code:
            messagebox.showwarning("提示", "请输入激活码")
            return
        
        status_label.config(text="正在验证...", foreground="blue")
        dialog.update()
        
        success, msg = activate_with_code(code)
        
        if success:
            status_label.config(text=msg, foreground="green")
            messagebox.showinfo("成功", msg)
            dialog.destroy()
            if on_success:
                on_success()
        else:
            status_label.config(text=msg, foreground="red")
    
    ttk.Button(btn_frame, text="在线购买激活", command=do_online_activate).pack(side=tk.LEFT, padx=10)
    ttk.Button(btn_frame, text="使用激活码", command=do_code_activate).pack(side=tk.LEFT, padx=10)


def show_payment_dialog(parent, order_no, qr_url, on_success):
    """显示支付对话框"""
    import threading
    import time
    
    pay_dialog = tk.Toplevel(parent)
    pay_dialog.title("扫码支付")
    pay_dialog.geometry("400x300")
    
    ttk.Label(pay_dialog, text="请使用微信扫码支付", font=("Arial", 12)).pack(pady=10)
    
    # 显示订单号
    ttk.Label(pay_dialog, text=f"订单号: {order_no}").pack(pady=5)
    
    # 状态
    status_var = tk.StringVar(value="等待支付...")
    ttk.Label(pay_dialog, textvariable=status_var).pack(pady=10)
    
    # 检查支付状态的线程
    def check_payment():
        for i in range(100):  # 最多检查5分钟
            time.sleep(3)
            success, msg, code = check_payment_status(order_no)
            
            if success:
                status_var.set(msg)
                pay_dialog.update()
                messagebox.showinfo("成功", msg)
                pay_dialog.destroy()
                if on_success:
                    on_success()
                return
            
            status_var.set(msg)
            pay_dialog.update()
        
        status_var.set("支付超时，请重试")
    
    threading.Thread(target=check_payment, daemon=True).start()