import json
import re
import shutil
from pathlib import Path
from typing import Dict, Iterator, List, Tuple


FRONTMATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n*", re.DOTALL)
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return iter(())
    lines = [line.strip() for line in read_text(path).splitlines() if line.strip()]
    return (json.loads(line) for line in lines)


def sanitize_filename(name: str) -> str:
    """把标题转换成可稳定落盘的文件名。"""
    cleaned = name.strip()
    for char in INVALID_FILENAME_CHARS:
        cleaned = cleaned.replace(char, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "未命名"


def split_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    match = FRONTMATTER_PATTERN.match(normalized)
    if not match:
        return {}, normalized.strip() + "\n"
    frontmatter = parse_simple_frontmatter(match.group(1))
    body = normalized[match.end():].strip() + "\n"
    return frontmatter, body


def parse_scalar(value: str) -> object:
    text = value.strip()
    if not text:
        return ""
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse_simple_frontmatter(frontmatter_text: str) -> Dict[str, object]:
    """
    只解析当前项目够用的 YAML 子集。

    这样做的原因很实际：当前环境没有 PyYAML，脚本要保持零额外依赖。
    """
    result: Dict[str, object] = {}
    current_list_key = None
    for raw_line in frontmatter_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("- ") and current_list_key:
            result.setdefault(current_list_key, [])
            result[current_list_key].append(parse_scalar(stripped[2:]))
            continue

        current_list_key = None
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            result[key] = []
            current_list_key = key
        else:
            result[key] = parse_scalar(value)
    return result


def yaml_escape_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def yaml_format_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return '""'
    return yaml_escape_string(str(value))


def dump_frontmatter(data: Dict[str, object]) -> str:
    lines: List[str] = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {yaml_format_scalar(item)}")
        else:
            lines.append(f"{key}: {yaml_format_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def clear_generated_output(output_dir: Path) -> None:
    """
    只清理脚本自己管理的目录，不碰 .obsidian。

    这样用户已经调好的 Obsidian 设置可以安全保留。
    """
    managed_names = [
        "01_试卷",
        "02_知识主题",
        "02_知识点",
        "03_索引",
        "04_题目",
        "assets",
        "obsidian_export_report.txt",
        "00_首页.md",
    ]
    for name in managed_names:
        target = output_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
