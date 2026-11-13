# 升级与旧来源迁移 · OpenAhoy 0.6.28

这是 OpenAhoy 原分发者指定的公开后继源。正式运行制品仍是未改写的 public v0.6.28 / commit ad078b170bc829ea5a5b8d5d081c6d3e98bcd6e6；本次只补迁移说明，不推出0.6.29、不修改该标签或包。旧PRIVATE源后来新增的v0.6.28只为旧checker发现这一迁移，目标仍为本公开正式包。

核验目标：OpenAhoy/OpenAhoy-Releases；ZIP SHA256 507048f2385c3fc06e585c5f092f64b467d7f61d1ec9d74f630ebfdb050c8aab；包内manifest SHA256 907b7b6962861984e29feb4bee4ee1bd5314d9af992a0008b1d570838a39eb88；496payload。读取该固定运行标签的RELEASE.json和完整manifest并逐项核验，不拿迁移说明冒运行包。

## 先核本机实际登记

用官方 `codex plugin list --json`、`codex plugin marketplace list --json` 查当前技术ID、市场来源、已装版本和启用状态。更新只操作OpenAhoy（技术name仍wechat-ecosystem），保留同名其他插件、现有namespace及所有账号、Keychain引用、个人规则、项目、原稿、历史和UNKNOWN。

先保存精确627回退软件及配置/数据保护记录。正常官方安装可能清理旧软件cache，不能只依赖原cache目录做回退。禁止恢复旧账号DB快照覆盖新数据。业务在途先等其完成，不杀其他任务。沿已验证包的 scripts/wce_update_brokers.py 的quiesced上下文持有两号启动门，配合既有设置/X/project等维护锁覆盖安装和回读；idle_drain只释放空闲旧broker，忙则等待安全点，未知先查原任务，不重发平台请求。

## A. 共享、本机用户维护的local marketplace

例如已启用wechat-ecosystem@my-plugins，市场内还含其他工具插件。**不能remove这个共享市场，也不能另外启用第二份OpenAhoy。** 根据官方marketplace登记找到用户维护的marketplace.json（不要改供应商cache/snapshot），保全原文件并按原SHA做单行CAS：保留所有其他条目、原目标字段，只把wechat-ecosystem那条source替换为：

```json
{
  "source": "git-subdir",
  "url": "https://github.com/OpenAhoy/OpenAhoy-Releases.git",
  "path": "plugins/wechat-ecosystem",
  "ref": "v0.6.28",
  "sha": "ad078b170bc829ea5a5b8d5d081c6d3e98bcd6e6"
}
```

采用同目录临时文件/原mode/owner核验和原字节CAS原子替换，不跟随symlink，不重写其他插件配置。然后执行 `codex plugin add wechat-ecosystem@原有marketplace名 --json`；上例原市场名为my-plugins。保持原技术ID和marketplace名，因此不会另起宿主插件data namespace。

如原市场为共享远端受管Git源，不直接编辑其vendor缓存；应让该市场维护者只更新OpenAhoy源条目，或使用当前宿主明确支持的单插件来源迁移入口。没有安全单条迁移入口时报告具体登记，不删除整个市场或猜新namespace。

## B. 独占OpenAhoy的旧私有分发marketplace

只有确认该市场仅有OpenAhoy时，才沿官方 `marketplace remove 该市场名` / `marketplace add https://github.com/OpenAhoy/OpenAhoy-Releases.git --ref v0.6.28` / `plugin add wechat-ecosystem@openahoy-distribution` 切公开源。先确认原namespace是否本来就是openahoy-distribution；原名不同不能在未核宿主data归属时静默重命名。不是 `plugin remove`，不卸载软件或删除账号资料。已固定旧Git tag的marketplace upgrade会保留原ref，因此仅刷新不足以切新版本。

## C. 从未安装

使用本公开固定运行标签的INSTALL_PROMPT.md与官方两步marketplace add/plugin add。首次账号应为空，用户本人在内嵌页完成绑定，不需要开发者GitHub邀请/token。

## 安装验收

逐manifest校核已装628全部496payload；仅一份OpenAhoy启用，其他插件启用/来源/版本保持。标准MCP initialize和工具目录、当前聊天真实原生调用及管理resource版本分别验证。628检查更新应指PUBLIC OpenAhoy/OpenAhoy-Releases且UP_TO_DATE。独立stdio不冒当前聊天已加载。

尽量使用宿主支持刷新；无可用单插件刷新、已证宿主仍用旧连接时再集中说明必要的一次重开，不盲重启整个Codex或强杀进程。保留原包做软件回退，不覆盖账号数据、不索取Secret、不读Keychain秘密、不新开平台授权，不以升级进行内容上传/发表/互动/定时任务。运营机只按本人委托在当地执行，不远控代装。
