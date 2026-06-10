import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image


# 本脚本用于给每套试卷生成和校验图形化答案文件。
# 主要输入：
#   1. clean_data/questions/**/answers.jsonl
#   2. answers.jsonl 中已有的 related_answer_images
# 主要输出：
#   1. 每份试卷目录下的 graphical_answers.jsonl
#   2. 每份试卷目录下的 graphical_answers_review.md
#
# 说明：
#   answers.jsonl 保存文字答案。
#   graphical_answers.jsonl 保存需要图片、标注、绘制的图形化答案。
#   两者通过 question_id 对齐，不互相替代。

ROOT_DIR = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT_DIR / "clean_data"
QUESTIONS_DIR = CLEAN_DIR / "questions"

VALID_GRAPHIC_TYPES = {
    "map_annotation",
    "profile_annotation",
    "sketch_answer",
    "standard_answer_image",
}
VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_STATUS = {"structured", "needs_review"}

REQUIRED_FIELDS = {
    "question_id",
    "question_number",
    "graphic_type",
    "image_paths",
    "description",
    "source_answer_heading",
    "status",
    "parse_confidence",
    "note",
}


def read_jsonl(path):
    """逐行读取 JSONL 文件，返回记录和解析错误。"""
    rows = []
    errors = []
    if not path.exists():
        return rows, [("missing_file", "-", f"文件不存在: {path}")]

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception as exc:
            errors.append(("json_parse_error", line_no, str(exc)))
    return rows, errors


def format_list_md(items):
    """把列表格式化为普通 Markdown 列表。"""
    if not items:
        return "- 无"
    return "\n".join(f"- `{item}`" for item in items)


def guess_graphic_type(answer_row):
    """根据题号和答案内容粗略判断图形化答案类型。"""
    answer_text = json.dumps(answer_row.get("answer_parts", {}), ensure_ascii=False)
    if "分水线" in answer_text or "绘制" in answer_text or "虚线" in answer_text:
        return "map_annotation"
    if "剖面" in answer_text or "拔河高度" in answer_text:
        return "profile_annotation"
    return "standard_answer_image"


def build_description(answer_row):
    """从答案内容生成图形化答案说明。"""
    parts = answer_row.get("answer_parts", {})
    if isinstance(parts, dict) and parts:
        snippets = []
        for key, value in sorted(parts.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0])):
            if "图" in str(value) or "绘制" in str(value) or "分水线" in str(value) or "如下" in str(value):
                snippets.append(f"{key}: {value}")
        if snippets:
            return "；".join(snippets)
    return "该题存在标准答案图片，需人工确认图片是否为有效图形化答案。"


def image_info(exam_dir, image_path):
    """读取图片尺寸；读取失败时返回错误信息。"""
    full_path = exam_dir / image_path
    if not full_path.exists():
        return {"exists": False, "width": None, "height": None, "size": 0, "error": "图片不存在"}

    try:
        with Image.open(full_path) as image:
            width, height = image.size
    except Exception as exc:
        return {
            "exists": True,
            "width": None,
            "height": None,
            "size": full_path.stat().st_size,
            "error": str(exc),
        }

    return {
        "exists": True,
        "width": width,
        "height": height,
        "size": full_path.stat().st_size,
        "error": "",
    }


def generate_graphical_answers(exam_dir, answers):
    """从 answers.jsonl 中抽取 related_answer_images，生成图形化答案记录。"""
    rows = []
    for answer in answers:
        image_paths = answer.get("related_answer_images", [])
        if not image_paths:
            continue

        infos = [image_info(exam_dir, image_path) for image_path in image_paths]
        has_bad_image = any(
            (not info["exists"])
            or info["error"]
            or (info["width"] is not None and info["height"] is not None and (info["width"] < 50 or info["height"] < 50))
            for info in infos
        )

        rows.append({
            "question_id": answer.get("question_id", ""),
            "question_number": answer.get("question_number", ""),
            "graphic_type": guess_graphic_type(answer),
            "image_paths": image_paths,
            "description": build_description(answer),
            "source_answer_heading": answer.get("source_answer_heading", ""),
            "status": "needs_review" if has_bad_image else "structured",
            "parse_confidence": "low" if has_bad_image else "high",
            "note": "图片尺寸过小或读取异常，需人工复核" if has_bad_image else "",
        })
    return rows


def validate_rows(exam_dir, rows):
    """校验 graphical_answers.jsonl 记录，并返回每题问题列表。"""
    row_issues = defaultdict(list)

    for qid, count in Counter(row.get("question_id") for row in rows).items():
        if qid and count > 1:
            row_issues[qid].append("question_id 重复")

    for row in rows:
        qid = row.get("question_id", "")
        missing_fields = sorted(REQUIRED_FIELDS - set(row))
        for field in missing_fields:
            row_issues[qid].append(f"缺少字段: {field}")

        if row.get("graphic_type") not in VALID_GRAPHIC_TYPES:
            row_issues[qid].append(f"非法 graphic_type: {row.get('graphic_type')}")
        if row.get("status") not in VALID_STATUS:
            row_issues[qid].append(f"非法 status: {row.get('status')}")
        if row.get("parse_confidence") not in VALID_CONFIDENCE:
            row_issues[qid].append(f"非法 parse_confidence: {row.get('parse_confidence')}")

        image_paths = row.get("image_paths", [])
        if not isinstance(image_paths, list) or not image_paths:
            row_issues[qid].append("image_paths 为空或不是数组")
            continue

        for image_path in image_paths:
            info = image_info(exam_dir, image_path)
            if not info["exists"]:
                row_issues[qid].append(f"图片不存在: {image_path}")
            elif info["error"]:
                row_issues[qid].append(f"图片读取失败: {image_path} {info['error']}")
            elif info["width"] < 50 or info["height"] < 50:
                row_issues[qid].append(f"图片尺寸过小: {image_path} {info['width']}x{info['height']}")

    return row_issues


def write_jsonl(path, rows):
    """写出 UTF-8 JSONL 文件。"""
    content = "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows)
    path.write_text(content + ("\n" if rows else ""), encoding="utf-8")


def write_review_md(exam_dir, rows, row_issues):
    """生成 graphical_answers_review.md。

    图形化答案需要展示路径、尺寸、状态和问题，使用分节结构比宽表格更稳定。
    """
    out_path = exam_dir / "graphical_answers_review.md"
    lines = [
        "# 图形化答案人工检查表",
        "",
        f"- 资料目录: `{exam_dir.relative_to(ROOT_DIR)}`",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 图形化答案数: {len(rows)}",
        "",
        "说明：本文件用于人工检查图形化答案，图片路径和尺寸按题目分节展示。",
        "",
    ]

    if not rows:
        lines.extend([
            "## 检查结果",
            "",
            "- 未从 `answers.jsonl` 中发现 `related_answer_images`。",
            "- 如果该卷确实没有图形化答案，可以保留空的 `graphical_answers.jsonl`。",
            "",
        ])

    for row in rows:
        qid = row.get("question_id", "")
        image_paths = row.get("image_paths", [])
        dimensions = []
        for image_path in image_paths:
            info = image_info(exam_dir, image_path)
            if info["width"] is None or info["height"] is None:
                dimensions.append(f"{image_path}: -")
            else:
                dimensions.append(f"{image_path}: {info['width']}x{info['height']}")

        issues = row_issues.get(qid, [])
        lines.extend([
            f"## 第 {row.get('question_number', '')} 题",
            "",
            f"- question_id: `{qid}`",
            f"- 图形类型: `{row.get('graphic_type', '')}`",
            f"- 状态: `{row.get('status', '')}`",
            f"- 置信度: `{row.get('parse_confidence', '')}`",
            f"- 来源标题: {row.get('source_answer_heading', '') or '无'}",
            f"- 备注: {row.get('note', '') or '无'}",
            "",
            "**图片路径**",
            "",
            format_list_md(image_paths),
            "",
            "**图片尺寸**",
            "",
            "\n".join(f"- {item}" for item in dimensions) or "- 无",
            "",
            "**说明**",
            "",
            row.get("description", "") or "-",
            "",
            "**自检问题**",
            "",
            "\n".join(f"- {item}" for item in issues) if issues else "- 无",
            "",
        ])

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def get_exam_dirs():
    """读取命令行参数，确定本次只处理哪一份或哪些试卷。"""
    parser = argparse.ArgumentParser(description="生成和校验 graphical_answers.jsonl")
    parser.add_argument(
        "--exam-dir",
        default="",
        help="只处理指定试卷目录；不填写时才扫描 clean_data/questions 下的全部试卷",
    )
    args = parser.parse_args()

    if args.exam_dir:
        exam_dir = Path(args.exam_dir)
        if not exam_dir.exists():
            raise SystemExit(f"指定试卷目录不存在: {exam_dir}")
        if not (exam_dir / "answers.jsonl").exists():
            raise SystemExit(f"指定试卷目录缺少 answers.jsonl: {exam_dir}")
        return [exam_dir]

    exam_dirs = sorted(path.parent for path in QUESTIONS_DIR.rglob("answers.jsonl"))
    if not exam_dirs:
        raise SystemExit(f"未找到 answers.jsonl: {QUESTIONS_DIR}")
    return exam_dirs


def main():
    exam_dirs = get_exam_dirs()

    total_issues = 0
    review_paths = []
    for exam_dir in exam_dirs:
        answers, errors = read_jsonl(exam_dir / "answers.jsonl")
        if errors:
            print(f"跳过 {exam_dir}: answers.jsonl 解析异常")
            total_issues += len(errors)
            continue

        rows = generate_graphical_answers(exam_dir, answers)
        out_jsonl = exam_dir / "graphical_answers.jsonl"
        write_jsonl(out_jsonl, rows)

        row_issues = validate_rows(exam_dir, rows)
        total_issues += sum(len(items) for items in row_issues.values())
        review_paths.append(write_review_md(exam_dir, rows, row_issues))

    print(f"图形化答案处理完成: {len(exam_dirs)} 份资料")
    print(f"问题数: {total_issues}")
    for path in review_paths:
        print(f"图形化答案检查表: {path}")


if __name__ == "__main__":
    main()
