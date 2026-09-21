# PDF Scan Enhancer

扫描版 PDF 一站式增强工具箱：先修图，再识别，后提取，从根源解决扫描件歪斜、脏污、文字复制乱序问题。

---

## 关于项目

很多影印版、扫描版 PDF 普遍存在页面歪斜、底色脏污、OCR 文字错位、复制时句子跳行乱序的问题，直接拿去翻译往往语句不通、排版混乱。

本项目针对这类**不规范扫描 PDF** 做全链路增强：先对页面图像自动纠偏、去噪、裁边，再重建高质量 OCR 文字层，最后通过版面分析提取出结构化的通顺文本。不是简单的 "直接 OCR 翻译"，而是先做「图像修复 + 文字对齐」，从源头提升后续阅读、复制、翻译的质量。

全程本地离线运行，文件不上传服务器，隐私安全。

---

## 核心特性

- **图像自动矫正**：页面纠偏、自动裁边、去除噪点与底色污渍
- **OCR 层重建**：强制重新识别，生成文字对齐精准的双层可检索 PDF
- **结构化文本提取**：基于版面分析，自动识别段落 / 标题 / 脚注，输出通顺 Markdown，解决普通复制的乱序问题
- **图形化操作界面**：基于 PySide6 开发，无需命令行，开箱即用
- **模块化架构**：核心引擎与界面完全分离，易扩展、可二次开发
- **本地离线运行**：所有处理均在本地完成，保护文档隐私

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 界面层 | PySide6 (Qt for Python) |
| OCR 与图像增强 | OCRmyPDF + Tesseract + unpaper |
| 版面分析与文本提取 | MinerU (PaddleOCR + 版面分析模型) |
| PDF 处理 | pikepdf |

---

## 快速开始

### 1. 环境要求

- Python 3.10+
- Windows 10/11（当前仅支持 Windows，后续可扩展 macOS/Linux）

### 2. 安装系统依赖

本项目需要以下系统级工具（非 Python 包），需手动安装：

#### Tesseract OCR（必须）

OCR 引擎核心，负责文字识别。

1. 下载安装包：https://github.com/UB-Mannheim/tesseract/wiki
2. 安装时勾选Additional language data，至少选择 `English` 和 `Chinese Simplified`
3. 安装后下载 `osd.traineddata`（页面方向检测）：
   - 从 https://github.com/tesseract-ocr/tessdata/raw/main/osd.traineddata 下载
   - 放入 Tesseract 安装目录下的 `tessdata` 文件夹（如 `C:\Program Files\Tesseract-OCR\tessdata\`）

> 程序会自动搜索常见安装路径（Program Files、Downloads 等），如果安装在非标准位置，可设置环境变量 `TESSDATA_PREFIX` 指向 tessdata 目录。

#### Ghostscript（必须）

PDF 渲染引擎，OCRmyPDF 依赖它处理 PDF 文件。

1. 下载安装包：https://ghostscript.com/releases/gsdnld.html
2. 选择 `Ghostscript for Windows (64 bit)` 下载
3. 安装后确保 `gswin64c.exe` 在系统 PATH 中

> 程序会自动搜索常见安装路径。

#### unpaper（可选）

图像去噪工具，用于清理扫描件的污渍和底色。如果未安装，程序会自动跳过此功能。

1. 下载预编译版本：https://github.com/unpaper/unpaper/releases
2. 将 `unpaper.exe` 放入 Tesseract 安装目录或系统 PATH 中的任意位置

### 3. 安装 Python 依赖

```bash
# 克隆仓库
git clone https://github.com/你的用户名/pdf-scan-enhancer.git
cd pdf-scan-enhancer

# 创建虚拟环境（推荐）
py -3.10 -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

> 首次运行时 MinerU 会自动下载版面分析模型（约 1.5GB），请确保网络畅通。

### 4. 启动程序

```bash
python main.py
```

### 5. 使用流程

1. 点击「选择文件」选择要处理的扫描版 PDF
2. 勾选处理选项（默认全选即可）
3. 点击「开始处理」，等待完成
4. 输出文件在 PDF 同目录的 `output/` 文件夹下

---

## 项目结构

```
PDF-Scan-Enhancer/
├── main.py                  # 程序入口
├── requirements.txt         # Python 依赖
├── src/
│   ├── core/                # 核心引擎（与界面解耦）
│   │   ├── ocr_engine.py    # OCR 增强引擎（OCRmyPDF + Tesseract）
│   │   ├── extract_engine.py # 结构化提取引擎（MinerU）
│   │   ├── translate_engine.py # 翻译引擎（待实现）
│   │   └── export_engine.py    # 导出引擎（待实现）
│   ├── ui/                  # 界面层
│   │   └── main_window.py   # 主窗口（PySide6）
│   └── workers/             # 后台线程
│       └── task_worker.py   # 处理任务线程
└── test_core.py             # 核心引擎测试脚本
```

---

## 开发路线图

### v0.1 MVP（已完成）

- [x] OCR 增强引擎：纠偏 + 去噪 + 双层 PDF 输出
- [x] 结构化提取引擎：MinerU 版面分析 + Markdown 输出
- [x] PySide6 图形界面：文件选择、参数配置、进度显示
- [x] 后台处理线程：异步执行，不阻塞 UI
- [x] 系统依赖自动检测：Tesseract / Ghostscript / unpaper 自动搜索

### v0.2 翻译功能

- [ ] 翻译引擎接入（DeepL API / 百度翻译 API）
- [ ] 界面增加翻译语言选择
- [ ] 翻译结果与原文对照输出

### v0.3 本地翻译 + 高级功能

- [ ] 本地大模型离线翻译支持（Ollama / llama.cpp）
- [ ] 中英对照 Markdown 输出
- [ ] 术语表 / 翻译记忆功能

### v0.4 批量与导出

- [ ] 批量文件 / 文件夹处理
- [ ] 配置预设（保存常用参数组合）
- [ ] 更多导出格式：DOCX、EPUB、HTML
- [ ] 处理结果预览界面

### v1.0 稳定版

- [ ] 跨平台支持（macOS / Linux）
- [ ] 一键打包可执行文件（PyInstaller / Nuitka）
- [ ] 自动更新机制
- [ ] 完整的单元测试和集成测试

### 远期规划

- [ ] 浏览器插件：选中扫描 PDF 直接调用增强
- [ ] 命令行工具模式（无 GUI 批量处理）
- [ ] 插件系统：支持自定义 OCR 引擎和翻译 API

---

## 贡献

欢迎提交 Issue 和 Pull Request。

---

## 开源协议

MIT License
