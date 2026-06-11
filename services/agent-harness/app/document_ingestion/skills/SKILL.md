# Document Ingestion Agent Skills

## 目标
文档导入 Agent 在 `agent-harness` 容器内处理用户上传的 `md/txt/pdf/docx` 文档，提取三类候选数据：

- `question`：雅思口语题目、Part 2 cue card、Part 3 follow-up。
- `knowledge`：主题知识、答题素材、复习资料、用户私有知识块。
- `background`：用户背景事实，如目标分数、职业、专业、兴趣、薄弱项。

## 技能路由
- `file_sniff`：识别文件类型、大小、来源、可见性和导入目的。
- `text_normalizer`：抽取并规范文本，保留页码、标题和段落边界。
- `question_extractor`：识别问号句、Part 标记、cue card 和 follow-up。
- `knowledge_chunker`：按标题和语义段落生成知识候选。
- `background_fact_extractor`：提取需要用户确认的背景事实。
- `materialization_planner`：为候选结果生成目标表和审核策略。

## 审核规则
- 公共上传只生成候选，状态进入 `awaiting_review`，必须由管理员审核后写正式表。
- 私有背景只生成候选，状态进入 `awaiting_user_confirmation`，必须由用户确认后写 `background_facts`。
- 私有知识和私有题目可由 Agent 自动写入用户私有 `knowledge_docs/knowledge_chunks`，不写公共题库正式表。

## 观测规则
- 默认事件只记录推理摘要、动作摘要、技能名称、进度和结果数量。
- 文件路径、对象存储 key、完整文本和候选 JSON 作为可展开产物记录。
- 原始文件内容不直接写入日志；大文本产物优先写 MinIO，只保留预览。
