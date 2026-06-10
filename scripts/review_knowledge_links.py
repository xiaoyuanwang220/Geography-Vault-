import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# 本脚本用于检查“题目 -> 知识点”的结构化关联是否可靠。
# 主要输入：
#   1. clean_data/questions/**/question_knowledge_links.jsonl
#   2. 同目录下的 questions.jsonl、answers.jsonl
#   3. config/knowledge_taxonomy_*.yaml
# 主要输出：
#   1. 每份试卷目录下的 question_knowledge_links_review.md，给用户逐题人工检查
#   2. clean_data/structure_report.txt，汇总所有需要人工处理的问题

# 项目固定根目录。后续如果迁移项目，只需要优先检查这里。
ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
CLEAN_DIR = ROOT_DIR / "clean_data"
QUESTIONS_DIR = CLEAN_DIR / "questions"

# question_knowledge_links.jsonl 中允许出现的标注状态。
# 新增状态前，要同步修改 agent.md 中的说明，避免脚本和规范不一致。
VALID_LABEL_STATUS = {
    "draft_for_manual_review",
    "reviewed",
    "needs_taxonomy_expansion",
    "needs_review",
}

# 置信度只允许这三个等级，便于后续筛选低置信度题目。
VALID_CONFIDENCE = {"high", "medium", "low"}

# 知识点在一道题中的作用角色。后续 Obsidian 图谱和统计分析应优先使用该角色，
# 避免把所有知识点都当成同等强度的简单关联。
VALID_KNOWLEDGE_ROLES = {
    "core_exam_point",
    "supporting_knowledge",
    "material_clue",
    "background_knowledge",
}

ROLE_LABELS = {
    "core_exam_point": "核心考点",
    "supporting_knowledge": "支撑知识",
    "material_clue": "材料线索",
    "background_knowledge": "背景知识",
}

# 推荐权重用于后续知识图谱边权和备考分析。脚本允许人工微调，但会提示明显偏离。
RECOMMENDED_ROLE_WEIGHTS = {
    "core_exam_point": 1.0,
    "supporting_knowledge": 0.7,
    "material_clue": 0.4,
    "background_knowledge": 0.2,
}

# 每一道题的知识点关联记录必须具备这些字段。
# 这些字段既支撑人工检查，也支撑后续知识图谱和共现统计。
REQUIRED_FIELDS = {
    "question_id",
    "question_number",
    "knowledge_points",
    "extra_tags",
    "taxonomy_version",
    "label_status",
    "confidence",
    "note",
}


def read_jsonl(path):
    """逐行读取 JSONL，返回记录和解析错误。"""
    rows = []
    errors = []

    # 文件缺失时不直接中断，交给最终报告统一展示，方便用户一次性处理问题。
    if not path.exists():
        return rows, [("missing_file", "-", f"文件不存在: {path}")]

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception as exc:
            # 保留具体行号，用户可以直接定位到损坏的 JSONL 行。
            errors.append(("json_parse_error", line_no, str(exc)))
    return rows, errors


def load_taxonomy_triples():
    """读取 config 下所有 taxonomy，提取 module/level1/level2 三元组。"""
    triples = set()
    duplicate_level2 = defaultdict(list)

    for path in sorted(CONFIG_DIR.glob("knowledge_taxonomy_*.yaml")):
        module = None
        level1 = None
        in_modules = False

        # 当前 taxonomy 文件结构较简单，这里用缩进规则读取三级知识点。
        # 如果未来 taxonomy 结构变复杂，建议改为 YAML 解析库读取。
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("modules:"):
                in_modules = True
                continue
            if not in_modules:
                continue
            if line.startswith("  - name: "):
                module = line.split(": ", 1)[1].strip()
                level1 = None
            elif line.startswith("      - name: "):
                level1 = line.split(": ", 1)[1].strip()
            elif line.startswith("          - "):
                level2 = line[12:].strip()
                triple = (module, level1, level2)
                triples.add(triple)

                # 记录二级知识点重名位置。重名不一定错误，但统计和建图必须用完整路径。
                duplicate_level2[level2].append(
                    {
                        "file": path.name,
                        "module": module,
                        "level1": level1,
                        "line": line_no,
                    }
                )

    duplicates = {
        name: refs
        for name, refs in duplicate_level2.items()
        if len(refs) > 1
    }
    return triples, duplicates


def format_kp(kp):
    """把知识点字典格式化为方便人工阅读的完整路径。"""
    return f"{kp.get('module', '')} / {kp.get('level1', '')} / {kp.get('level2', '')}"


def format_weight(value):
    """格式化知识点权重，避免整数和浮点展示不一致。"""
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    return str(value)


def format_list_md(items):
    """把普通列表格式化为 Markdown 列表。"""
    if not items:
        return "- 无"
    return "\n".join(f"- {item}" for item in items)


def format_knowledge_by_role(kps):
    """按知识点角色分组展示，突出备考价值。"""
    if not kps:
        return "- 无"

    lines = []
    for role in ("core_exam_point", "supporting_knowledge", "material_clue", "background_knowledge"):
        role_items = [kp for kp in kps if kp.get("role") == role]
        lines.append(f"### {ROLE_LABELS[role]}")
        lines.append("")
        if not role_items:
            lines.append("- 无")
        else:
            for kp in role_items:
                text = f"- {format_kp(kp)}"
                if "weight" in kp:
                    text += f" | 权重: `{format_weight(kp.get('weight'))}`"
                if kp.get("evidence"):
                    text += f" | 依据: {kp.get('evidence')}"
                if kp.get("note"):
                    text += f" | 备注: {kp.get('note')}"
                lines.append(text)
        lines.append("")

    unknown_items = [kp for kp in kps if kp.get("role") not in VALID_KNOWLEDGE_ROLES]
    if unknown_items:
        lines.append("### 未规范角色")
        lines.append("")
        for kp in unknown_items:
            lines.append(f"- {format_kp(kp)} | role: `{kp.get('role', '')}`")
        lines.append("")

    return "\n".join(lines).rstrip()


def validate_exam_dir(exam_dir, taxonomy_triples):
    """校验单份试卷的题目-知识点关联文件。"""
    # 每份试卷目录下，题目、答案、知识点关联都应该用 question_id 绑定。
    questions_path = exam_dir / "questions.jsonl"
    answers_path = exam_dir / "answers.jsonl"
    links_path = exam_dir / "question_knowledge_links.jsonl"

    questions, question_errors = read_jsonl(questions_path)
    answers, answer_errors = read_jsonl(answers_path)
    links, link_errors = read_jsonl(links_path)

    issues = []

    # 先把文件缺失或 JSONL 解析失败的问题加入报告。
    # 即使有错误，也继续做后续检查，尽量一次性暴露更多问题。
    for kind, line_no, detail in question_errors:
        issues.append(("严重", "questions.jsonl", "-", kind, detail, "修复 JSONL 后再继续校验"))
    for kind, line_no, detail in answer_errors:
        issues.append(("严重", "answers.jsonl", "-", kind, detail, "修复 JSONL 后再继续校验"))
    for kind, line_no, detail in link_errors:
        issues.append(("严重", "question_knowledge_links.jsonl", line_no, kind, detail, "修复 JSONL 后再继续校验"))

    question_ids = [row.get("question_id") for row in questions]
    answer_ids = [row.get("question_id") for row in answers]
    link_ids = [row.get("question_id") for row in links]

    # 严格检查顺序和集合是否一致。
    # 当前项目推荐三类 JSONL 顺序一致，这样人工比对成本最低。
    if questions and links and question_ids != link_ids:
        issues.append((
            "严重",
            "question_knowledge_links.jsonl",
            "-",
            "question_id_mismatch",
            "question_knowledge_links.jsonl 与 questions.jsonl 的 question_id 顺序或集合不一致",
            "按 question_id 对齐题目和知识点关联记录",
        ))
    if questions and answers and question_ids != answer_ids:
        issues.append((
            "严重",
            "answers.jsonl",
            "-",
            "question_id_mismatch",
            "answers.jsonl 与 questions.jsonl 的 question_id 顺序或集合不一致",
            "按 question_id 对齐题目和答案记录",
        ))

    # question_knowledge_links.jsonl 一行对应一道题，重复 question_id 会导致图谱边重复或覆盖。
    for qid, count in Counter(link_ids).items():
        if qid and count > 1:
            issues.append(("严重", "question_knowledge_links.jsonl", "-", "duplicate_question_id", qid, "删除或合并重复记录"))

    # row_issues 用于生成 question_knowledge_links_review.md 中的“自检问题”列。
    row_issues = defaultdict(list)
    for row_index, row in enumerate(links, 1):
        qid = row.get("question_id", "")
        qnum = row.get("question_number", "")

        # 检查必需字段，避免后续统计时缺少状态、置信度或备注。
        missing_fields = sorted(REQUIRED_FIELDS - set(row))
        for field in missing_fields:
            problem = f"缺少字段: {field}"
            row_issues[qid].append(problem)
            issues.append(("严重", "question_knowledge_links.jsonl", row_index, "missing_field", f"Q{qnum} {problem}", "补齐必需字段"))

        label_status = row.get("label_status")
        confidence = row.get("confidence")

        # 状态和置信度必须使用固定枚举值，否则后续筛选会失效。
        if label_status not in VALID_LABEL_STATUS:
            problem = f"非法 label_status: {label_status}"
            row_issues[qid].append(problem)
            issues.append(("严重", "question_knowledge_links.jsonl", row_index, "bad_label_status", f"Q{qnum} {problem}", "改为规范状态值"))
        if confidence not in VALID_CONFIDENCE:
            problem = f"非法 confidence: {confidence}"
            row_issues[qid].append(problem)
            issues.append(("严重", "question_knowledge_links.jsonl", row_index, "bad_confidence", f"Q{qnum} {problem}", "改为 high/medium/low"))

        # 这些状态不一定是错误，但必须显式进入报告，方便用户优先人工复核。
        if label_status == "needs_review":
            problem = "status=needs_review"
            row_issues[qid].append(problem)
            issues.append(("警告", "question_knowledge_links.jsonl", row_index, "needs_review", f"Q{qnum} 需要人工复核", "人工确认知识点后改状态"))
        if label_status == "needs_taxonomy_expansion":
            problem = "needs_taxonomy_expansion"
            row_issues[qid].append(problem)
            issues.append(("提示", "question_knowledge_links.jsonl", row_index, "needs_taxonomy_expansion", f"Q{qnum} 需要扩展 taxonomy", "将高频 extra_tags 纳入 taxonomy"))
        if confidence == "low":
            problem = "confidence=low"
            row_issues[qid].append(problem)
            issues.append(("警告", "question_knowledge_links.jsonl", row_index, "low_confidence", f"Q{qnum} 低置信度标注", "人工确认或调整知识点"))

        kps = row.get("knowledge_points", [])
        if not isinstance(kps, list):
            problem = "knowledge_points 不是数组"
            row_issues[qid].append(problem)
            issues.append(("严重", "question_knowledge_links.jsonl", row_index, "bad_knowledge_points", f"Q{qnum} {problem}", "改为数组"))
            continue

        seen_kps = set()
        for kp in kps:
            triple = (kp.get("module"), kp.get("level1"), kp.get("level2"))
            role = kp.get("role")
            weight = kp.get("weight")

            # 同一道题重复绑定同一个知识点，会影响后续共现次数统计。
            if triple in seen_kps:
                problem = f"重复知识点: {format_kp(kp)}"
                row_issues[qid].append(problem)
                issues.append(("警告", "question_knowledge_links.jsonl", row_index, "duplicate_knowledge_point", f"Q{qnum} {problem}", "删除重复知识点"))
            seen_kps.add(triple)

            # 标准知识点必须能在 taxonomy 中找到，否则先修 taxonomy 或修关联路径。
            if triple not in taxonomy_triples:
                problem = f"taxonomy 中不存在: {format_kp(kp)}"
                row_issues[qid].append(problem)
                issues.append(("严重", "question_knowledge_links.jsonl", row_index, "missing_taxonomy_ref", f"Q{qnum} {problem}", "修正知识点路径或补充 taxonomy"))

            # 每个知识点必须说明在题目中的作用，否则图谱会退化成简单关联。
            if role not in VALID_KNOWLEDGE_ROLES:
                problem = f"缺少或非法 role: {role}"
                row_issues[qid].append(problem)
                issues.append(("严重", "question_knowledge_links.jsonl", row_index, "bad_knowledge_role", f"Q{qnum} {problem}", "改为 core_exam_point/supporting_knowledge/material_clue/background_knowledge"))

            if not isinstance(weight, (int, float)):
                problem = f"缺少或非法 weight: {weight}"
                row_issues[qid].append(problem)
                issues.append(("严重", "question_knowledge_links.jsonl", row_index, "bad_knowledge_weight", f"Q{qnum} {problem}", "补充 0 到 1 之间的数值权重"))
            elif not 0 <= float(weight) <= 1:
                problem = f"weight 超出 0-1: {weight}"
                row_issues[qid].append(problem)
                issues.append(("严重", "question_knowledge_links.jsonl", row_index, "knowledge_weight_out_of_range", f"Q{qnum} {problem}", "将权重调整到 0 到 1 之间"))
            elif role in RECOMMENDED_ROLE_WEIGHTS and abs(float(weight) - RECOMMENDED_ROLE_WEIGHTS[role]) > 0.25:
                problem = f"weight 与推荐角色权重差异较大: {ROLE_LABELS[role]} 推荐 {RECOMMENDED_ROLE_WEIGHTS[role]}"
                row_issues[qid].append(problem)
                issues.append(("提示", "question_knowledge_links.jsonl", row_index, "knowledge_weight_deviation", f"Q{qnum} {problem}", "确认是否为人工有意调整"))

        roles = [kp.get("role") for kp in kps if isinstance(kp, dict)]
        if kps and "core_exam_point" not in roles:
            problem = "缺少核心考点 core_exam_point"
            row_issues[qid].append(problem)
            issues.append(("严重", "question_knowledge_links.jsonl", row_index, "missing_core_exam_point", f"Q{qnum} {problem}", "至少标出这道题真正考查的核心知识点"))

        # 如果没有标准知识点，必须明确说明是 taxonomy 不够，而不是漏标。
        if not kps and label_status != "needs_taxonomy_expansion":
            problem = "knowledge_points 为空但未标记 needs_taxonomy_expansion"
            row_issues[qid].append(problem)
            issues.append(("警告", "question_knowledge_links.jsonl", row_index, "empty_knowledge_points", f"Q{qnum} {problem}", "补充知识点或改状态"))

    return {
        "exam_dir": exam_dir,
        "questions": questions,
        "answers": answers,
        "links": links,
        "issues": issues,
        "row_issues": row_issues,
    }


def write_review_md(result):
    """生成给用户人工检查的 Markdown 文件。

    知识点路径和备注会随着题目变长，使用分节结构可以避免 Obsidian 表格预览抖动。
    """
    exam_dir = result["exam_dir"]
    links = result["links"]
    row_issues = result["row_issues"]
    out_path = exam_dir / "question_knowledge_links_review.md"

    lines = [
        "# 题目知识点关联人工检查表",
        "",
        f"- 资料目录: `{exam_dir.relative_to(ROOT_DIR)}`",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 题目数: {len(links)}",
        "",
        "说明：本文件用于人工检查题目知识点关联，标准知识点按题目完整展开。",
        "",
    ]

    for row in links:
        qid = row.get("question_id", "")

        # 按角色展示知识点，便于判断题目真正考什么、解题需要什么、材料提供什么。
        kps = row.get("knowledge_points", [])
        extras = row.get("extra_tags", [])
        issues = row_issues.get(qid, [])
        lines.extend([
            f"## 第 {row.get('question_number', '')} 题",
            "",
            f"- question_id: `{qid}`",
            f"- 状态: `{row.get('label_status', '')}`",
            f"- 置信度: `{row.get('confidence', '')}`",
            f"- taxonomy_version: `{row.get('taxonomy_version', '')}`",
            f"- 备注: {row.get('note', '') or '无'}",
            "",
            "**标准知识点**",
            "",
            format_knowledge_by_role(kps),
            "",
            "**额外标签**",
            "",
            format_list_md(extras),
            "",
            "**自检问题**",
            "",
            format_list_md(issues),
            "",
        ])

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def write_structure_report(results, duplicate_level2):
    """汇总所有试卷的结构化自检报告。"""
    total_issues = sum(len(result["issues"]) for result in results)
    lines = [
        f"结构化校验时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"试卷目录数: {len(results)}",
        f"问题数: {total_issues}",
        "",
    ]

    if duplicate_level2:
        # 这里作为提醒，不计入问题数。因为不同模块下出现同名知识点是正常现象。
        lines.append("## Taxonomy 提醒")
        lines.append("")
        lines.append(f"- 二级知识点重名数量: {len(duplicate_level2)}")
        lines.append("- 重名不一定是错误，但后续统计和建图必须使用 module/level1/level2 完整路径。")
        lines.append("")

    for result in results:
        rel = result["exam_dir"].relative_to(ROOT_DIR)
        review_md = result["exam_dir"] / "question_knowledge_links_review.md"

        # 每份试卷单独成段，便于用户从总报告跳转回具体资料目录处理。
        lines.append(f"## {rel}")
        lines.append("")
        lines.append(f"- questions: {len(result['questions'])}")
        lines.append(f"- answers: {len(result['answers'])}")
        lines.append(f"- question_knowledge_links: {len(result['links'])}")
        lines.append(f"- 人工检查表: {review_md.relative_to(ROOT_DIR)}")
        if result["issues"]:
            lines.append("")
            for level, file_name, line_no, kind, detail, suggestion in result["issues"]:
                lines.append(f"- {level} | {file_name} | 行: {line_no} | {kind} | {detail} | 建议: {suggestion}")
        else:
            lines.append("- 未发现明显问题")
        lines.append("")

    report_path = CLEAN_DIR / "structure_report.txt"
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report_path, total_issues


def get_exam_dirs():
    """读取命令行参数，确定本次只检查哪一份或哪些试卷。"""
    parser = argparse.ArgumentParser(description="检查题目与知识点关联并生成人工检查表")
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
        if not (exam_dir / "question_knowledge_links.jsonl").exists():
            raise SystemExit(f"指定试卷目录缺少 question_knowledge_links.jsonl: {exam_dir}")
        return [exam_dir]

    exam_dirs = sorted(path.parent for path in QUESTIONS_DIR.rglob("question_knowledge_links.jsonl"))
    if not exam_dirs:
        raise SystemExit(f"未找到 question_knowledge_links.jsonl: {QUESTIONS_DIR}")
    return exam_dirs


def main():
    # 先加载所有 taxonomy 标准路径，再逐份试卷检查引用是否存在。
    taxonomy_triples, duplicate_level2 = load_taxonomy_triples()
    exam_dirs = get_exam_dirs()

    results = []
    for exam_dir in exam_dirs:
        # 每份试卷都生成自己的人工检查表，同时把问题交给总报告汇总。
        result = validate_exam_dir(exam_dir, taxonomy_triples)
        write_review_md(result)
        results.append(result)

    report_path, issue_count = write_structure_report(results, duplicate_level2)

    # 控制台输出保持简短，详细问题放在 structure_report.txt。
    print(f"结构化校验完成: {len(results)} 份资料")
    print(f"问题数: {issue_count}")
    print(f"报告文件: {report_path}")
    for result in results:
        print(f"人工检查表: {result['exam_dir'] / 'question_knowledge_links_review.md'}")


if __name__ == "__main__":
    main()
