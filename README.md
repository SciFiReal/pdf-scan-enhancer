# PDF Scan Enhancer

扫描版 PDF 增强翻译工具，面向英文及各类外文书籍：图像矫正 → 精准OCR → 结构化提取 → 全文翻译，专为歪斜、脏污、低质量的扫描书籍/文献优化。

---

## 关于项目

很多影印版、扫描版 PDF 普遍存在页面歪斜、底色脏污、OCR 文字错位、复制时句子跳行乱序的问题，直接拿去翻译往往语句不通、排版混乱。

本项目针对这类**不规范扫描 PDF** 做全链路增强：先对页面图像自动纠偏、去噪、裁边，再重建高质量 OCR 文字层，最后通过版面分析提取出结构化的通顺文本。不是简单的 "直接 OCR 翻译"，而是先做「图像修复 + 文字对齐」，从源头提升后续阅读、复制、翻译的质量。

全程本地离线运行，文件不上传服务器，隐私安全。

---

## 核心特性

- **图像自动矫正**：页面纠偏、自动裁边、去除噪点与底色污渍
- **OCR 层重建**：强制重新识别，生成文字对齐精准的双层可检索 PDF
- **多语言 OCR**：支持英文、简/繁体中文、日文、韩文等识别语言
- **页码范围选择**：指定页码范围处理（如 `1-50,51-100,101-250`），多段自动分别处理后合并输出，适合大型书籍分段处理
- **PDF 合并**：多页码范围处理完成后，自动合并为一个完整的增强版 PDF
- **多章节 EPUB 合并导出**：多个分段翻译的 Markdown 自动合并为一本完整 EPUB（带目录），直接导入 Kindle 阅读
- **结构化文本提取**：基于版面分析，自动识别段落 / 标题 / 脚注，输出通顺 Markdown，解决普通复制的乱序问题
- **多引擎翻译**：支持 Ollama 本地大模型（离线免费）/ 百度翻译 API / Google 翻译，原文+译文双语对照输出
- **术语表支持**：可加载自定义 CSV/JSON 术语表，确保专业词汇翻译一致性
- **批量处理**：支持多选文件和文件夹导入，逐个顺序处理，实时显示进度
- **配置预设**：保存和快速加载常用参数组合，内置 3 套默认预设
- **多格式导出**：DOCX（Word）、EPUB（电子书）、HTML（网页）、TXT（纯文本）
- **结果预览**：直接查看生成的 Markdown 文本内容
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
| 翻译 | Ollama 本地模型 / deep-translator（百度翻译 API / Google 翻译） |
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

#### Ollama（可选，本地离线翻译）

本地大模型翻译引擎，完全离线、无需 API Key。

1. 下载安装 Ollama：https://ollama.com/download
2. 下载翻译模型（推荐）：
   ```bash
   ollama pull qwen2.5:7b
   ```
   其他可选模型：`llama3`、`mistral`、`gemma2` 等
3. 确保 Ollama 服务正在运行（安装后默认自动启动）

> 程序启动时会自动检测 Ollama 服务和已下载的模型，在翻译引擎下拉框中选择即可。

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

#### 单文件处理

1. 点击「添加文件」选择要处理的扫描版 PDF（支持多选）
2. 或点击「添加文件夹」批量导入整个目录下的所有 PDF
3. 在右侧面板配置处理选项（默认全选即可）
4. （可选）在「预设」下拉框中快速加载常用配置，或点击「保存为预设」存储当前设置
5. 点击「开始处理」，等待完成
6. 输出文件在 PDF 同目录的 `output/` 文件夹下
7. 点击「预览结果」可查看生成的 Markdown 文本内容

#### 批量处理

- 添加多个文件或文件夹后，程序会按顺序逐个处理
- 每个文件的进度会在界面底部实时显示
- 处理完成后，可在输出目录找到所有增强后的 PDF 和提取的文本

#### 大型书籍分段处理

处理 200+ 页的扫描书籍时，建议使用页码范围分段处理：

1. 在「页码范围」输入框中填入多段范围，用逗号分隔，如：`1-50,51-100,101-150,151-250`
2. 程序会自动将每段分别进行 OCR → 提取 → 翻译
3. 处理完成后自动合并输出：
   - **合并 PDF**（`书名_merged.pdf`）→ 电脑阅读完整版
   - **合并 EPUB**（`书名_merged.epub`）→ 导入 Kindle，自动带章节目录

> 留空页码范围则处理全部页面。单段范围（如 `1-50`）仅处理指定页，输出文件名带 `_p1-50` 后缀。

#### 导出格式

在「导出格式」下拉框中选择：
- **Word 文档（.docx）**：适合办公编辑，保留标题层级和表格结构
- **电子书（.epub）**：适合电子阅读器 / Kindle，自动分章节，多段范围处理时合并为完整电子书
- **网页（.html）**：带样式的静态页面，可直接浏览器打开
- **纯文本（.txt）**：去除所有格式，仅保留文字内容

#### 术语表使用（可选）

翻译专业文档时，可加载自定义术语表确保专业词汇翻译一致。

**CSV 格式**（两列：原文,译文）：
```csv
neural network,神经网络
backpropagation,反向传播
gradient descent,梯度下降
```

**JSON 格式**：
```json
{
  "neural network": "神经网络",
  "backpropagation": "反向传播",
  "gradient descent": "梯度下降"
}
```

在翻译选项中点击「选择」加载术语表文件即可。

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
│   │   ├── translate_engine.py # 翻译引擎（Ollama / 百度 / Google + 术语表）
│   │   ├── export_engine.py    # 导出引擎（DOCX/EPUB/HTML/TXT）
│   │   └── preset_manager.py   # 预设管理器（配置持久化）
│   ├── ui/                  # 界面层
│   │   └── main_window.py   # 主窗口（PySide6）
│   └── workers/             # 后台线程
│       ├── task_worker.py   # 单文件处理任务线程
│       └── batch_worker.py  # 批量处理任务线程
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

### v0.2 翻译功能（已完成）

- [x] 翻译引擎：百度翻译 API（国内推荐）+ Google 翻译（需代理）
- [x] 多语言支持：中/英/日/韩/法/德/西/俄
- [x] 双语对照输出：原文 + 译文 Markdown
- [x] 界面翻译配置：语言选择、引擎切换、API 密钥输入

### v0.3 本地翻译 + 高级功能（已完成）

- [x] Ollama 本地大模型离线翻译：支持 qwen2.5 / llama3 等模型，完全离线
- [x] 术语表功能：加载 CSV/JSON 术语表，翻译时注入专业词汇
- [x] 自动检测 Ollama 已安装模型，界面一键切换
- [ ] 翻译质量评估与反馈（延后）

### v0.4 批量与导出（已完成）

- [x] 批量文件 / 文件夹处理：支持多选文件和整个目录，逐个顺序处理
- [x] 配置预设：保存和加载常用参数组合，内置 3 套默认预设
- [x] 多格式导出：DOCX（Word）、EPUB（电子书）、HTML（网页）、TXT（纯文本）
- [x] 结果预览：直接查看生成的 Markdown 文本内容

### v0.5 大型文档支持 + 体验打磨（已完成）

- [x] 页码范围选择：支持指定页码范围（如 `1-50`），多段范围自动分段处理并合并
- [x] PDF 合并：多段增强 PDF 自动合并为完整版（`pikepdf`）
- [x] 多章节 EPUB 合并：多段翻译 Markdown 合并为一本完整 EPUB（带目录），适合 Kindle 阅读
- [x] OCR 识别语言选择：英文 / 简繁体中文 / 日文 / 韩文
- [x] 运行日志文件：自动写入 `~/.pdf-scan-enhancer/app.log`，滚动保留 2MB×3
- [x] 关闭确认 + 错误弹窗：处理中退出时确认，错误以弹窗提示
- [x] 翻译失败隔离：翻译失败不影响后续导出流程
- [x] Ollama 模型列表异步刷新：不阻塞 UI
- [x] Bug 修复：7 项高优先级问题（导出变量名、预设语言字段、取消逻辑等）

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
