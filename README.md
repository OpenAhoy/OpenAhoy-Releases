# OpenAhoy 0.6.90

OpenAhoy 是 Codex 中的账号与内容工作台，提供内嵌管理页、项目规则/Skills、创作模板、反馈诊断及软件更新入口。

- 微信公众号：本人绑定账号，按实际接口权限处理图文、草稿、归组和普通发表。
- X：在管理页保存自己的 X 开发者应用资料，再到 X 官方页面授权。可发布纯文字或带媒体的帖子，实际能力由该应用的权限、额度及账号权益决定。
- 小红书：独立普通 Chrome 会话，本人在官方页扫码；支持本人资料/可见笔记、图文表单提交和原笔记读回。不使用私人接口或导出 Cookie。验证码由本人在官方页面完成。
- 配置只在本机保存；安装包没有预绑账号、私人规则、文章、登录态或密钥。既有账号和规则不因软件更新重建。配置或安装本身不自动生产、发布或启用定时任务。

公众号和 X 加载配置时会用实色标出可准确对应的快捷选项，自定义文字单独显示。账号绑定与选择集中在 OpenAhoy 管理页。

新版 X 账号管理支持先保存应用资料，刷新会读回，授权可单独发起。账号卡状态更简洁。

视频工作区分为模型设置与项目成片，支持 Seedance 与 MiniMax H3。账号菜单支持在核对原身份后重新绑定或移除本地连接。

在符合原存储证明的机器上，OpenAhoy 可在管理页恢复两个原公众号绑定，由本人在 macOS 确认。

已有安装沿用原市场和插件 ID，可在管理页检查最新稳定版和安装状态。内嵌页停在旧版时，使用 [一步升级指引](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/main/UPDATE_PROMPT.md)。

AutoDL · MiniMax H3 的模型配置沿用原入口，可查询原项目任务和下载成片。

原 X 多图文章可继续建稿、发布和查询原回执。

「Jiusera」统一浏览动图、视频和音频，支持预览、下载、版本对比和按版本查看配乐关联。音频页支持 Suno 与 ACE Music，并可保存本机默认音乐供应商。ACE Music 使用独立的官方 Codex MCP 连接和本人 OAuth。已授权后可查看计划、余额、费用、模型与曲库；免费计划可通过官方歌曲页试听，MCP 文件下载按官方计划权限。本机配乐合成需要 FFmpeg 和 ffprobe。

公众号工作区选中已绑定账号后显示本号数据监控，可切换近 7 天与 30 天，查看关注、内容趋势和单篇累计统计。数据截至北京统计日，公众号接口权限与回包状态会直接显示。

软件更新通过公开正式发行与 Git 标签核对最新稳定版。跨版本安装可保全旧版 Python 运行缓存，并准备干净的回退包。X 长文原帖读回使用完整正文核对已成功发表的原帖，并继续校验作者和附件。旧版本的恢复步骤见更新指引。

## 安装与升级

当前支持 macOS Apple Silicon（arm64）。需要较新的 Codex（含官方 plugin 命令）和 arm64 Python 3.11+，Git 可用。插件不会自动安装 Python/浏览器或读取其他浏览器的登录态。

复制下列文字到目标电脑 Codex：

> 请先用官方 plugin list / marketplace list 查本机是否已有 OpenAhoy。已有安装先读取 https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.90/UPDATE_PROMPT.md 的迁移分类，只更新原 OpenAhoy 并保留 namespace，不移除共享市场、不另启第二份；只有从未安装时才读取固定 v0.6.90/INSTALL_PROMPT.md。目标运行包始终为正式公开0.6.90，核对其 RELEASE.json、SHA256SUMS 和完整manifest，保留账号、系统钥匙串、项目规则和原稿。安装后检查工具与管理页；此次不生产、上传、发表或启用定时任务，不索取Secret。

已安装用户按固定版 UPDATE_PROMPT.md 从 Codex 聊天同槽升级。公开安装源无需 GitHub 账号、token 或私库邀请。全新安装时先登记固定市场，登记成功后再安装：

```sh
codex plugin marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.90
codex plugin add wechat-ecosystem@openahoy-distribution
```

已有安装先读本仓库 UPDATE_PROMPT.md 的迁移分类：共享市场只更新 OpenAhoy 条目并保持原namespace，禁止remove整个共享市场；独占源才按实际登记切换。不要卸载插件、删除用户数据或手改缓存。`--ref v0.6.90` 固定本版，登记超时时先只读对账，完整步骤见 UPDATE_PROMPT.md。

安装后的当前聊天是否立即加载由 Codex 宿主决定；只有确实需要且没有单插件刷新入口时再集中提示一次，不承诺所有宿主免重开。桌面插件卡片/入口以实际宿主显示为准。

小红书还需要本机 Google Chrome 和 Codex 已有的 managed Node/Playwright 运行时；缺少时会报告依赖不可用，不自动下载安装。账号权限/平台挑战、X 官方资费与应用可用性不是软件安装成功的保证。作者、选题、Skills 和发文规则均由用户自己的项目配置决定。

## 本地构建

从目标版本的发行源码检出运行构建器。ZIP 直接使用该检出中 Git 市场的运行文件和已检入的原生助手。同一份源码生成相同字节的 ZIP。

```sh
python3 -B scripts/build_codex_plugin.py /absolute/path/openahoy-0.6.90-macos-arm64
```

修改发行源码后，先用 `python3 -B scripts/build_codex_plugin.py --refresh-manifest` 更新两份清单。该命令只更新本检出的清单。构建要求目标目录和 ZIP 均待创建。

## Jiusera

选择登记的项目和作品，即可在同一导演画布编排镜头、文字卡、图片、成片、音频和动图。平移、缩放和卡片位置随作品保存。在资产详情可预览、读回原配乐关系或下载原文件。图片可直接从本机导入，也可在选定镜头把文字或图片分镜交给 Codex 修改。供应商设置与原资产回执沿原入口使用。

## 发行与隐私

此仓库仅存干净运行包、官方 marketplace 元数据和公开说明，从新历史建立；私有开发仓库及私有历史没有公开。Release ZIP 是同一运行包的补充下载，Codex 的安装入口是本 Git marketplace，不能把 ZIP 当作直接插件安装命令。随包 Python/JavaScript 运行文件可读，不宣称源码不可见，也不表示以开源许可发布。

反馈支持从管理页或 Codex 对话查看脱敏预览，并在用户明确提交后发送。GitHub Issue 可能公开，凭据保留在本机安全入口。软件更新固定公开源 OpenAhoy/OpenAhoy-Releases。

许可与第三方说明见 LICENSE.md、THIRD_PARTY_NOTICES.md；通用创作模板沿各模板自带许可。平台名称与图标仅用于识别相应接入，并非官方背书。
