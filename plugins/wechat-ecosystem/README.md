# Jiusera for Codex

Jiusera 是 Codex 中的账号与内容工作台，提供内嵌管理页、项目规则/Skills、创作模板、反馈诊断及软件更新入口。

- 微信公众号：本人绑定账号，按实际接口权限处理图文、草稿、归组和普通发表。
- X：产品预置公开 OAuth Client ID，用户在 X 官方页面授权自己的账号；读写及媒体能力由官方应用权限、计费及账号权益决定。普通用户无需自行新建开发者应用。
- 小红书：独立普通 Chrome 会话，本人在官方页扫码；支持本人资料/可见笔记、图文表单提交和原笔记读回。不使用私人接口或导出 Cookie。验证码由本人在官方页面完成。
- 配置只在本机保存；安装包没有预绑账号、私人规则、文章、登录态或密钥。既有账号和规则不因软件更新重建。配置或安装本身不自动生产、发布或启用定时任务。

公众号和 X 加载配置时会用实色标出可准确对应的快捷选项，自定义文字单独显示。账号绑定与选择集中在 Jiusera 管理页。

## 安装与升级

当前支持 macOS Apple Silicon（arm64）。需要较新的 Codex（含官方 plugin 命令）和 arm64 Python 3.11+，Git 可用。插件不会自动安装 Python/浏览器或读取其他浏览器的登录态。

复制下列文字到目标电脑 Codex：

> 请用 Codex 的插件与市场列表核对已有安装。通过[发行说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/main/UPDATE_PROMPT.md)选择已发布的目标版本，沿原插件槽位更新，保留账号和本机配置。首次安装见[安装说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/main/INSTALL_PROMPT.md)。

## 发行与隐私

此仓库仅存干净运行包、官方 marketplace 元数据和公开说明，从新历史建立；私有开发仓库及私有历史没有公开。Release ZIP 是同一运行包的补充下载，Codex 的安装入口是本 Git marketplace，不能把 ZIP 当作直接插件安装命令。随包 Python/JavaScript 运行文件可读，不宣称源码不可见，也不表示以开源许可发布。

插件不自动上传诊断。用户点击提交反馈时才附上白名单脱敏诊断；GitHub Issue 可能公开，请先查看预览。反馈不要求提供账号秘密。软件更新固定公开源 OpenAhoy/OpenAhoy-Releases。

许可与第三方说明见 LICENSE.md、THIRD_PARTY_NOTICES.md；通用创作模板沿各模板自带许可。平台名称与图标仅用于识别相应接入，并非官方背书。
