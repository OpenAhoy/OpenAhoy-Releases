# 升级 OpenAhoy 至 0.6.29

正式源为 [OpenAhoy/OpenAhoy-Releases](https://github.com/OpenAhoy/OpenAhoy-Releases)。按 [v0.6.29 发行清单](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.29/RELEASE.json) 和随版 SHA256SUMS、package-manifest.json 核对制品。先用 Codex 官方命令读回实际版本、市场来源、技术 ID 和启用状态。内嵌页的升级入口只发起请求；由用户授权的目标电脑 Codex 执行实际安装。

- **公开独占市场**：技术 ID 保持 `wechat-ecosystem@openahoy-distribution`。固定旧标签时，普通 marketplace upgrade 会保留旧 ref；确认市场仅有 OpenAhoy 后，沿官方 marketplace remove/add 把市场登记更新到 `https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.29`，再用官方 `codex plugin add wechat-ecosystem@openahoy-distribution`。不卸载插件、不删除数据。
- **共享市场**：保留原市场名和其他插件，别删除整个市场或另启第二份 OpenAhoy。由该市场维护者只将 OpenAhoy 条目的 git-subdir ref 更新为 `v0.6.29`，并以该公开标签实际解析到的提交替换原 sha；核对后沿原 marketplace 名安装。保留已有单条变更保护；受管市场无法安全编辑时交原维护者。
- **旧私有来源**：较旧客户端可能只发现迁移用的 0.6.28。按 [0.6.28 迁移说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/5428de4f2c7d603a889863d2b8e5513d1b3066e0/UPDATE_PROMPT.md) 识别原命名和来源，再由用户选择采用公开源。全新安装见本版 INSTALL_PROMPT.md。

在安全点更新并保留原软件作为回退，包括 [0.6.28 稳定包](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.28)。保留账号、钥匙串、规则、项目、草稿、历史及未决请求；回退软件不覆盖账号数据。核对安装包完整性、标准 MCP 版本与工具、管理资源及原有账号可见性。当前聊天实际加载另行确认。不要重绑、代开授权、索取密钥或试发内容。
