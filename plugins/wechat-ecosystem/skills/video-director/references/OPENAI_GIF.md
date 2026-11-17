# OpenAI 动图

用户明确要求制作动图时，先通过 `image.openai.gif.configuration.status` 检查本机 OpenAI 动图 Key 是否已保存。配置状态不会验证 OpenAI 项目的 GIF 预览权限。未配置时请用户本人在右侧「视频生成 → 模型设置 → OpenAI · 动图」保存 Key，避免让 Key 进入聊天。已有 GIF 的上传或发表仍使用对应平台的正常入口。

Codex 负责生成或选定静态原图。提交前确认一张已登记项目中的 PNG、JPEG 或 WebP，核对实际项目相对路径、原图 SHA-256 和用户想要的动作。将动作和循环描述、项目 ID、选定参图及唯一 `generation_attempt_id` 交给 `image.openai.gif.submit`。它使用 GPT‑Image‑2.6 Flare 官方图片编辑接口生成一个动画，采用 API 的 9 帧、200ms、auto 默认值。提交会将选定的原图和提示词发送给 OpenAI，按用户自己的项目计费。

收到 `PROCESSING` 时，用 `image.openai.gif.status` 读取同一 attempt 的本机回执。`ASSET_READY` 后将 `path` 作为 GIF 原文件链接回复用户。右侧「预览与资产 → 动图」可直接预览、下载同一字节。`GIF_AUTH_REQUIRED` 指向钥匙校验，`GIF_ACCESS_REQUIRED` 指向 OpenAI 项目的模型或 GIF 预览权限，`GIF_QUOTA_REQUIRED` 指向额度或计费。`SUBMIT_UNKNOWN` 保留已有 `provider_request_id`；图片编辑没有按 ID 取成品的官方查询。`SAVE_PENDING` 表示可用同一准确原请求恢复项目副本，已有原件时不提交 API。不要为任何未知结果创建替代 attempt。

[OpenAI 动图指南](https://developers.openai.com/api/docs/guides/image-generation#generate-animated-gif-output) · [图片编辑 API](https://developers.openai.com/api/reference/resources/images/methods/edit)
