# 单份试卷半自动处理流程

本文档用于指导 AI 或人工按"单份试卷、半自动化、人工复核"的方式处理高考地理试卷。

执行前必须先阅读 `agent.md`，了解项目总规范、目录结构、文件格式要求和操作规则。

## 处理原则

- 一次只处理一份试卷
- 必须使用用户指定的原始文件、Markdown 文件或试卷目录
- 除非用户明确要求批量处理，否则不要全量扫描 raw_data、convert_data 或 clean_data
- 每个 JSONL 必须配套一个 review Markdown
- 每完成一个 JSONL 及其 review 后必须暂停，等待用户检查确认
- 所有题目、答案、解析、图形化答案、知识点链接都通过 question_id 对齐

## 流程断点

本流程必须按断点推进，不能一次性跑完所有 JSONL。

### 断点 1：raw_data -> convert_data -> clean_data

**操作**：
1. 将原始试卷放入 `raw_data/questions/`
2. 运行 `batch_convert.py` 转换原始资料
3. 运行 `clean_md.py` 清洗 Markdown

**检查**：
- `convert_data/convert_log.txt` 和 `convert_quality_report.txt`
- `clean_data/clean_report.txt`
- 确认试卷目录下有 `.md` 文件和 `images/` 目录

**确认**：用户检查 Markdown、图片、clean_report，确认无明显问题后，才进入结构化。

### 断点 2：生成 questions.jsonl + questions_review.md

**操作**：
1. 生成 `questions.jsonl`（保存题干、材料、选项、小问、题目图片）
2. 运行 `review_questions_answers.py --target questions` 生成 `questions_review.md`

**检查**：
- 题干、选项、小问是否完整
- 题组共用材料是否正确挂载
- 图表题图片是否与题干对应
- 不能确定的内容是否标记 `status=needs_review`

**确认**：用户检查 `questions_review.md` 后，才允许进入答案结构化。

### 断点 3：生成 answers.jsonl + answers_review.md

**操作**：
1. 生成 `answers.jsonl`（保存文字参考答案和答案图片引用）
2. 运行 `review_questions_answers.py --target answers` 生成 `answers_review.md`

**检查**：
- 答案是否对齐题号
- 开放题多种答案是否保留完整
- 小问编号与 answer_parts 是否一致
- 答案图片路径是否存在
- 解析和答案混排时，是否误把解析写入答案

**确认**：用户检查 `answers_review.md` 后，才允许进入解析结构化。

### 断点 4：生成 explanations.jsonl + explanations_review.md

**操作**：
1. 生成 `explanations.jsonl`（保存文字解析和解析来源）
2. 运行 `review_explanations.py` 生成 `explanations_review.md`

**检查**：
- 解析是否逐题对应
- 选择题解析是否说明正确选项和排除项
- 非选择题解析是否按小问拆分
- 解析和答案混排时是否被正确拆分
- 低置信度解析是否标记 `parse_confidence=low`

**确认**：用户检查 `explanations_review.md` 后，才允许进入图形化答案处理。

### 断点 5：生成 graphical_answers.jsonl + graphical_answers_review.md

**操作**：
1. 如果 `answers.jsonl` 中存在 `related_answer_images`，运行 `review_graphical_answers.py` 生成 `graphical_answers.jsonl` 和 `graphical_answers_review.md`
2. 如果该卷没有图形化答案，也应生成空文件，表示已经检查过

**检查**：
- 图片是否是真正的图形化答案
- 图片尺寸是否正常
- 是否误把占位图、小图标、无关图片当答案
- 图形类型 `graphic_type` 是否合理

**确认**：用户检查 `graphical_answers_review.md` 后，才允许进入知识点标注。

### 断点 6：生成 question_knowledge_links.jsonl + question_knowledge_links_review.md

**操作**：
1. 根据高中地理 taxonomy，为每道题生成 `question_knowledge_links.jsonl`
2. 运行 `review_knowledge_links.py` 生成 `question_knowledge_links_review.md` 和 `clean_data/structure_report.txt`

**检查**：
- question_id 是否对齐
- 知识点路径是否存在于 taxonomy
- 知识点是否标注 role 和 weight
- 每道题是否至少有一个 core_exam_point
- 是否重复标注同一知识点
- 低置信度题目是否需要人工确认

**确认**：用户检查 `question_knowledge_links_review.md` 后，才能进入统计、Obsidian 图谱、可视化或网站应用。

## 高风险注意事项

半自动化处理时，AI 必须特别注意以下问题，在生成 review 后提醒用户人工复核：

- **题组共用材料**：同一段材料可能对应多道题，不要重复拆错或漏挂到后续题目
- **图表题图片对应关系**：每道题引用的图片必须和题干、材料、选项对应
- **开放题多种参考答案**：如果参考答案给出多种可能性，必须完整保留
- **图形化答案**：如分水线、剖面标注、圈画区域，应进入 `graphical_answers.jsonl`
- **解析和答案混排**：原始资料中答案与解析常交替出现，必须拆到对应 JSONL
- **题号、小问、答案编号错位**：尤其注意题组、非选择题小问、答案段落编号是否与题目一致

## 最终交付检查

一份试卷处理完成时，该试卷目录下原则上应有：

```text
某试卷.md
images/
questions.jsonl + questions_review.md
answers.jsonl + answers_review.md
explanations.jsonl + explanations_review.md
graphical_answers.jsonl + graphical_answers_review.md
question_knowledge_links.jsonl + question_knowledge_links_review.md
```

最终必须确认：
- 所有 JSONL 能逐行解析
- 所有 review 文件已生成
- questions、answers、explanations 的 question_id 对齐
- 图形化答案没有误收无关图片
- question_knowledge_links.jsonl 是唯一知识点链接来源
- review 中没有未处理的严重问题

## AI 汇报格式

AI 处理完一份试卷后，应向用户汇报：

- 试卷名称
- 当前完成的是哪个断点
- 本断点生成了哪些 JSONL 和 review
- 自检问题数
- 需要人工重点看的题号
- 图片或图形化答案异常
- 知识点链接异常
- 是否可以进入人工复核
- 是否等待用户确认后再进入下一断点

不要只说"已完成"。必须把需要人工看的问题直接列出来。