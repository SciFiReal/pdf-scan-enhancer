import csv
import json
import logging
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

LANGUAGES = {
    "中文": "zh-CN",
    "英语": "en",
    "日语": "ja",
    "韩语": "ko",
    "法语": "fr",
    "德语": "de",
    "西班牙语": "es",
    "俄语": "ru",
}

BAIDU_LANG_MAP = {
    "zh-CN": "zh",
    "en": "en",
    "ja": "jp",
    "ko": "kor",
    "fr": "fra",
    "de": "de",
    "es": "spa",
    "ru": "ru",
    "auto": "auto",
}

OLLAMA_LANG_MAP = {
    "zh-CN": "中文（简体）",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "français",
    "de": "Deutsch",
    "es": "español",
    "ru": "русский",
    "auto": "auto-detected",
}

REQUEST_TIMEOUT = 30
OLLAMA_TIMEOUT = 120

BAIDU_QPS = 10
MAX_WORKERS = 4
BATCH_CHAR_LIMIT = 4500


class GlossaryLoader:
    """术语表加载器：支持 CSV 和 JSON 格式"""

    @staticmethod
    def load(path: str) -> dict[str, str]:
        if not path or not Path(path).exists():
            return {}

        ext = Path(path).suffix.lower()
        if ext == ".json":
            return GlossaryLoader._load_json(path)
        elif ext == ".csv":
            return GlossaryLoader._load_csv(path)
        else:
            logger.warning("不支持的术语表格式：%s，仅支持 .csv 和 .json", ext)
            return {}

    @staticmethod
    def _load_json(path: str) -> dict[str, str]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        logger.warning("术语表 JSON 格式错误，应为 {\"原文\": \"译文\"} 格式")
        return {}

    @staticmethod
    def _load_csv(path: str) -> dict[str, str]:
        result = {}
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                return {}
            for row in reader:
                if len(row) >= 2:
                    result[row[0].strip()] = row[1].strip()
        return result

    @staticmethod
    def format_for_prompt(glossary: dict[str, str]) -> str:
        if not glossary:
            return ""
        lines = ["以下术语表中的词汇请使用指定翻译："]
        for src, tgt in glossary.items():
            lines.append(f"  {src} → {tgt}")
        return "\n".join(lines)

    @staticmethod
    def format_for_text(glossary: dict[str, str]) -> str:
        if not glossary:
            return ""
        lines = ["[术语表]"]
        for src, tgt in glossary.items():
            lines.append(f"{src}={tgt}")
        return "\n".join(lines) + "\n[/术语表]"


def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    """列出 Ollama 本地已下载的模型"""
    try:
        req = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
            return models
    except Exception as e:
        logger.debug("Ollama 连接失败：%s", e)
        return []


class TranslateEngine:
    """翻译引擎：支持 Ollama 本地模型 / 百度翻译 API / Google 翻译"""

    def __init__(self, provider: str = "ollama", source: str = "auto",
                 target: str = "zh-CN", baidu_appid: str = "", baidu_key: str = "",
                 ollama_url: str = "http://localhost:11434", ollama_model: str = "",
                 glossary: dict[str, str] | None = None):
        self.provider = provider
        self.source = source
        self.target = target
        self.baidu_appid = baidu_appid
        self.baidu_key = baidu_key
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.glossary = glossary or {}

    def _get_translator(self):
        if self.provider == "baidu":
            if not self.baidu_appid or not self.baidu_key:
                raise ValueError("百度翻译需要填写 APP ID 和密钥\n"
                                 "请前往 https://fanyi-api.baidu.com/ 免费注册获取")
            from deep_translator import BaiduTranslator
            return BaiduTranslator(
                appid=self.baidu_appid,
                appkey=self.baidu_key,
                source=self._to_baidu_lang(self.source),
                target=self._to_baidu_lang(self.target),
            )
        elif self.provider == "google":
            from deep_translator import GoogleTranslator
            src = "auto" if self.source == "auto" else self.source
            return GoogleTranslator(source=src, target=self.target)
        else:
            if not self.ollama_model:
                raise ValueError("Ollama 翻译需要选择本地模型\n"
                                 "请先安装 Ollama 并下载模型（如 qwen2.5）")
            return None

    @staticmethod
    def _to_baidu_lang(lang: str) -> str:
        return BAIDU_LANG_MAP.get(lang, lang)

    def _build_ollama_prompt(self, text: str) -> str:
        target_name = OLLAMA_LANG_MAP.get(self.target, self.target)

        if self.source != "auto":
            source_name = OLLAMA_LANG_MAP.get(self.source, "auto-detected")
            instruction = f"将以下{source_name}文本翻译为{target_name}，只输出译文，不要解释。"
        else:
            instruction = f"将以下文本翻译为{target_name}，只输出译文，不要解释。"

        parts = [instruction]

        if self.glossary:
            parts.append(GlossaryLoader.format_for_prompt(self.glossary))

        parts.append(f"\n{text}")
        return "\n".join(parts)

    def _translate_ollama(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        prompt = self._build_ollama_prompt(text)
        payload = json.dumps({
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "").strip()
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Ollama 连接失败（{self.ollama_url}），请确认 Ollama 正在运行\n{e}"
            )
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                raise TimeoutError(f"Ollama 翻译超时（{OLLAMA_TIMEOUT}秒），模型可能负载过高")
            raise

    def _translate_chunk(self, translator, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        if translator is None:
            return self._translate_ollama(text)

        if self.glossary and self.provider in ("baidu", "google"):
            text = GlossaryLoader.format_for_text(self.glossary) + "\n" + text

        try:
            return translator.translate(text) or ""
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                raise TimeoutError("翻译请求超时，请检查网络连接")
            if self.provider == "google" and "connection" in error_msg.lower():
                raise ConnectionError("Google 翻译连接失败，国内用户请使用百度翻译或开启代理")
            raise

    def translate_text(self, text: str) -> str:
        translator = self._get_translator()
        chunks = _split_for_api(text, BATCH_CHAR_LIMIT)
        results = []
        for i, chunk in enumerate(chunks):
            result = self._translate_chunk(translator, chunk)
            if not result:
                logger.warning("翻译返回空结果（第 %d 段），保留原文", i + 1)
                results.append(chunk)
            else:
                results.append(result)
        return "\n".join(results)

    def translate_markdown(self, md_path: str, output_path: str = "",
                           progress_callback=None) -> str:
        """生成纯译文 Markdown"""
        md_file = Path(md_path)
        if not md_file.exists():
            raise FileNotFoundError(f"Markdown 文件不存在：{md_path}")

        content = md_file.read_text(encoding="utf-8")
        paragraphs = content.split("\n\n")

        translatable = []
        skip_indices = set()
        for i, para in enumerate(paragraphs):
            stripped = para.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-") or stripped.startswith("|"):
                skip_indices.add(i)
            else:
                translatable.append((i, stripped))

        translated_map = self._batch_translate(
            [t for _, t in translatable],
            indices=[i for i, _ in translatable],
            total_paragraphs=len(paragraphs),
            progress_callback=progress_callback,
        )

        result_parts = []
        for i, para in enumerate(paragraphs):
            if i in skip_indices:
                result_parts.append(para)
            else:
                result_parts.append(translated_map.get(i, para))

        translated_md = "\n\n".join(result_parts)

        if not output_path:
            output_path = str(md_file.parent / f"{md_file.stem}_translated.md")

        Path(output_path).write_text(translated_md, encoding="utf-8")
        logger.info("翻译完成，写入：%s", output_path)
        return output_path

    def translate_markdown_bilingual(self, md_path: str, output_path: str = "",
                                     progress_callback=None) -> str:
        """生成双语对照 Markdown（原文+译文交替）"""
        md_file = Path(md_path)
        if not md_file.exists():
            raise FileNotFoundError(f"Markdown 文件不存在：{md_path}")

        content = md_file.read_text(encoding="utf-8")
        paragraphs = content.split("\n\n")

        translatable = []
        skip_indices = set()
        heading_indices = set()
        for i, para in enumerate(paragraphs):
            stripped = para.strip()
            if not stripped:
                skip_indices.add(i)
            elif stripped.startswith("#"):
                heading_indices.add(i)
                translatable.append((i, stripped.lstrip("#").strip()))
            elif stripped.startswith("-") or stripped.startswith("|"):
                skip_indices.add(i)
            else:
                translatable.append((i, stripped))

        translated_map = self._batch_translate(
            [t for _, t in translatable],
            indices=[i for i, _ in translatable],
            total_paragraphs=len(paragraphs),
            progress_callback=progress_callback,
        )

        bilingual_parts = []
        for i, para in enumerate(paragraphs):
            if i in skip_indices:
                bilingual_parts.append(para)
            elif i in heading_indices:
                translated = translated_map.get(i, "")
                bilingual_parts.append(f"{para}\n\n*{translated}*")
            else:
                translated = translated_map.get(i, "")
                bilingual_parts.append(f"{para}\n\n---\n\n*{translated}*")

        bilingual_md = "\n\n".join(bilingual_parts)

        if not output_path:
            output_path = str(md_file.parent / f"{md_file.stem}_bilingual.md")

        Path(output_path).write_text(bilingual_md, encoding="utf-8")
        logger.info("双语对照完成，写入：%s", output_path)
        return output_path

    def translate_markdown_both(self, md_path: str, output_dir: str = "",
                                progress_callback=None) -> tuple[str, str]:
        """同时生成纯译文和双语对照两个文件
        
        Returns:
            (translated_path, bilingual_path) 元组
        """
        md_file = Path(md_path)
        if not md_file.exists():
            raise FileNotFoundError(f"Markdown 文件不存在：{md_path}")

        content = md_file.read_text(encoding="utf-8")
        paragraphs = content.split("\n\n")

        # 识别可翻译段落
        translatable = []
        skip_indices = set()
        heading_indices = set()
        for i, para in enumerate(paragraphs):
            stripped = para.strip()
            if not stripped:
                skip_indices.add(i)
            elif stripped.startswith("#"):
                heading_indices.add(i)
                translatable.append((i, stripped.lstrip("#").strip()))
            elif stripped.startswith("-") or stripped.startswith("|"):
                skip_indices.add(i)
            else:
                translatable.append((i, stripped))

        # 一次性翻译所有段落
        translated_map = self._batch_translate(
            [t for _, t in translatable],
            indices=[i for i, _ in translatable],
            total_paragraphs=len(paragraphs),
            progress_callback=progress_callback,
        )

        # 生成纯译文文件
        pure_parts = []
        for i, para in enumerate(paragraphs):
            if i in skip_indices:
                pure_parts.append(para)
            else:
                pure_parts.append(translated_map.get(i, para))
        translated_md = "\n\n".join(pure_parts)

        if not output_dir:
            output_dir = str(md_file.parent)
        
        translated_path = str(Path(output_dir) / f"{md_file.stem}_translated.md")
        Path(translated_path).write_text(translated_md, encoding="utf-8")
        logger.info("纯译文完成，写入：%s", translated_path)

        # 生成双语对照文件
        bilingual_parts = []
        for i, para in enumerate(paragraphs):
            if i in skip_indices:
                bilingual_parts.append(para)
            elif i in heading_indices:
                translated = translated_map.get(i, "")
                bilingual_parts.append(f"{para}\n\n*{translated}*")
            else:
                translated = translated_map.get(i, "")
                bilingual_parts.append(f"{para}\n\n---\n\n*{translated}*")
        bilingual_md = "\n\n".join(bilingual_parts)

        bilingual_path = str(Path(output_dir) / f"{md_file.stem}_bilingual.md")
        Path(bilingual_path).write_text(bilingual_md, encoding="utf-8")
        logger.info("双语对照完成，写入：%s", bilingual_path)

        return translated_path, bilingual_path

    def _batch_translate(self, texts: list[str], indices: list[int],
                         total_paragraphs: int, progress_callback=None) -> dict[int, str]:
        if not texts:
            return {}

        if self.provider == "ollama":
            return self._batch_translate_ollama(
                texts, indices, total_paragraphs, progress_callback,
            )

        batches = _build_batches(texts, indices, BATCH_CHAR_LIMIT)
        result_map = {}
        completed = 0

        def _translate_batch(batch_texts, batch_indices):
            translator = self._get_translator()
            batch_results = []
            for text in batch_texts:
                result = self._translate_chunk(translator, text)
                batch_results.append(result)
            return list(zip(batch_indices, batch_results))

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            for batch_texts, batch_indices in batches:
                future = executor.submit(_translate_batch, batch_texts, batch_indices)
                futures[future] = len(batch_texts)

            for future in as_completed(futures):
                batch_size = futures[future]
                try:
                    results = future.result()
                    for idx, translated in results:
                        result_map[idx] = translated
                except Exception as e:
                    logger.error("批量翻译出错：%s", e)

                completed += batch_size
                if progress_callback:
                    pct = int(completed / len(texts) * 100)
                    progress_callback(completed, len(texts), pct)

        return result_map

    def _batch_translate_ollama(self, texts: list[str], indices: list[int],
                                total_paragraphs: int,
                                progress_callback=None) -> dict[int, str]:
        """Ollama 专用批量翻译，并发数较低避免模型过载"""
        result_map = {}
        completed = 0
        max_workers = 2

        def _translate_one(idx, text):
            return idx, self._translate_ollama(text)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, text in zip(indices, texts):
                future = executor.submit(_translate_one, idx, text)
                futures[future] = idx

            for future in as_completed(futures):
                try:
                    idx, translated = future.result()
                    result_map[idx] = translated
                except Exception as e:
                    logger.error("Ollama 翻译出错（段落 %d）：%s", futures[future], e)

                completed += 1
                if progress_callback:
                    pct = int(completed / len(texts) * 100)
                    progress_callback(completed, len(texts), pct)

        return result_map


def _build_batches(texts: list[str], indices: list[int],
                   max_chars: int) -> list[tuple[list[str], list[int]]]:
    batches = []
    current_texts = []
    current_indices = []
    current_len = 0

    for text, idx in zip(texts, indices):
        text_len = len(text)

        if text_len > max_chars:
            if current_texts:
                batches.append((current_texts, current_indices))
                current_texts = []
                current_indices = []
                current_len = 0
            batches.append(([text], [idx]))
            continue

        if current_len + text_len > max_chars and current_texts:
            batches.append((current_texts, current_indices))
            current_texts = []
            current_indices = []
            current_len = 0

        current_texts.append(text)
        current_indices.append(idx)
        current_len += text_len

    if current_texts:
        batches.append((current_texts, current_indices))

    return batches


def _split_for_api(text: str, max_len: int = 4500) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = text.rfind(". ", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at + 1])
        text = text[split_at + 1:]
    return chunks
