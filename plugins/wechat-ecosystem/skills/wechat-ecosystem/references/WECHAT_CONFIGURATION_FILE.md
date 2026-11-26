# 公众号配置文件

在所选公众号的「配置文件」下载 v2，或选择本机文件查看差异，再保存到同一公众号。按 `account_ref` 匹配当前连接。显示名用于阅读，可随公众号更名。未保存预览和本号已生效配置分别显示。

格式为 `openahoy.production-preferences`，`schema_version: 2`，`platform: wechat_official_account`。每个字段是 `{mode,text}`。

| 字段 | 含义 |
| --- | --- |
| `audience_topics` | 主题、读者、内容形式和目标。多项可逐行。 |
| `author`, `voice` | 作者署名、文风与组织方式。 |
| `image_preferences`, `visual_layout` | 配图与手机图文排版，包括可预览的正文字号。 |
| `content_qa`, `delivery_publication` | 创作复查和交付偏好。 |
| `additional_notes` | 其他创作偏好及已有模板标识。 |

`override` 使用本号的字符串。空字符串是本号显式置空。`inherit` 使用保存当时本号的上游有效内容，文件中的 `text` 记录导出时所见，供查看与版本对照。重新导入用当前有效默认值，默认版本变化在预览提示。导出版本用于溯源，保存必须比较当前 store 与 scope 版本。两个版本或所选连接发生变化时保留草稿并重新读取。

`templates` 与包内模板标识一一对应，用 id、version 和 manifest SHA-256。项目引用包含 project id、source digest、以及已选 Skill 的 id 和文件 SHA-256。真正使用时用 `own.projects.read` 查当前工作区的登记并逐块取源。配置文件不复制项目源文件、技能正文或机器路径；来源变动在导入预览提示，项目重关联走现有项目界面。配置文件不会触发生成、上传、发表、群发、账号绑定或自动任务。

旧 v1 完整八项字符串文件可通过同名唯一账号在预览后载入，所有值按 `override` 恢复。它没有继承、版本和稳定连接信息；保存后可重新下载 v2。
