import logging
import os
import subprocess
from pathlib import Path

import ocrmypdf

logger = logging.getLogger(__name__)

_SEARCH_DIRS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    Path(r"D:\Downloads"),
    Path(r"C:\Downloads"),
    Path.home() / "Downloads",
    Path(r"D:\"),
    Path(r"E:\"),
]


def _ensure_deps_on_path() -> None:
    """自动搜索 Tesseract / Ghostscript / unpaper 并加入 PATH"""
    extra = []
    targets = {"tesseract.exe", "gswin64c.exe", "unpaper.exe"}

    for base in _SEARCH_DIRS:
        if not base.exists():
            continue
        for target in targets:
            for p in base.rglob(target):
                extra.append(str(p.parent))
                break

    if extra:
        current = os.environ.get("PATH", "")
        for d in set(extra):
            if d not in current:
                os.environ["PATH"] = d + os.pathsep + current
                logger.debug("已加入 PATH: %s", d)


def _find_bin(name: str) -> str | None:
    """在 _SEARCH_DIRS 和 PATH 中查找可执行文件，返回完整路径"""
    exe = name if name.endswith(".exe") else f"{name}.exe"
    for base in _SEARCH_DIRS:
        candidate = base / "Tesseract-OCR" / exe
        if candidate.exists():
            return str(candidate)
    for dir_entry in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(dir_entry) / exe
        if candidate.exists():
            return str(candidate)
    return None


def _find_tesseract_bin() -> str | None:
    return _find_bin("tesseract")


def _find_tessdata_dir() -> str | None:
    """定位 Tesseract 的 tessdata 目录"""
    env = os.environ.get("TESSDATA_PREFIX")
    if env and Path(env).is_dir():
        return env

    tesseract = _find_tesseract_bin()
    if tesseract:
        candidate = Path(tesseract).parent / "tessdata"
        if candidate.is_dir():
            return str(candidate)

        try:
            result = subprocess.run(
                [tesseract, "--print-parameters"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stderr.splitlines():
                if "tessdata" in line.lower():
                    p = Path(line.strip().split()[-1])
                    if p.is_dir():
                        return str(p)
        except Exception:
            pass

    for base in _SEARCH_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("tessdata"):
            if p.is_dir() and (p / "osd.traineddata").exists():
                return str(p)

    return None


class OCREngine:
    """扫描PDF增强引擎：纠偏、去噪、重建OCR文字层，输出双层可检索PDF"""

    @staticmethod
    def process(
        input_path: str,
        output_path: str,
        language: str = "eng",
        deskew: bool = True,
        clean: bool = True,
        force_ocr: bool = True,
        rotate_pages: bool = True,
    ) -> bool:
        """
        处理PDF：图像增强 + OCR层重建
        :param input_path: 输入PDF路径
        :param output_path: 输出PDF路径
        :param language: OCR语言 (eng / chi_sim+eng)
        :param deskew: 页面纠偏
        :param clean: 清理污渍噪点（需要unpaper）
        :param force_ocr: 强制重OCR（覆盖原有文字层）
        :param rotate_pages: 自动旋转页面方向（需要osd.traineddata）
        :return: 成功返回True，失败返回False
        """
        try:
            _ensure_deps_on_path()

            input_file = Path(input_path)
            output_file = Path(output_path)

            if not input_file.exists():
                logger.error("输入文件不存在：%s", input_path)
                return False

            output_file.parent.mkdir(parents=True, exist_ok=True)

            if clean and not _find_bin("unpaper"):
                logger.warning("unpaper 未安装，跳过图像去噪（clean=False）")
                clean = False

            if rotate_pages:
                tessdata = _find_tessdata_dir()
                if not tessdata or not Path(tessdata, "osd.traineddata").exists():
                    logger.warning("osd.traineddata 缺失，跳过自动旋转（rotate_pages=False）")
                    rotate_pages = False

            ocrmypdf.ocr(
                input_file=input_file,
                output_file=output_file,
                language=language,
                deskew=deskew,
                clean=clean,
                force_ocr=force_ocr,
                rotate_pages=rotate_pages,
                output_type="pdf",
                progress_bar=False,
                optimize=1,
            )

            return output_file.exists()

        except ocrmypdf.exceptions.PriorOcrFoundError:
            logger.warning("PDF已包含OCR层，启用force_ocr可覆盖")
            return False
        except ocrmypdf.exceptions.MissingDependencyError as e:
            logger.error("缺少依赖：%s", e)
            return False
        except Exception as e:
            logger.error("OCR处理失败：%s", e)
            return False
