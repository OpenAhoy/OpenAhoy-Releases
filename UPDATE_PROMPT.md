# 升级 OpenAhoy 至 0.6.57

先等当前发文或生成任务结束。使用 [固定发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.57) 和 [发行清单](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.57/RELEASE.json) 核对 ZIP、SHA256SUMS 和 package-manifest.json。保留原市场登记与回退包、账号资料、钥匙串、项目规则、排期、草稿、合组回执及已有恢复材料。未决业务按原请求 ID 查询。

## 从原管理页升级

原账号状态正常时，在 OpenAhoy 管理页检查更新，确认目标 0.6.57 后执行一次。安装完成后按提示结束工作并完整重开 Codex，回到原 OpenAhoy，核对版本为 0.6.57、重启提示已消失、原账号仍在。账号列表与生产规则可先只读检查。0.6.55 旧页面可能在软件已安装后报告读回失败；遇到此情况，先对照下面的只读回执和准确版本，避免再点更新。若请求结果未知、状态仍不能确认，先按原回执查询和只读检查，不再次触发安装。

## 管理页无法完成时

先用官方 Codex CLI 只读查原插件 ID、市场来源、名称、固定 ref 和已装版本：

```sh
codex plugin list --json
codex plugin marketplace list --json
```

如果管理页因原绑定校验而中止，保留原账号恢复资料；切换软件不会自动恢复故障账号。若原来源为公开 Git 仓库 `https://github.com/OpenAhoy/OpenAhoy-Releases.git`，且 `openahoy-distribution` 市场只有 OpenAhoy，先保存可恢复的原登记来源、ref 与原软件包，再改为固定标签 `v0.6.57`：

```sh
codex plugin marketplace remove openahoy-distribution
codex plugin marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.57
```

仅在市场登记成功且回读 ref 与来源一致后，才安装原插件 `codex plugin add wechat-ecosystem@openahoy-distribution`，然后执行上述只读核对。市场登记超时先停止，读回市场、已装版本和暂存状态，再按保存的原来源与 ref 恢复必要的登记。不要重复移除、切换到 main 或覆盖账户数据。公开固定标签制品下载和 Codex 市场成功登记是两项验证。

共享市场由维护者仅更新 OpenAhoy 条目的 `git-subdir` ref 与提交 SHA，再从原市场安装。旧私有来源先按 [0.6.28 迁移说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/5428de4f2c7d603a889863d2b8e5513d1b3066e0/UPDATE_PROMPT.md) 核对原插件 ID 与来源。全新安装用本标签的 INSTALL_PROMPT.md。

如果公众号卡仍提示绑定待恢复，先点击「查看恢复方法」，沿原身份和恢复材料处理。身份恢复及列表刷新后，才使用原卡片菜单重绑或移除。升级不会重试未决业务操作。

## 软件恢复

[v0.6.55](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.55) 是前一公开稳定版；0.6.56 是本地验证版。优先同 ID、原市场重装经校验的 v0.6.57，以保留升级结果读回修复。仅在原软件升级事务已核对到终态、且目标数据与旧包兼容时，才考虑恢复到 0.6.55。保留新旧软件状态、原账号与未决回执。旧版不能解释新版软件回执的全部状态；用官方市场和 `codex plugin list --json` 核对当前安装，再查看实际加载版本。不要删除回执或用旧快照覆盖。

不要从本版直接降到 0.6.54 来处理当前安装：它不能正确读取 v0.6.55 及之后的新 X 绑定、小红书停用与 MiniMax H3 回执。相关限制见 [v0.6.55 升级说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.55/UPDATE_PROMPT.md)。
