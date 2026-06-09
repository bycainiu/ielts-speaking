# Pronunciation Drill: MFA / Kaldi GOP 技术方案

> 状态：Accepted for MVP adapter boundary  
> 更新时间：2026-06-08  
> 对应任务：P6-010

## 目标

固定文本跟读训练需要比 IELTS Mock Exam 更细的反馈粒度。P6-010 将 Pronunciation Drill 从通用语音 evidence 链路中拆出独立 API：它接收目标文本、转写和词级时间戳，返回 word-level 与 phoneme-level 反馈，用于专项练习页面或运营端内容验收。

该链路只服务 fixed-text drill，不参与 Mock Exam 的最终评分，也不输出 IELTS band。

## API

`POST /speech/pronunciation-drill`

请求示例：

```json
{
  "audio_asset_id": "audio_drill_001",
  "target_text": "Technology improves education",
  "transcript": "Technology improve education",
  "duration_ms": 3600,
  "word_timestamps": [
    { "word": "Technology", "start_ms": 0, "end_ms": 850, "confidence": 0.84 },
    { "word": "improve", "start_ms": 900, "end_ms": 1420, "confidence": 0.68 },
    { "word": "education", "start_ms": 1700, "end_ms": 2860, "confidence": 0.79 }
  ],
  "phoneme_hints": [
    { "word": "technology", "phonemes": ["T", "EH", "K", "N", "AA", "L", "AH", "JH", "IY"] }
  ],
  "provider": "deterministic_mfa_kaldi_gop"
}
```

响应核心字段：

- `alignment`：目标词数、实际词数、aligned/missing/substituted 统计和 alignment confidence。
- `word_feedback`：每个目标词的 GOP-compatible score、accuracy、timing、stress、status 和说明。
- `phoneme_feedback`：目标词下的音素级 GOP-compatible score、accuracy、status 和说明。
- `policy.ielts_band_output_allowed=false`：协议层强制不输出 IELTS band。

## 链路边界

Mock Exam / Free Speaking：

- 入口：`POST /speech/assess`
- 输出：音频质量、fluency、sentence-level pronunciation evidence
- 消费方：`ScoringWorkflow`
- 约束：只作为综合评分 evidence，不直接映射 IELTS band

Pronunciation Drill / Fixed Text：

- 入口：`POST /speech/pronunciation-drill`
- 输出：word-level、phoneme-level、stress/timing feedback
- 消费方：专项跟读训练 UI、内容/教研验收工具
- 约束：不进入 Mock Exam scoring path，不输出 IELTS band

## MVP 实现

当前版本提供 `deterministic_mfa_kaldi_gop` adapter boundary：

- 使用 `target_text` 与 `transcript` 做稳定词序对齐。
- 使用 `word_timestamps.confidence`、词相似度和时长比例生成 GOP-compatible word score。
- 使用 `phoneme_hints` 或轻量 grapheme-to-phoneme 近似生成 phoneme feedback。
- 对 `mfa_adapter`、`kaldi_gop_adapter` 预留 provider 枚举；未配置真实运行时时返回可重试 adapter error。

这一实现用于协议、前端联调和回归测试，不宣称等同真实 MFA/Kaldi GOP 模型输出。

## 后续替换点

1. 接入 MFA forced alignment：从目标文本和音频生成 word/phoneme alignment。
2. 接入 Kaldi GOP：用 acoustic likelihood 生成 phoneme GOP score。
3. 接入内容侧 phoneme hints：教研可为高频句型维护标准音素与重音位置。
4. 接入校准集：P10-006 完成后，用授权语音样本校准 GOP 阈值和 learner-facing 文案。

## 风险控制

- 口音公平性：drill feedback 只提示清晰度、节奏和目标文本对齐，不把口音本身视为错误。
- 误导性评分：协议禁止 `overall_band`、`predicted_band` 等 direct band 字段。
- 运行时隔离：真实 MFA/Kaldi 可作为独立 adapter 接入，不影响 Mock Exam 主评分链路稳定性。
