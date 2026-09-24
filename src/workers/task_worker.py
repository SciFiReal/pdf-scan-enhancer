from PySide6.QtCore import QThread, Signal
from src.core.ocr_engine import OCREngine
from src.core.extract_engine import ExtractEngine
from src.core.translate_engine import TranslateEngine
from src.core.export_engine import ExportEngine
from pathlib import Path


def _parse_page_ranges(pages_str: str) -> list[str]:
    """将 "1-50,51-100,101-150" 解析为 ["1-50", "51-100", "101-150"]"""
    if not pages_str:
        return []
    parts = [p.strip() for p in pages_str.split(",") if p.strip()]
    return parts


class ProcessWorker(QThread):
    """后台处理线程，负责跑完整流程"""
    log_updated = Signal(str)
    progress_stage = Signal(int)
    stage_updated = Signal(str)
    finished_ok = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, input_pdf: str, output_dir: str, options: dict):
        super().__init__()
        self.input_pdf = input_pdf
        self.output_dir = output_dir
        self.options = options
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            pages_str = self.options.get("pages", "")
            ranges = _parse_page_ranges(pages_str)

            if len(ranges) > 1:
                self._run_multi_range(ranges)
            else:
                self._run_single(pages_str)
        except Exception as e:
            self.error_occurred.emit(str(e))

    # ── 单范围 / 无范围 ──

    def _run_single(self, pages: str):
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        base_name = Path(self.input_pdf).stem
        pages_suffix = f"_p{pages.replace(',', '-').replace(' ', '')}" if pages else ""

        self.stage_updated.emit("OCR 增强...")
        self.log_updated.emit("▶ 开始处理：页面纠偏 + 图像增强 + 重建OCR层")
        self.progress_stage.emit(10)

        ocr_output = str(Path(self.output_dir) / f"{base_name}{pages_suffix}_enhanced.pdf")

        ocr_ok = OCREngine.process(
            input_path=self.input_pdf,
            output_path=ocr_output,
            language=self.options.get("language", "eng"),
            deskew=self.options.get("deskew", True),
            clean=self.options.get("clean", True),
            force_ocr=self.options.get("force_ocr", True),
            pages=pages,
        )

        if self._cancelled:
            self.log_updated.emit("⚠ 用户取消处理")
            return

        if not ocr_ok:
            self.error_occurred.emit("OCR增强失败，请检查Tesseract是否已安装")
            return

        self.log_updated.emit("✅ OCR增强完成，生成增强版PDF")
        self.progress_stage.emit(50)

        md_path = self._extract_and_translate(ocr_output, base_pct=50)

        self._final_export(md_path)

        self.stage_updated.emit("完成")
        self.progress_stage.emit(100)
        self.finished_ok.emit(ocr_output)

    # ── 多范围处理 + 合并 ──

    def _run_multi_range(self, ranges: list[str]):
        base_name = Path(self.input_pdf).stem
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        total_ranges = len(ranges)
        self.log_updated.emit(f"▶ 多页码范围模式：共 {total_ranges} 个范围")
        self.log_updated.emit(f"  范围：{', '.join(ranges)}")

        all_ocr_pdfs = []
        all_md_files = []
        all_translated_md = []

        for i, page_range in enumerate(ranges):
            if self._cancelled:
                self.log_updated.emit("⚠ 用户取消处理")
                return

            range_label = f"[{i+1}/{total_ranges}] 页码 {page_range}"
            range_suffix = f"_p{page_range.replace(' ', '')}"
            range_dir = str(Path(self.output_dir) / f"{base_name}{range_suffix}")
            Path(range_dir).mkdir(parents=True, exist_ok=True)

            base_pct = int(i / total_ranges * 90)

            # OCR
            self.stage_updated.emit(f"OCR 增强 {range_label}")
            self.log_updated.emit(f"\n▶ {range_label}：OCR增强...")
            self.progress_stage.emit(base_pct + int(10 / total_ranges))

            ocr_output = str(Path(range_dir) / f"{base_name}{range_suffix}_enhanced.pdf")
            ocr_ok = OCREngine.process(
                input_path=self.input_pdf,
                output_path=ocr_output,
                language=self.options.get("language", "eng"),
                deskew=self.options.get("deskew", True),
                clean=self.options.get("clean", True),
                force_ocr=self.options.get("force_ocr", True),
                pages=page_range,
            )

            if not ocr_ok:
                self.log_updated.emit(f"  ⚠ OCR增强失败，跳过此范围")
                continue

            all_ocr_pdfs.append(ocr_output)
            self.log_updated.emit(f"  ✅ OCR增强完成")

            if self._cancelled:
                return

            # 提取
            md_path = None
            if self.options.get("extract_md", True):
                self.stage_updated.emit(f"结构化提取 {range_label}")
                self.log_updated.emit(f"  ▶ 结构化提取...")
                try:
                    md_path = ExtractEngine.extract_to_markdown(
                        input_pdf=ocr_output,
                        output_dir=range_dir,
                    )
                    all_md_files.append(md_path)
                    self.log_updated.emit(f"  ✅ 提取完成")
                except Exception as e:
                    self.log_updated.emit(f"  ⚠ 提取失败：{e}")

            if self._cancelled:
                return

            # 翻译
            translated_path = None
            if self.options.get("translate", False) and md_path:
                self.stage_updated.emit(f"翻译 {range_label}")
                self.log_updated.emit(f"  ▶ 翻译...")
                try:
                    translated_path = self._translate_single(md_path, base_pct)
                    if translated_path:
                        all_translated_md.append(translated_path)
                        self.log_updated.emit(f"  ✅ 翻译完成")
                except Exception as e:
                    self.log_updated.emit(f"  ⚠ 翻译失败：{e}")

        # ── 合并阶段 ──
        if self._cancelled:
            return

        self.stage_updated.emit("合并输出...")
        self.log_updated.emit(f"\n{'='*40}")
        self.log_updated.emit("▶ 开始合并所有范围...")
        self.progress_stage.emit(92)

        # 合并 PDF
        merged_pdf_path = ""
        if len(all_ocr_pdfs) > 1:
            merged_pdf_path = str(Path(self.output_dir) / f"{base_name}_merged.pdf")
            try:
                ExportEngine.merge_pdfs(all_ocr_pdfs, merged_pdf_path)
                self.log_updated.emit(f"  ✅ PDF合并完成：{merged_pdf_path}")
            except Exception as e:
                self.log_updated.emit(f"  ⚠ PDF合并失败：{e}")
                merged_pdf_path = ""
        elif len(all_ocr_pdfs) == 1:
            merged_pdf_path = all_ocr_pdfs[0]

        self.progress_stage.emit(95)

        # 合并 EPUB / 导出
        source_md_list = all_translated_md if all_translated_md else all_md_files
        export_format = self.options.get("export_format", "")

        if export_format == "epub" and len(source_md_list) > 1:
            epub_path = str(Path(self.output_dir) / f"{base_name}_merged.epub")
            try:
                ExportEngine.export_multiple_md_to_epub(
                    source_md_list, epub_path, title=base_name,
                )
                self.log_updated.emit(f"  ✅ EPUB合并导出完成：{epub_path}")
            except Exception as e:
                self.log_updated.emit(f"  ⚠ EPUB导出失败：{e}")
        elif export_format and source_md_list:
            for md_path in source_md_list:
                try:
                    ExportEngine.export(md_path, export_format)
                except Exception as e:
                    self.log_updated.emit(f"  ⚠ 导出失败：{e}")

        self.stage_updated.emit("完成")
        self.progress_stage.emit(100)
        self.log_updated.emit(f"\n全部处理完成！")
        if merged_pdf_path:
            self.log_updated.emit(f"合并PDF：{merged_pdf_path}")
        self.finished_ok.emit(merged_pdf_path or self.output_dir)

    # ── 辅助方法 ──

    def _extract_and_translate(self, ocr_output: str, base_pct: int) -> str | None:
        """提取 + 翻译，返回最终的 md 路径（译文或原文）"""
        base_name = Path(ocr_output).stem
        md_path = None

        if self.options.get("extract_md", True):
            if self._cancelled:
                return None
            self.stage_updated.emit("结构化提取...")
            self.log_updated.emit("▶ 开始结构化提取：版面分析 + 生成Markdown")

            md_path = ExtractEngine.extract_to_markdown(
                input_pdf=ocr_output,
                output_dir=self.output_dir,
            )
            self.log_updated.emit(f"✅ 文本提取完成：{md_path}")
            self.progress_stage.emit(base_pct + 20)

        if self.options.get("translate", False) and md_path:
            if self._cancelled:
                return md_path
            self.stage_updated.emit("翻译中...")
            self.log_updated.emit("▶ 开始翻译...")

            try:
                translated_path = self._translate_single(md_path, base_pct + 20)
                if translated_path:
                    self.log_updated.emit(f"✅ 纯译文完成：{translated_path}")
                    return translated_path
            except Exception as e:
                self.log_updated.emit(f"⚠ 翻译失败（将使用原文导出）：{e}")

        return md_path

    def _translate_single(self, md_path: str, base_pct: int) -> str | None:
        """翻译单个 MD 文件，返回译文路径"""
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

        provider_names = {"ollama": "Ollama 本地模型", "baidu": "百度翻译", "google": "Google 翻译"}
        provider_name = provider_names.get(engine.provider, engine.provider)
        self.log_updated.emit(f"  翻译引擎：{provider_name}")

        def on_progress(done, total, pct):
            if self._cancelled:
                return
            self.progress_stage.emit(base_pct + int(pct * 0.25 / 100))

        translated_path, bilingual_path = engine.translate_markdown_both(
            md_path, progress_callback=on_progress,
        )

        if self._cancelled:
            return None

        self.log_updated.emit(f"  ✅ 双语对照完成：{bilingual_path}")
        return translated_path

    def _final_export(self, md_path: str | None):
        """最终导出（单范围模式）"""
        if not md_path:
            return

        export_format = self.options.get("export_format", "")
        if not export_format:
            return

        if self._cancelled:
            return

        self.stage_updated.emit("导出中...")
        self.log_updated.emit(f"▶ 导出为 {export_format.upper()} 格式...")
        try:
            if self.options.get("translate") and md_path:
                export_source = md_path
            else:
                export_source = md_path
            export_path = ExportEngine.export(export_source, export_format)
            self.log_updated.emit(f"✅ 导出完成：{export_path}")
        except Exception as e:
            self.log_updated.emit(f"⚠ 导出失败：{e}")
        self.progress_stage.emit(98)
