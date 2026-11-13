# OpenAhoy 0.6.28

OpenAhoy 是 Codex 中的账号与内容工作台，提供内嵌管理页、项目规则/Skills、创作模板、反馈诊断及软件更新入口。

- 微信公众号：本人绑定账号，按实际接口权限处理图文、草稿、归组和普通发表。
- X：产品预置公开 OAuth Client ID，用户在 X 官方页面授权自己的账号；读写及媒体能力由官方应用权限、计费及账号权益决定。普通用户无需自行新建开发者应用。
- 小红书：独立普通 Chrome 会话，本人在官方页扫码；支持本人资料/可见笔记、图文表单提交和原笔记读回。不使用私人接口或导出 Cookie。验证码由本人在官方页面完成。
- 配置只在本机保存；安装包没有预绑账号、私人规则、文章、登录态或密钥。既有账号和规则不因软件更新重建。配置或安装本身不自动生产、发布或启用定时任务。

## 安装与升级

当前支持 macOS Apple Silicon（arm64）。需要较新的 Codex（含官方 plugin 命令）和 arm64 Python 3.11+，Git 可用。插件不会自动安装 Python/浏览器或读取其他浏览器的登录态。

复制下列文字到目标电脑 Codex：

> 请从 https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.28/INSTALL_PROMPT.md 按固定版本说明安装 OpenAhoy 0.6.28。核对公开 RELEASE.json、SHA256SUMS 和包内 manifest，使用本机支持的 Codex 官方插件命令；保留现有账号、系统钥匙串、项目规则与原稿。完成后检查空账号或原绑定、工具目录和管理资源，再打开内嵌页供我本人绑定。此次仅安装初始化，不生产、上传、发表或创建定时任务；不索取任何 Secret。

公开安装源无需 GitHub 账号、token 或私库邀请。固定版官方 CLI 命令：

```sh
codex plugin marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.28
codex plugin add wechat-ecosystem@openahoy-distribution
```

若同名 marketplace 已存在，先读其当前来源和版本，再按官方 marketplace remove/add 或现有 upgrade 能力切换公开源；不要卸载插件、删除用户数据或手改缓存。`--ref v0.6.28` 固定本版，后续升级按 UPDATE_PROMPT.md 明确选择新版本。

安装后的当前聊天是否立即加载由 Codex 宿主决定；只有确实需要且没有单插件刷新入口时再集中提示一次，不承诺所有宿主免重开。桌面插件卡片/入口以实际宿主显示为准。

小红书还需要本机 Google Chrome 和 Codex 已有的 managed Node/Playwright 运行时；缺少时会报告依赖不可用，不自动下载安装。账号权限/平台挑战、X 官方资费与应用可用性不是软件安装成功的保证。作者、选题、Skills 和发文规则均由用户自己的项目配置决定。

## 发行与隐私

此仓库仅存干净运行包、官方 marketplace 元数据和公开说明，从新历史建立；私有开发仓库及私有历史没有公开。Release ZIP 是同一运行包的补充下载，Codex 的安装入口是本 Git marketplace，不能把 ZIP 当作直接插件安装命令。随包 Python/JavaScript 运行文件可读，不宣称源码不可见，也不表示以开源许可发布。

插件不自动上传诊断。用户点击提交反馈时才附上白名单脱敏诊断；GitHub Issue 可能公开，请先查看预览。反馈不要求提供账号秘密。软件更新固定公开源 OpenAhoy/OpenAhoy-Releases。

许可与第三方说明见 LICENSE.md、THIRD_PARTY_NOTICES.md；通用创作模板沿各模板自带许可。平台名称与图标仅用于识别相应接入，并非官方背书。
