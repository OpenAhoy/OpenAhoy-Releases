# ACE Music 歌曲与项目配乐

ACE Music 适用于用户明确选择该供应商，或已由 [歌曲与视频配乐](MUSIC_WORKFLOW.md) 读取本机设置并选中该供应商的任务。旧任务沿其原供应商和回执。

在 OpenAhoy「媒体工坊 → 音频」的 ACE Music 卡查看授权状态、账户和曲库。创作调用当前聊天独立的官方 MCP，连接名为 `ace-music`，生产地址为 `https://acemusic.ai/mcp`。通过 Codex 官方入口登记这一条，保持已有 MCP 设置和连接名。账号本人在 ACE Music 官方页面完成 OAuth，面板可等待、取消和核对授权。无需 API key。换账号时在 ACE Music 卡点「重新连接 ACE Music」，在官方浏览器页面确认使用目标账号。授权返回后重新读取账号和曲库。

## 创作与原任务

1. 通过官方 `get_skill` 读取适用创作要求。写词使用 `name: lyrics`，其他创作按工具目录选用。按实际工具签名准备标题、歌词、风格、结构和模型。用 `get_account` 核对当前连接、套餐、可用模型、Credits 和费用。若真实响应缺少报价或显示不明，不估算费用。
2. 先提供曲目方案和官方费用，在用户明确授权本次计费后只提交一次 `create_song`。保留全部原歌曲 ID。用 `get_song` 的 `ids` 查询原 ID；提交结果未知时先核对官方曲库和原任务，避免重复扣费。
3. 汇报每版实际状态与官方提供的歌曲页面或播放资源。免费账户保留曲库与官方页面试听。MCP 文件下载以官方账户和具体曲目的实际权限为准。只在用户要求导入且官方允许时对选中的原 ID 调用 `download_song`，优先 MP3 或现有导入接口支持的 WAV。遇到 `plan_required` 保留原曲和官方查看入口。
4. 通过 `media.library.prepare` 取得现有统一媒体项目。将获准下载的音频存入项目根，计算 SHA-256 后调用 `audio.project.import`，`provider` 为 `ace-music`，`provider_id` 为原曲 ID，填写本次本机 attempt 和项目相对路径。保持原任务与本机资产的对应关系。
5. 配乐用 `audio.project.mix`，按原视频任务和原音频任务引用素材，为不同来源提供各自的项目 ID。用户选定两项资产及混音意图后再合成。已有音频可以直接从本机库选取。

[ACE Music 官方连接说明](https://acemusic.ai/help/articles/connect-ace-music-to-your-ai-assistant/) · [官方 Credits 与下载说明](https://acemusic.ai/help/articles/ace-music-mcp-credits-downloads-troubleshooting/)
