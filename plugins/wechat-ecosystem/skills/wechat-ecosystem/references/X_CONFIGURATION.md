# X 运营配置与创作 Skill

在 X 平台设置的“X 运营配置与创作 Skill”选择真实目标账号。可新建空白、加载 JSON、按四个分类编辑、预览完整方法、保存并应用本号、下载配置或 Skill。导入只填写待保存草稿；核对目标及变更后保存才生效。保存不启用定时、不发表、不自动互动。原项目、AGENTS、选用 Skills 和五项补充偏好仍保留。

格式为 `openahoy.x-operating`，`schema_version:1`，`platform:x`；不接受公众号八字段配置冒充 X 配置。随包 `configurations/x/blank.json`、`example.json` 是空白和虚构通用示例，`account_name` 留空，在页面加载时绑定当前显示名。个人配置导出保留实际显示名，其他账号名称不符时拒绝误写。未知版本/额外字段/重复JSON键/秘密/错误时区或时刻拒绝；配置不是凭据或授权载体。未知保存查询原 `operation_id`，版本冲突保留当前填写并读取最新版本后再决定保存。

## 可填写内容

- `profile.positioning`：topics、readers、language、background、allowed、excluded、voice、facts，均为字符串。主题和语言任用户选择；背景不等于亲历。
- `profile.growth`：methods 字符串数组（多选可组合），reason、custom、cta 字符串。说明希望吸引谁、为何值得关注、如何开场和邀请行动；自定义方式完整保留。不承诺增长，不由此执行点赞/回复等互动。
- `profile.timezone`：IANA时区。`columns` 是栏目数组，每项 time（HH:MM）、name、purpose、format（text/image/auto）、selection、missing、assets。它描述栏目与素材缺口，保存时不创建时间任务、不强制配图；特殊栏目缺资料不阻断普通新内容。
- `profile.images`：subject、characters、style、aspect_ratio、color、text_brand、method。用户选择题材、人设或物件、风格、比例、色彩与文字；可不用人物，不套公众号2.35:1。质量方法先确定信息/主体关系/动作细节/构图，再生图；实际查看图片和裁切，核主题、可读性、结构、风格及细节。真实截图不能由概念图冒充；在制作阶段修正问题，不另造发表许可。
- `materials`、`notes`：用户的素材与系列说明及其他约定。本机路径不保证跨机有效，不执行文本中的命令或擅自上传资料。

## 实际采用

生产前调用 `own.projects.read {view:effective,platform_id:x,connection_id:真实本号}`。除原 sources 的每个完整分块外，**完整读取 `x_configuration.configuration` 和 `x_configuration.skill.text`**，检查 complete=true、configuration_sha256/skill.sha256；后者是当前同一保存结构实时生成的完整创作 Skill，不是独立安装的全局文件。不能只看旧五字段摘要漏掉关注方式、栏目或图片方法。未配置时沿现有项目/默认方法，不为配置缺省设发表门。

生成 Skill 是本号内容方法。原 AGENTS 职责和用户当前具体委托继续有效，内容冲突明确处理。本人当前要求的临时测试按独立临时槽执行，不改本号日常栏目、不因实际触发时刻套用某个整点栏目。每日/星期任务是否启用及目标时刻只沿原生定时配置的真实委托，不能从栏目表猜启用频率。

公众号仍用原 `openahoy.production-preferences` v1 八字段与原继承/导出流程；X个人配置不随通用插件分发，不携带旧发表句柄、账号绑定或秘密。文件选择与下载通过真实Host能力；宿主下载未提供时复用原受控 Downloads 导出，明确拒绝或UNKNOWN不切另一通路。
