# Voice Clone Policy

MVP 阶段默认禁用 voice clone。

## 规则

- 未经 operator 显式启用，不得使用 voice clone 音色。
- 启用 voice clone 必须先具备明确授权、声明和审核流程。
- 当策略 disabled 时，`voiceclone:` 或 `clone:` 前缀的 voice_id 会被服务端阻断。
- 默认 TTS 主链路应使用非克隆考官音色。

## 运维

- Operator 和 admin 可通过 `/api/admin/compliance/voice-clone-policy` 查看或更新策略。
- 后台 Review Board 展示当前策略状态，并可立即禁用 voice clone。
- 本地默认配置保存在 `app_settings.voice_clone_policy`，初始值为 `enabled=false`。

## MVP 边界

Voice clone 上传、审核、批准不进入 MVP 主链路。在完整授权与审核流程上线前，生产类环境必须保持 voice clone disabled。
