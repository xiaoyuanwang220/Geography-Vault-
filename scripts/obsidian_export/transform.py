from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from .io_utils import sanitize_filename
from .models import ExamRecord, ExportBundle, QuestionRecord, TopicKey, TopicRecord


def build_topics(questions: Dict[str, QuestionRecord]) -> Dict[TopicKey, TopicRecord]:
    topics: Dict[TopicKey, TopicRecord] = {}
    for question in questions.values():
        for key in sorted(question.topic_keys, key=lambda item: (item.module, item.level1)):
            topic = topics.setdefault(key, TopicRecord(key=key))
            topic.question_ids.append(question.question_id)
            own_points = question.topic_fine_points.get(key, set())
            topic.fine_points.update(own_points)
            topic.question_fine_points.setdefault(question.question_id, set()).update(own_points)
            topic.regions.add(question.region)
            topic.years.add(question.year)
            topic.exam_titles.add(question.exam_title)
    for topic in topics.values():
        topic.question_ids.sort(
            key=lambda qid: (
                -questions[qid].year,
                questions[qid].region,
                int(questions[qid].question_number or 0),
            )
        )
    return topics


def build_export_bundle(exams: Dict[str, ExamRecord], questions: Dict[str, QuestionRecord]) -> ExportBundle:
    return ExportBundle(
        exams=exams,
        questions=questions,
        topics=build_topics(questions),
        missing_images=[],
    )


def topic_slug(key: TopicKey) -> str:
    return sanitize_filename(f"{key.module}__{key.level1}")


def question_slug(question: QuestionRecord) -> str:
    return sanitize_filename(f"{question.exam_title}__Q{question.question_number}")


def module_sort_key(module: str) -> Tuple[str, str]:
    return (module or "未分类", module or "未分类")


def exam_sort_key(exam: ExamRecord) -> Tuple[str, int, str]:
    return (exam.region, -exam.year, exam.title)


def question_summary(question: QuestionRecord, max_length: int = 80) -> str:
    """
    主题页默认只展示摘要，避免一个主题页直接爆成长卷。
    """
    if question.question_type == "constructed_response" and question.sub_questions:
        joined = "；".join(
            f"({index}){text}" for index, text in sorted(question.sub_questions.items(), key=lambda item: item[0])
        )
        base = joined
    else:
        base = question.question_text
    compact = " ".join(base.split())
    return compact if len(compact) <= max_length else compact[: max_length - 1] + "…"


def dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def grouped_exams_by_region(exams: Dict[str, ExamRecord]) -> Dict[str, List[ExamRecord]]:
    grouped: Dict[str, List[ExamRecord]] = defaultdict(list)
    for exam in exams.values():
        grouped[exam.region].append(exam)
    for region in grouped:
        grouped[region].sort(key=lambda exam: (-exam.year, exam.title))
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def top_topics(topics: Dict[TopicKey, TopicRecord]) -> List[TopicRecord]:
    return sorted(
        topics.values(),
        key=lambda topic: (-topic.question_count, -topic.exam_count, topic.key.title),
    )


def topics_by_module(topics: Dict[TopicKey, TopicRecord]) -> Dict[str, List[TopicRecord]]:
    grouped: Dict[str, List[TopicRecord]] = defaultdict(list)
    for topic in topics.values():
        grouped[topic.key.module or "未分类"].append(topic)
    for module in grouped:
        grouped[module].sort(key=lambda topic: (-topic.question_count, -topic.exam_count, topic.key.title))
    return dict(sorted(grouped.items(), key=lambda item: item[0]))
