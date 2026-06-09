# Knowledge Chunk Spec

> 适用范围：Agent Harness RAG、pgvector 索引任务、MCP 检索工具、Ragas 回归评估。  
> 当前实现入口：`services/agent-harness/app/rag/chunk_schema.py` 与 `llamaindex_service.py`。

## 1. 设计目标

知识 chunk 的核心目标不是“把文本切小”，而是让检索结果可过滤、可解释、可审计。每个 chunk 必须回答三个问题：

1. 这段内容来自哪类知识：题库、Rubric、用户背景、主题知识或历史复盘。
2. Agent 在什么场景可以使用它：考试提问、练习个性化、评分、反馈。
3. 前端、Go Backend、Agent Trace 如何解释它：来源、状态、用户、题目、评分维度、隐私级别。

## 2. 通用规则

所有 chunk 会自动继承以下 metadata：

| 字段 | 类型 | 说明 |
|---|---|---|
| `doc_type` | string | `question_bank`、`rubric`、`user_profile`、`topic_knowledge`、`review_history` |
| `title` | string | 文档标题，用于检索解释和 Trace 展示 |
| `status` | string | `draft`、`reviewing`、`active`、`archived`；默认检索只返回 `active` |
| `source_id` | string | 可选，指向业务源记录，如 question、background_fact、score_report |
| `owner_user_id` | string | 可选，用户私有知识必须带用户维度 |

切片规则：

- MVP 默认 `KNOWLEDGE_CHUNK_MAX_CHARS=1200`、`KNOWLEDGE_CHUNK_OVERLAP_CHARS=120`。
- 题库、用户背景、Rubric 等结构化内容优先“一条业务记录一个 document”，避免跨题、跨用户或跨评分维度混切。
- 长文本可以切成多个 chunk，但每个 chunk 必须保留完整 metadata，保证 Top K 结果仍可过滤。
- 只有 `active` 内容进入正式检索；`draft/reviewing` 只允许后台预览或评测环境使用。

## 3. 题库 Chunk

推荐粒度：

- Part 1/3：一道题一个 document，follow-up 可作为同题 metadata 或独立 chunk。
- Part 2：cue card prompt、bullet points 和该题基础信息放在同一 document；过长材料再切片。

必填 metadata：

| 字段 | 类型 | 说明 |
|---|---|---|
| `season_id` | string | 季度 ID，主过滤字段 |
| `part` | string | `"1"`、`"2"`、`"3"`，统一存为字符串，匹配 pgvector 表达式索引 |
| `topic` | string | 主题名或主题 slug，用于主题练习与检索解释 |
| `source_type` | string | `original`、`authorized`、`user_recall`、`internal` |

导入侧可以临时传入 `season`，Agent Harness 会规范化为 `season_id`；检索和 pgvector 索引统一使用 `season_id`。

推荐 metadata：

| 字段 | 说明 |
|---|---|
| `question_id` | 指向 `questions.id` |
| `topic_id` | 指向 `topics.id` |
| `review_status` | 内容审核状态 |
| `difficulty` | 1-5 的难度标记 |
| `license` | 版权或授权说明 |
| `cue_card_id` | Part 2 cue card ID |
| `has_cue_card` | 是否包含 Part 2 cue card |
| `cue_card_prompt` | Part 2 cue card 原始提示 |
| `cue_card_bullet_points` | Part 2 bullet points，字符串数组 |
| `cue_card_preparation_seconds` | Part 2 准备时长 |
| `cue_card_speaking_seconds` | Part 2 建议回答时长 |
| `followup_count` | active follow-up 数量 |
| `followup_templates` | active follow-up 结构化列表，供 `question-bank-mcp` 返回追问模板 |

常用过滤：

```json
{
  "doc_type": "question_bank",
  "season_id": "2026-q2",
  "part": "2",
  "topic": "objects"
}
```

## 4. Rubric Chunk

推荐粒度：

- 一个评分维度和一个 band descriptor 一个 document。
- 内部评分策略、误扣分规则、anchor sample 可以独立 document，但必须标明 criterion。

必填 metadata：

| 字段 | 类型 | 说明 |
|---|---|---|
| `criterion` | string | `fluency_coherence`、`lexical_resource`、`grammatical_range_accuracy`、`pronunciation` |
| `band` | string | IELTS band，支持 `0` 到 `9`，0.5 递增 |
| `descriptor` | string | 可展示的评分描述摘要 |

推荐 metadata：

| 字段 | 说明 |
|---|---|
| `rubric_id` | 原始 Rubric 记录 ID，便于 Trace 和评分工作流引用 |
| `rubric_version` | Rubric 或内部评分策略版本 |
| `anchor_sample_id` | 对齐样本 ID |
| `policy_type` | `official_descriptor`、`internal_policy`、`anchor_example` |

常用过滤：

```json
{
  "doc_type": "rubric",
  "criterion": "fluency_coherence",
  "band": ["6", "6.5", "7"]
}
```

## 5. 用户背景 Chunk

推荐粒度：

- 一个 `background_fact` 一个 document。
- 被用户 privacy exclusions 命中的事实不得写入 Agent 可用索引。
- 用户更新问卷后，相关 user_profile document 必须按 `source_id` 或稳定 `doc_id` 重建。

必填 metadata：

| 字段 | 类型 | 说明 |
|---|---|---|
| `privacy_level` | string | `normal`、`sensitive`、`private` |
| `allowed_usage` | string[] | `question_personalization`、`feedback_personalization`、`scoring_context` 至少一个 |

推荐 metadata：

| 字段 | 说明 |
|---|---|
| `topic` | 背景事实所属主题 |
| `fact_key` | 如 `hobby`、`workplace`、`learning_goal` |
| `fact_id` | 指向 `background_facts.id` 或稳定事实 ID |
| `fact_value_hash` | fact value 的 SHA-256，用于 Trace/审计对齐，不暴露原文 |
| `questionnaire_id` | 背景问卷 ID |
| `owner_user_id` | 用户 ID，由服务端注入 |

隐私规则：

- `private` 默认不进入模型上下文，除非后续显式策略允许。
- `is_excluded=true` 或命中 privacy exclusions 的 facts 不得进入可检索索引。
- `allowed_usage` 必须由服务端根据用户授权与产品场景写入，Agent 不可自行扩大用途。
- Trace 只记录 chunk ID、doc_type、metadata 摘要，不记录完整私密文本。
- 用户更新问卷时应按用户重建 `user_profile_index`，先删除旧 user_profile chunks，再写入当前可用 facts。

常用过滤：

```json
{
  "doc_type": "user_profile",
  "owner_user_id": "user_123",
  "allowed_usage": ["question_personalization"]
}
```

## 6. 主题知识 Chunk

推荐粒度：

- 一个观点、例子、词汇组、表达组或答题结构一个 document。
- Part 3 抽象讨论优先检索主题观点和例子；参考答案生成优先检索表达和结构。

必填 metadata：

| 字段 | 类型 | 说明 |
|---|---|---|
| `topic` | string | 主题名或 slug |

推荐 metadata：

| 字段 | 说明 |
|---|---|
| `knowledge_type` | `idea`、`example`、`vocabulary`、`expression`、`structure`、`background` |
| `source_type` | `original`、`authorized`、`user_recall`、`internal` |
| `difficulty` | 适合 Band 5/6/7 等层级 |

## 7. 历史复盘 Chunk

推荐粒度：

- 一段回答摘录、一个评分证据、一个反馈建议或一个弱点标签一个 document。
- 历史复盘必须绑定用户和 session，避免跨用户检索。

必填 metadata：

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 来源练习或考试 session |
| `part` | string | `"1"`、`"2"`、`"3"` |
| `review_item_type` | string | `answer_excerpt`、`score_evidence`、`feedback_item`、`weakness` |

推荐 metadata：

| 字段 | 说明 |
|---|---|
| `criterion` | 关联评分维度 |
| `report_id` | 复盘报告 ID |
| `turn_id` | 来源 turn ID |
| `owner_user_id` | 用户 ID，由服务端注入 |

## 8. 工程约束

- `chunk_schema.py` 是 ingest 边界的唯一 metadata 校验入口。
- 新增索引任务时必须先构造符合本规范的 `KnowledgeDocument`。
- 新增 doc_type 或 metadata 字段时，需要同步更新本文档、`chunk_schema.py` 和对应测试。
- 对用户数据类 chunk，必须先完成隐私过滤，再调用 `ingest_documents()`。
