# 隐私合规控制

## 录音授权

- `POST /api/privacy/consents` 记录显式录音授权，`consent_type=recording`。
- `GET /api/privacy/consents?consent_type=recording` 返回当前用户最新授权记录。
- Live Session UI 在最新录音授权未接受前阻止麦克风录音。
- 音频上传服务会在存储 `user_recording` 前再次校验录音授权。

## 数据删除

- `POST /api/privacy/data-deletion` 必须传入 `confirmation=DELETE_MY_DATA`。
- 按 session 删除时可标记相关录音为已删除，并软删除练习 session，使报告通过常规 API 不可访问。
- 背景资料删除会移除问卷答案和 facts，并软删除 profile 记录。
- 已删除音频资产不会再返回 signed URL。

## Privacy Filter

- Agent Harness `filter_agent_background()` 会排除 `private`、`is_excluded` 以及命中用户 `privacy_exclusions` 的 facts。
- Trace payload 入库前使用脱敏 helper，避免保存邮箱、token、密钥等敏感内容。
- MCP profile 检索保留 `privacy_level` 过滤规则，默认不返回 private facts。
