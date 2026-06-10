from pathlib import Path

from .io_utils import clear_generated_output, ensure_dir, sanitize_filename, write_text
from .render import (
    render_exam_index,
    render_exam_page,
    render_homepage,
    render_module_index,
    render_question_page,
    render_report,
    render_top_topic_index,
    render_topic_index,
    render_topic_page,
)
from .source import load_exam_records, load_question_records
from .transform import build_export_bundle, question_slug, topic_slug, topics_by_module


def ensure_output_structure(output_dir: Path) -> None:
    for name in ("01_试卷", "02_知识主题", "03_索引", "04_题目", "assets"):
        ensure_dir(output_dir / name)


def export_obsidian_vault(source_dir: Path, output_dir: Path) -> None:
    """
    整个导出流程只在这里编排。

    这样做的目的，是把“做什么”留在 pipeline，
    把“怎么读”“怎么算”“怎么写页面”分别留给 source/transform/render。
    """
    clear_generated_output(output_dir)
    ensure_output_structure(output_dir)

    exams = load_exam_records(source_dir)
    questions = load_question_records(exams)
    bundle = build_export_bundle(exams, questions)

    for exam in bundle.exams.values():
        exam_path = output_dir / "01_试卷" / f"{sanitize_filename(exam.title)}.md"
        write_text(exam_path, render_exam_page(exam, bundle, output_dir))

    for question in bundle.questions.values():
        write_text(
            output_dir / "04_题目" / f"{question_slug(question)}.md",
            render_question_page(question, bundle, output_dir),
        )

    for topic in bundle.topics.values():
        write_text(
            output_dir / "02_知识主题" / f"{topic_slug(topic.key)}.md",
            render_topic_page(topic, bundle),
        )

    write_text(output_dir / "03_索引" / "试卷索引.md", render_exam_index(bundle))
    write_text(output_dir / "03_索引" / "高频考点总览.md", render_top_topic_index(bundle))
    write_text(output_dir / "03_索引" / "知识主题总索引.md", render_topic_index(bundle))

    for module, topics in topics_by_module(bundle.topics).items():
        write_text(
            output_dir / "03_索引" / f"模块索引__{sanitize_filename(module)}.md",
            render_module_index(module, topics),
        )

    write_text(output_dir / "00_首页.md", render_homepage(bundle))
    write_text(output_dir / "obsidian_export_report.txt", render_report(bundle))
