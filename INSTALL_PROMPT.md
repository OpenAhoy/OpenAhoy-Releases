# 安装 OpenAhoy 0.6.54

请先阅读本版本 README.md 的系统、Python 与各平台运行条件。仅支持 macOS arm64；不需要 GitHub 登录或邀请。

让目标电脑 Codex 执行：

1. 匿名读取本固定标签的 RELEASE.json、SHA256SUMS、package-manifest.json，核对同版本 ZIP 的大小、SHA256 和全部 payload。固定 Git 标签为 v0.6.54，仓库为 https://github.com/OpenAhoy/OpenAhoy-Releases 。
2. 使用当前官方命令：`codex plugin marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.54`，随后 `codex plugin add wechat-ecosystem@openahoy-distribution`。先核当前 marketplace 来源；如同名已存在，沿官方命令切换，保留插件和账号资料，不手改缓存。
3. 核对安装为0.6.54、标准MCP初始化和工具目录、账号列表及管理资源；首次用户应为空，已有用户保留原绑定、系统钥匙串、规则、原稿与UNKNOWN任务。不要复制他人 .wce、配置或密钥。
4. 展开 OpenAhoy 管理页。用户本人在安全页绑定公众号，或在 X 官方 OAuth /小红书官方扫码完成授权。Secret 只填本机专用安全入口，不发聊天。没有授权只停在未绑定。
5. 仅安装与项目初始化：可按用户选择关联其既有 AGENTS.md 和 Skills，保留人工内容。不自动生产文章、上传、发表、点赞、回复、创建或启用定时任务。

软件安装、当前聊天原生加载、实际平台登录与业务分别报告；不将本机空用户CLI验证说成他人桌面已经采用。无需索取 GitHub token 或插件维护者的账号权限。
