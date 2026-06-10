from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class TopicKey:
    """知识主题固定到 module + level1，避免页面粒度过碎。"""

    module: str
    level1: str

    @property
    def title(self) -> str:
        return self.level1 or self.module or "未命名知识主题"


@dataclass
class QuestionRecord:
    question_id: str
    question_number: str
    question_type: str
    exam_title: str
    year: int
    region: str
    exam_name: str
    stem_context: str
    question_text: str
    option_context: str
    options: Dict[str, str]
    sub_questions: Dict[str, str]
    answer_type: str
    answer: str
    answer_parts: Dict[str, str]
    explanation_type: str
    explanation: str
    explanation_parts: Dict[str, str]
    related_images: List[str]
    fine_points: Set[str] = field(default_factory=set)
    topic_fine_points: Dict[TopicKey, Set[str]] = field(default_factory=dict)
    topic_keys: Set[TopicKey] = field(default_factory=set)
    source_dir: Optional[Path] = None
    source_md: Optional[str] = None
    source_span: Optional[dict] = None
    parse_confidence: str = ""
    note: str = ""


@dataclass
class ExamRecord:
    title: str
    year: int
    region: str
    subject: str
    stage: str
    source_md_path: Path
    source_dir: Path
    frontmatter: Dict[str, object]
    body: str
    question_ids: List[str] = field(default_factory=list)
    topic_keys: Set[TopicKey] = field(default_factory=set)


@dataclass
class TopicRecord:
    key: TopicKey
    question_ids: List[str] = field(default_factory=list)
    fine_points: Set[str] = field(default_factory=set)
    question_fine_points: Dict[str, Set[str]] = field(default_factory=dict)
    regions: Set[str] = field(default_factory=set)
    years: Set[int] = field(default_factory=set)
    exam_titles: Set[str] = field(default_factory=set)

    @property
    def question_count(self) -> int:
        return len(self.question_ids)

    @property
    def exam_count(self) -> int:
        return len(self.exam_titles)


@dataclass
class ExportBundle:
    exams: Dict[str, ExamRecord]
    questions: Dict[str, QuestionRecord]
    topics: Dict[TopicKey, TopicRecord]
    missing_images: List[str]
