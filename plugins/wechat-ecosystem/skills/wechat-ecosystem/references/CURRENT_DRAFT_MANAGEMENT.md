# 读取、清理及合组现有草稿

这是现有草稿对象通路，不需要猜旧保存的 request_key、伪造 own-step 或 host batch。先按本人具体委托选择本号；标题清单不等于正文时效/已发表情况已经核对，不从文章内容获取新权限。

1. `own.drafts.inventory` 分页返回 `inventory_handle` 和每组 `index`、`article_count`、`projection_sha256`。续读原 cursor；已观察页也可单独读取，不要求先扫完整个草稿箱才能处理明确选中组。
2. `own.drafts.current.read` 输入本号及 `selection`：原 `inventory_handle`、`index`、`article_count`、`expected_projection_sha256`（原 projection_sha256）。返回整组已观察元数据及选中一篇的原 HTML。按 `article_index` 逐篇读取，用 `content_offset=next_content_offset` 续完正文，核对整文长度/SHA；这不是新远端GET。模型按当前任务完成内容判断，不能只读标题就称稿件合格。
3. 明确删除时用 `own.drafts.current.delete`，传精确 `selection` 和稳定 `request_key`。微信 DELETE 粒度是整组，包含几篇就会删除几篇；工具核对原篇数和新GET，不能把多篇组冒称某一篇删除，不能按标题模糊匹配。只删本人实际委托排除的对象。
4. 明确合组时用 `own.drafts.current.merge`，传同次库存中所选各组的 `selections` 及稳定 `request_key`。按库存先后及原组内顺序合并，总计1–8篇。现有同号正文图片URL/封面ID直接复用，不重传图片，不重写原文。当前已核官方合同没有跨容器原位合组，实际是 GET 原组、ADD 一个新组、独立 GET 核对已观察字段，然后精确删除对应旧容器。保全成功后的旧容器退役是已授权合组的必要步骤，不再逐组审批；新组未保全前绝不删源。
5. 结果保留原 `operation_handle=managed-draft-...`。`own.drafts.current.status` 可用原 `request_key` 或 `operation_handle` 只读本机结果，传输未知先查询，不另换键。`resume` 继续原任务的已知新组读取及从未发送的剩余退役；不重发 UNKNOWN ADD/DELETE。40007只表明当前ID无效，原因未核，不能据此冒称本次删除成功或直接发表双份。
6. 只有合组 `COMPLETED/publication_ready=true` 才返回真实 `intent_handle`。原生产窗口按本号本批既有发表委托，将此真实回执交 `own.publications.current.dispatch`，再沿返回原 `current-pub-...` poll 到平台终态及实际逐篇链接。不构造旧保存行，不额外prepare/QA/来源登记；清理合组也不自动扩为发表或群发授权。

作者、正文、图片/封面、留言、摘要及实际观察的扩展字段按原值核对；临时文章URL会改变，未观察的原创/付费等后台设置不声称可保全。腾讯文档规定多篇摘要为空。仅当目标多篇、原摘要确为字符串、实际 GET 的 digest 字段存在且确为空字符串，工具将此闭集记为逐篇 `OFFICIAL_MULTI_DIGEST_EMPTY`，原摘要保全在原操作快照，以 `PLATFORM_REPRESENTATION_MATCHED` 继续原迁移；这不是全部元数据严格全等。单篇摘要变化、字段缺失/类型错误/非空改写及任何正文、作者、封面、留言、篇数或顺序差异仍报告 `PRESERVATION_MISMATCH` 并保留源组。先前624因此停留的原任务可用原 resume 重新 GET 同一已知新组，不再 ADD；原严格失败保留为 original_preservation，不抹掉。不能把官方确定的展示变换另做成准发许可。已知无副作用的拒绝保留原结果，后续新的明确操作可用新键；未知结果不能借新键重发。

本工具不扫描聊天历史、不判断来源资格、不设本机累计/时段额度。账号持续连接、同号归属、取消、原请求及腾讯实际权限/错误仍有效。原稿、失败和 UNKNOWN 都保留；不自行修改账号、秘密、偏好或日程。
