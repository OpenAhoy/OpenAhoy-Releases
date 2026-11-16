# 升级 OpenAhoy 至 0.6.61

从 [固定发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.61) 核对版本和安装包。等当前发文或生成任务结束，沿用原插件、市场、绑定、草稿、排期和未决回执。不要删除残留端点或手改插件缓存。

## 在 Codex 聊天里更新

把下面这段发给目标机器的 Codex：

> 请在这台 Mac 把现有 OpenAhoy 同槽升级到官方公开 v0.6.61。用官方 Codex 插件管理核对当前市场名、来源、固定 ref 和已装插件 ID，保留原登记和软件包。核对 [固定发行页](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.61) 的 RELEASE.json、SHA256SUMS 和完整包清单。若原登记是仅含 OpenAhoy 的公开 Git 市场 openahoy-distribution，保留原来源 https://github.com/OpenAhoy/OpenAhoy-Releases.git，把原登记换到 v0.6.61，安装并读回同一个 wechat-ecosystem@openahoy-distribution。只更新软件，保留原绑定、草稿、排期和操作回执。若原来源不同，先报告原登记，由原市场维护方沿同一插件条目更新。

旧 v0.6.60 的管理页在发现未运行的后台留下的文件时，可能报 `UPDATE_BUSINESS_BUSY`。遇到这个错误，使用上面的 Codex 插件管理路径。固定旧标签的普通刷新仍会装旧版。

独占公开市场的同槽步骤是在 Codex 宿主以 `marketplace/remove` 移除原市场登记，再用 `marketplace/add` 对原 URL 登记 `v0.6.61`。登记成功并核对来源和 ref 后，使用 `plugin/install` 安装原插件。Codex 也可代为使用官方 `codex plugin marketplace` 与 `codex plugin add` 完成同一路径，用户无需自行打开终端。登记结果未知时先查实际登记和已装版本，再按原记录恢复登记。共享市场由维护者仅调整原 OpenAhoy 条目的固定 ref 与提交，保留市场和插件 ID。

## 打开原账号恢复

插件安装后读回 v0.6.61。若当前 Codex 还在加载旧版，等当前任务结束后完整重开 Codex。回到原 OpenAhoy，看到 v0.6.61 后进入「公众号」。账号卡若提示本机绑定待恢复，点「查看恢复方法」。页面核对并列出两个原公众号 AppID 后，点击「在 macOS 中确认恢复」，由本人在系统弹窗确认一次。等页面显示「两个原绑定已恢复」，再刷新核对原账号、草稿和排期。若两号本来正常，直接检查原账号和业务回执。

没有确认按钮，或者账号与本机登记不符时，保留当前界面，把错误交给 Codex 检查。恢复完成后，请原业务聊天先按原请求 ID 查两篇原稿的草稿及发表回执。结果未知时查原任务；已发表的稿件读回实际链接。

## 软件恢复

首选同一市场、同一插件 ID 的 [v0.6.61](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.61) 校验包。已使用新版恢复，或机器重启后发生存储设备身份变化时，保留新旧凭据、快照、草稿及所有原回执。v0.6.60 可能仍会拒绝绑定读取和旧软件升级。不要用旧版的结果判断草稿丢失，不用旧快照覆盖本机状态，也不重新绑定。

[v0.6.60](https://github.com/OpenAhoy/OpenAhoy-Releases/releases/tag/v0.6.60) 保留作前一稳定版。仅在原软件事务已核到终态，且未采用新版恢复或卷凭据、当前状态已确认兼容时考虑软件回退。
