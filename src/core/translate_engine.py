import logging
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

BAIDU_QPS = 10
MAX_WORKERS = 4
BATCH_CHAR_LIMIT = 4500


class TranslateEngine:
    """翻译引擎：支持 Google 翻译（需代理）和百度翻译 API（国内推荐）"""

    def __init__(self, provider: str = "google", source: str = "auto",
                 target: str = "zh-CN", baidu_appid: str = "", baidu_key: str = ""):
        self.provider = provider
        self.source = source
        self.target = target
        self.baidu_appid = baidu_appid
        self.baidu_key = baidu_key

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
        else:
            from deep_translator import GoogleTranslator
            src = "auto" if self.source == "auto" else self.source
            return GoogleTranslator(source=src, target=self.target)

    @staticmethod
    def _to_baidu_lang(lang: str) -> str:
        return BAIDU_LANG_MAP.get(lang, lang)

    def _translate_chunk(self, translator, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
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
        for chunk in chunks:
            results.append(self._translate_chunk(translator, chunk))
        return "\n".join(r for r in results if r)

    def translate_markdown(self, md_path: str, output_path: str = "",
                           progress_callback=None) -> str:
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

    def _batch_translate(self, texts: list[str], indices: list[int],
                         total_paragraphs: int, progress_callback=None) -> dict[int, str]:
        if not texts:
            return {}

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
