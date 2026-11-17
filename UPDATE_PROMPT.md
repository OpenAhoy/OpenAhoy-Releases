# OpenAhoy 0.6.71 更新指引

等当前业务任务到安全点后，把以下指令发给目标机器上的 Codex。

> 请用 Codex 官方插件管理，把本机现有 OpenAhoy 沿原市场和原插件 ID 同槽更新到固定正式版 v0.6.71。核对发行页的 RELEASE.json、SHA256SUMS 和完整包清单。如果原市场是专属公开来源 openahoy-distribution，保留并记录原来源与 ref 后，将 https://github.com/OpenAhoy/OpenAhoy-Releases.git 的原登记切到 v0.6.71，再安装原 wechat-ecosystem@openahoy-distribution。保留原绑定、草稿、配置、排期及未决回执。安装后核对 MCP 实际加载的版号和公众号只读列表。 [固定发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.71)

旧版若报忙或页面不可用，让 Codex 使用上面的软件安装路径。用户无需打开终端。专属公开市场的官方步骤为移除原市场登记、从原来源登记固定标签 `v0.6.71`、安装原插件。登记结果不明时，先读回原市场、ref 与已安装版本，再按原记录处理。共享市场由维护者更新原 OpenAhoy 条目的固定版本，沿用原插件 ID。固定旧标签的市场刷新仍会选旧版。

确认 Codex 实际加载 0.6.71。若仍在运行旧进程，等当前任务结束后再重开 Codex。管理页可查看已加载版本和查到的最新稳定版。

新版有独立「动图生成」页。使用原项目，OpenAI Key 由本人在安全设置里填写。已有动图成片从项目资产读取和下载。已有生成请求使用原编号查询，结果未知时保留原回执。

X 原生文章沿同一 X 账号和原应用的授权使用。保留封面及正文图的原上传回执。已有 Article ID 或 Post ID 时，按原回执查询。若 X API 省略正文结构或图序所需字段，核对状态会显示 INCOMPLETE，可使用已有权限打开原文章补查正文。遇到结果未知，不用相同标题重新创建或发表。

软件需要恢复时，优先使用同市场、同插件 ID 的 v0.6.71 校验包。已配置动图、已有 GIF 或 X 文章记录，以及存在在途或未知提交时，请保留原 Key、素材、成片和操作回执，用 v0.6.71 查原请求。v0.6.68 不读取这两类新业务记录，只用于已确认没有依赖新版状态且软件事务已结束的兼容回退。未决公众号合组仍按原操作 ID 查询。 [上一公开稳定版](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.68)
