# 升级 OpenAhoy 至 0.6.54

正式源为 [OpenAhoy/OpenAhoy-Releases](https://github.com/OpenAhoy/OpenAhoy-Releases)。按 [v0.6.54 发行清单](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.54/RELEASE.json) 和随版 SHA256SUMS、package-manifest.json 核对制品。先用 Codex 官方命令读回实际版本、市场来源、技术 ID 和启用状态。支持直接升级的版本可在内嵌页安装并查看进度。旧版仍可按下面的官方 CLI 路径升级。

- **公开独占市场**：技术 ID 保持 `wechat-ecosystem@openahoy-distribution`。固定旧标签时，普通 marketplace upgrade 会保留旧 ref；确认市场仅有 OpenAhoy 后，沿官方 marketplace remove/add 把市场登记更新到 `https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.54`，再用官方 `codex plugin add wechat-ecosystem@openahoy-distribution`。不卸载插件、不删除数据。
- **共享市场**：保留原市场名和其他插件，别删除整个市场或另启第二份 OpenAhoy。由该市场维护者只将 OpenAhoy 条目的 git-subdir ref 更新为 `v0.6.54`，并以该公开标签实际解析到的提交替换原 sha；核对后沿原 marketplace 名安装。保留已有单条变更保护；受管市场无法安全编辑时交原维护者。
- **旧私有来源**：较旧客户端可能只发现迁移用的 0.6.28。按 [0.6.28 迁移说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/5428de4f2c7d603a889863d2b8e5513d1b3066e0/UPDATE_PROMPT.md) 识别原命名和来源，再由用户选择采用公开源。全新安装见本版 INSTALL_PROMPT.md。

在安全点升级，保留原安装来源、版本和已校验的软件包。保留账号、钥匙串、规则、项目、草稿、历史和未决请求，软件恢复无需删除、还原或覆盖用户数据。

## 软件恢复

- 已授权自有 X 应用后，旧公开版 0.6.31 不能读取更新后的连接格式，会影响 X 账号列表。保留现有数据，用相同插件技术 ID 从本版公开发行源重新安装已校验的 0.6.54，可恢复兼容运行环境。只执行软件恢复，不重绑、不重新提交原任务。用原回执查询其状态。
- 已保留原 0.6.53 软件及原安装来源的设备，也可按原来源恢复 0.6.53。该版本在隔离验证中读回两个连接、自有应用与原应用未决记录。它不是公开发行下载项。
- 0.6.31 是前一公开稳定版。只有确认 X 数据仍为旧格式时，才考虑用它恢复软件。即使误装 0.6.31，也应保留现有数据并重新安装 0.6.54，不把授权前的备份覆盖到当前记录。

核对安装包完整性、标准 MCP 版本与工具、管理资源及原有账号可见性。当前聊天实际加载另行确认。
