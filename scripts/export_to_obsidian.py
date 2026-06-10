import argparse
from pathlib import Path

from obsidian_export.pipeline import export_obsidian_vault


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT_DIR / "clean_data" / "questions"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "obsidian_vault"


def build_parser() -> argparse.ArgumentParser:
    """CLI 入口保持很薄，只负责收参数并调导出流程。"""
    parser = argparse.ArgumentParser(
        description="把 clean_data/questions 下的结构化题库导出成 Obsidian 知识库"
    )
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE_DIR),
        help="输入目录，默认指向 clean_data/questions",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认指向 obsidian_vault",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    source_dir = Path(args.source)
    output_dir = Path(args.output)

    if not source_dir.exists():
        raise SystemExit(f"输入目录不存在: {source_dir}")

    export_obsidian_vault(source_dir=source_dir, output_dir=output_dir)
    print(f"导出完成，输出目录: {output_dir}")


if __name__ == "__main__":
    main()
