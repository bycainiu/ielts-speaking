# 协作规范

## 分支策略

- `main`：稳定发布分支，只接受已通过 Review 和质量门禁的变更。
- `dev`：日常集成分支，功能完成后先合入这里。
- `feature/<scope>-<name>`：功能分支，例如 `feature/agent-exam-workflow`。
- `fix/<scope>-<name>`：缺陷修复分支。

## 提交规范

提交信息使用简洁的 Conventional Commits 风格：

```text
feat(agent): add exam workflow skeleton
fix(api): handle missing jwt secret in production
docs: update local startup guide
```

常用类型：

- `feat`：新增功能。
- `fix`：修复缺陷。
- `docs`：文档变更。
- `test`：测试变更。
- `refactor`：不改变行为的结构优化。
- `chore`：构建、脚本、依赖等维护事项。

## Code Review 要求

- P0/P1 功能至少 1 名相关模块负责人 Review。
- 涉及隐私、鉴权、Agent 工具调用、评分策略的变更必须额外说明风险。
- 不在 PR 中夹带无关重构，除非该重构是完成当前任务的必要前置。

## PR 模板要求

每个 PR 至少说明：

- 变更内容。
- 覆盖的任务编号。
- 已执行的测试或无法执行的原因。
- 风险与回滚方案。

