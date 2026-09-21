"""
核心引擎测试脚本
用法：修改下方 input_pdf 路径，运行 python test_core.py
作用：单独验证 OCR引擎 + 文本提取引擎，不启动Qt界面
"""
from pathlib import Path
from src.core.ocr_engine import OCREngine
from src.core.extract_engine import ExtractEngine

# ====================== 配置区（只改这里就行） ======================
# 测试用的PDF：建议放几页的小文件，不要直接跑整本
input_pdf = r"D:\Computer\Project\PDF-Scan-Enhancer\Getting unstuck  how dead ends become new paths (Butler, Timothy) (z-library.sk, 1lib.sk, z-lib.sk).pdf"  # 改成你的测试PDF路径
output_dir = r"test_output"        # 输出文件夹，自动创建
language = "eng"                   # 英文书就 eng，中英混合就 chi_sim+eng
# ===================================================================

def test_ocr_engine():
    """测试：OCR增强 + 纠偏去噪 + 重建文字层"""
    print("="*60)
    print("【1/2】开始测试 OCR 增强引擎...")
    print(f"输入文件：{input_pdf}")

    input_path = Path(input_pdf)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 输出文件名：原文件名 + _enhanced
    output_pdf = out_dir / f"{input_path.stem}_enhanced.pdf"

    try:
        success = OCREngine.process(
            input_path=str(input_path),
            output_path=str(output_pdf),
            language=language,
            deskew=True,    # 纠偏
            clean=True,     # 去噪
            force_ocr=True, # 强制重OCR
            rotate_pages=True
        )

        if success and output_pdf.exists():
            print(f"✅ OCR 处理完成！")
            print(f"输出文件：{output_pdf.resolve()}")
            print(f"文件大小：{output_pdf.stat().st_size / 1024 / 1024:.2f} MB")
            return str(output_pdf)
        else:
            print("❌ OCR 处理失败：未生成输出文件")
            return None

    except Exception as e:
        print(f"❌ OCR 处理报错：{str(e)}")
        return None


def test_extract_engine(enhanced_pdf_path):
    """测试：结构化提取 Markdown"""
    print("\n" + "="*60)
    print("【2/2】开始测试 结构化文本提取引擎...")
    print(f"输入文件：{enhanced_pdf_path}")

    out_dir = Path(output_dir)

    try:
        md_path = ExtractEngine.extract_to_markdown(
            input_pdf=enhanced_pdf_path,
            output_dir=str(out_dir)
        )

        md_file = Path(md_path)
        if md_file.exists():
            print(f"✅ 文本提取完成！")
            print(f"输出Markdown：{md_file.resolve()}")
            print(f"文件大小：{md_file.stat().st_size} 字节")

            # 打印前300字预览，看段落是否通顺
            print("\n📝 内容预览（前300字）：")
            print("-"*40)
            with open(md_file, "r", encoding="utf-8") as f:
                preview = f.read(300)
                print(preview)
            print("-"*40)
            return True
        else:
            print("❌ 提取失败：未生成Markdown文件")
            return False

    except Exception as e:
        print(f"❌ 提取报错：{str(e)}")
        return False


if __name__ == "__main__":
    # 检查输入文件存在
    if not Path(input_pdf).exists():
        print(f"❌ 测试文件不存在：{input_pdf}")
        print("请先修改脚本里的 input_pdf 路径为真实PDF路径")
        exit(1)

    # 分步测试
    enhanced_pdf = test_ocr_engine()

    if enhanced_pdf:
        extract_ok = test_extract_engine(enhanced_pdf)
        print("\n" + "="*60)
        if extract_ok:
            print("🎉 核心引擎全部测试通过！可以接Qt界面了")
        else:
            print("⚠️  提取环节异常，请排查ExtractEngine")
    else:
        print("\n" + "="*60)
        print("⚠️  OCR环节异常，请排查OCREngine / Tesseract环境")
