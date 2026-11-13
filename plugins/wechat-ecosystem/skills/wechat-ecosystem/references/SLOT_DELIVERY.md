# 全稿入箱后直接普通发表

原生产窗口完成本批全部文章并按每组最多8篇保存到本号草稿箱后，逐组调用 `own.publications.current.dispatch`，传本号 `connection_id` 及原保存回执的 `attempt_id`（`own-step-...`）。1篇和不足8篇的尾组照发，同一回合即可执行。

服务端直接取原保存记录中的真实草稿标识，调用微信官方 `freepublish.submit`。不需要额外prepare、内容精确比较、QA证明、聊天扫描、生产结束声明、协调登记或自建来源资格。

返回的 `current-pub-...` 用于 `own.publications.current.poll`，查询原任务终态和逐篇微信链接。`own.publications.current.status` 接受原保存句柄或发表句柄，零网络读取本机状态。已提交或结果未知的原请求保留，只查询原任务，避免重复发表。账号认证、参数编码和微信官方权限/错误仍实际处理。
