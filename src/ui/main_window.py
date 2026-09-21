from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QFileDialog, QCheckBox,
    QProgressBar, QTextEdit, QLabel, QGroupBox
)
from PySide6.QtCore import Qt
from src.workers.task_worker import ProcessWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Scan Enhancer - 扫描PDF增强工具")
        self.resize(720, 520)
        self.worker = None

        # 中心控件
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
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

        # 2. 参数选项区
        option_group = QGroupBox("处理选项")
        option_layout = QVBoxLayout(option_group)
        
        self.chk_deskew = QCheckBox("自动纠偏（摆正歪斜页面）")
        self.chk_deskew.setChecked(True)
        self.chk_clean = QCheckBox("图像去噪（清理污渍底色）")
        self.chk_clean.setChecked(True)
        self.chk_force = QCheckBox("强制重OCR（覆盖原有文字层）")
        self.chk_force.setChecked(True)
        self.chk_extract = QCheckBox("提取结构化Markdown文本")
        self.chk_extract.setChecked(True)
        
        option_layout.addWidget(self.chk_deskew)
        option_layout.addWidget(self.chk_clean)
        option_layout.addWidget(self.chk_force)
        option_layout.addWidget(self.chk_extract)
        layout.addWidget(option_group)

        # 3. 操作按钮
        self.btn_start = QPushButton("开始处理")
        self.btn_start.setStyleSheet("padding: 8px; font-size: 14px;")
        self.btn_start.clicked.connect(self._start_process)
        layout.addWidget(self.btn_start)

        # 4. 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 5. 日志输出
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

    def _start_process(self):
        input_path = self.input_edit.text().strip()
        if not input_path:
            self._append_log("❌ 请先选择PDF文件")
            return

        # 收集参数
        options = {
            "deskew": self.chk_deskew.isChecked(),
            "clean": self.chk_clean.isChecked(),
            "force_ocr": self.chk_force.isChecked(),
            "extract_md": self.chk_extract.isChecked(),
            "language": "eng"
        }

        # 输出目录 = 输入文件同目录下的output文件夹
        from pathlib import Path
        output_dir = str(Path(input_path).parent / "output")

        # 禁用按钮，启动线程
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
        self._append_log(f"\n🎉 全部处理完成！\n输出文件：{output_path}")
        self.btn_start.setEnabled(True)
        self.progress_bar.setValue(100)

    def _on_error(self, error_msg: str):
        self._append_log(f"\n❌ 处理出错：{error_msg}")
        self.btn_start.setEnabled(True)
