# 初始化当前运营项目

内嵌页“项目与 Skills → 初始化当前项目”把明确委托发到当前聊天，由当前 Codex 调用原生 `own.projects.initialize` 实际落盘与登记。消息 ACK 仅表示已发送，不是文件完成或聊天已加载。只需关联原来源时继续用 `own.projects.sync`，不强制初始化才能发文。

1. 从当前聊天真实工作区确定项目名和绝对路径并说明目标；不能用插件 cwd、账号名或旧聊天猜测，无法确定才询问。先读适用 AGENTS/override 与用户指令；只处理本人选定项目。
2. 读取根 `AGENTS.md` 和 `.agents/skills/openahoy-production/SKILL.md` 实际字节及 SHA256；不存在传 `MISSING`。用 `own.projects.read {view:"catalog"}` 取得 revision，不让用户重复填配置或确认同一委托。
3. 调用 `own.projects.initialize {project_root,expected_agents_sha256,expected_skill_sha256,operation_id,expected_revision}`，沿页面给出的原 `project-<32hex>` operation_id。直接用户要求时生成一次并保存，不在未知后换键。工具仅追加自身 AGENTS 段、创建项目桥接 Skill、登记原位来源；不替换用户正文、个人账号配置或原规则，不修改模型、权限和调度，不自动生产发表。
4. 根 override、用户修改的维护段、同名 Skill、链接或指纹冲突时停止相关写入，说明具体对象。保留文件，不删除 override、不改名躲避冲突、不把维护段塞进其他用户规则。正常重复执行不重复追加或替换文件。
5. `INITIALIZED` 表示文件已实际读回并登记；`current_chat_consumed:false` 表示工具没有证明聊天已采用。`FILES_WRITTEN_REGISTRATION_PENDING` 表示文件存在但登记失败，保留文件，查询原 operation，再按当前 revision 用 `own.projects.sync` 登记实际来源，不重新生成。`PROJECT_INIT_RESULT_UNKNOWN` 或断线先读实际文件和原 `own.projects.read {view:"operation",operation_id}`；按已存在字节恢复，不盲重发。旧回执不能掩盖新用户修改。
6. 当前 Codex 显式完整读取生成的 AGENTS 段、桥接 Skill，以及其当前插件/目标平台引用；按 source/chunks/完整 SHA 核对，不只看名称或摘要。没有目标账号时不猜账号，只完成通用来源读取，明确本号规则待实际任务读取，不声称已经采用。
7. 回报实际项目路径、两个文件指纹、project_id、规范版本/指纹、当前聊天已读与未读来源。页面刷新会查询原登记回执并实际读取来源，显示“来源已登记且实际可读”；不声称聊天自动加载，不保存个人偏好。平台默认和本号关联选择仍按本人原设置。

公众号由当前 Codex 完成研究、文字、真实配图及排版，最终必须存在可读取且图片可解析的完整含图 HTML，再按有效委托走原上传、入草稿、普通发表和实际 URL 读回。不能以纯文字、占位图或完成声明代替文件；图片/HTML兼容细节引用当前随包同源标准，不另造配额、QA许可或版本批准。

X 按 X 的图文/线程与媒体格式交付，不要求先生成公众号 HTML。身份、署名、选题、受众、风格、图片内容/比例与排版来自用户及本号配置，通用桥接不包含维护者私人账号或风格。
