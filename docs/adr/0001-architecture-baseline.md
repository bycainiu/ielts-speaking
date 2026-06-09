# ADR 0001：系统架构基线

## 状态

Accepted

## 背景

雅思口语产品需要强状态、强时序、强规则和强评测能力。单次 Prompt 或普通聊天式 Agent 难以稳定控制 Part 1 / Part 2 / Part 3 的流程、追问、计时、评分、复盘和安全边界。

## 决策

采用以下边界：

- Frontend / PWA：Next.js + React + TypeScript，负责 Live UI、录音、播放、报告展示和后台基础页面。
- Go Backend / BFF：Go + Gin，负责业务 API、鉴权、WebSocket Gateway、音频资产、Agent Harness Client 和数据持久化。
- Agent Harness：Python FastAPI，负责考试/练习/评分/反馈工作流、多 Agent 编排、结构化输出和事件适配。
- 数据层：PostgreSQL + pgvector、Redis、MinIO/S3。
- 协议层：共享 JSON Schema 约束 WebSocket 事件、Agent API、Agent Run 和评分报告。
- 工具边界：Agent 通过 MCP 或受控内部接口访问题库、用户背景、Rubric、语音指标和报告工具。

## 关键原则

- Go Backend 不直接拼复杂 Prompt，只负责业务身份、权限、状态和转发。
- Agent Harness 不处理用户登录和业务权限，`user_id` / `tenant_id` 由后端注入。
- Agent 输出必须结构化，关键输出要通过 schema 校验。
- 用户隐私字段最小化传输，Trace 中敏感内容需要脱敏。
- 考试模式与练习模式严格分离，练习提示不能泄漏到考试模式。

## 后果

这套架构让前端、Go 后端、Agent Harness、内容和 QA 可以并行推进。代价是初期协议和工程基线要更严谨，但后续替换模型、扩展题库、增强语音链路和评分校准时不需要推翻整体结构。

