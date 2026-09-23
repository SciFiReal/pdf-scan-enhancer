from PySide6.QtCore import QThread, Signal
from src.core.ocr_engine import OCREngine
from src.core.extract_engine import ExtractEngine
from src.core.translate_engine import TranslateEngine
from src.core.export_engine import ExportEngine
from pathlib import Path


class BatchWorker(QThread):
    """批量处理线程：依次处理多个 PDF 文件"""
    log_updated = Signal(str)
    progress_stage = Signal(int)
    file_progress = Signal(int, int)
    finished_ok = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, input_files: list[str], output_dir: str, options: dict):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.options = options

    def run(self):
        total = len(self.input_files)
        results = []
        failed = []

        for i, input_pdf in enumerate(self.input_files):
            file_name = Path(input_pdf).name
            self.log_updated.emit(f"\n{'='*40}")
            self.log_updated.emit(f"▶ 处理文件 [{i+1}/{total}]：{file_name}")
            self.file_progress.emit(i + 1, total)

            try:
                result = self._process_single(input_pdf, i, total)
                if result:
                    results.append(result)
                else:
                    failed.append(file_name)
            except Exception as e:
                self.log_updated.emit(f"⚠ {file_name} 处理失败：{e}")
                failed.append(file_name)

        self.log_updated.emit(f"\n{'='*40}")
        self.log_updated.emit(f"批量处理完成：成功 {len(results)} 个，失败 {len(failed)} 个")
        if failed:
            self.log_updated.emit(f"失败文件：{', '.join(failed)}")

        self.progress_stage.emit(100)
        self.finished_ok.emit(results)

    def _process_single(self, input_pdf: str, file_index: int, total_files: int) -> str | None:
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        base_name = Path(input_pdf).stem
        file_output_dir = str(Path(self.output_dir) / base_name)
        Path(file_output_dir).mkdir(parents=True, exist_ok=True)

        base_pct = file_index / total_files * 100
        step_pct = 1 / total_files * 100

        self.log_updated.emit("  ▶ OCR增强...")
        self.progress_stage.emit(int(base_pct + step_pct * 0.1))

        ocr_output = str(Path(file_output_dir) / f"{base_name}_enhanced.pdf")
        ocr_ok = OCREngine.process(
            input_path=input_pdf,
            output_path=ocr_output,
            language=self.options.get("language", "eng"),
            deskew=self.options.get("deskew", True),
            clean=self.options.get("clean", True),
            force_ocr=self.options.get("force_ocr", True),
        )

        if not ocr_ok:
            self.log_updated.emit(f"  ⚠ OCR增强失败，跳过此文件")
            return None

        self.log_updated.emit("  ✅ OCR增强完成")
        self.progress_stage.emit(int(base_pct + step_pct * 0.4))

        md_path = None
        if self.options.get("extract_md", True):
            self.log_updated.emit("  ▶ 结构化提取...")
            self.progress_stage.emit(int(base_pct + step_pct * 0.5))

            md_path = ExtractEngine.extract_to_markdown(
                input_pdf=ocr_output,
                output_dir=file_output_dir,
            )
            self.log_updated.emit(f"  ✅ 提取完成")
            self.progress_stage.emit(int(base_pct + step_pct * 0.7))

        if self.options.get("translate", False) and md_path:
            self.log_updated.emit("  ▶ 翻译...")

            translate_opts = self.options.get("translate_options", {})
            engine = TranslateEngine(
                provider=translate_opts.get("provider", "ollama"),
                source=translate_opts.get("source", "auto"),
                target=translate_opts.get("target", "zh-CN"),
                baidu_appid=translate_opts.get("baidu_appid", ""),
                baidu_key=translate_opts.get("baidu_key", ""),
                ollama_url=translate_opts.get("ollama_url", "http://localhost:11434"),
                ollama_model=translate_opts.get("ollama_model", ""),
                glossary=translate_opts.get("glossary"),
            )

            def on_progress(done, total, pct):
                translate_pct = base_pct + step_pct * (0.7 + pct / 100 * 0.25)
                self.progress_stage.emit(int(translate_pct))

            # 始终生成两个文件：纯译文 + 双语对照
            translated_path, bilingual_path = engine.translate_markdown_both(
                md_path, progress_callback=on_progress,
            )
            self.log_updated.emit(f"  ✅ 纯译文完成")
            self.log_updated.emit(f"  ✅ 双语对照完成")
            md_path = translated_path

        export_format = self.options.get("export_format", "")
        if export_format and md_path:
            self.log_updated.emit(f"  ▶ 导出 {export_format.upper()}...")
            try:
                # 优先导出纯译文，其次原始英文
                export_source = translated_path if self.options.get("translate") else md_path
                export_path = ExportEngine.export(export_source, export_format)
                self.log_updated.emit(f"  ✅ 导出完成")
            except Exception as e:
                self.log_updated.emit(f"  ⚠ 导出失败：{e}")

        self.progress_stage.emit(int(base_pct + step_pct))
        return ocr_output
