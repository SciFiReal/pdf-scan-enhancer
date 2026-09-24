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


class BatchWorker(QThread):
    """批量处理线程：依次处理多个 PDF 文件"""
    log_updated = Signal(str)
    progress_stage = Signal(int)
    stage_updated = Signal(str)
    file_progress = Signal(int, int)
    finished_ok = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, input_files: list[str], output_dir: str, options: dict):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.options = options
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.input_files)
        results = []
        failed = []

        for i, input_pdf in enumerate(self.input_files):
            if self._cancelled:
                self.log_updated.emit("\n⚠ 用户取消处理")
                break

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

        self.stage_updated.emit("完成")
        self.progress_stage.emit(100)
        self.finished_ok.emit(results)

    def _process_single(self, input_pdf: str, file_index: int, total_files: int) -> str | None:
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        base_name = Path(input_pdf).stem

        pages_str = self.options.get("pages", "")
        ranges = _parse_page_ranges(pages_str)

        base_pct = file_index / total_files * 100
        step_pct = 1 / total_files * 100

        if len(ranges) > 1:
            return self._process_multi_range(
                input_pdf, base_name, ranges, file_index, total_files, base_pct, step_pct,
            )
        else:
            return self._process_single_range(
                input_pdf, base_name, pages_str, file_index, total_files, base_pct, step_pct,
            )

    def _process_single_range(
        self, input_pdf, base_name, pages, file_index, total_files, base_pct, step_pct,
    ) -> str | None:
        pages_suffix = f"_p{pages.replace(',', '-').replace(' ', '')}" if pages else ""
        file_output_dir = str(Path(self.output_dir) / f"{base_name}{pages_suffix}")
        Path(file_output_dir).mkdir(parents=True, exist_ok=True)

        self.stage_updated.emit(f"OCR 增强 ({file_index+1}/{total_files})")
        self.log_updated.emit("  ▶ OCR增强...")
        self.progress_stage.emit(int(base_pct + step_pct * 0.1))

        ocr_output = str(Path(file_output_dir) / f"{base_name}{pages_suffix}_enhanced.pdf")
        ocr_ok = OCREngine.process(
            input_path=input_pdf,
            output_path=ocr_output,
            language=self.options.get("language", "eng"),
            deskew=self.options.get("deskew", True),
            clean=self.options.get("clean", True),
            force_ocr=self.options.get("force_ocr", True),
            pages=pages,
        )

        if self._cancelled:
            return None

        if not ocr_ok:
            self.log_updated.emit(f"  ⚠ OCR增强失败，跳过此文件")
            return None

        self.log_updated.emit("  ✅ OCR增强完成")
        self.progress_stage.emit(int(base_pct + step_pct * 0.4))

        md_path = None
        if self.options.get("extract_md", True):
            if self._cancelled:
                return None
            self.stage_updated.emit(f"结构化提取 ({file_index+1}/{total_files})")
            self.log_updated.emit("  ▶ 结构化提取...")
            self.progress_stage.emit(int(base_pct + step_pct * 0.5))

            md_path = ExtractEngine.extract_to_markdown(
                input_pdf=ocr_output,
                output_dir=file_output_dir,
            )
            self.log_updated.emit(f"  ✅ 提取完成")
            self.progress_stage.emit(int(base_pct + step_pct * 0.7))

        translated_path = None
        if self.options.get("translate", False) and md_path:
            if self._cancelled:
                return None
            self.stage_updated.emit(f"翻译中 ({file_index+1}/{total_files})")
            self.log_updated.emit("  ▶ 翻译...")

            try:
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
                    if self._cancelled:
                        return
                    translate_pct = base_pct + step_pct * (0.7 + pct / 100 * 0.25)
                    self.progress_stage.emit(int(translate_pct))

                translated_path, bilingual_path = engine.translate_markdown_both(
                    md_path, progress_callback=on_progress,
                )

                if self._cancelled:
                    return None

                self.log_updated.emit(f"  ✅ 纯译文完成")
                self.log_updated.emit(f"  ✅ 双语对照完成")
                md_path = translated_path

            except Exception as e:
                self.log_updated.emit(f"  ⚠ 翻译失败（将使用原文导出）：{e}")
                translated_path = None

        export_format = self.options.get("export_format", "")
        if export_format and md_path:
            if self._cancelled:
                return None
            self.stage_updated.emit(f"导出中 ({file_index+1}/{total_files})")
            self.log_updated.emit(f"  ▶ 导出 {export_format.upper()}...")
            try:
                if self.options.get("translate") and translated_path:
                    export_source = translated_path
                else:
                    export_source = md_path
                export_path = ExportEngine.export(export_source, export_format)
                self.log_updated.emit(f"  ✅ 导出完成")
            except Exception as e:
                self.log_updated.emit(f"  ⚠ 导出失败：{e}")

        self.progress_stage.emit(int(base_pct + step_pct))
        return ocr_output

    def _process_multi_range(
        self, input_pdf, base_name, ranges, file_index, total_files, base_pct, step_pct,
    ) -> str | None:
        """处理单个文件的多页码范围，合并输出"""
        total_ranges = len(ranges)
        self.log_updated.emit(f"  多页码范围：共 {total_ranges} 个范围 → {', '.join(ranges)}")

        all_ocr_pdfs = []
        all_md_files = []
        all_translated_md = []

        for i, page_range in enumerate(ranges):
            if self._cancelled:
                return None

            range_suffix = f"_p{page_range.replace(' ', '')}"
            range_dir = str(Path(self.output_dir) / f"{base_name}{range_suffix}")
            Path(range_dir).mkdir(parents=True, exist_ok=True)

            range_pct = base_pct + step_pct * (i / total_ranges)

            self.stage_updated.emit(f"OCR 增强 [{i+1}/{total_ranges}] 页码 {page_range}")
            self.log_updated.emit(f"  ▶ [{i+1}/{total_ranges}] 页码 {page_range}：OCR增强...")
            self.progress_stage.emit(int(range_pct + step_pct / total_ranges * 0.1))

            ocr_output = str(Path(range_dir) / f"{base_name}{range_suffix}_enhanced.pdf")
            ocr_ok = OCREngine.process(
                input_path=input_pdf,
                output_path=ocr_output,
                language=self.options.get("language", "eng"),
                deskew=self.options.get("deskew", True),
                clean=self.options.get("clean", True),
                force_ocr=self.options.get("force_ocr", True),
                pages=page_range,
            )

            if not ocr_ok:
                self.log_updated.emit(f"    ⚠ OCR增强失败，跳过")
                continue

            all_ocr_pdfs.append(ocr_output)
            self.log_updated.emit(f"    ✅ OCR增强完成")

            if self._cancelled:
                return None

            md_path = None
            if self.options.get("extract_md", True):
                self.log_updated.emit(f"    ▶ 结构化提取...")
                try:
                    md_path = ExtractEngine.extract_to_markdown(
                        input_pdf=ocr_output, output_dir=range_dir,
                    )
                    all_md_files.append(md_path)
                    self.log_updated.emit(f"    ✅ 提取完成")
                except Exception as e:
                    self.log_updated.emit(f"    ⚠ 提取失败：{e}")

            if self._cancelled:
                return None

            translated_path = None
            if self.options.get("translate", False) and md_path:
                self.log_updated.emit(f"    ▶ 翻译...")
                try:
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

                    def on_progress(done, total, pct, _range_pct=range_pct):
                        if self._cancelled:
                            return
                        self.progress_stage.emit(int(_range_pct + step_pct / total_ranges * (0.7 + pct / 100 * 0.25)))

                    translated_path, bilingual_path = engine.translate_markdown_both(
                        md_path, progress_callback=on_progress,
                    )
                    if translated_path:
                        all_translated_md.append(translated_path)
                    self.log_updated.emit(f"    ✅ 翻译完成")
                except Exception as e:
                    self.log_updated.emit(f"    ⚠ 翻译失败：{e}")

        # 合并
        self.log_updated.emit(f"  ▶ 合并 {total_ranges} 个范围的输出...")
        merged_result = None

        if len(all_ocr_pdfs) > 1:
            merged_pdf = str(Path(self.output_dir) / f"{base_name}_merged.pdf")
            try:
                ExportEngine.merge_pdfs(all_ocr_pdfs, merged_pdf)
                self.log_updated.emit(f"    ✅ PDF合并完成")
                merged_result = merged_pdf
            except Exception as e:
                self.log_updated.emit(f"    ⚠ PDF合并失败：{e}")
        elif len(all_ocr_pdfs) == 1:
            merged_result = all_ocr_pdfs[0]

        source_md_list = all_translated_md if all_translated_md else all_md_files
        export_format = self.options.get("export_format", "")

        if export_format == "epub" and len(source_md_list) > 1:
            epub_path = str(Path(self.output_dir) / f"{base_name}_merged.epub")
            try:
                ExportEngine.export_multiple_md_to_epub(
                    source_md_list, epub_path, title=base_name,
                )
                self.log_updated.emit(f"    ✅ EPUB合并导出完成")
            except Exception as e:
                self.log_updated.emit(f"    ⚠ EPUB导出失败：{e}")
        elif export_format and source_md_list:
            for md_path in source_md_list:
                try:
                    ExportEngine.export(md_path, export_format)
                except Exception as e:
                    self.log_updated.emit(f"    ⚠ 导出失败：{e}")

        self.progress_stage.emit(int(base_pct + step_pct))
        return merged_result
