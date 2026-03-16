# PDF合并工具

一个简单的 PDF 合并工具，支持图片转 PDF 并自动调整为固定尺寸。

## 功能特性

- ✅ PDF 文件合并
- ✅ 图片转 PDF（支持 jpg, png, bmp, gif, tiff, webp 等格式）
- ✅ 自动将竖版图片旋转为横版
- ✅ 固定尺寸输出（1694×1096 像素）
- ✅ 激活码验证系统

## 下载

前往 [Releases](https://github.com/wfnlj/wfnlj-tools/releases) 页面下载最新版本。

## 开发

```bash
# 安装依赖
pip install pillow numpy pyinstaller

# 运行
python run.py

# 打包
pyinstaller PDF合并工具.spec
```

## License

MIT License