# 高考地理 Obsidian 知识库

把高考地理试卷整理成一套适合在 Obsidian 中浏览、统计、串联和长期维护的知识库。

这个项目不是简单地把题目转成 Markdown，而是在做一条完整的数据整理和知识导出流水线：

- 上游：原始试卷整理与清洗
- 中游：题目、答案、解析、知识点映射结构化
- 下游：导出成适合 Obsidian 使用的知识主题页、单题页、试卷页和统计索引页

当前项目重点面向以下场景：

- 分析高频考点
- 组织高考地理专题复习材料
- 为教师、新手教师、师范生提供可检索的教学知识库
- 为后续做知识图谱、讲义生成、专题训练提供稳定底座

## 当前公开版包含内容

为了控制版权风险和仓库体积，这个公开版目录只保留了一份最小样本数据：

- `clean_data/questions/2025年山东高考地理真题/`
- 基于这份样本数据导出的 `obsidian_vault/`

也就是说，当前 `opensource` 目录中的数据和导出结果只对应山东卷示例，不包含其他地区试卷。

详细说明见：

- [项目总览](docs/project-overview.md)
- [开源发布清单](docs/open-source-checklist.md)

## 许可与使用边界

本项目当前采用“非商用源码公开”方式分享，而不是 OSI 定义下的开源许可证。

- 代码默认采用 [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)
- 文档默认采用 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
- 仓库中的第三方试卷、题目、答案、解析、图片和导出结果，如无特别说明，不因本仓库公开而自动获得可再分发或可商用授权

这意味着：

- 你可以在非商用场景下学习、使用、修改和继续完善本项目代码
- 你不可以基于本仓库代码直接进行商业化使用，除非另行获得授权
- 你在使用自己的题库数据生成知识库时，仍需自行确认原始资料和生成结果的版权与使用边界

更完整的许可说明见 [LICENSE](LICENSE)。

## 当前能力

项目当前已经支持：

- 从 `clean_data/questions` 读取结构化题库数据
- 按 `(module, level1)` 聚合生成知识主题页
- 为每个 `question_id` 生成单题页
- 生成试卷页、主题页、单题页、索引页、统计页
- 生成“高频考点总览”作为 Obsidian 主入口之一
- 按地区分组输出试卷索引，同地区内按年份从新到旧排序
- 复制并重写题目相关图片到 `assets/`

当前导出的 Obsidian 页面结构：

```text
obsidian_vault/
  00_首页.md
  01_试卷/
  02_知识主题/
  03_索引/
  04_题目/
  assets/
  obsidian_export_report.txt
```

## 仓库结构

```text
<PROJECT_ROOT>
├─ clean_data/              # 公开版样本数据，仅保留山东卷
├─ config/                  # 地理知识点 taxonomy 配置
├─ docs/                    # 项目说明与发布说明
├─ obsidian_vault/          # 基于山东样本生成的演示知识库
├─ scripts/
│  ├─ export_to_obsidian.py
│  ├─ clean_md.py
│  ├─ review_questions_answers.py
│  ├─ review_explanations.py
│  ├─ review_knowledge_links.py
│  └─ obsidian_export/
│     ├─ io_utils.py
│     ├─ source.py
│     ├─ models.py
│     ├─ transform.py
│     ├─ render.py
│     └─ pipeline.py
├─ LICENSE
├─ .gitignore
└─ exam_processing_workflow.md
```

## 导出架构

当前 Obsidian 导出脚本已经从单体脚本拆成模块化结构：

- `source.py`
  - 负责读取 `clean_data` 和各类 `jsonl`
  - 把原始数据装配成试卷和题目对象
- `models.py`
  - 定义试卷、题目、知识主题、统计对象等中间模型
- `transform.py`
  - 负责聚合、排序、主题映射、摘要生成
- `render.py`
  - 负责把中间模型渲染成 Markdown 页面
- `pipeline.py`
  - 负责串联整个导出流程
- `export_to_obsidian.py`
  - 作为薄 CLI 入口，仅负责接收参数并启动导出

这种拆分方式的重点不是“代码看起来整齐”，而是为了后续能稳定维护：

- 调整统计口径时，尽量只改 `transform.py`
- 调整页面样式时，尽量只改 `render.py`
- 调整输入数据格式时，尽量只改 `source.py`

## 当前页面模型

### 1. 首页

`00_首页.md` 作为知识库总入口，默认引导进入：

- 高频考点总览
- 试卷索引
- 知识主题总索引

### 2. 试卷页

每份试卷一个页面，保留原始试卷全文与题目导航，适合作为整套卷的入口。

### 3. 知识主题页

每个主题页对应一个 `(module, level1)` 聚合主题，承担三种职责：

- 考点分析页
- 题目聚合页
- 专题卷母版

页面中会展示：

- 题目总数
- 覆盖试卷数
- 涉及地区
- 涉及年份范围
- 下属细知识点
- 关联题目摘要列表

### 4. 单题页

每道题一个独立页面，用于完整承载备课所需内容：

- 来源试卷
- 关联知识主题
- 细知识点
- 题目材料
- 题干
- 图片
- 答案
- 解析
- 教学备注预留区

## 快速开始

### 环境要求

- Windows
- Python 3.9+
- 可读写本仓库目录

当前脚本没有依赖额外第三方包，默认按标准库运行。

### 生成 Obsidian 知识库

在仓库根目录执行：

```powershell
python scripts/export_to_obsidian.py
```

如需指定输入和输出目录：

```powershell
python scripts/export_to_obsidian.py --source <PROJECT_ROOT>/clean_data/questions --output <PROJECT_ROOT>/obsidian_vault
```

执行完成后，主要查看：

- `obsidian_vault/00_首页.md`
- `obsidian_vault/03_索引/高频考点总览.md`
- `obsidian_vault/obsidian_export_report.txt`

## 数据流

项目当前采用分层数据流：

```text
raw_data
  -> convert_data
  -> clean_data
  -> 结构化 JSONL
  -> Obsidian 中间模型
  -> Obsidian Markdown 页面
```

其中：

- `raw_data` 是原始资料
- `clean_data` 是清洗后的可结构化资料
- `questions.jsonl / answers.jsonl / explanations.jsonl / question_knowledge_links.jsonl` 是结构化数据
- `obsidian_vault` 是最终展示产物

## 当前设计原则

### 稳定主键

- 题目主键使用现有 `question_id`
- 知识主题键使用 `(module, level1)`

这样做是为了让后续主题合并、拆分、题目迁移时，可控地更新页面和统计结果。

### 纯 Markdown 预生成

当前统计页和索引页都由脚本预生成，不依赖 Dataview 等 Obsidian 插件。

这样做的好处是：

- 使用环境更简单
- 页面结果稳定
- 分享和迁移更方便

### 主题页展示摘要，单题页承载全文

知识主题页默认展示题目摘要与跳转，避免主题页过长；完整内容进入单题页，便于备课和复用。
