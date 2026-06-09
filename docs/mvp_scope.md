# MVP 范围说明

## 必须进入 MVP

- 用户注册、登录和基础鉴权。
- 用户背景问卷与隐私排除字段。
- 题库导入、审核状态和基础管理。
- `full_exam`、`part_practice`、`topic_practice` 三种模式。
- 浏览器录音、上传、ASR 转写、TTS 播放。
- Agent Harness 控制 Part 1 / Part 2 / Part 3 流程。
- RAG 检索题库、Rubric 和用户背景。
- 四维模拟评分：Fluency & Coherence、Lexical Resource、Grammatical Range & Accuracy、Pronunciation。
- 复盘报告：分数、证据、建议、参考答案、训练计划、录音回放。
- Docker Compose 本地完整环境。
- 核心路径端到端测试、基础 Trace、隐私授权与数据删除能力。

## MVP 明确降级或延期

- 完整实时双工语音：MVP 采用低延迟回合制。
- 高复杂 3D Avatar：MVP 使用轻量状态展示，Live2D/VRM 后续迭代。
- 教师端复杂运营后台：MVP 只保留题库和知识库管理基础能力。
- 商业化支付：不进入 MVP。
- A2A 外部 Agent 深度协作：先保留协议边界。
- 大规模多租户权限体系：先支持普通用户、运营、管理员三类角色。

## 首版题库与内容策略

- 题目必须记录 `source_type`、`license`、`review_status`。
- 原创题、授权题、用户回忆题分开管理。
- 只有 `active` 且审核通过的题目进入正式练习。
- 不对外宣称拥有 IELTS 官方未公开题库。

## 验收口径

MVP 的核心不是“AI 能聊天”，而是用户能稳定完成一次雅思口语练习或模拟考试，并在结束后得到可解释、可复盘、可继续训练的模拟评分报告。

