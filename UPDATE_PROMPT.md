# OpenAhoy 跨版本升级指引

在管理页点「检查更新」。看到最新稳定版后点「立即升级」。如果页面仍显示旧版、停在旧回执、没有升级按钮，或旧私有源需要登录，把下面的请求发给安装 OpenAhoy 的本机 Codex。只要一次授权，即可从现有版本直达公开最新稳定版。

> 请把这台电脑已安装的 OpenAhoy 直接更新到公开最新稳定版。先确认官方 Codex 的现有 OpenAhoy 插件 ID、所属市场、来源、ref 和实际已装版本，再匿名读取 OpenAhoy/OpenAhoy-Releases 的 latest 发行及其 RELEASE.json，核对固定 Git 标签和提交、ZIP 和包清单。按下文的市场类型走官方 Codex 安装入口，只更新原 OpenAhoy，保持原插件 ID 和市场命名空间。先核对原升级请求和业务是否空闲，保留原账号、钥匙串、配置、排期、草稿、成片、历史及未知回执。更新后核对已安装版本和实际运行版本，无需逐版升级或重新绑定。

## 确认目标

1. 从 [GitHub 正式稳定发行](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/latest) 读取正式版本，并核对 [该版本的发行元数据](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/latest/download/RELEASE.json)。将版本与固定标签、Git 提交、该提交内的 `RELEASE.json`、ZIP SHA-256 和 `package-manifest.json` 对齐。源未同步或网络不通时保留原安装，重新查询同一官方入口。发现相同或更高的已装版本时只核对现状。
2. 先沿原回执查询进行中或结果未知的安装。发现已安装等待加载时按实际宿主提示重开一次。不要清除升级回执或恢复历史业务快照来使按钮可用。

## 按原市场更新一次

- **专属公开市场** `openahoy-distribution`。确认市场只含 OpenAhoy，并保存原固定版本与回退依据。通过官方 Codex 的 marketplace remove / add 把该独占市场的登记切到已核对的公开固定标签，再执行 `codex plugin add wechat-ecosystem@openahoy-distribution`。旧登记跟着默认分支时，也可直接固定到目标版。保留固定旧 ref 的 marketplace upgrade 只会刷新那个旧 ref。
- **共享市场**。由该市场维护者只更新 OpenAhoy 一条来源，既有名称和其他插件保持不变。使用维护者更新后的源，再通过官方 Codex 对原 `wechat-ecosystem@原市场名` 安装一次。用户维护的本机市场可将这一条指向已完整核验、保留在市场根内的插件源目录，也可以使用固定公开 tag 和 Git SHA 的 `git-subdir`，插件路径为 `plugins/wechat-ecosystem`。保留原条目供回退。共享市场的远端登记沿该市场自己的维护通路更新。
- **旧私有来源**。有访问权并从原按钮发起时，可使用旧私有仓库里与目标公开版本同载荷的固定标签。若旧源无权访问，可从这里明确委托本机 Codex 更新原条目为公开来源。保留原市场和插件 ID，避免双份启用。旧版的刷新按钮能否直接工作取决于它原来编译的来源和宿主能力。

完成后用官方 plugin list 与标准 MCP 启动回读目标版本，再核对管理页的「当前运行」。回退前先核对升级、排期、令牌刷新和发表的原回执，保留现有账号与业务资料，仅沿相同市场和插件 ID 回退软件到已验证版本。0.6.82 的上一公开版为 [0.6.81](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.81)。
