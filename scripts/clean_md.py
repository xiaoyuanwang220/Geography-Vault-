import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT_DIR / "convert_data"
CLEAN_DIR = ROOT_DIR / "clean_data"
RAW_DIR = ROOT_DIR / "raw_data"

SOURCE_EXTS = {".docx", ".pptx", ".pdf"}
CATEGORY_DIRS = {"questions", "textbooks", "shared_knowledge", "uncategorized"}
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
FRONTMATTER_PATTERN = re.compile(r"\A---\n.*?\n---\n+", re.DOTALL)


def read_text(path):
    return path.read_text(encoding="utf-8-sig")


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def yaml_quote(value):
    text = str(value).replace("\\", "/").replace('"', '\\"')
    return f'"{text}"'


def find_source_file(md_path):
    rel = md_path.relative_to(SOURCE_DIR)
    candidates = []
    source_rel = rel
    if len(rel.parts) >= 3 and rel.parts[0] in CATEGORY_DIRS and rel.parts[-2] == md_path.stem:
        source_rel = Path(rel.parts[0]) / rel.name
    for ext in SOURCE_EXTS:
        candidates.append(RAW_DIR / source_rel.with_suffix(ext))
    for candidate in candidates:
        if candidate.exists():
            return candidate

    matches = []
    for ext in SOURCE_EXTS:
        matches.extend(RAW_DIR.rglob(f"{md_path.stem}{ext}"))
    return matches[0] if matches else None


def infer_category(md_path):
    """根据 Markdown 所在目录或文件名推断资料分类。"""
    rel = md_path.relative_to(SOURCE_DIR)
    if rel.parts and rel.parts[0] in CATEGORY_DIRS:
        return rel.parts[0]

    name = md_path.stem
    if any(word in name for word in ("真题", "试题", "习题", "练习", "试卷", "题库")):
        return "questions"
    if any(word in name for word in ("课本", "教材", "教科书", "必修", "选择性必修")):
        return "textbooks"
    if any(word in name for word in ("知识点", "笔记", "分享", "讲义", "总结")):
        return "shared_knowledge"
    return "uncategorized"


def target_relative_path(md_path):
    """生成 clean_data 中的相对路径。

    目标结构固定为：
    分类/文档名/文档名.md

    图片放在该文档目录下的 images/，避免同一分类下多个资料的图片混在一起。
    """
    rel = md_path.relative_to(SOURCE_DIR)
    category = infer_category(md_path)

    if len(rel.parts) >= 3 and rel.parts[0] in CATEGORY_DIRS and rel.parts[-2] == md_path.stem:
        return rel
    if rel.parts and rel.parts[0] in CATEGORY_DIRS:
        return Path(rel.parts[0]) / md_path.stem / rel.name
    return Path(category) / md_path.stem / rel.name


def infer_metadata(md_path, source_file):
    name = md_path.stem
    category = infer_category(md_path)
    metadata = {
        "title": name,
        "category": category,
        "source_file": source_file.name if source_file else "",
        "source_type": source_file.suffix.lstrip(".") if source_file else "",
        "converted_file": str(md_path.relative_to(ROOT_DIR)),
        "status": "cleaned",
        "cleaned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    year_match = re.search(r"(20\d{2}|19\d{2})", name)
    if year_match:
        metadata["year"] = year_match.group(1)
    if "地理" in name:
        metadata["subject"] = "地理"
    if "山东" in name:
        metadata["region"] = "山东"
    if "高考" in name:
        metadata["stage"] = "高考"

    return metadata


def build_frontmatter(metadata):
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {yaml_quote(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def normalize_markdown(content):
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = FRONTMATTER_PATTERN.sub("", content)
    content = re.sub(r"[ \t]+$", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip() + "\n"


def image_links(content):
    return [match.group(1).strip() for match in IMAGE_PATTERN.finditer(content)]


def line_numbers_with(text, token):
    """返回包含指定文本的行号，便于人工定位。"""
    return [
        index
        for index, line in enumerate(text.splitlines(), 1)
        if token in line
    ]


def image_link_lines(content):
    """返回 Markdown 图片链接及其所在行号。"""
    result = []
    for line_no, line in enumerate(content.splitlines(), 1):
        for match in IMAGE_PATTERN.finditer(line):
            result.append((line_no, match.group(1).strip()))
    return result


def copy_linked_images(content, source_md, target_md):
    missing = []
    copied = 0
    for link in image_links(content):
        if "://" in link or link.startswith("#"):
            continue
        source_image = (source_md.parent / link).resolve()
        target_image = target_md.parent / link
        if not source_image.exists():
            missing.append(link)
            continue
        target_image.parent.mkdir(parents=True, exist_ok=True)
        if not target_image.exists() or source_image.stat().st_size != target_image.stat().st_size:
            shutil.copy2(source_image, target_image)
            copied += 1
    return copied, missing


def inspect_clean_result(content, target_md, source_file, metadata, missing_images):
    """检查清洗结果，并返回面向人工修改的问题清单。"""
    issues = []
    if not content.strip():
        issues.append(("严重", "-", "正文为空", "检查 convert_data 中的 Markdown 是否转换失败"))

    if not source_file:
        issues.append(("警告", "-", "未匹配到原始文件", "检查 raw_data 中是否存在同名 docx/pptx/pdf"))

    if metadata.get("category") == "uncategorized":
        issues.append(("警告", "-", "资料分类为 uncategorized", "人工判断应归入 questions/textbooks/shared_knowledge 哪一类"))

    for line_no in line_numbers_with(content, "<UNK>"):
        issues.append(("警告", line_no, "发现 <UNK> 占位符", "回到原始资料核对该处字符、公式或特殊符号"))

    missing_set = set(missing_images)
    for line_no, link in image_link_lines(content):
        if link in missing_set:
            issues.append(("严重", line_no, f"图片链接缺失: {link}", "检查对应 images 目录或重新转换原始文件"))

    if metadata.get("category") == "questions" and not (target_md.parent / "answers.jsonl").exists():
        issues.append(("提示", "-", "题目类资料尚未结构化答案", "后续生成 answers.jsonl 时必须绑定 question_id 与 answer"))

    return issues


def clean_file(md_path):
    rel = md_path.relative_to(SOURCE_DIR)
    target_md = CLEAN_DIR / target_relative_path(md_path)
    source_file = find_source_file(md_path)
    metadata = infer_metadata(md_path, source_file)

    content = normalize_markdown(read_text(md_path))
    final_content = build_frontmatter(metadata) + content
    write_text(target_md, final_content)

    copied_images, missing_images = copy_linked_images(content, md_path, target_md)
    issues = inspect_clean_result(content, target_md, source_file, metadata, missing_images)
    return {
        "source": rel,
        "target": target_md.relative_to(ROOT_DIR),
        "source_file": source_file.relative_to(ROOT_DIR) if source_file else "",
        "images": len(image_links(content)),
        "copied_images": copied_images,
        "missing_images": missing_images,
        "unk_count": content.count("<UNK>"),
        "issues": issues,
    }


def find_markdown_files(source_dir):
    return sorted(
        path for path in source_dir.rglob("*.md")
        if path.is_file() and path.name.lower() not in {"readme.md", "clean_report.md"}
    )


def write_report(results):
    issue_count = sum(len(item["issues"]) for item in results)
    lines = [
        f"清洗时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"输入目录: {SOURCE_DIR}",
        f"输出目录: {CLEAN_DIR}",
        f"处理文件数: {len(results)}",
        f"问题数: {issue_count}",
        "",
    ]
    for item in results:
        lines.append(f"[完成] {item['source']} -> {item['target']}")
        lines.append(f"  原始文件: {item['source_file']}")
        lines.append(f"  图片链接: {item['images']}, 复制图片: {item['copied_images']}")
        if item["issues"]:
            for level, line_no, problem, suggestion in item["issues"]:
                lines.append(f"  - {level} | 行: {line_no} | {problem} | 建议: {suggestion}")
        else:
            lines.append("  - 未发现明显问题")
        lines.append("")
    write_text(CLEAN_DIR / "clean_report.txt", "\n".join(lines).rstrip() + "\n")
    return issue_count


def main():
    global SOURCE_DIR, CLEAN_DIR

    parser = argparse.ArgumentParser(description="清洗转换后的 Markdown，并补充知识库元数据")
    parser.add_argument("--source", default=str(SOURCE_DIR), help="转换后的 Markdown 目录")
    parser.add_argument("--file", default="", help="只清洗指定 Markdown 文件；路径应位于 convert_data 下")
    parser.add_argument("--output", default=str(CLEAN_DIR), help="清洗后的输出目录")
    args = parser.parse_args()

    SOURCE_DIR = Path(args.source)
    CLEAN_DIR = Path(args.output)
    target_file = Path(args.file) if args.file else None

    if not SOURCE_DIR.exists():
        raise SystemExit(f"输入目录不存在: {SOURCE_DIR}")

    if target_file:
        if not target_file.exists():
            raise SystemExit(f"指定 Markdown 文件不存在: {target_file}")
        if target_file.suffix.lower() != ".md":
            raise SystemExit(f"指定文件不是 Markdown: {target_file}")
        md_files = [target_file]
    else:
        md_files = find_markdown_files(SOURCE_DIR)
    if not md_files:
        raise SystemExit(f"未找到 Markdown 文件: {SOURCE_DIR}")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    results = [clean_file(path) for path in md_files]
    issue_count = write_report(results)

    print(f"清洗完成: {len(results)} 个 Markdown 文件")
    print(f"输出目录: {CLEAN_DIR}")
    print(f"报告文件: {CLEAN_DIR / 'clean_report.txt'}")
    if issue_count:
        print(f"质量检查发现 {issue_count} 个问题，请优先查看 clean_report.txt")
    else:
        print("质量检查未发现明显问题")


if __name__ == "__main__":
    main()
