# OpenAhoy 0.6.77 更新指引

在 OpenAhoy 管理页点「检查更新」。出现「立即升级」时可沿原入口安装。升级后按提示完整退出并重开 Codex，再看「当前运行」是否为 0.6.77。

0.6.77 的更新卡分别显示当前运行、最新稳定版和已安装待启用的版本。哪怕本机前次安装回执暂时读不到，也可查看是否有公开新版。如果安装状态仍待核实，请先用「查看升级状态」对账，避免重复安装。

若内嵌入口无法完成更新，把下面这段发给本机 Codex：

> 请通过官方 Codex 插件管理，沿本机原市场和原插件 ID 更新现有 OpenAhoy 到固定版 v0.6.77。先核对原来源、ref、插件 ID、实际安装版本及发行清单。先对账未决安装，再决定下一步。保留账号绑定、配置、草稿、排期和原业务回执。更新后核对实际加载版本。 [正式发行](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.77)

- 专属公开市场 `openahoy-distribution` 确认来自 `https://github.com/OpenAhoy/OpenAhoy-Releases.git` 时，记录原 ref，只切换该原市场的登记到固定标签 `v0.6.77`，再用官方 `codex plugin add wechat-ecosystem@openahoy-distribution` 安装。共享市场由维护者更新原条目，沿用原插件 ID。
- 如需软件回退，先核对安装状态和原版本，再沿同一市场和插件 ID 安装固定 v0.6.76，保留既有绑定及回执。 [0.6.76 回退版](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.76)
