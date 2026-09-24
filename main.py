import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


def _setup_logging():
    log_dir = Path.home() / ".pdf-scan-enhancer"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    handler = RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)


def main():
    _setup_logging()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
