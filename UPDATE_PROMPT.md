# 升级 OpenAhoy 至 0.6.60

先等当前发文或生成任务结束。使用 [固定发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.60) 和 [发行清单](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.60/RELEASE.json) 核对 ZIP、SHA256SUMS 和 package-manifest.json。保留原市场登记与回退包、账号资料、钥匙串、项目规则、排期、草稿、合组回执及已有恢复材料。未决业务按原请求 ID 查询。

## 从原管理页升级

原账号状态正常时，在 OpenAhoy 管理页检查更新，确认目标 0.6.60 后执行一次。安装完成后按提示结束工作并完整重开 Codex，回到原 OpenAhoy，核对版本为 0.6.60、重启提示已消失、原账号仍在。账号列表与生产规则可先只读检查。0.6.55 旧页面可能在软件已安装后报告读回失败；遇到此情况，先对照下面的只读回执和准确版本，避免再点更新。若请求结果未知、状态仍不能确认，先按原回执查询和只读检查，不再次触发安装。

## 管理页无法完成时

先用官方 Codex CLI 只读查原插件 ID、市场来源、名称、固定 ref 和已装版本：

```sh
codex plugin list --json
codex plugin marketplace list --json
```

如果管理页因原绑定校验而中止，保留原账号恢复资料；切换软件不会自动恢复故障账号。若原来源为公开 Git 仓库 `https://github.com/OpenAhoy/OpenAhoy-Releases.git`，且 `openahoy-distribution` 市场只有 OpenAhoy，先保存可恢复的原登记来源、ref 与原软件包，再改为固定标签 `v0.6.60`：

```sh
codex plugin marketplace remove openahoy-distribution
codex plugin marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.60
```

仅在市场登记成功且回读 ref 与来源一致后，才安装原插件 `codex plugin add wechat-ecosystem@openahoy-distribution`，然后执行上述只读核对。市场登记超时先停止，读回市场、已装版本和暂存状态，再按保存的原来源与 ref 恢复必要的登记。不要重复移除、切换到 main 或覆盖账户数据。公开固定标签制品下载和 Codex 市场成功登记是两项验证。

共享市场由维护者仅更新 OpenAhoy 条目的 `git-subdir` ref 与提交 SHA，再从原市场安装。旧私有来源先按 [0.6.28 迁移说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/5428de4f2c7d603a889863d2b8e5513d1b3066e0/UPDATE_PROMPT.md) 核对原插件 ID 与来源。全新安装用本标签的 INSTALL_PROMPT.md。

如果公众号卡仍提示绑定待恢复，先点击「查看恢复方法」，沿原身份和恢复材料处理。身份恢复及列表刷新后，才使用原卡片菜单重绑或移除。升级不会重试未决业务操作。

## 软件恢复

优先用原市场和同一插件 ID 重装经校验的 [v0.6.60](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.60)。已通过新版提交 X 纯文字时，保留原请求与回执，用 v0.6.60 查询。旧版 v0.6.57 无法可靠核对纯文字帖子。若原帖 ID 未知，原请求保持待确认，勿因旧版显示异常重发。已保存的纯文字排期也需用支持纯文字的版本执行。

[v0.6.57](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.57) 是前一公开稳定版。只在原软件事务已核对到终态，且当前状态和任务可由旧版处理时考虑恢复 v0.6.57。保留原软件回执、账号资料、显示名及历史，不覆盖旧数据。旧版可能不能解释新版软件回执或提供新版绑定诊断，安装和实际加载以官方 CLI 及宿主读回为准。

不要将 v0.6.54 用作当前回退包。它不能正确读取新版 X 绑定、小红书停用记录与 MiniMax H3 回执。更多见 [v0.6.55 升级说明](https://github.com/OpenAhoy/OpenAhoy-Releases/blob/v0.6.55/UPDATE_PROMPT.md)。
