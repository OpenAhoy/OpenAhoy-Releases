# AutoDL · MiniMax H3

在 Jiusera「设置 → 模型管理 → 画布 · 视频」找到独立的「AutoDL · MiniMax H3」卡片，填写服务站的 HTTPS Base URL 和 Token。Token 独立存入系统钥匙串。卡片未配置时预填 AutoDL 官方地址 `https://autodl.art`。可替换为自有中转站。已有配置会显示已保存地址。预填只用于界面，需本人填写 Token 并保存后才可用于提交。

调用 `video.director.read`，用 `action=models` 读取 `relay → MiniMax-H3-Relay → workflow → workflows` 的实时插件能力目录。选好再调用 `video.relay.generation.submit`，传项目 ID、固定的 `generation_attempt_id` 与显式 `workflow_id`。如果用户已经在画布保存镜头配置，使用该精确修订的导演台生成入口。导演台中通过 AutoDL 的工作流下拉菜单选择相同的 ID。

| 需要的控制 | 官方工作流与输入 |
| --- | --- |
| 文生视频 | `minimax_h3_lightx2v_no_pic`，提示词，1–15 秒 |
| 一张或多张参考图 | `minimax_h3_lightx2v_v5`（1–10 秒）或 `minimax_h3_lightx2v_v5_15s`（1–15 秒），按顺序放 1–9 张图 |
| 首尾画面分别对齐 | `minimax_h3_lightx2v`，显式传 `first_frame`、`last_frame`、提示词。两张普通参考图仍按参考图处理 |
| 单图配原音对口型 | `minimax_h3_image_audio_to_video`，一图一音，`audio_duration` 1–15 秒 |
| 多图多音 | `minimax_h3_image_audio_to_video_v2`（1–10 秒）或 `minimax_h3_image_audio_to_video_v2_15s`（1–15 秒）；按各自顺序传参考图、参考音频 |
| 动作迁移、角色替换 | 按目标选择 Wan 动作迁移、H3 单角色或 H3 多角色，明确角色图和 `reference_video` |
| 高速、高质、短剧、九图及其他变体 | 按插件目录中该 ID 的输入、时长、分辨率、种子、画质和风格选项 |

当前官方公开目录有 26 项视频工作流。仅有一张图时可使用单图参考。必须精确对齐首帧但还没有尾帧时，先确认是否补齐尾帧或另选明确支持首帧的供应商。若用户只给两张参考图，保留参考语义。多个合适变体都能满足要求时，优先沿既有项目模式，遇到时长、角色替换或素材含义冲突再确认。

素材使用服务商能读取的 HTTPS URL；本地原件沿用户已授权的托管流程取得链接。每种模式的图片、音频、视频格式从目录读取，保持输入次序。省略可选分辨率、时长和种子时沿用服务商默认。原来未带 `workflow_id` 的调用继续用原 `minimax_h3_zm_nono` 路径和回执。MiniMax 直连与 Token Hex 使用各自的模型和参数。

以原项目 ID 和 attempt 调用 `video.ark.generation.status`，用 `poll: true` 查询原任务。成功后成片进入原视频资产库。遇到 `SUBMIT_UNKNOWN` 时保留原 attempt，向服务商核对原请求。原站和原 Token 用于查询未结束的旧任务。用量和实际扣费以该站账单为准。

原任务已完成但停在 `SAVE_PENDING` 时，继续对原 attempt 使用 `poll: true`。遇到断流或失效结果链接，插件会查询同一个原任务并尝试重新下载。找不到唯一结果、验证失败或本机保存失败时，查看回执中的 `query_error` 或 `download_error`。成片验证通过后才会进入资产库。

官方 `https://autodl.art` 的提交、查询及已确认的官方结果桶下载遇到系统 DNS 仅返回 Fake IP 时，会通过 Cloudflare HTTPS DNS 查询对应公开域名，并按原域名校验证书。自定义中转站和其他结果域名继续使用本机 DNS。下载不带 AutoDL Token。

官方生成每个 attempt 只提交一次。发送完请求后，客户端最多等到提交开始后的 50 秒接收响应头。超时保留同一个未知回执，回执中的 `operation_phase` 可用于诊断。这个等待时间不影响其他中转站的提交或原任务轮询。

`VIDEO_RELAY_PUBLIC_DNS_REQUIRED` 表示未能获得符合要求的公网地址，插件在连接服务站前停止了这次调用。已有任务 ID 时，网络恢复后继续查询原任务。

[AutoDL 工作流协议](https://autodl.art/docs/comfyui_api/)给出通用提交、鉴权和轮询格式。[官方工作流目录](https://www.autodl.art/large-model/comfyui)及各项目的详情提供精确参数与结果示例。其他中转站兼容性以实际验证为准。
