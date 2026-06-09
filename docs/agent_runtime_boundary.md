# Agent Runtime Boundary

> 更新时间：2026-06-08

## 目标

本文档用于收口 P2-001 的 Agent Harness 运行时边界，明确当前 MVP 如何同时满足稳定回归和后续 Microsoft Agent Framework 深度编排迁移。

## 当前实现

- Agent Harness 以 FastAPI 独立服务运行，提供 `/healthz`、`/metrics`、`/agent/sessions/{session_id}/plan`、`/consume-asr`、`/next-turn`、`/score`、`/agent/runs/{run_id}`、`/trace`、`/cancel` 等接口。
- 当前业务工作流由 `ExamWorkflow`、`PracticeWorkflow`、`ScoringWorkflow` 的确定性状态机承载，用于保证考试流程、评分流程、AG-UI 事件和回归测试稳定。
- `app.core.runtime.AgentRuntime` 已显式暴露 Microsoft Agent Framework 适配边界，`/healthz` 和 Agent Run summary 会返回：
  - `adapter=microsoft-agent-framework`
  - `adapter_package=agent-framework-core`
  - `framework=deterministic-workflow`
  - `mode=deterministic`
- `services/agent-harness/requirements.txt` 已加入 `agent-framework-core>=1.0,<2.0`，容器构建时会安装 Microsoft Agent Framework Python core package。

## 为什么保留确定性工作流

IELTS Speaking 主链路是强状态、强时序、强规则的考试流程。当前 Phase 2-12 已有 200+ 个 Agent Harness 回归用例覆盖题组规划、追问、三段考试、评分、RAG、MCP、隐私与红队防护。直接把主链路一次性迁移到图编排会扩大风险面，因此当前策略是：

1. FastAPI 服务、模型适配、MCP、RAG、Trace 与 AG-UI 协议先稳定。
2. Microsoft Agent Framework 作为运行时适配边界进入依赖和健康检查。
3. 后续按节点迁移 `QuestionSetPlannerAgent`、`ExaminerAgent`、`FollowupPlannerAgent`、`ScoringWorkflow`，每迁移一个节点都保持同一组协议测试和 E2E 测试通过。

## 后续深度迁移验收

后续如果启动 Microsoft Agent Framework 深度迁移，应逐项满足：

- `ExamWorkflow` 可由 Agent Framework workflow graph 或等价 executor 承载，并保留现有 state schema。
- 每个节点仍输出当前 `packages/protocol` 定义的事件和结构化结果。
- MCP 工具调用继续通过现有 scope、allowlist、audit sink 和隐私过滤。
- Trace 继续保留 `session_id`、`run_id`、`workflow_node`、`prompt_version`、`tool_calls`、`structured_output_validity` 和错误摘要。
- `python -m pytest services/agent-harness/tests`、Protocol validate、Go/Web 集成验证和 Docker build 继续通过。
