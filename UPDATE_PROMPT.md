# 升级 OpenAhoy 至 0.6.55

使用 [固定版发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.55) 和 [发行清单](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.55/RELEASE.json) 核对 ZIP、SHA256SUMS 和 package-manifest.json。先等当前发文或生成任务结束。保留原安装来源与回退包、现有账号资料、系统钥匙串、规则、排期、草稿与合组回执。持有恢复目录、经校验的快照或待确认案例时一并保留。使用原请求 ID 查询未决任务。

## 通过 Codex 升级

如果管理页升级因绑定校验失败，请在目标机器用 Codex 官方 CLI 更新软件。先运行以下只读命令，核对实际插件 ID、市场登记、固定 ref 和来源。

```sh
codex plugin list --json
codex plugin marketplace list --json
```

仅当原市场是公开 Git 源 `https://github.com/OpenAhoy/OpenAhoy-Releases.git`、名称为 `openahoy-distribution` 且只有 OpenAhoy 时，执行以下命令。这里移除的是原市场登记。保留插件与业务数据，再把同一市场登记到新标签。

```sh
codex plugin marketplace remove openahoy-distribution
codex plugin marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.55
codex plugin add wechat-ecosystem@openahoy-distribution
codex plugin list --json
```

共享市场由维护者仅更新 OpenAhoy 条目的 `git-subdir` ref 与提交 SHA，从原市场名安装。旧私有来源先按 [0.6.28 迁移说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/5428de4f2c7d603a889863d2b8e5513d1b3066e0/UPDATE_PROMPT.md) 核对原技术 ID 与来源，再决定是否迁移。全新安装使用本标签的 INSTALL_PROMPT.md。

打开原 OpenAhoy 管理页，确认加载 0.6.55 与原账号列表。若当前聊天仍加载旧资源，在发文空闲时刷新插件或按宿主提示重开 Codex。若公众号故障卡仍提示绑定待恢复，使用「查看恢复方法」，沿现有恢复材料与本人确认的步骤恢复原身份。恢复后刷新账号列表，确认原账号与合组回执，再从「更多」选择重新绑定或移除。重新绑定沿原账号处理。移除会停用目标本地连接并保留原草稿和操作回执。软件升级不会替用户恢复故障绑定，也不会重发未决业务操作。

## 软件恢复

- [v0.6.54](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.54) 是前一公开稳定版。遇到本版新状态时优先重装校验过的 v0.6.55，使用同一插件 ID 与原市场。保留 MiniMax H3 任务回执和 MP4。v0.6.54 不支持 H3 查询与资产身份验证。
- 使用过 v0.6.55 的账号移除功能时，保留现有停用记录并用 v0.6.55 恢复。v0.6.54 会忽略新版小红书停用标记，可能把停用账号重新显示为已连接。
- 在 v0.6.55 成功绑定或重新绑定 X 账号后，保留现有连接表和原回执，使用同一插件 ID 的 v0.6.55 恢复。v0.6.54 无法读取新增绑定标记，整个 X 账号列表可能显示为需要处理。不要用旧连接快照覆盖当前授权或历史回执。
- 仅在确认没有上述新状态且已有数据与 v0.6.54 兼容时，才考虑回退到 v0.6.54。
