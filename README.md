# OpenAhoy 0.6.71

OpenAhoy 是 Codex 中的账号与内容工作台，提供内嵌管理页、项目规则/Skills、创作模板、反馈诊断及软件更新入口。

- 微信公众号：本人绑定账号，按实际接口权限处理图文、草稿、归组和普通发表。
- X：在管理页保存自己的 X 开发者应用资料，再到 X 官方页面授权。可发布纯文字或带媒体的帖子，实际能力由该应用的权限、额度及账号权益决定。
- 小红书：独立普通 Chrome 会话，本人在官方页扫码；支持本人资料/可见笔记、图文表单提交和原笔记读回。不使用私人接口或导出 Cookie。验证码由本人在官方页面完成。
- 配置只在本机保存；安装包没有预绑账号、私人规则、文章、登录态或密钥。既有账号和规则不因软件更新重建。配置或安装本身不自动生产、发布或启用定时任务。

公众号和 X 加载配置时会用实色标出可准确对应的快捷选项，自定义文字单独显示。账号绑定与选择集中在 OpenAhoy 管理页。

新版 X 账号管理支持先保存应用资料，刷新会读回，授权可单独发起。账号卡状态更简洁。

视频工作区分为模型设置与项目成片，支持 Seedance 与 MiniMax H3。账号菜单支持在核对原身份后重新绑定或移除本地连接。

在符合原存储证明的机器上，OpenAhoy 可在管理页恢复两个原公众号绑定，由本人在 macOS 确认。

0.6.71 修复管理页刷新、旧后台状态误判和升级占用提示，沿用原市场和插件 ID。

AutoDL · MiniMax H3 在「视频生成 → 模型设置」中有独立卡片，沿用原项目任务和成片下载入口。

0.6.71 改善 AutoDL 官方工作流回执和成片下载在部分网络下的可用性。

0.6.71 新增独立「动图生成」页，以及 X 原生多图文章的建稿、发布和原回执查询。管理页显示已查到的最新稳定版。

## 安装与升级

当前支持 macOS Apple Silicon（arm64）。需要较新的 Codex（含官方 plugin 命令）和 arm64 Python 3.11+，Git 可用。插件不会自动安装 Python/浏览器或读取其他浏览器的登录态。

复制下列文字到目标电脑 Codex：

> 请先用官方 plugin list / marketplace list 查本机是否已有 OpenAhoy。已有安装先读取 https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.71/UPDATE_PROMPT.md 的迁移分类，只更新原 OpenAhoy 并保留 namespace，不移除共享市场、不另启第二份；只有从未安装时才读取固定 v0.6.71/INSTALL_PROMPT.md。目标运行包始终为正式公开0.6.71，核对其 RELEASE.json、SHA256SUMS 和完整manifest，保留账号、系统钥匙串、项目规则和原稿。安装后检查工具与管理页；此次不生产、上传、发表或启用定时任务，不索取Secret。

已安装用户按固定版 UPDATE_PROMPT.md 从 Codex 聊天同槽升级。公开安装源无需 GitHub 账号、token 或私库邀请。全新安装时先登记固定市场，登记成功后再安装：

```sh
codex plugin marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.71
codex plugin add wechat-ecosystem@openahoy-distribution
```

已有安装先读本仓库 UPDATE_PROMPT.md 的迁移分类：共享市场只更新 OpenAhoy 条目并保持原namespace，禁止remove整个共享市场；独占源才按实际登记切换。不要卸载插件、删除用户数据或手改缓存。`--ref v0.6.71` 固定本版，登记超时时先只读对账，完整步骤见 UPDATE_PROMPT.md。

安装后的当前聊天是否立即加载由 Codex 宿主决定；只有确实需要且没有单插件刷新入口时再集中提示一次，不承诺所有宿主免重开。桌面插件卡片/入口以实际宿主显示为准。

小红书还需要本机 Google Chrome 和 Codex 已有的 managed Node/Playwright 运行时；缺少时会报告依赖不可用，不自动下载安装。账号权限/平台挑战、X 官方资费与应用可用性不是软件安装成功的保证。作者、选题、Skills 和发文规则均由用户自己的项目配置决定。

## 发行与隐私

此仓库仅存干净运行包、官方 marketplace 元数据和公开说明，从新历史建立；私有开发仓库及私有历史没有公开。Release ZIP 是同一运行包的补充下载，Codex 的安装入口是本 Git marketplace，不能把 ZIP 当作直接插件安装命令。随包 Python/JavaScript 运行文件可读，不宣称源码不可见，也不表示以开源许可发布。

反馈支持从管理页或 Codex 对话查看脱敏预览，并在用户明确提交后发送。GitHub Issue 可能公开，凭据保留在本机安全入口。软件更新固定公开源 OpenAhoy/OpenAhoy-Releases。

许可与第三方说明见 LICENSE.md、THIRD_PARTY_NOTICES.md；通用创作模板沿各模板自带许可。平台名称与图标仅用于识别相应接入，并非官方背书。
