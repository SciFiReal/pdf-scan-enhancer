from PySide6.QtCore import QThread, Signal
from src.core.ocr_engine import OCREngine
from src.core.extract_engine import ExtractEngine
from pathlib import Path

class ProcessWorker(QThread):
    """后台处理线程，负责跑完整流程"""
    # 信号：日志文本、进度阶段、完成、出错
    log_updated = Signal(str)
    progress_stage = Signal(int)  # 0-100，阶段式进度
    finished_ok = Signal(str)     # 成功，返回输出文件路径
    error_occurred = Signal(str)  # 失败，返回错误信息

    def __init__(self, input_pdf: str, output_dir: str, options: dict):
        super().__init__()
        self.input_pdf = input_pdf
        self.output_dir = output_dir
        self.options = options  # 界面传过来的参数：deskew/clean/language等

    def run(self):
        try:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            base_name = Path(self.input_pdf).stem

            # 阶段1：OCR增强
            self.log_updated.emit("▶ 开始处理：页面纠偏 + 图像增强 + 重建OCR层")
            self.progress_stage.emit(10)

            ocr_output = str(Path(self.output_dir) / f"{base_name}_enhanced.pdf")

            ocr_ok = OCREngine.process(
                input_path=self.input_pdf,
                output_path=ocr_output,
                language=self.options.get("language", "eng"),
                deskew=self.options.get("deskew", True),
                clean=self.options.get("clean", True),
                force_ocr=self.options.get("force_ocr", True),
            )

            if not ocr_ok:
                self.error_occurred.emit("OCR增强失败，请检查Tesseract是否已安装")
                return

            self.log_updated.emit("✅ OCR增强完成，生成增强版PDF")
            self.progress_stage.emit(60)

            # 阶段2：结构化提取
            if self.options.get("extract_md", True):
                self.log_updated.emit("▶ 开始结构化提取：版面分析 + 生成Markdown")

                md_path = ExtractEngine.extract_to_markdown(
                    input_pdf=ocr_output,
                    output_dir=self.output_dir,
                )

                self.log_updated.emit(f"✅ 文本提取完成：{md_path}")
                self.progress_stage.emit(100)

            self.finished_ok.emit(ocr_output)

        except Exception as e:
            self.error_occurred.emit(str(e))
