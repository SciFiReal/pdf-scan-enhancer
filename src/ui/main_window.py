from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QFileDialog, QCheckBox,
    QProgressBar, QTextEdit, QLabel, QGroupBox,
    QComboBox, QGridLayout, QListWidget, QInputDialog,
    QMessageBox, QDialog, QDialogButtonBox, QTabWidget,
)
from PySide6.QtCore import Qt, QThread, Signal
from src.workers.task_worker import ProcessWorker
from src.workers.batch_worker import BatchWorker
from src.core.translate_engine import LANGUAGES, list_ollama_models, GlossaryLoader
from src.core.export_engine import SUPPORTED_FORMATS
from src.core.preset_manager import PresetManager


PROVIDER_MAP = {0: "ollama", 1: "baidu", 2: "google"}


class _ModelListWorker(QThread):
    models_loaded = Signal(list)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        models = list_ollama_models(self.url)
        self.models_loaded.emit(models)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Scan Enhancer - 扫描PDF增强工具 v0.5")
        self.resize(800, 860)
        self.worker = None
        self._model_worker = None
        self.preset_mgr = PresetManager()
        self.last_output_dir = ""

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # 1. 文件选择区
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)

        btn_row = QHBoxLayout()
        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_files.clicked.connect(self._add_files)
        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_clear_files = QPushButton("清空")
        self.btn_clear_files.clicked.connect(self._clear_files)
        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_add_folder)
        btn_row.addWidget(self.btn_clear_files)
        file_layout.addLayout(btn_row)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(80)
        file_layout.addWidget(self.file_list)

        self.file_count_label = QLabel("已选择 0 个文件")
        file_layout.addWidget(self.file_count_label)

        layout.addWidget(file_group)

        # 2. 预设
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("配置预设："))
        self.combo_preset = QComboBox()
        self.combo_preset.setMinimumWidth(200)
        self.combo_preset.addItem("（不使用预设）")
        for name in self.preset_mgr.list_names():
            self.combo_preset.addItem(name)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.combo_preset)

        self.btn_save_preset = QPushButton("保存为预设")
        self.btn_save_preset.setFixedWidth(90)
        self.btn_save_preset.clicked.connect(self._save_preset)
        preset_row.addWidget(self.btn_save_preset)

        self.btn_delete_preset = QPushButton("删除")
        self.btn_delete_preset.setFixedWidth(50)
        self.btn_delete_preset.clicked.connect(self._delete_preset)
        preset_row.addWidget(self.btn_delete_preset)
        layout.addLayout(preset_row)

        # 3. OCR 处理选项
        ocr_group = QGroupBox("OCR 处理选项")
        ocr_layout = QVBoxLayout(ocr_group)

        self.chk_deskew = QCheckBox("自动纠偏（摆正歪斜页面）")
        self.chk_deskew.setChecked(True)
        self.chk_clean = QCheckBox("图像去噪（清理污渍底色）")
        self.chk_clean.setChecked(True)
        self.chk_force = QCheckBox("强制重OCR（覆盖原有文字层）")
        self.chk_force.setChecked(True)
        self.chk_extract = QCheckBox("提取结构化Markdown文本")
        self.chk_extract.setChecked(True)

        ocr_lang_row = QHBoxLayout()
        ocr_lang_row.addWidget(QLabel("OCR 识别语言："))
        self.combo_ocr_lang = QComboBox()
        self.combo_ocr_lang.addItem("英文", "eng")
        self.combo_ocr_lang.addItem("简体中文 + 英文", "chi_sim+eng")
        self.combo_ocr_lang.addItem("繁体中文 + 英文", "chi_tra+eng")
        self.combo_ocr_lang.addItem("日文 + 英文", "jpn+eng")
        self.combo_ocr_lang.addItem("韩文 + 英文", "kor+eng")
        ocr_lang_row.addWidget(self.combo_ocr_lang)
        ocr_lang_row.addStretch()

        pages_row = QHBoxLayout()
        pages_row.addWidget(QLabel("页码范围："))
        self.edit_pages = QLineEdit()
        self.edit_pages.setPlaceholderText("如：1-50,51-100,101-250（多段自动合并，留空=全部）")
        self.edit_pages.setMaximumWidth(250)
        pages_row.addWidget(self.edit_pages)
        pages_row.addStretch()

        ocr_layout.addWidget(self.chk_deskew)
        ocr_layout.addWidget(self.chk_clean)
        ocr_layout.addWidget(self.chk_force)
        ocr_layout.addWidget(self.chk_extract)
        ocr_layout.addLayout(ocr_lang_row)
        ocr_layout.addLayout(pages_row)
        layout.addWidget(ocr_group)

        # 4. 翻译选项
        translate_group = QGroupBox("翻译选项")
        translate_layout = QVBoxLayout(translate_group)

        self.chk_translate = QCheckBox("启用翻译")
        self.chk_translate.setChecked(False)
        self.chk_translate.toggled.connect(self._on_translate_toggled)
        translate_layout.addWidget(self.chk_translate)

        param_widget = QWidget()
        param_layout = QGridLayout(param_widget)
        param_layout.setContentsMargins(20, 0, 0, 0)

        param_layout.addWidget(QLabel("翻译引擎："), 0, 0)
        self.combo_provider = QComboBox()
        self.combo_provider.addItems([
            "Ollama 本地模型（离线免费）",
            "百度翻译 API（国内推荐）",
            "Google 翻译（需代理）",
        ])
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        param_layout.addWidget(self.combo_provider, 0, 1)

        param_layout.addWidget(QLabel("原文语言："), 1, 0)
        self.combo_source = QComboBox()
        self.combo_source.addItem("自动检测", "auto")
        for name, code in LANGUAGES.items():
            self.combo_source.addItem(name, code)
        param_layout.addWidget(self.combo_source, 1, 1)

        param_layout.addWidget(QLabel("翻译为："), 2, 0)
        self.combo_target = QComboBox()
        for name, code in LANGUAGES.items():
            self.combo_target.addItem(name, code)
        self.combo_target.setCurrentIndex(0)
        param_layout.addWidget(self.combo_target, 2, 1)

        translate_layout.addWidget(param_widget)

        self.ollama_widget = QWidget()
        ollama_layout = QGridLayout(self.ollama_widget)
        ollama_layout.setContentsMargins(20, 0, 0, 0)

        ollama_layout.addWidget(QLabel("模型："), 0, 0)
        ollama_model_row = QHBoxLayout()
        self.combo_ollama_model = QComboBox()
        self.combo_ollama_model.setMinimumWidth(200)
        ollama_model_row.addWidget(self.combo_ollama_model)
        self.btn_refresh_models = QPushButton("刷新")
        self.btn_refresh_models.setFixedWidth(60)
        self.btn_refresh_models.clicked.connect(self._refresh_ollama_models)
        ollama_model_row.addWidget(self.btn_refresh_models)
        ollama_layout.addLayout(ollama_model_row, 0, 1)

        ollama_layout.addWidget(QLabel("服务地址："), 1, 0)
        self.edit_ollama_url = QLineEdit("http://localhost:11434")
        ollama_layout.addWidget(self.edit_ollama_url, 1, 1)

        translate_layout.addWidget(self.ollama_widget)

        self.baidu_widget = QWidget()
        baidu_layout = QGridLayout(self.baidu_widget)
        baidu_layout.setContentsMargins(20, 0, 0, 0)

        baidu_layout.addWidget(QLabel("APP ID："), 0, 0)
        self.edit_baidu_appid = QLineEdit()
        self.edit_baidu_appid.setPlaceholderText("百度翻译开放平台获取")
        baidu_layout.addWidget(self.edit_baidu_appid, 0, 1)

        baidu_layout.addWidget(QLabel("密钥："), 1, 0)
        self.edit_baidu_key = QLineEdit()
        self.edit_baidu_key.setPlaceholderText("百度翻译开放平台获取")
        self.edit_baidu_key.setEchoMode(QLineEdit.EchoMode.Password)
        baidu_layout.addWidget(self.edit_baidu_key, 1, 1)

        translate_layout.addWidget(self.baidu_widget)

        glossary_row = QHBoxLayout()
        glossary_row.setContentsMargins(20, 0, 0, 0)
        glossary_row.addWidget(QLabel("术语表："))
        self.edit_glossary = QLineEdit()
        self.edit_glossary.setPlaceholderText("可选，加载 CSV/JSON 术语表")
        glossary_row.addWidget(self.edit_glossary)
        self.btn_glossary = QPushButton("选择")
        self.btn_glossary.setFixedWidth(60)
        self.btn_glossary.clicked.connect(self._choose_glossary)
        glossary_row.addWidget(self.btn_glossary)
        translate_layout.addLayout(glossary_row)

        self.ollama_widget.setVisible(False)
        self.baidu_widget.setVisible(False)

        layout.addWidget(translate_group)

        # 5. 导出选项
        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("导出格式："))
        self.combo_export = QComboBox()
        self.combo_export.addItem("不导出（仅 Markdown）", "")
        for fmt, desc in SUPPORTED_FORMATS.items():
            self.combo_export.addItem(desc, fmt)
        export_row.addWidget(self.combo_export)
        layout.addLayout(export_row)

        # 6. 操作按钮
        action_row = QHBoxLayout()
        self.btn_start = QPushButton("开始处理")
        self.btn_start.setStyleSheet("padding: 8px; font-size: 14px;")
        self.btn_start.clicked.connect(self._start_process)
        action_row.addWidget(self.btn_start)

        self.btn_preview = QPushButton("预览结果")
        self.btn_preview.setStyleSheet("padding: 8px; font-size: 14px;")
        self.btn_preview.setEnabled(False)
        self.btn_preview.clicked.connect(self._show_preview)
        action_row.addWidget(self.btn_preview)
        layout.addLayout(action_row)

        # 7. 进度条
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.lbl_stage = QLabel("")
        self.lbl_stage.setStyleSheet("color: #666; padding-left: 8px;")
        progress_row.addWidget(self.progress_bar)
        progress_row.addWidget(self.lbl_stage)
        layout.addLayout(progress_row)

        # 8. 日志输出
        layout.addWidget(QLabel("处理日志："))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        self._refresh_ollama_models()

    # ── 文件管理 ──

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择PDF文件", "", "PDF文件 (*.pdf)"
        )
        for f in files:
            if self.file_list.findItems(f, Qt.MatchFlag.MatchExactly):
                continue
            self.file_list.addItem(f)
        self._update_file_count()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            count = 0
            for pdf in Path(folder).glob("*.pdf"):
                path_str = str(pdf)
                if not self.file_list.findItems(path_str, Qt.MatchFlag.MatchExactly):
                    self.file_list.addItem(path_str)
                    count += 1
            self._append_log(f"从文件夹添加 {count} 个PDF")
        self._update_file_count()

    def _clear_files(self):
        self.file_list.clear()
        self._update_file_count()

    def _update_file_count(self):
        count = self.file_list.count()
        self.file_count_label.setText(f"已选择 {count} 个文件")

    def _get_file_list(self) -> list[str]:
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]

    # ── 预设 ──

    def _on_preset_changed(self, index):
        if index <= 0:
            return
        name = self.combo_preset.currentText()
        preset = self.preset_mgr.get(name)
        if not preset:
            return

        self.chk_deskew.setChecked(preset.get("deskew", True))
        self.chk_clean.setChecked(preset.get("clean", True))
        self.chk_force.setChecked(preset.get("force_ocr", True))
        self.chk_extract.setChecked(preset.get("extract_md", True))
        self.chk_translate.setChecked(preset.get("translate", False))

        lang = preset.get("language", "eng")
        for i in range(self.combo_ocr_lang.count()):
            if self.combo_ocr_lang.itemData(i) == lang:
                self.combo_ocr_lang.setCurrentIndex(i)
                break

        self.edit_pages.setText(preset.get("pages", ""))

        t_opts = preset.get("translate_options", {})
        provider = t_opts.get("provider", "ollama")
        provider_idx = {"ollama": 0, "baidu": 1, "google": 2}.get(provider, 0)
        self.combo_provider.setCurrentIndex(provider_idx)

        source = t_opts.get("source", "auto")
        for i in range(self.combo_source.count()):
            if self.combo_source.itemData(i) == source:
                self.combo_source.setCurrentIndex(i)
                break

        target = t_opts.get("target", "zh-CN")
        for i in range(self.combo_target.count()):
            if self.combo_target.itemData(i) == target:
                self.combo_target.setCurrentIndex(i)
                break

        export_fmt = preset.get("export_format", "")
        for i in range(self.combo_export.count()):
            if self.combo_export.itemData(i) == export_fmt:
                self.combo_export.setCurrentIndex(i)
                break

        self._append_log(f"已加载预设：{name}")

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "保存预设", "预设名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        options = self._collect_options()
        self.preset_mgr.add(name, options)
        self.combo_preset.addItem(name)
        self._append_log(f"预设已保存：{name}")

    def _delete_preset(self):
        idx = self.combo_preset.currentIndex()
        if idx <= 0:
            return
        name = self.combo_preset.currentText()
        reply = QMessageBox.question(
            self, "删除预设", f"确定删除预设「{name}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.preset_mgr.remove(name)
            self.combo_preset.removeItem(idx)
            self._append_log(f"预设已删除：{name}")

    # ── 翻译/引擎切换 ──

    def _choose_glossary(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择术语表文件", "", "术语表 (*.csv *.json)"
        )
        if file_path:
            self.edit_glossary.setText(file_path)

    def _refresh_ollama_models(self):
        url = self.edit_ollama_url.text().strip() or "http://localhost:11434"
        self.combo_ollama_model.clear()
        self.combo_ollama_model.addItem("加载中...")
        self.btn_refresh_models.setEnabled(False)

        self._model_worker = _ModelListWorker(url)
        self._model_worker.models_loaded.connect(self._on_models_loaded)
        self._model_worker.finished.connect(
            lambda: self.btn_refresh_models.setEnabled(True)
        )
        self._model_worker.start()

    def _on_models_loaded(self, models: list):
        self.combo_ollama_model.clear()
        if models:
            self.combo_ollama_model.addItems(models)
        else:
            self.combo_ollama_model.addItem("（未检测到模型）")

    def _on_translate_toggled(self, checked):
        self.combo_provider.setEnabled(checked)
        self.combo_source.setEnabled(checked)
        self.combo_target.setEnabled(checked)
        self.btn_glossary.setEnabled(checked)
        self.edit_glossary.setEnabled(checked)
        if checked:
            self._on_provider_changed(self.combo_provider.currentIndex())
        else:
            self.ollama_widget.setVisible(False)
            self.baidu_widget.setVisible(False)

    def _on_provider_changed(self, index):
        is_translate_on = self.chk_translate.isChecked()
        provider = PROVIDER_MAP.get(index, "ollama")
        self.ollama_widget.setVisible(provider == "ollama" and is_translate_on)
        self.baidu_widget.setVisible(provider == "baidu" and is_translate_on)

    # ── 收集参数 ──

    def _collect_options(self) -> dict:
        provider = PROVIDER_MAP.get(self.combo_provider.currentIndex(), "ollama")

        glossary = {}
        glossary_path = self.edit_glossary.text().strip()
        if glossary_path:
            glossary = GlossaryLoader.load(glossary_path)

        return {
            "deskew": self.chk_deskew.isChecked(),
            "clean": self.chk_clean.isChecked(),
            "force_ocr": self.chk_force.isChecked(),
            "extract_md": self.chk_extract.isChecked(),
            "language": self.combo_ocr_lang.currentData(),
            "pages": self.edit_pages.text().strip(),
            "translate": self.chk_translate.isChecked(),
            "translate_options": {
                "provider": provider,
                "source": self.combo_source.currentData(),
                "target": self.combo_target.currentData(),
                "baidu_appid": self.edit_baidu_appid.text().strip(),
                "baidu_key": self.edit_baidu_key.text().strip(),
                "ollama_url": self.edit_ollama_url.text().strip(),
                "ollama_model": self.combo_ollama_model.currentText().strip(),
                "glossary": glossary,
            },
            "export_format": self.combo_export.currentData() or "",
        }

    # ── 处理 ──

    def _start_process(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            return

        files = self._get_file_list()
        if not files:
            self._append_log("请先添加PDF文件")
            return

        options = self._collect_options()

        if options["translate_options"].get("glossary"):
            self._append_log(f"已加载术语表：{len(options['translate_options']['glossary'])} 条术语")

        self.btn_start.setText("取消")
        self.btn_preview.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_stage.setText("")
        self.log_box.clear()

        if len(files) == 1:
            input_path = files[0]
            output_dir = str(Path(input_path).parent / "output")
            self.last_output_dir = output_dir

            self.worker = ProcessWorker(input_path, output_dir, options)
            self.worker.log_updated.connect(self._append_log)
            self.worker.progress_stage.connect(self.progress_bar.setValue)
            self.worker.stage_updated.connect(self._on_stage_updated)
            self.worker.finished_ok.connect(self._on_finish_single)
            self.worker.error_occurred.connect(self._on_error)
            self.worker.start()
        else:
            first_file = files[0]
            output_dir = str(Path(first_file).parent / "output")
            self.last_output_dir = output_dir

            self.worker = BatchWorker(files, output_dir, options)
            self.worker.log_updated.connect(self._append_log)
            self.worker.progress_stage.connect(self.progress_bar.setValue)
            self.worker.stage_updated.connect(self._on_stage_updated)
            self.worker.finished_ok.connect(self._on_finish_batch)
            self.worker.error_occurred.connect(self._on_error)
            self.worker.start()

    def _append_log(self, text: str):
        self.log_box.append(text)

    def _on_stage_updated(self, text: str):
        self.lbl_stage.setText(text)

    def _on_finish_single(self, output_path: str):
        self._append_log(f"\n全部处理完成！\n输出文件：{output_path}")
        self.btn_start.setText("开始处理")
        self.btn_preview.setEnabled(True)
        self.progress_bar.setValue(100)

    def _on_finish_batch(self, results: list):
        self.btn_start.setText("开始处理")
        self.btn_preview.setEnabled(len(results) > 0)
        self.progress_bar.setValue(100)

    def _on_error(self, error_msg: str):
        self._append_log(f"\n处理出错：{error_msg}")
        self.btn_start.setText("开始处理")
        QMessageBox.critical(self, "处理出错", error_msg)

    # ── 预览 ──

    def _show_preview(self):
        output_dir = Path(self.last_output_dir)
        if not output_dir.exists():
            self._append_log("没有找到输出目录")
            return

        md_files = list(output_dir.rglob("*.md"))
        if not md_files:
            self._append_log("没有找到 Markdown 输出文件")
            return

        if len(md_files) == 1:
            self._preview_file(str(md_files[0]))
            return

        names = [f.name for f in md_files]
        name, ok = QInputDialog.getItem(
            self, "选择预览文件", "选择要预览的文件：", names, 0, False,
        )
        if ok and name:
            for f in md_files:
                if f.name == name:
                    self._preview_file(str(f))
                    break

    def _preview_file(self, path: str):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"预览 - {Path(path).name}")
        dialog.resize(700, 500)

        dlg_layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        content = Path(path).read_text(encoding="utf-8")
        text_edit.setPlainText(content)
        dlg_layout.addWidget(text_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dialog.reject)
        dlg_layout.addWidget(btn_box)

        dialog.exec()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "确认退出",
                "正在处理中，确定要退出吗？\n退出后当前任务将被中断。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(3000)
        event.accept()
