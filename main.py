# 发票合并工具 - 简化版
# 支持 PDF 和图片格式发票合并

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import PyPDF2
from PIL import Image
import threading
import tempfile

from activation_ui import check_and_show_activation
from simple_activation_client import SimpleActivationClient


def detect_image_orientation(img):
    """
    根据图片内容判断是否需要旋转
    规则：右下角有红色盖章 = 下面，左上角有二维码 = 上面
    返回需要旋转的角度（0, 90, 180, 270）
    """
    import numpy as np
    
    width, height = img.size
    
    # 转换为numpy数组进行分析
    img_array = np.array(img.convert('RGB'))
    
    # 定义四个角落的区域（取角落的10%区域）
    corner_size_w = width // 10
    corner_size_h = height // 10
    
    # 四个角落的区域
    top_left = img_array[0:corner_size_h, 0:corner_size_w]
    top_right = img_array[0:corner_size_h, -corner_size_w:]
    bottom_left = img_array[-corner_size_h:, 0:corner_size_w]
    bottom_right = img_array[-corner_size_h:, -corner_size_w:]
    
    # 检测红色像素（红色印章）
    def count_red_pixels(region):
        # 红色：R > 150, G < 100, B < 100
        red_mask = (region[:,:,0] > 150) & (region[:,:,1] < 100) & (region[:,:,2] < 100)
        return np.sum(red_mask)
    
    # 检测黑白区域（二维码特征：高对比度）
    def detect_qr_code(region):
        gray = 0.299 * region[:,:,0] + 0.587 * region[:,:,1] + 0.114 * region[:,:,2]
        # 二维码特征：黑白分明，方差大
        variance = np.var(gray)
        return variance
    
    # 计算四个角落的红色像素数量
    red_tl = count_red_pixels(top_left)
    red_tr = count_red_pixels(top_right)
    red_bl = count_red_pixels(bottom_left)
    red_br = count_red_pixels(bottom_right)
    
    # 计算四个角落的二维码可能性（高方差=可能有二维码）
    qr_tl = detect_qr_code(top_left)
    qr_tr = detect_qr_code(top_right)
    qr_bl = detect_qr_code(bottom_left)
    qr_br = detect_qr_code(bottom_right)
    
    # 判断逻辑
    # 正确方向：左上角有二维码（高方差），右下角有红色盖章
    # 如果红色印章在右上角，说明需要逆时针旋转90度
    # 如果红色印章在左上角，说明需要旋转180度
    # 如果红色印章在左下角，说明需要顺时针旋转90度
    
    red_positions = {'top_left': red_tl, 'top_right': red_tr, 'bottom_left': red_bl, 'bottom_right': red_br}
    max_red_pos = max(red_positions, key=red_positions.get)
    
    # 如果红色印章在右下角，方向正确
    if max_red_pos == 'bottom_right':
        return 0
    # 如果红色印章在左下角，需要顺时针旋转90度
    elif max_red_pos == 'bottom_left':
        return 90
    # 如果红色印章在左上角，需要旋转180度
    elif max_red_pos == 'top_left':
        return 180
    # 如果红色印章在右上角，需要逆时针旋转90度
    else:  # top_right
        return 270



def image_to_pdf(image_path, output_pdf_path, dpi=200):
    """
    将图片转换为PDF
    - 固定尺寸：1694 x 1096 像素（横版）
    - 竖版图片自动旋转为横版
    """
    img = Image.open(image_path)
    
    # 转换为RGB
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # 获取图片尺寸
    img_width, img_height = img.size
    
    # 如果是竖版，旋转90度变成横版
    if img_height > img_width:
        img = img.rotate(-90, expand=True)
        img_width, img_height = img.size
    
    # 固定的发票PDF尺寸（横版）：1694 x 1096
    target_width, target_height = 1694, 1096
    
    # 计算缩放比例（保持宽高比）
    scale_w = target_width / img_width
    scale_h = target_height / img_height
    scale = min(scale_w, scale_h)
    
    # 缩放图片
    new_width = int(img_width * scale)
    new_height = int(img_height * scale)
    img = img.resize((new_width, new_height), Image.LANCZOS)
    
    # 创建目标尺寸的页面
    page = Image.new('RGB', (target_width, target_height), (255, 255, 255))
    
    # 居中放置
    x = (target_width - new_width) // 2
    y = (target_height - new_height) // 2
    page.paste(img, (x, y))
    
    # 保存为PDF
    page.save(output_pdf_path, 'PDF', resolution=dpi, save_all=False)
    
    return output_pdf_path


class PDFMergerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("发票合并工具 v2.0")
        self.root.geometry("700x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.pdf_files = []
        self.output_directory = ""
        self.status_var = None
        
        # 检查激活
        self.activation_ui, self.activation_client = check_and_show_activation(
            root_window=self.root,
            product_id="pdf_merger",
            server_url="https://wfnlj520.com",
            on_activation_success=self.create_ui,
            on_already_activated=self.create_ui
        )
        
        # 如果已激活（activation_ui 为 None），创建主界面
        if self.activation_ui is None:
            print("已激活，创建主界面")
            self.create_ui()
    
    def create_ui(self):
        """创建主界面"""
        print("create_ui 被调用")
        
        # 清除之前的界面
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.pdf_files = []
        self.output_directory = ""
        self.status_var = tk.StringVar(value="准备就绪")
        
        # 主框架
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(main, text="发票合并工具", font=("Microsoft YaHei", 18, "bold")).pack(pady=(0, 15))
        
        # 文件列表
        file_frame = ttk.LabelFrame(main, text="发票文件列表（支持PDF和图片）", padding=10)
        file_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.file_listbox = tk.Listbox(list_frame, height=10, font=("Microsoft YaHei", 10))
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        
        # 按钮行
        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="添加文件", command=self.add_files, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="移除选中", command=self.remove_selected, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空列表", command=self.clear_list, width=12).pack(side=tk.LEFT, padx=5)
        
        # 输出设置
        out_frame = ttk.LabelFrame(main, text="输出设置", padding=10)
        out_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 保存目录
        dir_frame = ttk.Frame(out_frame)
        dir_frame.pack(fill=tk.X, pady=2)
        ttk.Label(dir_frame, text="保存目录:", width=10).pack(side=tk.LEFT)
        self.output_dir_var = tk.StringVar()
        ttk.Entry(dir_frame, textvariable=self.output_dir_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(dir_frame, text="浏览", command=self.browse_dir, width=8).pack(side=tk.RIGHT)
        
        # 文件名
        name_frame = ttk.Frame(out_frame)
        name_frame.pack(fill=tk.X, pady=2)
        ttk.Label(name_frame, text="文件名:", width=10).pack(side=tk.LEFT)
        self.filename_var = tk.StringVar(value="合并发票")
        ttk.Entry(name_frame, textvariable=self.filename_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(name_frame, text=".pdf").pack(side=tk.LEFT)
        
        # 合并按钮
        ttk.Button(main, text="开始合并", command=self.merge_files, width=20).pack(pady=10)
        
        # 状态栏
        ttk.Label(main, textvariable=self.status_var, font=("Microsoft YaHei", 10)).pack()
        
        print("主界面创建完成")
    
    def add_files(self):
        files = filedialog.askopenfilenames(
            title="选择PDF或图片文件",
            filetypes=[
                ("PDF和图片", "*.pdf *.jpg .jpeg .png .bmp .gif .tiff .tif .webp .ico"),
                ("PDF文件", "*.pdf"),
                ("图片", "*.jpg .jpeg .png .bmp .gif .tiff .tif .webp .ico")
            ]
        )
        if files:
            for f in files:
                if f not in self.pdf_files:
                    self.pdf_files.append(f)
                    name = os.path.basename(f)
                    if os.path.splitext(f)[1].lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp', '.ico']:
                        name = f"[图片] {name}"
                    self.file_listbox.insert(tk.END, name)
            if not self.output_directory:
                self.output_directory = os.path.dirname(files[0])
                self.output_dir_var.set(self.output_directory)
            self.status_var.set(f"已添加 {len(files)} 个文件")
    
    def remove_selected(self):
        sel = self.file_listbox.curselection()
        if sel:
            self.file_listbox.delete(sel[0])
            del self.pdf_files[sel[0]]
            self.status_var.set("已移除")
    
    def clear_list(self):
        self.file_listbox.delete(0, tk.END)
        self.pdf_files = []
        self.status_var.set("已清空")
    
    def browse_dir(self):
        d = filedialog.askdirectory(title="选择保存目录")
        if d:
            self.output_directory = d
            self.output_dir_var.set(d)
    
    def merge_files(self):
        if not self.activation_client or not self.activation_client.activated:
            messagebox.showerror("错误", "软件未激活")
            return
        if not self.pdf_files:
            messagebox.showwarning("警告", "请添加文件")
            return
        if not self.output_directory:
            messagebox.showwarning("警告", "请选择保存目录")
            return
        
        name = self.filename_var.get().strip() or "合并发票"
        if not name.endswith('.pdf'):
            name += '.pdf'
        out_path = os.path.join(self.output_directory, name)
        
        if os.path.exists(out_path):
            if not messagebox.askyesno("确认", "文件已存在，是否覆盖？"):
                return
        
        def do_merge():
            temps = []
            try:
                self.status_var.set("处理中...")
                merger = PyPDF2.PdfMerger()
                
                for i, f in enumerate(self.pdf_files):
                    self.status_var.set(f"处理 ({i+1}/{len(self.pdf_files)})")
                    ext = os.path.splitext(f)[1].lower()
                    
                    if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp', '.ico']:
                        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                        tmp.close()
                        image_to_pdf(f, tmp.name, dpi=200)
                        temps.append(tmp.name)
                        merger.append(tmp.name)
                    else:
                        merger.append(f)
                
                with open(out_path, 'wb') as o:
                    merger.write(o)
                merger.close()
                
                for t in temps:
                    try:
                        os.unlink(t)
                    except:
                        pass
                
                self.status_var.set("完成！")
                messagebox.showinfo("完成", f"合并完成！\n\n保存位置：{out_path}")
                
            except Exception as e:
                for t in temps:
                    try:
                        os.unlink(t)
                    except:
                        pass
                self.status_var.set("失败")
                messagebox.showerror("错误", f"合并失败：{e}")
        
        threading.Thread(target=do_merge, daemon=True).start()
    
    def on_close(self):
        try:
            if self.activation_client:
                self.activation_client.cleanup_on_exit()
        except:
            pass
        self.root.destroy()
    
    def run(self):
        self.root.mainloop()


def main():
    app = PDFMergerApp()
    app.run()


if __name__ == "__main__":
    main()