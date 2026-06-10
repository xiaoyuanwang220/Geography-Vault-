import re
import shutil
from pathlib import Path
from typing import Dict, List

from .io_utils import dump_frontmatter, ensure_dir, sanitize_filename
from .models import ExamRecord, ExportBundle, QuestionRecord, TopicKey, TopicRecord
from .transform import (
    dedupe_preserve_order,
    grouped_exams_by_region,
    question_slug,
    question_summary,
    top_topics,
    topic_slug,
    topics_by_module,
)


IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def markdown_link(target: str, label: str) -> str:
    return f"[[{target}|{label}]]"


def markdown_table_link(target: str, label: str) -> str:
    """
    表格里不要使用 Obsidian 的别名链接 `[[path|label]]`。
    因为其中的 `|` 会被 Markdown 表格当作分列符，导致“知识主题 / 题目数 / 覆盖试卷数”错位。
    这里统一改成普通 Markdown 链接，后续如果索引目录层级变化，只需要改这个函数。
    """
    return f"[{label}](../{target}.md)"


def format_year_span(years: List[int]) -> str:
    if not years:
        return "暂无"
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]} - {years[-1]}"


def copy_exam_asset(question_or_exam_source_dir: Path, image_path: str, output_dir: Path, asset_dir_name: str, missing_images: List[str]) -> str:
    normalized_relative = image_path.replace("\\", "/")
    source_image = question_or_exam_source_dir / Path(normalized_relative)
    if not source_image.exists():
        missing_images.append(f"{asset_dir_name}: {normalized_relative}")
        return image_path.replace("\\", "/")

    target_asset_dir = output_dir / "assets" / asset_dir_name
    ensure_dir(target_asset_dir)
    target_image = target_asset_dir / source_image.name
    shutil.copy2(source_image, target_image)
    relative_path = Path("..") / "assets" / asset_dir_name / source_image.name
    return relative_path.as_posix()


def rewrite_exam_body_images(exam: ExamRecord, output_dir: Path, missing_images: List[str]) -> str:
    asset_dir_name = sanitize_filename(exam.title)

    def replace(match: re.Match) -> str:
        alt_text = match.group(1) or "图片"
        raw_path = match.group(2).strip()
        if "://" in raw_path or raw_path.startswith("#"):
            return match.group(0)
        converted = copy_exam_asset(exam.source_dir, raw_path, output_dir, asset_dir_name, missing_images)
        return f"![{alt_text}]({converted})"

    return IMAGE_PATTERN.sub(replace, exam.body)


def topic_target(key: TopicKey) -> str:
    return f"02_知识主题/{topic_slug(key)}"


def question_target(question: QuestionRecord) -> str:
    return f"04_题目/{question_slug(question)}"


def render_exam_page(exam: ExamRecord, bundle: ExportBundle, output_dir: Path) -> str:
    frontmatter = dict(exam.frontmatter)
    frontmatter.update(
        {
            "title": exam.title,
            "type": "exam",
            "region": exam.region,
            "year": exam.year,
            "subject": exam.subject,
            "stage": exam.stage,
            "tags": dedupe_preserve_order(["高考", exam.subject, exam.region]),
            "obsidian_export": True,
        }
    )

    topic_links = [
        markdown_link(topic_target(key), key.title)
        for key in sorted(exam.topic_keys, key=lambda item: (item.module, item.level1))
    ]

    lines = [f"# {exam.title}", ""]
    lines.extend(["## 关联知识主题", "", " ".join(topic_links) if topic_links else "暂无", ""])
    lines.extend(["## 题目导航", ""])
    for question_id in exam.question_ids:
        question = bundle.questions[question_id]
        summary = question_summary(question)
        lines.append(
            f"- {markdown_link(question_target(question), f'第{question.question_number}题')}：{summary}"
        )
    lines.extend(["", "## 试卷原文", "", rewrite_exam_body_images(exam, output_dir, bundle.missing_images).strip(), ""])
    return dump_frontmatter(frontmatter) + "\n".join(lines).strip() + "\n"


def render_question_page(question: QuestionRecord, bundle: ExportBundle, output_dir: Path) -> str:
    frontmatter = {
        "title": f"{question.exam_title} 第{question.question_number}题",
        "type": "question",
        "question_id": question.question_id,
        "question_number": question.question_number,
        "question_type": question.question_type,
        "region": question.region,
        "year": question.year,
        "subject": "地理",
        "obsidian_export": True,
    }

    topic_links = [
        markdown_link(topic_target(key), key.title)
        for key in sorted(question.topic_keys, key=lambda item: (item.module, item.level1))
    ]
    fine_points = sorted(question.fine_points)

    lines = [f"# {question.exam_title} 第{question.question_number}题", ""]
    lines.extend(["## 来源试卷", "", f"- {markdown_link(f'01_试卷/{sanitize_filename(question.exam_title)}', question.exam_title)}", ""])
    lines.extend(["## 关联知识主题", "", " ".join(topic_links) if topic_links else "暂无", ""])
    lines.extend(["## 细知识点", "", "、".join(fine_points) if fine_points else "暂无", ""])
    lines.extend(["## 题目元信息", ""])
    lines.append(f"- 题型：{question.question_type or '未知'}")
    lines.append(f"- 解析置信度：{question.parse_confidence or '未知'}")
    if question.source_span:
        lines.append(f"- 原文定位：第{question.source_span.get('start_line', '?')}行 - 第{question.source_span.get('end_line', '?')}行")
    if question.note:
        lines.append(f"- 备注：{question.note}")
    lines.append("")

    if question.stem_context:
        lines.extend(["## 题目材料", "", question.stem_context, ""])

    lines.extend(["## 题目", ""])
    lines.append(question.question_text or "暂无题干")
    lines.append("")

    if question.options:
        lines.extend(["### 选项", ""])
        if question.option_context:
            lines.append(question.option_context)
            lines.append("")
        for option_key, option_value in question.options.items():
            lines.append(f"- {option_key}. {option_value}")
        lines.append("")

    if question.sub_questions:
        lines.extend(["### 小问", ""])
        for index, text in sorted(question.sub_questions.items(), key=lambda item: item[0]):
            lines.append(f"- （{index}）{text}")
        lines.append("")

    if question.related_images:
        lines.extend(["## 相关图片", ""])
        asset_dir_name = sanitize_filename(question.exam_title)
        for image_path in question.related_images:
            converted = copy_exam_asset(question.source_dir, image_path, output_dir, asset_dir_name, bundle.missing_images)
            lines.append(f"![图片]({Path('..').joinpath(converted).as_posix() if not converted.startswith('..') else converted})")
        lines.append("")

    lines.extend(["## 答案", ""])
    if question.answer_parts:
        for index, text in sorted(question.answer_parts.items(), key=lambda item: item[0]):
            lines.append(f"- （{index}）{text}")
    else:
        lines.append(question.answer or "暂无答案")
    lines.append("")

    lines.extend(["## 解析", ""])
    if question.explanation_parts:
        for index, text in sorted(question.explanation_parts.items(), key=lambda item: item[0]):
            lines.append(f"### （{index}）")
            lines.append("")
            lines.append(text)
            lines.append("")
    else:
        lines.append(question.explanation or "暂无解析")
        lines.append("")

    lines.extend(["## 教学备注（预留）", "", "- 易错点：", "- 课堂提示：", "- 讲解建议：", ""])
    return dump_frontmatter(frontmatter) + "\n".join(lines).strip() + "\n"


def render_topic_page(topic: TopicRecord, bundle: ExportBundle) -> str:
    frontmatter = {
        "title": topic.key.title,
        "type": "knowledge_topic",
        "module": topic.key.module,
        "level1": topic.key.level1,
        "question_count": topic.question_count,
        "exam_count": topic.exam_count,
        "tags": ["知识主题", "地理", topic.key.module],
        "obsidian_export": True,
    }

    lines = [f"# {topic.key.title}", ""]
    lines.extend(["## 所属模块", "", markdown_link(f"03_索引/模块索引__{sanitize_filename(topic.key.module)}", topic.key.module), ""])
    lines.extend(["## 统计概览", ""])
    years = sorted(topic.years, reverse=True)
    lines.append(f"- 题目数：{topic.question_count}")
    lines.append(f"- 覆盖试卷数：{topic.exam_count}")
    lines.append(f"- 涉及地区：{'、'.join(sorted(topic.regions)) if topic.regions else '暂无'}")
    lines.append(f"- 涉及年份：{format_year_span(years)}")
    lines.append("")

    lines.extend(["## 下属细知识点", "", "、".join(sorted(topic.fine_points)) if topic.fine_points else "暂无", ""])
    lines.extend(["## 关联题目（专题卷）", ""])
    for question_id in topic.question_ids:
        question = bundle.questions[question_id]
        lines.append(
            f"- {markdown_link(question_target(question), f'{question.region}{question.year} 第{question.question_number}题')}：{question_summary(question, max_length=90)}"
        )
        lines.append(f"  - 来源试卷：{markdown_link(f'01_试卷/{sanitize_filename(question.exam_title)}', question.exam_title)}")
        topic_points = sorted(topic.question_fine_points.get(question.question_id, set()))
        if topic_points:
            lines.append(f"  - 细知识点：{'、'.join(topic_points)}")
    lines.extend(["", "## 教学备注（预留）", "", "- 常见误区：", "- 课堂串讲线索：", "- 可延伸到的教材章节：", ""])
    return dump_frontmatter(frontmatter) + "\n".join(lines).strip() + "\n"


def render_exam_index(bundle: ExportBundle) -> str:
    lines = ["# 试卷索引", ""]
    grouped = grouped_exams_by_region(bundle.exams)
    for region, exams in grouped.items():
        lines.extend([f"## {region}", ""])
        for exam in exams:
            lines.append(f"- {markdown_link(f'01_试卷/{sanitize_filename(exam.title)}', exam.title)}（{exam.year}）")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_top_topic_index(bundle: ExportBundle) -> str:
    lines = ["# 高频考点总览", "", "| 知识主题 | 题目数 | 覆盖试卷数 |", "| --- | ---: | ---: |"]
    for topic in top_topics(bundle.topics):
        lines.append(
            f"| {markdown_table_link(topic_target(topic.key), topic.key.title)} | {topic.question_count} | {topic.exam_count} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_topic_index(bundle: ExportBundle) -> str:
    lines = ["# 知识主题总索引", ""]
    for module in topics_by_module(bundle.topics):
        lines.append(f"- {markdown_link(f'03_索引/模块索引__{sanitize_filename(module)}', module)}")
    lines.append("")
    return "\n".join(lines)


def render_module_index(module: str, topics: List[TopicRecord]) -> str:
    lines = [f"# {module}", "", "| 知识主题 | 题目数 | 覆盖试卷数 |", "| --- | ---: | ---: |"]
    for topic in topics:
        lines.append(
            f"| {markdown_table_link(topic_target(topic.key), topic.key.title)} | {topic.question_count} | {topic.exam_count} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_homepage(bundle: ExportBundle) -> str:
    lines = [
        "# 地理知识图谱",
        "",
        f"- 试卷数：{len(bundle.exams)}",
        f"- 知识主题数：{len(bundle.topics)}",
        f"- 题目数：{len(bundle.questions)}",
        "",
        "## 主入口",
        "",
        f"- {markdown_link('03_索引/高频考点总览', '高频考点总览')}",
        f"- {markdown_link('03_索引/试卷索引', '试卷索引')}",
        f"- {markdown_link('03_索引/知识主题总索引', '知识主题总索引')}",
        "",
        "## 使用说明",
        "",
        "1. 先看高频考点总览，找到高频知识主题。",
        "2. 进入知识主题页，浏览对应题组摘要与统计。",
        "3. 需要完整材料、答案和解析时，点进单题页。",
        "",
    ]
    return "\n".join(lines)


def render_report(bundle: ExportBundle) -> str:
    lines = [
        f"导出试卷数: {len(bundle.exams)}",
        f"导出知识主题数: {len(bundle.topics)}",
        f"导出单题页数: {len(bundle.questions)}",
        f"缺失图片数: {len(bundle.missing_images)}",
        "",
    ]
    if bundle.missing_images:
        lines.append("缺失图片明细:")
        for item in bundle.missing_images:
            lines.append(f"- {item}")
    else:
        lines.append("未发现缺失图片。")
    lines.append("")
    return "\n".join(lines)
