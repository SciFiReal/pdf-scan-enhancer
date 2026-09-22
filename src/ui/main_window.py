from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QFileDialog, QCheckBox,
    QProgressBar, QTextEdit, QLabel, QGroupBox,
    QComboBox, QGridLayout,
)
from PySide6.QtCore import Qt
from src.workers.task_worker import ProcessWorker
from src.core.translate_engine import LANGUAGES


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Scan Enhancer - 扫描PDF增强工具")
        self.resize(760, 680)
        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. 文件选择区
        file_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择要处理的扫描版PDF...")
        self.btn_browse = QPushButton("选择文件")
        self.btn_browse.clicked.connect(self._choose_file)
        file_layout.addWidget(self.input_edit)
        file_layout.addWidget(self.btn_browse)
        layout.addLayout(file_layout)

        # 2. OCR 处理选项
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

        ocr_layout.addWidget(self.chk_deskew)
        ocr_layout.addWidget(self.chk_clean)
        ocr_layout.addWidget(self.chk_force)
        ocr_layout.addWidget(self.chk_extract)
        layout.addWidget(ocr_group)

        # 3. 翻译选项
        translate_group = QGroupBox("翻译选项")
        translate_layout = QVBoxLayout(translate_group)

        self.chk_translate = QCheckBox("启用翻译")
        self.chk_translate.setChecked(False)
        self.chk_translate.toggled.connect(self._on_translate_toggled)
        translate_layout.addWidget(self.chk_translate)

        # 翻译参数网格
        param_widget = QWidget()
        param_layout = QGridLayout(param_widget)
        param_layout.setContentsMargins(20, 0, 0, 0)

        # 翻译服务商
        param_layout.addWidget(QLabel("翻译引擎："), 0, 0)
        self.combo_provider = QComboBox()
        self.combo_provider.addItems(["百度翻译 API（国内推荐）", "Google 翻译（需代理）"])
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        param_layout.addWidget(self.combo_provider, 0, 1)

        # 原文语言
        param_layout.addWidget(QLabel("原文语言："), 1, 0)
        self.combo_source = QComboBox()
        self.combo_source.addItem("自动检测", "auto")
        for name, code in LANGUAGES.items():
            self.combo_source.addItem(name, code)
        param_layout.addWidget(self.combo_source, 1, 1)

        # 目标语言
        param_layout.addWidget(QLabel("翻译为："), 2, 0)
        self.combo_target = QComboBox()
        for name, code in LANGUAGES.items():
            self.combo_target.addItem(name, code)
        self.combo_target.setCurrentIndex(0)  # 默认中文
        param_layout.addWidget(self.combo_target, 2, 1)

        # 双语对照
        self.chk_bilingual = QCheckBox("生成双语对照（原文+译文）")
        self.chk_bilingual.setChecked(True)
        param_layout.addWidget(self.chk_bilingual, 3, 0, 1, 2)

        translate_layout.addWidget(param_widget)

        # 百度 API 密钥区
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
        self.baidu_widget.setVisible(False)

        layout.addWidget(translate_group)

        # 4. 操作按钮
        self.btn_start = QPushButton("开始处理")
        self.btn_start.setStyleSheet("padding: 8px; font-size: 14px;")
        self.btn_start.clicked.connect(self._start_process)
        layout.addWidget(self.btn_start)

        # 5. 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 6. 日志输出
        layout.addWidget(QLabel("处理日志："))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

    def _choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择PDF文件", "", "PDF文件 (*.pdf)"
        )
        if file_path:
            self.input_edit.setText(file_path)

    def _on_translate_toggled(self, checked):
        self.combo_provider.setEnabled(checked)
        self.combo_source.setEnabled(checked)
        self.combo_target.setEnabled(checked)
        self.chk_bilingual.setEnabled(checked)
        if checked:
            self.baidu_widget.setVisible(self.combo_provider.currentIndex() == 0)
        else:
            self.baidu_widget.setVisible(False)

    def _on_provider_changed(self, index):
        is_baidu = index == 0
        self.baidu_widget.setVisible(is_baidu and self.chk_translate.isChecked())

    def _start_process(self):
        input_path = self.input_edit.text().strip()
        if not input_path:
            self._append_log("请先选择PDF文件")
            return

        options = {
            "deskew": self.chk_deskew.isChecked(),
            "clean": self.chk_clean.isChecked(),
            "force_ocr": self.chk_force.isChecked(),
            "extract_md": self.chk_extract.isChecked(),
            "language": "eng",
            "translate": self.chk_translate.isChecked(),
            "translate_options": {
                "provider": "baidu" if self.combo_provider.currentIndex() == 0 else "google",
                "source": self.combo_source.currentData(),
                "target": self.combo_target.currentData(),
                "bilingual": self.chk_bilingual.isChecked(),
                "baidu_appid": self.edit_baidu_appid.text().strip(),
                "baidu_key": self.edit_baidu_key.text().strip(),
            },
        }

        from pathlib import Path
        output_dir = str(Path(input_path).parent / "output")

        self.btn_start.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_box.clear()

        self.worker = ProcessWorker(input_path, output_dir, options)
        self.worker.log_updated.connect(self._append_log)
        self.worker.progress_stage.connect(self.progress_bar.setValue)
        self.worker.finished_ok.connect(self._on_finish)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _append_log(self, text: str):
        self.log_box.append(text)

    def _on_finish(self, output_path: str):
        self._append_log(f"\n全部处理完成！\n输出文件：{output_path}")
        self.btn_start.setEnabled(True)
        self.progress_bar.setValue(100)

    def _on_error(self, error_msg: str):
        self._append_log(f"\n处理出错：{error_msg}")
        self.btn_start.setEnabled(True)
