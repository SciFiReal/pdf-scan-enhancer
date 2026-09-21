import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ExtractEngine:
    """PDF结构化提取引擎：版面分析 + 输出Markdown"""

    @staticmethod
    def extract_to_markdown(input_pdf: str, output_dir: str) -> str:
        """
        提取PDF为结构化Markdown
        :param input_pdf: 输入PDF路径（建议用OCR增强后的PDF）
        :param output_dir: 输出文件夹
        :return: 生成的md文件路径
        """
        from mineru import parse

        input_path = Path(input_pdf)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在：{input_pdf}")

        logger.info("MinerU 开始解析：%s", input_path.name)

        result = parse(
            path=str(input_path),
            tier="standard",
            ocr_mode="ocr",
            image_analysis=True,
            page_range="",
        )

        md_text = result.markdown()
        md_path = out_dir / f"{input_path.stem}.md"
        md_path.write_text(md_text, encoding="utf-8")

        structured = result.structured_content()
        json_path = out_dir / f"{input_path.stem}_structured.json"
        json_path.write_text(
            json.dumps(structured, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("Markdown 已写入：%s", md_path)
        return str(md_path)
