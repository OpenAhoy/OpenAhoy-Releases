# OpenAhoy 0.6.79 更新指引

在 OpenAhoy 管理页点「检查更新」，出现「立即升级」后沿原入口安装。按提示完整退出并重开 Codex，再确认「当前运行」为 0.6.79。

若内嵌入口无法完成更新，把下面这段发给本机 Codex：

> 请通过官方 Codex 插件管理，沿本机原市场和原插件 ID 更新现有 OpenAhoy 到固定版 v0.6.79。先核对原来源、ref、插件 ID、已装版本与本版清单。遇到未决安装时先回读原结果。保留原账号绑定、配置、草稿、排期、媒体及业务回执，更新后核对实际加载版本。 [正式发行](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.79)

- 专属公开市场 `openahoy-distribution` 确认来自 `https://github.com/OpenAhoy/OpenAhoy-Releases.git` 时，记录原 ref，只切换该市场登记到固定标签 `v0.6.79`，再使用官方 `codex plugin add wechat-ecosystem@openahoy-distribution`。共享市场由维护者更新原条目，沿用原插件 ID。
- 「媒体工坊」统一浏览动图、视频、音频，可筛选、预览和下载。切换视频版本可查看有原回执证明的配乐，从音频也能反查使用它的成片版本。无完整来源的历史成片按实际记录显示。已连接的 Suno 可查询账号、用量、额度与曲库。创作和重做继续在原 Codex 对话里进行。
- 上一公开稳定版为 0.6.77。若已用 0.6.79 的统一音频库或跨项目配乐，先在新版导出需要使用的媒体，并保留原文件、项目标识和回执。0.6.77 无法识别部分新统一库资产、跨项目来源和版本关联，相关工作可用原槽 0.6.79 继续查看。若只需软件回退且确认没有未决安装，可沿原市场和插件 ID 固定到 v0.6.77，原媒体资料无需迁移或重建。 [0.6.77 回退版](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.77)
