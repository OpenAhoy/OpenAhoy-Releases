# AutoDL · MiniMax H3

在 OpenAhoy「视频生成 → 模型设置」找到独立的「AutoDL · MiniMax H3」卡片，填写服务站的 HTTPS Base URL 和 Token。Token 独立存入系统钥匙串。卡片未配置时预填 AutoDL 官方地址 `https://autodl.art`。可替换为自有中转站。已有配置会显示已保存地址。预填只用于界面，需本人填写 Token 并保存后才可用于提交。

取得本次计费生成授权后，Codex 可调用 `video.relay.generation.submit`，提供项目 ID、稳定的 `generation_attempt_id`、提示词和按顺序排列的素材：

- `reference_images` 接收 1–9 张 JPG、PNG 或 WebP 的 HTTPS URL。工作流按 `ref_image_0` 至 `ref_image_8` 接收参考图。
- 可选的 `reference_audio` 接收最多 3 个 MP3 或 WAV HTTPS URL。工作流按 `ref_audio_0` 至 `ref_audio_2` 接收参考音频。
- 可选的 `duration` 为 1–15 秒。可选的 `resolution` 为 480p、768p 或 960p，各有横屏与竖屏对应值。省略时由服务站应用默认值。
- 这是多图参考工作流，官方规则未提供首尾帧控制参数。素材 URL 必须已可供服务商读取。本地文件需沿用户已授权的素材托管流程取得 URL。

以原项目 ID 和 attempt 调用 `video.ark.generation.status`，用 `poll: true` 查询原任务。成功后成片进入原视频资产库。遇到 `SUBMIT_UNKNOWN` 时保留原 attempt，向服务商核对原请求。原站和原 Token 用于查询未结束的旧任务。用量和实际扣费以该站账单为准。

原任务已完成但停在 `SAVE_PENDING` 时，继续对原 attempt 使用 `poll: true`。遇到断流或失效结果链接，插件会查询同一个原任务并尝试重新下载。找不到唯一结果、验证失败或本机保存失败时，查看回执中的 `query_error` 或 `download_error`。成片验证通过后才会进入资产库。

官方 `https://autodl.art` 的提交、查询及已确认的官方结果桶下载遇到系统 DNS 仅返回 Fake IP 时，会通过 Cloudflare HTTPS DNS 查询对应公开域名，并按原域名校验证书。自定义中转站和其他结果域名继续使用本机 DNS。下载不带 AutoDL Token。

官方生成每个 attempt 只提交一次。发送完请求后，客户端最多等到提交开始后的 50 秒接收响应头。超时保留同一个未知回执，回执中的 `operation_phase` 可用于诊断。这个等待时间不影响其他中转站的提交或原任务轮询。

`VIDEO_RELAY_PUBLIC_DNS_REQUIRED` 表示未能获得符合要求的公网地址，插件在连接服务站前停止了这次调用。已有任务 ID 时，网络恢复后继续查询原任务。

[AutoDL 工作流协议](https://autodl.art/docs/comfyui_api/)给出通用提交、鉴权和轮询格式。[官方工作流元数据](https://www.autodl.art/api/v1/comfyui/workflows/minimax_h3_zm_nono)提供此工作流的精确参数及结果示例。其他中转站兼容性以实际验证为准。
