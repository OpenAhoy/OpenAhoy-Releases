# OpenAhoy 0.6.73 更新指引

等当前业务任务到安全点后，把以下指令发给目标机器上的 Codex。

> 请用 Codex 官方插件管理，把本机现有 OpenAhoy 沿原市场和原插件 ID 同槽更新到固定正式版 v0.6.73。核对发行页的 RELEASE.json、SHA256SUMS 和完整包清单。如果原市场是专属公开来源 openahoy-distribution，保留并记录原来源与 ref 后，将 https://github.com/OpenAhoy/OpenAhoy-Releases.git 的原登记切到 v0.6.73，再安装原 wechat-ecosystem@openahoy-distribution。保留原绑定、草稿、配置、排期及未决回执。安装后核对 MCP 实际加载的版号和公众号只读列表。 [固定发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.73)

旧版若报忙或页面不可用，让 Codex 使用上面的软件安装路径。用户无需打开终端。专属公开市场的官方步骤为移除原市场登记、从原来源登记固定标签 `v0.6.73`、安装原插件。登记结果不明时，先读回原市场、ref 与已安装版本，再按原记录处理。共享市场由维护者更新原 OpenAhoy 条目的固定版本，沿用原插件 ID。固定旧标签的市场刷新仍会选旧版。

确认 Codex 实际加载 0.6.73。如果旧进程仍在使用，等当前任务结束后再重开。打开「媒体工坊」，可分别进入动图、视频和音频。原项目及原任务沿已有入口打开。

视频设置显示火山方舟、MiniMax 中国站、MiniMax 国际站、AutoDL · MiniMax H3、Token Hex · 方舟视频五张卡。MiniMax 两站分别使用各自的 Key。已有配置先读回，新增 Key 由本人在对应卡片安全输入。主体参考采用 MiniMax S2V-01，实际模型权限与额度由对应站点决定。方舟 CLI 身份未落盘，MiniMax 中国站的 OAuth 归属未确认。卡片或客户端可以显示，并不表示这些控制面权限已经通过。

音频可导入项目内已有音轨并为视频本机配乐，合成需要系统安装 FFmpeg 和 ffprobe。随包登记 Suno MCP，真实 Suno 生成及下载仍待验证。已有供应商任务请按原站、账号和任务编号查询。

软件需要恢复时，优先使用原市场和同一插件 ID 的 v0.6.73。若已有 Token Hex、MiniMax S2V、音频配乐或 Suno 原任务，保留原记录并用 0.6.73 接续。0.6.71 可能用方舟直连来查询 Token Hex 任务，因此不要用旧版轮询或补发这类任务。已有 GIF、X 原生文章或未决公众号合组继续沿原回执查询。仅在确认当前状态与旧版兼容且没有依赖新版的任务时，才考虑纯软件回退。 [上一公开稳定版](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.71)
