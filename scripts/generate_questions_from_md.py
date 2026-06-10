#!/usr/bin/env python3
"""
根据已清洗的 .md 试卷文件，生成 questions.jsonl。
用法: python generate_questions_from_md.py --exam-dir "路径"
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def parse_md_frontmatter(text):
    """提取 YAML frontmatter。"""
    m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            key, val = line.split(':', 1)
            meta[key.strip()] = val.strip().strip('"')
    return meta


def extract_exam_name(md_path):
    """从文件名或 frontmatter 获取试卷名。"""
    p = Path(md_path) if not isinstance(md_path, Path) else md_path
    name = p.stem  # 文件名去掉 .md
    return name


def find_related_images(text, image_dir, images_in_text=None):
    """从文本中提取引用的图片路径。"""
    if images_in_text is None:
        images_in_text = set()
    # 找到所有 images\xx.png 引用
    refs = re.findall(r'images[\\/]image_(\d+)\.png', text)
    return sorted(set([f"images/image_{r}.png" for r in refs]))


def parse_questions_from_md(md_text, meta, md_rel_path):
    """
    解析 MD 文本，返回 questions 列表。
    格式：山东高考地理 15 选择题 + 4 非选择题（或广西 16 选择题 + 3 非选择题）
    """
    year = meta.get("year", "2025")
    subject = meta.get("subject", "地理")
    stage = meta.get("stage", "高考")
    region = meta.get("region", "")
    source_file = meta.get("source_file", "")

    questions = []

    # ---- 分割文本为"题目区域"和"答案解析区域" ----
    # 找到 【答案】 标记作为分界
    answers_section_match = re.search(r'【答案】', md_text)

    # ---- 提取题目区域（答案区域之前）----
    if answers_section_match:
        question_text_area = md_text[:answers_section_match.start()]
    else:
        question_text_area = md_text

    # ---- 1. 提取选择题 ----
    # 匹配选择题题号格式: "数字. 题干内容\nA. ... B. ... C. ... D. ..."
    # 非选择题: "数字. 阅读材料..." 后面跟着 (1) (2) 等

    # 先找到所有题号
    # 选择题: 数字. 后跟选项 A/B/C/D
    # 非选择题: 数字. 后跟"阅读"或"材料"

    lines = md_text.split('\n')
    full_text = '\n'.join(lines)

    # 提取所有图片引用及其位置，用于确定每道题关联的图片
    img_positions = [(m.start(), m.group()) for m in re.finditer(r'!\[图片\]\(images[\\/]image_\d+\.png\)', full_text)]

    def get_images_for_range(start, end):
        """获取某段文本范围内出现的图片。"""
        imgs = []
        for pos, img_ref in img_positions:
            if start <= pos <= end:
                m = re.search(r'(images[\\/]image_\d+\.png)', img_ref)
                if m:
                    imgs.append(m.group(1).replace('\\', '/'))
        return sorted(set(imgs))

    # 找到选择题和非选择题的分界线
    # 山东: "二、非选择题" 
    # 广西: "二、非选择题"
    non_choice_match = re.search(r'二、非选择题', full_text)
    if non_choice_match:
        choice_section = full_text[:non_choice_match.start()]
        non_choice_section = full_text[non_choice_match.start():]
    else:
        choice_section = full_text
        non_choice_section = ""

    # ---- 提取选择题 ----
    # 匹配: 数字. 题干...\n选项行
    # 需要处理带"阅读材料，完成下列要求"格式的题组题干(stem_context)

    # 先提取所有选择题题号的位置
    choice_pattern = re.compile(
        r'^(\d+)\.\s+(.*?)(?=\n\d+\.\s|\n【答案】|\n二、非选择题|\Z)',
        re.MULTILINE | re.DOTALL
    )

    # 使用更精确的方式解析选择题
    # 先找到所有题目编号
    all_question_starts = list(re.finditer(r'\n(\d+)\.\s', full_text))

    # 还需要找到题组引言（题干材料）的位置
    # 题组引言出现在题号之前，通常是较长的段落描述+图片

    stem_contexts = {}  # question_number -> stem_context

    # 提取选择题组的stem_context
    # 策略：对于每个题组（1-3题, 4-5题, 6-7题等），题组的stem_context是该题组第一题之前的材料文本
    
    # 先识别非选择题题号
    non_choice_q_nums = set()
    if non_choice_section:
        non_choice_matches = list(re.finditer(r'^(\d+)\.\s', non_choice_section, re.MULTILINE))
        for m in non_choice_matches:
            non_choice_q_nums.add(int(m.group(1)))

    # 解析每个选择题
    choice_questions = []

    for i, qm in enumerate(all_question_starts):
        q_num = int(qm.group(1))
        if q_num in non_choice_q_nums:
            continue
        if q_num > 20:  # 基本安全上限
            continue

        q_start = qm.start()

        # 题目文本范围
        if i + 1 < len(all_question_starts):
            q_end = all_question_starts[i + 1].start()
        else:
            q_end = len(full_text)

        q_block = full_text[q_start:q_end]

        # 提取题干文本和选项
        # 选择题格式: "数字. 题干\n\nA. ... B. ... C. ... D. ..."
        # 或者 "数字. 题干\nA. ①②B. ②③C. ①④D. ③④"

        # 提取 question_text（选项之前）
        # 选项行可能紧跟题干或换行
        option_match = re.search(r'\nA\.\s', q_block)
        if option_match:
            q_text = q_block[len(f"{q_num}. "):option_match.start()].strip()
            options_block = q_block[option_match.start():]
        else:
            q_text = q_block[len(f"{q_num}. "):].strip()
            options_block = ""

        # 清理题干中的图片引用（保留在 related_images 中）
        q_text_clean = re.sub(r'!\[图片\]\(images[\\/]image_\d+\.png\)\n?', '', q_text).strip()
        
        # 移除尾部的换行和多余空白
        q_text_clean = q_text_clean.strip()

        # 提取选项
        options = {}
        if options_block:
            # 清理图片引用
            options_block_clean = re.sub(r'!\[图片\]\(images[\\/]image_\d+\.png\)\s*', '', options_block).strip()
            # 选项格式：A. 内容B. 内容C. 内容D. 内容（可能同行）
            # 或者分行：\nA. 内容\nB. 内容\nC. 内容\nD. 内容
            # 用前瞻断言拆分: 每个选项以 A./B./C./D. 开头
            opt_matches = re.findall(r'([A-D])\.\s*(.*?)(?=[A-D]\.|\n\n|\Z)', options_block_clean, re.DOTALL)
            for opt_letter, opt_content in opt_matches:
                opt_content = opt_content.strip().rstrip('\n').strip()
                options[opt_letter] = opt_content

        # 确定 stem_context
        # 对于题组中非第一题，使用简短引用
        # 对于第一题，取题号之前的材料文本
        
        # 查找该题组的起始材料
        # 查找本题之前的最近一个"据此完成下面小题"或"完成下列要求"或较长的材料段落
        before_text = full_text[:q_start]
        
        # 寻找最近的题组材料起始位置
        # 题组通常以图片或大段文字开始，以"据此完成下面小题"结尾
        # 我们找到该题之前的最后一个 "据此完成下面小题" 或 "完成下列要求" 的位置
        
        stem_markers = list(re.finditer(r'(据此完成下面小题|完成下列要求|完成下面小题)', before_text))
        if stem_markers:
            last_marker = stem_markers[-1]
            # 材料从上一个答案解析之后开始
            prev_answer = list(re.finditer(r'【点睛】', before_text[:last_marker.start()]))
            if prev_answer:
                stem_start = prev_answer[-1].end()
            else:
                stem_start = 0
            stem_text = before_text[stem_start:last_marker.end()].strip()
        else:
            stem_text = ""

        # 清理 stem_context 中的图片引用
        stem_text_clean = re.sub(r'!\[图片\]\(images[\\/]image_\d+\.png\)\s*', '', stem_text).strip()
        # 截断过长的 stem_context
        if len(stem_text_clean) > 600:
            stem_text_clean = stem_text_clean[:600] + "..."

        # 找到同一题组的第一题
        # 同一题组的题目共享 stem_context
        # 判断：如果本题之前没有"据此完成下面小题"之类的标记在上一题之后，说明是同一题组
        # 简化处理：如果 stem_text 一样，则同一题组
        
        # 获取相关图片
        related_imgs = get_images_for_range(q_start, q_end)

        choice_questions.append({
            "question_number": str(q_num),
            "question_text": q_text_clean,
            "options": options,
            "stem_context": stem_text_clean,
            "related_images": related_imgs,
            "q_start": q_start,
            "q_end": q_end,
        })

    # ---- 为选择题分组设置 stem_context ----
    # 同一题组（连续的题号共享同一个 stem_context）的后续题只保留简短引用
    grouped_stems = {}
    for cq in choice_questions:
        sc = cq["stem_context"]
        if sc not in grouped_stems:
            grouped_stems[sc] = cq["question_number"]
        else:
            # 后续题使用简短版本
            first_num = grouped_stems[sc]
            cq["stem_context_short"] = f"材料题组（见第{first_num}题）。"

    # ---- 2. 提取非选择题 ----
    non_choice_questions = []

    if non_choice_section:
        # 非选择题格式: "数字. 阅读材料/图文材料...\n\n（1）...\n（2）..."
        nc_matches = list(re.finditer(r'^(\d+)\.\s+(.*?)(?=\n\d+\.\s|\Z)', non_choice_section, re.MULTILINE | re.DOTALL))

        for nc_m in nc_matches:
            q_num = int(nc_m.group(1))
            q_block = nc_m.group(0)

            # 提取 question_text（通常是"阅读材料，完成下列要求。"）
            # 提取 sub_questions
            q_text_match = re.search(r'^\d+\.\s+(.*?)(?=\n（\d+）|\Z)', q_block, re.DOTALL)
            if q_text_match:
                q_text_raw = q_text_match.group(1).strip()
            else:
                q_text_raw = q_block.split('.', 1)[1].strip() if '.' in q_block else q_block

            q_text_clean = re.sub(r'!\[图片\]\(images[\\/]image_\d+\.png\)\s*', '', q_text_raw).strip()

            # 提取小问 —— 只在【答案】之前的部分提取
            sub_qs = {}
            # 截取【答案】之前的文本
            ans_idx = q_block.find('【答案】')
            q_block_before_ans = q_block[:ans_idx] if ans_idx != -1 else q_block
            sq_matches = re.finditer(r'（(\d+)）\s*(.*?)(?=（\d+）|\Z)', q_block_before_ans, re.DOTALL)
            for sq_m in sq_matches:
                sq_num = sq_m.group(1)
                sq_text = sq_m.group(2).strip()
                # 清理图片引用
                sq_text = re.sub(r'!\[图片\]\(images[\\/]image_\d+\.png\)\s*', '', sq_text).strip()
                if sq_text:  # 只保留非空的
                    sub_qs[sq_num] = sq_text

            # stem_context: 非选择题的材料（题目之前的文本）
            nc_start = nc_m.start() + non_choice_match.start()  # 在全文中的位置
            nc_end = nc_start + len(q_block)

            # stem_context = question_text_raw 去掉图片
            stem_text = q_text_clean[:600] if len(q_text_clean) > 600 else q_text_clean

            # 相关图片
            nc_full_start = full_text.find(q_block)
            if nc_full_start == -1:
                nc_full_start = nc_start
            nc_full_end = nc_full_start + len(q_block)
            related_imgs = get_images_for_range(nc_full_start, nc_full_end)

            non_choice_questions.append({
                "question_number": str(q_num),
                "question_text": q_text_clean if q_text_clean else "阅读材料，完成下列要求。",
                "sub_questions": sub_qs,
                "stem_context": stem_text,
                "related_images": related_imgs,
            })

    # ---- 组装最终结构 ----
    exam_name = Path(md_rel_path).stem
    prefix_parts = [year]
    if region:
        prefix_parts.append(region)
    prefix_parts.append(subject)
    prefix_parts.append(exam_name)
    prefix = "-".join(prefix_parts)

    result = []

    for cq in choice_questions:
        sc = cq.get("stem_context_short", cq["stem_context"])
        rec = {
            "question_id": f"{prefix}-Q{cq['question_number']}",
            "question_number": cq["question_number"],
            "question_type": "single_choice",
            "source_md": md_rel_path,
            "source_file": source_file,
            "subject": subject,
            "year": year,
            "region": region,
            "stage": stage,
            "exam_name": meta.get("title", exam_name),
            "stem_context": sc,
            "question_text": cq["question_text"],
            "options": cq["options"],
            "related_images": cq["related_images"],
            "status": "structured",
        }
        # 检查选项完整性
        if set(rec["options"].keys()) != {"A", "B", "C", "D"}:
            rec["status"] = "needs_review"
        if not rec["question_text"]:
            rec["status"] = "needs_review"
        result.append(rec)

    for nq in non_choice_questions:
        rec = {
            "question_id": f"{prefix}-Q{nq['question_number']}",
            "question_number": nq["question_number"],
            "question_type": "constructed_response",
            "source_md": md_rel_path,
            "source_file": source_file,
            "subject": subject,
            "year": year,
            "region": region,
            "stage": stage,
            "exam_name": meta.get("title", exam_name),
            "stem_context": nq["stem_context"],
            "question_text": nq["question_text"],
            "sub_questions": nq["sub_questions"],
            "related_images": nq["related_images"],
            "status": "structured",
        }
        if not rec["sub_questions"]:
            rec["status"] = "needs_review"
        result.append(rec)

    # 按题号排序
    result.sort(key=lambda x: int(x["question_number"]))
    return result


def main():
    parser = argparse.ArgumentParser(description="从 MD 试卷生成 questions.jsonl")
    parser.add_argument("--exam-dir", required=True, help="试卷目录路径")
    args = parser.parse_args()

    exam_dir = Path(args.exam_dir)
    if not exam_dir.is_dir():
        print(f"错误: 目录不存在: {exam_dir}", file=sys.stderr)
        sys.exit(1)

    # 找到 .md 文件
    md_files = list(exam_dir.glob("*.md"))
    # 排除 *_review.md
    md_files = [f for f in md_files if not f.name.endswith('_review.md')]

    if not md_files:
        print(f"错误: 目录下没有 .md 文件: {exam_dir}", file=sys.stderr)
        sys.exit(1)

    # 检查是否已有 questions.jsonl
    jsonl_path = exam_dir / "questions.jsonl"
    if jsonl_path.exists() and jsonl_path.stat().st_size > 0:
        print(f"已有 questions.jsonl，跳过: {exam_dir}")
        return

    all_questions = []

    for md_file in md_files:
        print(f"解析: {md_file.name}")
        md_text = md_file.read_text(encoding='utf-8')
        meta = parse_md_frontmatter(md_text)

        # 计算相对路径
        try:
            rel_path = md_file.relative_to(ROOT_DIR)
            md_rel_path = str(rel_path).replace('\\', '/')
        except ValueError:
            md_rel_path = str(md_file)

        questions = parse_questions_from_md(md_text, meta, md_rel_path)
        all_questions.extend(questions)

    # 写入 JSONL
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for q in all_questions:
            f.write(json.dumps(q, ensure_ascii=False) + '\n')

    print(f"\n=== 生成完成 ===")
    print(f"试卷目录: {exam_dir.name}")
    print(f"生成题目数: {len(all_questions)}")
    needs_review = [q for q in all_questions if q['status'] == 'needs_review']
    print(f"标记 needs_review: {len(needs_review)}")
    if needs_review:
        print(f"  需要人工检查的题号: {', '.join(q['question_number'] for q in needs_review)}")
    print(f"输出文件: {jsonl_path}")


if __name__ == "__main__":
    main()
