from PySide6.QtCore import QThread, Signal
from src.core.ocr_engine import OCREngine
from src.core.extract_engine import ExtractEngine
from src.core.translate_engine import TranslateEngine
from pathlib import Path


class ProcessWorker(QThread):
    """后台处理线程，负责跑完整流程"""
    log_updated = Signal(str)
    progress_stage = Signal(int)
    finished_ok = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, input_pdf: str, output_dir: str, options: dict):
        super().__init__()
        self.input_pdf = input_pdf
        self.output_dir = output_dir
        self.options = options

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
            self.progress_stage.emit(50)

            # 阶段2：结构化提取
            md_path = None
            if self.options.get("extract_md", True):
                self.log_updated.emit("▶ 开始结构化提取：版面分析 + 生成Markdown")

                md_path = ExtractEngine.extract_to_markdown(
                    input_pdf=ocr_output,
                    output_dir=self.output_dir,
                )

                self.log_updated.emit(f"✅ 文本提取完成：{md_path}")
                self.progress_stage.emit(70)

            # 阶段3：翻译
            if self.options.get("translate", False) and md_path:
                self.log_updated.emit("▶ 开始翻译...")

                translate_opts = self.options.get("translate_options", {})
                engine = TranslateEngine(
                    provider=translate_opts.get("provider", "google"),
                    source=translate_opts.get("source", "auto"),
                    target=translate_opts.get("target", "zh-CN"),
                    baidu_appid=translate_opts.get("baidu_appid", ""),
                    baidu_key=translate_opts.get("baidu_key", ""),
                )

                provider_name = "Google" if engine.provider == "google" else "百度"
                self.log_updated.emit(f"  翻译引擎：{provider_name}")

                def on_translate_progress(done, total, pct):
                    self.log_updated.emit(f"  翻译进度：{done}/{total} 段 ({pct}%)")
                    translate_pct = 70 + int(pct * 0.25)
                    self.progress_stage.emit(translate_pct)

                bilingual = translate_opts.get("bilingual", True)
                if bilingual:
                    bilingual_path = engine.translate_markdown_bilingual(
                        md_path, progress_callback=on_translate_progress,
                    )
                    self.log_updated.emit(f"✅ 双语对照完成：{bilingual_path}")
                else:
                    translated_path = engine.translate_markdown(
                        md_path, progress_callback=on_translate_progress,
                    )
                    self.log_updated.emit(f"✅ 翻译完成：{translated_path}")

                self.progress_stage.emit(95)

            self.progress_stage.emit(100)
            self.finished_ok.emit(ocr_output)

        except Exception as e:
            self.error_occurred.emit(str(e))
