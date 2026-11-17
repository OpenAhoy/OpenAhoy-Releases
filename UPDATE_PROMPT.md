# OpenAhoy 0.6.81 更新指引

在 OpenAhoy 管理页点「检查更新」，出现「立即升级」后沿原入口安装。按提示完整退出并重开 Codex，再确认「当前运行」为 0.6.81。

若内嵌入口无法完成更新，把下面这段发给本机 Codex：

> 请通过官方 Codex 插件管理，沿本机原市场和原插件 ID 更新现有 OpenAhoy 到固定版 v0.6.81。先核对原来源、ref、插件 ID、已装版本与本版清单。遇到未决安装时先回读原结果。保留原账号绑定、配置、草稿、排期、媒体及业务回执，更新后核对实际加载版本。 [正式发行](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.81)

- 专属公开市场 `openahoy-distribution` 确认来自 `https://github.com/OpenAhoy/OpenAhoy-Releases.git` 时，记录原 ref，只切换该市场登记到固定标签 `v0.6.81`，再使用官方 `codex plugin add wechat-ecosystem@openahoy-distribution`。共享市场由维护者更新原条目，沿用原插件 ID。
- 重开后可在管理页检查原账号和媒体。首页宣传片可以暂停。系统开启减少动态效果时，可按需开始播放。
- 上一公开稳定版为 0.6.80。如需软件回退，先在 0.6.81 以原请求 ID 对账未决排期、刷新、发表和升级请求，确认进入安全终态。保留原任务、系统钥匙串及回执，完成对账后沿同一市场和插件 ID 固定到 0.6.80。旧版无法处理新版部分排期结清状态和升级回执查询，新增的视频诊断也可能不显示。 [0.6.80 回退版](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.80)
