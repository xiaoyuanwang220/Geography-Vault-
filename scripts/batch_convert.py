import os
import sys
import shutil
import traceback
import re
import argparse
from pathlib import Path
from datetime import datetime

# 允许脚本无论从哪个目录启动，都能导入同目录下的 convert_to_md.py。
sys.path.insert(0, str(Path(__file__).parent))
from convert_to_md import convert_word_to_md, convert_ppt_to_md, convert_pdf_to_md

# 批量转换的固定输入/输出目录。
# raw_data 放原始 Word/PPT/PDF，convert_data 放生成的 Markdown 和图片。
ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / "raw_data"
OUTPUT_DIR = ROOT_DIR / "convert_data"

# 当前批处理支持的原始文档格式，以及需要原样复制的独立图片格式。
SUPPORTED_EXTS = {".docx", ".pptx", ".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".tiff", ".webp"}
CATEGORY_DIRS = {"questions", "textbooks", "shared_knowledge", "uncategorized"}
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def classify_path(path):
    """根据文件所在目录或文件名判断资料分类。

    优先使用 raw_data 下已有的一级分类目录；如果原始文件直接放在 raw_data，
    就根据文件名关键词自动归类。
    """
    parts = path.parts
    for part in parts:
        if part in CATEGORY_DIRS:
            return part

    name = path.stem
    if any(word in name for word in ("真题", "试题", "习题", "练习", "试卷", "题库")):
        return "questions"
    if any(word in name for word in ("课本", "教材", "教科书", "必修", "选择性必修")):
        return "textbooks"
    if any(word in name for word in ("知识点", "笔记", "分享", "讲义", "总结")):
        return "shared_knowledge"
    return "uncategorized"


def find_files(root_dir):
    """递归查找 raw_data 中所有可转换的文档文件。"""
    files = []
    for path in sorted(root_dir.rglob("*")):
        if path.suffix.lower() in SUPPORTED_EXTS and path.is_file():
            files.append(path)
    return files


def copy_existing_images(raw_dir, output_dir):
    """复制 raw_data 中独立存在的图片文件。

    有些资料会把图片作为单独文件放在文档旁边，而不是嵌入 Word/PPT/PDF。
    这类图片也要进入 convert_data/images，后续清洗和建图时才能统一管理。
    """
    copied = 0
    for path in sorted(raw_dir.rglob("*")):
        if path.suffix.lower() in IMAGE_EXTS and path.is_file():
            rel = path.relative_to(raw_dir)
            category = classify_path(rel)
            dest = output_dir / category / "external_images" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied += 1
    return copied


def output_markdown_path(input_path, output_dir, raw_root):
    """计算转换后 Markdown 的输出路径。"""
    rel = input_path.relative_to(raw_root)
    category = classify_path(rel)
    md_name = rel.stem + ".md"
    doc_dir = rel.stem
    if rel.parts and rel.parts[0] in CATEGORY_DIRS:
        return output_dir / rel.parent / doc_dir / md_name
    return output_dir / category / rel.parent / doc_dir / md_name


def convert_file(input_path, output_dir, raw_root):
    """转换单个文件，并保持它相对于 raw_data 的子目录结构。"""
    md_output = output_markdown_path(input_path, output_dir, raw_root)
    md_output.parent.mkdir(parents=True, exist_ok=True)

    ext = input_path.suffix.lower()
    if ext == ".docx":
        return convert_word_to_md(input_path, md_output), md_output
    elif ext == ".pptx":
        return convert_ppt_to_md(input_path, md_output), md_output
    elif ext == ".pdf":
        return convert_pdf_to_md(input_path, md_output), md_output
    return False, md_output


def line_numbers_with(text, token):
    """返回包含指定文本的行号，便于人工快速定位。"""
    return [
        index
        for index, line in enumerate(text.splitlines(), 1)
        if token in line
    ]


def markdown_image_links(text):
    """提取 Markdown 图片链接中的相对路径。"""
    return [match.group(1).strip() for match in IMAGE_PATTERN.finditer(text)]


def inspect_markdown(md_path):
    """检查转换后的 Markdown 是否存在明显需要人工处理的问题。"""
    issues = []
    if not md_path.exists():
        issues.append(("严重", "-", "Markdown 文件未生成", "检查转换函数是否报错"))
        return issues

    text = md_path.read_text(encoding="utf-8-sig")
    if not text.strip():
        issues.append(("严重", "-", "Markdown 内容为空", "检查原始文件是否为空或转换器是否支持该文件"))
        return issues

    if len(text.strip()) < 100:
        issues.append(("警告", "-", "Markdown 内容很短", "人工确认是否漏提正文或图片"))

    for line_no in line_numbers_with(text, "<UNK>"):
        issues.append(("警告", line_no, "发现 <UNK> 占位符", "回到原始资料核对该处字符或公式"))

    for link in markdown_image_links(text):
        if "://" in link or link.startswith("#"):
            continue
        image_path = (md_path.parent / link).resolve()
        if not image_path.exists():
            issues.append(("严重", "-", f"图片链接缺失: {link}", "检查 images 目录或重新转换该文件"))

    return issues


def write_quality_report(results, output_dir):
    """写入转换质量报告，列出需要人工复核的位置。"""
    lines = [
        f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"输出目录: {output_dir}",
        "",
    ]
    issue_count = 0
    for item in results:
        rel = item["source"]
        status = item["status"]
        md_path = item["markdown_path"]
        issues = item["issues"]
        lines.append(f"[{status}] {rel}")
        lines.append(f"  Markdown: {md_path}")
        if item["error"]:
            lines.append(f"  错误: {item['error']}")
        if issues:
            for level, line_no, problem, suggestion in issues:
                issue_count += 1
                lines.append(f"  - {level} | 行: {line_no} | {problem} | 建议: {suggestion}")
        else:
            lines.append("  - 未发现明显问题")
        lines.append("")

    lines.insert(2, f"问题数: {issue_count}")
    report_path = output_dir / "convert_quality_report.txt"
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return report_path, issue_count


def main():
    """批量转换入口：扫描 raw_data，输出 Markdown、图片和转换日志。"""
    parser = argparse.ArgumentParser(description="转换 raw_data 中的 Word/PPT/PDF 为 Markdown")
    parser.add_argument(
        "--input",
        default=str(RAW_DIR),
        help="指定要转换的原始文件或目录；默认扫描整个 raw_data",
    )
    args = parser.parse_args()
    input_path = Path(args.input)

    if not RAW_DIR.exists():
        print(f"错误: 原始数据目录不存在: {RAW_DIR}")
        sys.exit(1)
    if not input_path.exists():
        print(f"错误: 指定输入不存在: {input_path}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_EXTS:
            print(f"错误: 不支持的文件类型: {input_path}")
            sys.exit(1)
        files = [input_path]
    else:
        files = find_files(input_path)
    if not files:
        print(f"未找到可转换的文件 (支持: {', '.join(SUPPORTED_EXTS)})")
        print(f"请检查输入路径: {input_path}")
        sys.exit(0)

    print(f"原始数据目录: {RAW_DIR}")
    print(f"本次输入:     {input_path}")
    print(f"输出目录:     {OUTPUT_DIR}")
    print(f"找到 {len(files)} 个文件待转换")
    print("-" * 60)

    # results 用于最后生成 convert_log.txt，方便追踪每个文件是否成功。
    success_count = 0
    fail_count = 0
    results = []

    for f in files:
        rel = f.relative_to(RAW_DIR)
        print(f"[转换] {rel} ... ", end="", flush=True)
        try:
            # 每个文件独立捕获异常，避免一个坏文件中断整批转换。
            ok, md_path = convert_file(f, OUTPUT_DIR, RAW_DIR)
            issues = inspect_markdown(md_path) if ok else []
            if ok:
                print(f"成功 -> {md_path.relative_to(OUTPUT_DIR)}")
                results.append({
                    "source": rel,
                    "status": "成功",
                    "markdown_path": md_path.relative_to(OUTPUT_DIR),
                    "error": "",
                    "issues": issues,
                })
                success_count += 1
            else:
                print("失败")
                results.append({
                    "source": rel,
                    "status": "失败",
                    "markdown_path": md_path.relative_to(OUTPUT_DIR),
                    "error": "转换函数返回False",
                    "issues": [("严重", "-", "转换函数返回 False", "查看控制台输出或单独运行 convert_to_md.py")],
                })
                fail_count += 1
        except Exception as e:
            print(f"失败: {e}")
            md_path = output_markdown_path(f, OUTPUT_DIR, RAW_DIR)
            results.append({
                "source": rel,
                "status": "失败",
                "markdown_path": md_path.relative_to(OUTPUT_DIR),
                "error": str(e),
                "issues": [("严重", "-", "转换时抛出异常", "查看错误信息并检查原始文件")],
            })
            fail_count += 1

    print()

    # 除了文档内嵌图片，也把 raw_data 中已有的独立图片同步到输出目录。
    image_source_dir = input_path if input_path.is_dir() else input_path.parent
    img_count = copy_existing_images(image_source_dir, OUTPUT_DIR)
    if img_count > 0:
        print(f"复制了 {img_count} 个独立图片文件到 images/ 目录")

    print("-" * 60)
    print(f"转换完成: 成功 {success_count}, 失败 {fail_count}, 共 {len(files)}")

    if fail_count > 0:
        print("\n失败详情:")
        for item in results:
            if item["status"] == "失败":
                print(f"  - {item['source']}: {item['error']}")

    report_path, issue_count = write_quality_report(results, OUTPUT_DIR)
    if issue_count:
        print(f"\n质量检查发现 {issue_count} 个问题，请查看: {report_path}")
    else:
        print(f"\n质量检查未发现明显问题，报告已保存: {report_path}")

    # 写入 UTF-8 日志，后续清洗、排错、复现转换结果时都可以参考。
    log_path = OUTPUT_DIR / "convert_log.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"转换时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"原始目录: {RAW_DIR}\n")
        f.write(f"输出目录: {OUTPUT_DIR}\n")
        f.write(f"成功: {success_count}, 失败: {fail_count}, 共: {len(files)}\n\n")
        for item in results:
            f.write(f"[{item['status']}] {item['source']}")
            if item["error"]:
                f.write(f"  | {item['error']}")
            f.write("\n")
    print(f"\n日志已保存: {log_path}")


if __name__ == "__main__":
    main()
