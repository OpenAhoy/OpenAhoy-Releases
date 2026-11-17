# OpenAhoy 0.6.76 更新指引

在 OpenAhoy 管理页选择「检查更新」和「立即升级」。按提示重开 Codex，再核对实际运行版本为 0.6.76。

如果原页只显示「查看升级状态」或按钮不可用，把下面这段发给本机 Codex：

> 请通过官方 Codex 插件管理，沿本机原市场和原插件 ID 更新现有 OpenAhoy 到固定版 v0.6.76。先核对原来源、ref、插件 ID、实际安装版本与发行清单。更新时保留账号绑定、草稿、配置、排期和业务回执。更新后核对实际加载版本。 [正式发行](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.76)

- 原市场为来自 `https://github.com/OpenAhoy/OpenAhoy-Releases.git` 的专属 `openahoy-distribution` 时，记录原 ref，仅移除对应市场登记，用同一来源登记固定标签 `v0.6.76`，然后用官方 `codex plugin add wechat-ecosystem@openahoy-distribution` 安装到原槽位。共享市场由维护者更新原条目并沿用原插件 ID。安装结果未知时，先读回原市场和已装版本。
- 升级后可在原聊天检查 `x.profile.read`、`x.posts.read` 和 `x.posts.readback`。已有帖子直接读原帖或原发布回执，无需重发。其他插件配置可能影响 Codex 最终分配的工具描述预算。
- 如需软件回退，先读回原安装结果并确认无未决安装，再沿同一市场及插件 ID 采用固定 v0.6.75，继续保留原业务数据与回执。0.6.75 在相同隔离配置下仍会出现工具预算不足。 [0.6.75 回退版](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.75)
