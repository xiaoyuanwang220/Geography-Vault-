from collections import defaultdict
from pathlib import Path
from typing import Dict, List
import re

from .io_utils import read_jsonl, read_text, split_frontmatter
from .models import ExamRecord, QuestionRecord, TopicKey


def discover_exam_markdown_files(source_dir: Path) -> List[Path]:
    result: List[Path] = []
    for exam_dir in sorted(path for path in source_dir.iterdir() if path.is_dir()):
        markdown_files = sorted(
            path for path in exam_dir.glob("*.md") if not path.name.endswith("_review.md")
        )
        if not markdown_files:
            continue
        expected_name = f"{exam_dir.name}.md"
        preferred = next((path for path in markdown_files if path.name == expected_name), None)
        result.append(preferred or markdown_files[0])
    return result


def parse_year(value: object, fallback_text: str) -> int:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    match = re.search(r"(20\d{2}|19\d{2})", fallback_text)
    return int(match.group(1)) if match else 0


def normalize_region(value: object, title: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    for region in ("广东", "福建", "广西", "山东", "江苏", "浙江", "北京", "上海"):
        if region in title:
            return region
    return "未知地区"


def load_exam_records(source_dir: Path) -> Dict[str, ExamRecord]:
    exams: Dict[str, ExamRecord] = {}
    for md_path in discover_exam_markdown_files(source_dir):
        frontmatter, body = split_frontmatter(read_text(md_path))
        title = str(frontmatter.get("title") or md_path.stem)
        exams[title] = ExamRecord(
            title=title,
            year=parse_year(frontmatter.get("year"), title),
            region=normalize_region(frontmatter.get("region"), title),
            subject=str(frontmatter.get("subject") or "地理"),
            stage=str(frontmatter.get("stage") or "高考"),
            source_md_path=md_path,
            source_dir=md_path.parent,
            frontmatter=frontmatter,
            body=body,
        )
    return exams


def load_question_records(exams: Dict[str, ExamRecord]) -> Dict[str, QuestionRecord]:
    questions: Dict[str, QuestionRecord] = {}

    for exam in exams.values():
        questions_by_id: Dict[str, dict] = {}
        answers_by_id: Dict[str, dict] = {}
        explanations_by_id: Dict[str, dict] = {}
        topic_links_by_id: Dict[str, List[dict]] = defaultdict(list)

        for record in read_jsonl(exam.source_dir / "questions.jsonl"):
            questions_by_id[record["question_id"]] = record
        for record in read_jsonl(exam.source_dir / "answers.jsonl"):
            answers_by_id[record["question_id"]] = record
        for record in read_jsonl(exam.source_dir / "explanations.jsonl"):
            explanations_by_id[record["question_id"]] = record
        for record in read_jsonl(exam.source_dir / "question_knowledge_links.jsonl"):
            topic_links_by_id[record["question_id"]] = list(record.get("knowledge_points", []))

        exam_question_ids = sorted(
            questions_by_id.keys(),
            key=lambda qid: (
                int(questions_by_id[qid].get("question_number", 0) or 0),
                qid,
            ),
        )

        for question_id in exam_question_ids:
            q = questions_by_id[question_id]
            a = answers_by_id.get(question_id, {})
            e = explanations_by_id.get(question_id, {})
            question = QuestionRecord(
                question_id=question_id,
                question_number=str(q.get("question_number", "")),
                question_type=str(q.get("question_type", "")),
                exam_title=exam.title,
                year=exam.year,
                region=exam.region,
                exam_name=str(q.get("exam_name", exam.title)),
                stem_context=str(q.get("stem_context", "")),
                question_text=str(q.get("question_text", "")),
                option_context=str(q.get("option_context", "")),
                options=dict(q.get("options", {}) or {}),
                sub_questions=dict(q.get("sub_questions", {}) or {}),
                answer_type=str(a.get("answer_type", "")),
                answer=str(a.get("answer", "")),
                answer_parts=dict(a.get("answer_parts", {}) or {}),
                explanation_type=str(e.get("explanation_type", "")),
                explanation=str(e.get("explanation", "")),
                explanation_parts=dict(e.get("explanation_parts", {}) or {}),
                related_images=list(q.get("related_images", []) or []),
                source_dir=exam.source_dir,
                source_md=q.get("source_md"),
                source_span=q.get("source_span"),
                parse_confidence=str(q.get("parse_confidence", "")),
                note=str(q.get("note", "")),
            )

            for knowledge in topic_links_by_id.get(question_id, []):
                module = str(knowledge.get("module", "") or "").strip()
                level1 = str(knowledge.get("level1", "") or "").strip()
                level2 = str(knowledge.get("level2", "") or "").strip()
                key = TopicKey(module=module, level1=level1)
                question.topic_keys.add(key)
                question.topic_fine_points.setdefault(key, set())
                if level2:
                    question.fine_points.add(level2)
                    question.topic_fine_points[key].add(level2)

            questions[question_id] = question
            exam.question_ids.append(question_id)
            exam.topic_keys.update(question.topic_keys)

    return questions
