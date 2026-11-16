# OpenAhoy 0.6.65 更新指引

等当前业务任务到安全点后，把以下指令发给目标机器上的 Codex。

> 请用 Codex 官方插件管理，把本机现有 OpenAhoy 沿原市场和原插件 ID 同槽更新到固定正式版 v0.6.65。核对发行页的 RELEASE.json、SHA256SUMS 和完整包清单。如果原市场是专属公开来源 openahoy-distribution，保留并记录原来源与 ref 后，将 https://github.com/OpenAhoy/OpenAhoy-Releases.git 的原登记切到 v0.6.65，再安装原 wechat-ecosystem@openahoy-distribution。保留原绑定、草稿、配置、排期及未决回执。安装后核对 MCP 实际加载的版号和公众号只读列表。 [固定发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.65)

旧版若报忙或页面不可用，让 Codex 使用上面的软件安装路径。用户无需打开终端。专属公开市场的官方步骤为移除原市场登记、从原来源登记固定标签 `v0.6.65`、安装原插件。登记结果不明时，先读回原市场、ref 与已安装版本，再按原记录处理。共享市场由维护者更新原 OpenAhoy 条目的固定版本，沿用原插件 ID。固定旧标签的市场刷新仍会选旧版。

如果实际安装了新包、当前聊天仍加载旧进程，等当前任务到安全点后再重开 Codex。确认 0.6.65 已加载，再打开 OpenAhoy →「视频生成」→「模型设置」。这里新增独立的 **AutoDL · MiniMax H3** 卡片。未配置时会预填 https://autodl.art，已保存的站点会继续显示。Token 由本人填在卡片的安全输入框。既有 MiniMax 中国站、国际站及方舟仍用各自的配置。

已有 AutoDL 任务时，在原项目按原请求 ID 查成片，并从项目资产区播放和下载原片。结果未知时查原任务，勿再次提交同一生成。生成是否计费及金额以服务方账单为准。

软件需要恢复时，优先使用同一市场、同一插件 ID 的 v0.6.65 校验包。已保存中转站配置、存在 AutoDL 做的视频、在途任务或未知提交时，保留原站与 Token、原任务回执和 MP4。v0.6.63 无法可靠查询和验证 AutoDL · MiniMax H3 的中转记录。沿原请求恢复查询，不用旧版重发。

[v0.6.63](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.63) 是前一公开稳定版。只在没有依赖新版的中转状态、软件事务已确认结束且当前状态兼容时考虑回退。未决公众号合组须保留原候选、原组和回执，用此版或已确认兼容的 0.6.63 查原操作，勿用更旧不兼容软件继续。
