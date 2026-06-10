import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# 本脚本用于检查 explanations.jsonl，并生成解析人工检查表。
# 主要输入：
#   1. clean_data/questions/**/questions.jsonl
#   2. clean_data/questions/**/answers.jsonl
#   3. clean_data/questions/**/explanations.jsonl
# 主要输出：
#   1. 每份试卷目录下的 explanations_review.md
#   2. 控制台输出问题数量和检查表路径
#
# 说明：
#   question_knowledge_links.jsonl 是题目与知识点的唯一权威链接。
#   本脚本不会把知识点写入 explanations.jsonl，也不会要求解析记录包含知识点。

ROOT_DIR = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT_DIR / "clean_data"
QUESTIONS_DIR = CLEAN_DIR / "questions"

VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_STATUS = {"structured", "needs_review"}
REQUIRED_FIELDS = {
    "question_id",
    "question_number",
    "explanation_type",
    "source_file",
    "source_span",
    "parse_confidence",
    "status",
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


def md_escape(value):
    """转义 Markdown 表格中的特殊字符。"""
    text = str(value).replace("\n", " ").replace("\r", " ")
    return text.replace("|", "\\|")


def short_text(value, limit=120):
    """把长解析压缩成表格里可快速扫读的摘要。"""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def format_explanation_full(row):
    """把选择题解析或非选择题分小问解析完整展开为 Markdown。"""
    if "explanation" in row:
        return str(row.get("explanation", "")).strip() or "-"

    parts = row.get("explanation_parts", {})
    if isinstance(parts, dict):
        items = []
        for key in sorted(parts, key=lambda item: int(item) if str(item).isdigit() else str(item)):
            value = str(parts[key]).strip() or "-"
            items.append(f"{key}. {value}")
        return "\n\n".join(items) or "-"

    return "-"


def format_answer_images(answer_row):
    """从 answers.jsonl 中读取图形化答案图片路径，供 review 展示。"""
    images = answer_row.get("related_answer_images", []) if answer_row else []
    if not images:
        return "-"
    return "\n".join(f"- `{item}`" for item in images)


def validate_exam_dir(exam_dir):
    """校验单份试卷的 explanations.jsonl 与题目、答案是否对齐。"""
    questions_path = exam_dir / "questions.jsonl"
    answers_path = exam_dir / "answers.jsonl"
    explanations_path = exam_dir / "explanations.jsonl"

    questions, question_errors = read_jsonl(questions_path)
    answers, answer_errors = read_jsonl(answers_path)
    explanations, explanation_errors = read_jsonl(explanations_path)

    issues = []
    for kind, line_no, detail in question_errors:
        issues.append(("严重", "questions.jsonl", line_no, kind, detail, "修复 JSONL 后再继续校验"))
    for kind, line_no, detail in answer_errors:
        issues.append(("严重", "answers.jsonl", line_no, kind, detail, "修复 JSONL 后再继续校验"))
    for kind, line_no, detail in explanation_errors:
        issues.append(("严重", "explanations.jsonl", line_no, kind, detail, "修复 JSONL 后再继续校验"))

    question_ids = [row.get("question_id") for row in questions]
    answer_ids = [row.get("question_id") for row in answers]
    explanation_ids = [row.get("question_id") for row in explanations]

    if questions and explanations and question_ids != explanation_ids:
        issues.append((
            "严重",
            "explanations.jsonl",
            "-",
            "question_id_mismatch",
            "explanations.jsonl 与 questions.jsonl 的 question_id 顺序或集合不一致",
            "按 question_id 对齐题目和解析记录",
        ))
    if answers and explanations and answer_ids != explanation_ids:
        issues.append((
            "严重",
            "explanations.jsonl",
            "-",
            "answer_id_mismatch",
            "explanations.jsonl 与 answers.jsonl 的 question_id 顺序或集合不一致",
            "按 question_id 对齐答案和解析记录",
        ))

    for qid, count in Counter(explanation_ids).items():
        if qid and count > 1:
            issues.append(("严重", "explanations.jsonl", "-", "duplicate_question_id", qid, "删除或合并重复解析记录"))

    row_issues = defaultdict(list)
    for row_index, row in enumerate(explanations, 1):
        qid = row.get("question_id", "")
        qnum = row.get("question_number", "")

        # 解析文件不应重复维护知识点，知识点唯一权威来源是 question_knowledge_links.jsonl。
        if "related_knowledge_points" in row:
            problem = "不应包含 related_knowledge_points"
            row_issues[qid].append(problem)
            issues.append(("严重", "explanations.jsonl", row_index, "duplicated_knowledge_links", f"Q{qnum} {problem}", "删除该字段，改用 question_id 关联 question_knowledge_links.jsonl"))

        missing_fields = sorted(REQUIRED_FIELDS - set(row))
        for field in missing_fields:
            problem = f"缺少字段: {field}"
            row_issues[qid].append(problem)
            issues.append(("严重", "explanations.jsonl", row_index, "missing_field", f"Q{qnum} {problem}", "补齐必需字段"))

        if "explanation" not in row and "explanation_parts" not in row:
            problem = "缺少 explanation 或 explanation_parts"
            row_issues[qid].append(problem)
            issues.append(("严重", "explanations.jsonl", row_index, "missing_explanation_body", f"Q{qnum} {problem}", "补充解析正文"))

        if row.get("parse_confidence") not in VALID_CONFIDENCE:
            problem = f"非法 parse_confidence: {row.get('parse_confidence')}"
            row_issues[qid].append(problem)
            issues.append(("严重", "explanations.jsonl", row_index, "bad_parse_confidence", f"Q{qnum} {problem}", "改为 high/medium/low"))
        elif row.get("parse_confidence") == "low":
            problem = "parse_confidence=low"
            row_issues[qid].append(problem)
            issues.append(("警告", "explanations.jsonl", row_index, "low_confidence", f"Q{qnum} 低置信度解析", "人工复核解析是否准确"))

        if row.get("status") not in VALID_STATUS:
            problem = f"非法 status: {row.get('status')}"
            row_issues[qid].append(problem)
            issues.append(("严重", "explanations.jsonl", row_index, "bad_status", f"Q{qnum} {problem}", "改为 structured 或 needs_review"))
        elif row.get("status") == "needs_review":
            problem = "status=needs_review"
            row_issues[qid].append(problem)
            issues.append(("警告", "explanations.jsonl", row_index, "needs_review", f"Q{qnum} 解析需要人工复核", "人工确认后改为 structured"))

        source_span = row.get("source_span", {})
        if not isinstance(source_span, dict) or "start_line" not in source_span or "end_line" not in source_span:
            problem = "source_span 缺少 start_line 或 end_line"
            row_issues[qid].append(problem)
            issues.append(("警告", "explanations.jsonl", row_index, "bad_source_span", f"Q{qnum} {problem}", "补充原文件行号范围，便于回看"))

    return {
        "exam_dir": exam_dir,
        "questions": questions,
        "answers": answers,
        "explanations": explanations,
        "issues": issues,
        "row_issues": row_issues,
    }


def write_review_md(result):
    """生成 explanations_review.md，方便用户逐题完整检查解析。

    解析文字通常很长，如果放入 Markdown 表格，Obsidian preview 会反复计算列宽，
    容易出现横向滚动和页面抖动。因此这里使用逐题块状结构，完整保留解析正文。
    """
    exam_dir = result["exam_dir"]
    answers_by_id = {row.get("question_id"): row for row in result["answers"]}
    row_issues = result["row_issues"]
    out_path = exam_dir / "explanations_review.md"

    lines = [
        "# 题目解析人工检查表",
        "",
        f"- 资料目录: `{exam_dir.relative_to(ROOT_DIR)}`",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 解析数: {len(result['explanations'])}",
        "",
        "说明：本文件用于人工检查解析内容，解析正文完整展示，不做摘要截断。",
        "",
    ]

    for row in result["explanations"]:
        qid = row.get("question_id", "")
        source_span = row.get("source_span", {})
        if isinstance(source_span, dict):
            span_text = f"{source_span.get('start_line', '-')}-{source_span.get('end_line', '-')}"
        else:
            span_text = "-"

        issues = row_issues.get(qid, [])
        lines.extend([
            f"## 第 {row.get('question_number', '')} 题",
            "",
            f"- question_id: `{qid}`",
            f"- 类型: `{row.get('explanation_type', '')}`",
            f"- 置信度: `{row.get('parse_confidence', '')}`",
            f"- 状态: `{row.get('status', '')}`",
            f"- 来源行号: `{span_text}`",
            f"- 备注: {row.get('note', '') or '无'}",
            "",
            "**自检问题**",
            "",
        ])

        if issues:
            lines.extend(f"- {item}" for item in issues)
        else:
            lines.append("- 无")

        lines.extend([
            "",
            "**图形化答案**",
            "",
            format_answer_images(answers_by_id.get(qid)),
            "",
            "**完整解析**",
            "",
            format_explanation_full(row),
            "",
        ])

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def get_exam_dirs():
    """读取命令行参数，确定本次只检查哪一份或哪些试卷。"""
    parser = argparse.ArgumentParser(description="检查 explanations.jsonl 并生成人工检查表")
    parser.add_argument(
        "--exam-dir",
        default="",
        help="只检查指定试卷目录；不填写时才扫描 clean_data/questions 下的全部试卷",
    )
    args = parser.parse_args()

    if args.exam_dir:
        exam_dir = Path(args.exam_dir)
        if not exam_dir.exists():
            raise SystemExit(f"指定试卷目录不存在: {exam_dir}")
        if not (exam_dir / "explanations.jsonl").exists():
            raise SystemExit(f"指定试卷目录缺少 explanations.jsonl: {exam_dir}")
        return [exam_dir]

    exam_dirs = sorted(path.parent for path in QUESTIONS_DIR.rglob("explanations.jsonl"))
    if not exam_dirs:
        raise SystemExit(f"未找到 explanations.jsonl: {QUESTIONS_DIR}")
    return exam_dirs


def main():
    exam_dirs = get_exam_dirs()

    total_issues = 0
    review_paths = []
    for exam_dir in exam_dirs:
        result = validate_exam_dir(exam_dir)
        review_paths.append(write_review_md(result))
        total_issues += len(result["issues"])

    print(f"解析校验完成: {len(exam_dirs)} 份资料")
    print(f"问题数: {total_issues}")
    for path in review_paths:
        print(f"解析人工检查表: {path}")


if __name__ == "__main__":
    main()
