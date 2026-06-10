import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# 本脚本用于给 questions.jsonl 和 answers.jsonl 生成 Markdown 人工检查表。
# 主要输入：
#   1. clean_data/questions/**/questions.jsonl
#   2. clean_data/questions/**/answers.jsonl
# 主要输出：
#   1. 每份试卷目录下的 questions_review.md
#   2. 每份试卷目录下的 answers_review.md
#
# 说明：
#   questions.jsonl 负责题干、选项、材料、图片。
#   answers.jsonl 负责参考答案和答案图片。
#   两者必须通过 question_id 对齐。

ROOT_DIR = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT_DIR / "clean_data"
QUESTIONS_DIR = CLEAN_DIR / "questions"

VALID_QUESTION_TYPES = {"single_choice", "constructed_response"}
VALID_ANSWER_TYPES = {"single_choice", "constructed_response"}
VALID_STATUS = {"structured", "needs_review"}

QUESTION_REQUIRED_FIELDS = {
    "question_id",
    "question_number",
    "question_type",
    "question_text",
    "source_md",
    "source_file",
    "status",
}

ANSWER_REQUIRED_FIELDS = {
    "question_id",
    "question_number",
    "answer_type",
    "source_md",
    "source_answer_heading",
    "status",
}


def read_jsonl(path):
    """逐行读取 JSONL，返回记录和解析错误。"""
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
    """转义 Markdown 表格中会破坏列结构的字符。"""
    text = str(value).replace("\n", " ").replace("\r", " ")
    return text.replace("|", "\\|")


def short_text(value, limit=90):
    """把长文本压缩成适合 review 表格快速扫读的摘要。"""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def format_images_md(images):
    """把图片路径格式化为普通 Markdown 列表。"""
    if not images:
        return "- 无"
    return "\n".join(f"- `{item}`" for item in images)


def format_options_md(row):
    """把选择题选项格式化为普通 Markdown 列表。"""
    options = row.get("options", {})
    if not isinstance(options, dict) or not options:
        return "- 无"
    return "\n".join(
        f"- {key}. {value}"
        for key, value in sorted(options.items())
    )


def format_sub_questions_md(row):
    """把非选择题小问格式化为普通 Markdown 列表。"""
    sub_questions = row.get("sub_questions", {})
    if not isinstance(sub_questions, dict) or not sub_questions:
        return "- 无"
    return "\n".join(
        f"- 小问 {key}: {value}"
        for key, value in sorted(sub_questions.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0]))
    )


def format_answer_md(row):
    """把选择题答案或非选择题分问答案完整格式化为普通 Markdown。"""
    if "answer" in row:
        return str(row.get("answer", "")).strip() or "-"

    parts = row.get("answer_parts", {})
    if not isinstance(parts, dict) or not parts:
        return "- 无"
    return "\n\n".join(
        # 答案 review 用于人工核对，不能截断开放题的多个可能答案。
        # 解析 review 可以摘要化，但参考答案必须尽量完整展示。
        f"{key}. {value}"
        for key, value in sorted(parts.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0]))
    )


def format_issues_md(issues):
    """把自检问题格式化为普通 Markdown 列表。"""
    if not issues:
        return "- 无"
    return "\n".join(f"- {item}" for item in issues)


def validate_exam_dir(exam_dir, target="both"):
    """检查单份试卷的题目和答案结构，并生成每行自检问题。"""
    questions_path = exam_dir / "questions.jsonl"
    answers_path = exam_dir / "answers.jsonl"

    questions, question_errors = read_jsonl(questions_path) if target in {"questions", "both"} or questions_path.exists() else ([], [])
    answers, answer_errors = read_jsonl(answers_path) if target in {"answers", "both"} or answers_path.exists() else ([], [])

    question_issues = defaultdict(list)
    answer_issues = defaultdict(list)
    global_issues = []

    for kind, line_no, detail in question_errors:
        global_issues.append(("questions.jsonl", line_no, kind, detail))
    for kind, line_no, detail in answer_errors:
        global_issues.append(("answers.jsonl", line_no, kind, detail))

    question_ids = [row.get("question_id") for row in questions]
    answer_ids = [row.get("question_id") for row in answers]

    if target in {"answers", "both"} and questions and answers and question_ids != answer_ids:
        message = "questions.jsonl 与 answers.jsonl 的 question_id 顺序或集合不一致"
        global_issues.append(("answers.jsonl", "-", "question_id_mismatch", message))

    for qid, count in Counter(question_ids).items():
        if qid and count > 1:
            question_issues[qid].append("question_id 重复")
    for qid, count in Counter(answer_ids).items():
        if qid and count > 1:
            answer_issues[qid].append("question_id 重复")

    for row in questions:
        qid = row.get("question_id", "")
        qtype = row.get("question_type")
        missing_fields = sorted(QUESTION_REQUIRED_FIELDS - set(row))
        for field in missing_fields:
            question_issues[qid].append(f"缺少字段: {field}")

        if qtype not in VALID_QUESTION_TYPES:
            question_issues[qid].append(f"非法 question_type: {qtype}")
        if row.get("status") not in VALID_STATUS:
            question_issues[qid].append(f"非法 status: {row.get('status')}")
        if not str(row.get("question_text", "")).strip():
            question_issues[qid].append("题干为空")

        if qtype == "single_choice" and not row.get("options"):
            question_issues[qid].append("选择题缺少 options")
        if qtype == "constructed_response" and not row.get("sub_questions"):
            question_issues[qid].append("非选择题缺少 sub_questions")

        for image_path in row.get("related_images", []):
            if not (exam_dir / image_path).exists():
                question_issues[qid].append(f"题目图片不存在: {image_path}")

    for row in answers:
        qid = row.get("question_id", "")
        atype = row.get("answer_type")
        missing_fields = sorted(ANSWER_REQUIRED_FIELDS - set(row))
        for field in missing_fields:
            answer_issues[qid].append(f"缺少字段: {field}")

        if atype not in VALID_ANSWER_TYPES:
            answer_issues[qid].append(f"非法 answer_type: {atype}")
        if row.get("status") not in VALID_STATUS:
            answer_issues[qid].append(f"非法 status: {row.get('status')}")

        if atype == "single_choice" and not str(row.get("answer", "")).strip():
            answer_issues[qid].append("选择题答案为空")
        if atype == "constructed_response" and not row.get("answer_parts"):
            answer_issues[qid].append("非选择题缺少 answer_parts")

        for image_path in row.get("related_answer_images", []):
            if not (exam_dir / image_path).exists():
                answer_issues[qid].append(f"答案图片不存在: {image_path}")

    return {
        "exam_dir": exam_dir,
        "questions": questions,
        "answers": answers,
        "question_issues": question_issues,
        "answer_issues": answer_issues,
        "global_issues": global_issues,
    }


def require_jsonl_for_target(exam_dir, target):
    """根据本次 review 目标检查必需 JSONL 是否存在。"""
    required_files = []
    if target in {"questions", "both"}:
        required_files.append("questions.jsonl")
    if target in {"answers", "both"}:
        required_files.append("answers.jsonl")

    for file_name in required_files:
        path = exam_dir / file_name
        if not path.exists():
            raise SystemExit(f"指定试卷目录缺少 {file_name}: {exam_dir}")


def write_questions_review(result):
    """生成 questions_review.md，方便人工检查题目结构。

    题干、选项和小问可能很长，用分节结构比 Markdown 表格更适合 Obsidian preview。
    """
    exam_dir = result["exam_dir"]
    out_path = exam_dir / "questions_review.md"
    lines = [
        "# 题目结构人工检查表",
        "",
        f"- 资料目录: `{exam_dir.relative_to(ROOT_DIR)}`",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 题目数: {len(result['questions'])}",
        "",
        "说明：本文件用于人工检查题目结构，题干、选项和小问完整展示，不使用宽表格。",
        "",
    ]

    for row in result["questions"]:
        qid = row.get("question_id", "")
        issues = result["question_issues"].get(qid, [])
        lines.extend([
            f"## 第 {row.get('question_number', '')} 题",
            "",
            f"- question_id: `{qid}`",
            f"- 类型: `{row.get('question_type', '')}`",
            f"- 状态: `{row.get('status', '')}`",
            f"- 来源文件: `{row.get('source_file', '')}`",
            "",
            "**自检问题**",
            "",
            format_issues_md(issues),
            "",
            "**题干**",
            "",
            str(row.get("question_text", "")).strip() or "-",
            "",
            "**选项**",
            "",
            format_options_md(row),
            "",
            "**小问**",
            "",
            format_sub_questions_md(row),
            "",
            "**题目图片**",
            "",
            format_images_md(row.get("related_images", [])),
            "",
        ])

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def write_answers_review(result):
    """生成 answers_review.md，方便人工检查答案结构。

    开放题答案可能包含多种可能性，必须完整展示，避免表格截断或 preview 抖动。
    """
    exam_dir = result["exam_dir"]
    out_path = exam_dir / "answers_review.md"
    lines = [
        "# 参考答案人工检查表",
        "",
        f"- 资料目录: `{exam_dir.relative_to(ROOT_DIR)}`",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 答案数: {len(result['answers'])}",
        "",
        "说明：本文件用于人工检查参考答案，答案正文完整展示，不使用宽表格。",
        "",
    ]

    for row in result["answers"]:
        qid = row.get("question_id", "")
        issues = result["answer_issues"].get(qid, [])
        lines.extend([
            f"## 第 {row.get('question_number', '')} 题",
            "",
            f"- question_id: `{qid}`",
            f"- 类型: `{row.get('answer_type', '')}`",
            f"- 状态: `{row.get('status', '')}`",
            f"- 来源标题: {row.get('source_answer_heading', '') or '无'}",
            "",
            "**自检问题**",
            "",
            format_issues_md(issues),
            "",
            "**参考答案**",
            "",
            format_answer_md(row),
            "",
            "**答案图片**",
            "",
            format_images_md(row.get("related_answer_images", [])),
            "",
        ])

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def parse_args():
    """读取命令行参数，确定本次只检查哪一份或哪些试卷。"""
    parser = argparse.ArgumentParser(description="生成 questions/answers 的人工检查表")
    parser.add_argument(
        "--exam-dir",
        default="",
        help="只检查指定试卷目录；不填写时才扫描 clean_data/questions 下的全部试卷",
    )
    parser.add_argument(
        "--target",
        choices=("questions", "answers", "both"),
        default="both",
        help="指定本次只生成 questions_review、answers_review，或两者都生成",
    )
    return parser.parse_args()


def get_exam_dirs(args):
    """根据命令行参数确定本次处理的试卷目录。"""
    if args.exam_dir:
        exam_dir = Path(args.exam_dir)
        if not exam_dir.exists():
            raise SystemExit(f"指定试卷目录不存在: {exam_dir}")
        require_jsonl_for_target(exam_dir, args.target)
        return [exam_dir]

    marker = "answers.jsonl" if args.target == "answers" else "questions.jsonl"
    exam_dirs = sorted(path.parent for path in QUESTIONS_DIR.rglob(marker))
    if not exam_dirs:
        raise SystemExit(f"未找到 {marker}: {QUESTIONS_DIR}")
    return exam_dirs


def main():
    args = parse_args()
    exam_dirs = get_exam_dirs(args)

    total_issues = 0
    review_paths = []
    for exam_dir in exam_dirs:
        result = validate_exam_dir(exam_dir, args.target)
        if args.target in {"questions", "both"}:
            review_paths.append(write_questions_review(result))
        if args.target in {"answers", "both"}:
            review_paths.append(write_answers_review(result))
        total_issues += len(result["global_issues"])
        if args.target in {"questions", "both"}:
            total_issues += sum(len(items) for items in result["question_issues"].values())
        if args.target in {"answers", "both"}:
            total_issues += sum(len(items) for items in result["answer_issues"].values())

    print(f"题目与答案校验完成: {len(exam_dirs)} 份资料")
    print(f"问题数: {total_issues}")
    for path in review_paths:
        print(f"人工检查表: {path}")


if __name__ == "__main__":
    main()
