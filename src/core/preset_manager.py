import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".pdf-scan-enhancer"
PRESETS_FILE = CONFIG_DIR / "presets.json"

DEFAULT_PRESETS = {
    "英文论文（百度翻译）": {
        "deskew": True,
        "clean": True,
        "force_ocr": True,
        "extract_md": True,
        "translate": True,
        "translate_options": {
            "provider": "baidu",
            "source": "en",
            "target": "zh-CN",
            "bilingual": True,
        },
        "export_format": "docx",
    },
    "Ollama 离线翻译": {
        "deskew": True,
        "clean": True,
        "force_ocr": True,
        "extract_md": True,
        "translate": True,
        "translate_options": {
            "provider": "ollama",
            "source": "auto",
            "target": "zh-CN",
            "bilingual": True,
        },
        "export_format": "docx",
    },
    "快速提取（不翻译）": {
        "deskew": True,
        "clean": True,
        "force_ocr": True,
        "extract_md": True,
        "translate": False,
        "translate_options": {},
        "export_format": "",
    },
}


class PresetManager:
    """配置预设管理器：保存/加载/删除常用参数组合"""

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.presets = self._load()

    def _load(self) -> dict:
        if PRESETS_FILE.exists():
            try:
                data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.warning("预设文件读取失败：%s", e)
        return dict(DEFAULT_PRESETS)

    def save_to_disk(self):
        try:
            PRESETS_FILE.write_text(
                json.dumps(self.presets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("预设保存失败：%s", e)

    def list_names(self) -> list[str]:
        return list(self.presets.keys())

    def get(self, name: str) -> dict | None:
        return self.presets.get(name)

    def add(self, name: str, options: dict):
        self.presets[name] = options
        self.save_to_disk()
        logger.info("预设已保存：%s", name)

    def remove(self, name: str):
        if name in self.presets:
            del self.presets[name]
            self.save_to_disk()
            logger.info("预设已删除：%s", name)

    def reset_defaults(self):
        self.presets = dict(DEFAULT_PRESETS)
        self.save_to_disk()
