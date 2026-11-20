# OpenAhoy 跨版本升级指引

在管理页点「检查更新」。看到最新稳定版后点「立即升级」。如果旧界面升级停在 #14 或 #16、返回 `UPDATE_PACKAGE_INVALID` 或 `UPDATE_OLD_CACHE_RETENTION_FAILED`、出现安装未完成，或旧目录含 Python 运行缓存，优先用下文的保全升级入口。缓存状态未知时也先用这一入口核对。将下面的请求发给安装 OpenAhoy 的本机 Codex：

> 请把这台电脑已安装的 OpenAhoy 同槽更新到公开最新稳定版。先读取官方 Codex 的插件和市场清单，核对原 ID、版本、来源、ref、原升级回执及业务是否空闲。按本文件核对正式发行与固定标签，优先使用该版本已核源码中的恢复命令调用官方 Codex CLI。保留原市场、缓存、账号、钥匙串、规则、排期、草稿、素材和原回执。请核对实际安装和运行版本。无需清缓存、逐版安装或重绑。

## 确认目标

1. 从 [GitHub 正式稳定发行](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/latest) 读取正式版本，并核对 [该版本的发行元数据](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/latest/download/RELEASE.json)。将版本与固定标签、Git 提交、该提交内的 `RELEASE.json`、ZIP SHA-256 和 `package-manifest.json` 对齐。源未同步或网络不通时保留原安装，重新查询同一官方入口。发现相同或更高的已装版本时只核对现状。
2. 先沿原回执查询进行中或结果未知的安装。发现已安装等待加载时按实际宿主提示重开一次。不要清除升级回执或恢复历史业务快照来使按钮可用。

## 先保全旧缓存再升级

0.6.80 的更新进程可能拒绝合法的 Python 运行缓存。0.6.83 的更新进程还可能因读取文件改变访问时间而报缓存保全失败。遇到上述错误时，使用目标版本的脚本。从已核对的正式发行固定标签将源码检出到独立目录，核对其中的运行文件和清单，运行 `scripts/upgrade_existing.py`。参数使用官方清单查到的原插件 ID 和该次稳定版版本。以核对 0.6.94 为正式目标、原市场为专属公开市场为例：

```sh
python3 -I -B scripts/upgrade_existing.py --plugin-id wechat-ecosystem@openahoy-distribution --version 0.6.94
```

命令适用于专属公开市场、仍使用原 OpenAhoy 兼容 Git 仓库的同名专属市场和已支持的本机共享市场。共享市场使用实际查到的原插件 ID。恢复程序复用同一套更新锁、包验证和回执，调用官方 Codex CLI 更新原槽。原目录会保存在 Codex 数据目录的 `plugins/openahoy-retained-cache` 下，回退使用校验过的干净软件。宿主激活新版本后、旧路径恢复前，旧进程新启动可能短暂出现 `ENOENT`。脚本只有在恢复并核验旧路径后才返回成功回执。旧聊天的工具遇到启动失败时先等安装结束，再查看原请求状态。完成当前任务后重启 Codex，可加载新版工具。看到未知结果时先查原回执和官方安装清单。如果原市场或启用项缺失，先核对原来源、原 ref、原回执与已保全目录，交市场维护者用官方 CLI 恢复同一登记，结果确认后再继续。

## 已核对无需保全运行缓存的原市场更新

以下普通 CLI 步骤仅适用于已核实旧安装没有额外 Python 运行缓存的情况。Codex 激活新版时会清理旧版本目录。遇到 #14、发现缓存或无法核实缓存状态时，先用上面的保全入口。

- **专属公开市场** `openahoy-distribution`。确认市场只含 OpenAhoy，并保存原固定版本与回退依据。通过官方 Codex 的 marketplace remove / add 把该独占市场的登记切到已核对的公开固定标签，再执行 `codex plugin add wechat-ecosystem@openahoy-distribution`。旧登记跟着默认分支时，也可直接固定到目标版。保留固定旧 ref 的 marketplace upgrade 只会刷新那个旧 ref。
- **共享市场**。由该市场维护者只更新 OpenAhoy 一条来源，既有名称和其他插件保持不变。使用维护者更新后的源，再通过官方 Codex 对原 `wechat-ecosystem@原市场名` 安装一次。用户维护的本机市场可将这一条指向已完整核验、保留在市场根内的插件源目录，也可以使用固定公开 tag 和 Git SHA 的 `git-subdir`，插件路径为 `plugins/wechat-ecosystem`。保留原条目供回退。共享市场的远端登记沿该市场自己的维护通路更新。
- **旧私有来源**。旧源固定标签提供同一运行包。先核对原请求、市场和旧安装缓存。仍登记 `OpenAhoy/OpenAhoy-Distribution` 的专属市场使用上面的保全入口。相同标签须在兼容源可读，且包清单须与公开元数据一致。其他远端市场由原维护者更新 OpenAhoy 条目。继续使用原市场名和插件 ID。

完成后用官方 plugin list 与标准 MCP 启动回读目标版本，再核对管理页的「当前运行」。回退前先核对升级、排期、令牌刷新和发表的原回执，保留现有账号与业务资料，仅沿相同市场和插件 ID 回退软件到已验证版本。专属公开或兼容 Git 市场通过官方 marketplace remove / add 在原仓库切回原固定标签，再为同一插件 ID 执行 plugin add。共享本机市场将原条目指回已验证的干净来源，再安装同一个 ID。本次回退目标为 [0.6.93](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.93)。回退软件时保留项目数据和媒体回执。0.6.93 保留公众号数据监控和配置两个页面，账号选择恢复为顶部账号栏。
