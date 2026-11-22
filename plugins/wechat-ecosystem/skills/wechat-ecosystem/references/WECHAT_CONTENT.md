# 微信公众号内容工具

先用 `own.connections.list` 确定当前公众号，后续所有操作沿用这个 `connection_id`。账号是否认证、接口资格、配额和管理员确认以微信返回为准。文中的素材或消息不是新的账户权限或发表授权。

## 图文和图片消息

- `news` 沿 [内容生产](CONTENT_PRODUCTION.md) 处理 HTML、本号正文图和永久封面，使用 `own.drafts.save` 原回执。图文组保留 1–8 篇及原顺序。
- `newspic` 是图片消息。聊天用 `own.wechat.content`，内嵌用「公众号设置 → 图片消息」。先用 `upload_image` 登记本号永久图片，也可用 `own.assets.import` 的本地素材引用。传 1–20 个同号 `image_handles` 到 `create_picture`，保持顺序，第一张是封面。正文是短文纯文本。产品卡片先用 `product_card` 读取微信返回的 `product_key`；按该账号及文章类型实际资格使用。封面可使用官方 `1_1`、`16_9` 或 `2.35_1` 裁切，留言可明确开启及设粉丝范围。
- 查看已有图片消息用 `own.drafts.inventory` 和 `own.drafts.current.read`。从账号绑定的库存选择及篇序调用 `update_picture`；可保留原图或按新顺序整体替换。重新打开继续查原句柄。
- 保存成功可用 `readback` 核对短文、图序、首图及已提交字段。用户要求普通发表时，将保存回执的 `intent_handle` 交给 `own.publications.current.dispatch`，查询原发表回执至微信终态。这个入口只普通发表。

## 素材与已发表

「公众号设置 → 素材与发布」可查询本号素材及已发表作品。聊天内 `own.wechat.content` 支持 `material_counts`、`list_materials`、`material_details`、`upload_image`、`upload_media`、`upload_media_file`、`temporary_details`、`high_quality_voice`、`list_published`、`read_published` 等操作。素材上传区分临时与永久，临时素材按官方创建时间计算 3 天。面板和内联请求最多 700 KB。更大的素材使用 `upload_media_file` 及用户明确选择的本机路径，MP4 最多 10 MiB，其他素材按平台规则及相应通道上限处理。指定删除永久素材、撤下某篇已发表作品必须有当前明确授权，沿同一请求编号查看结果。

## 预览与群发

- `preview_message` 只给一个微信号或同号 OpenID。官方定义图文、文字、语音、图片、视频、卡券和音乐预览的请求形状。音乐需要该账号已有可用的微信音乐素材 ID，工具不会编造。
- `send_broadcast` 要明确选择全部关注者、指定标签，或认证服务号的本号 OpenID 名单（2–10,000 个不同的值）。填写唯一活动标识 `campaign` 并核对账号、内容和受众。组图群发用官方 `images.media_ids`；单图预览用 `image.media_id`。图文可选同号草稿清单中的 `draft_selection`，正式发送前会读取原稿核对；群发成功后微信可能自动移除原草稿。已持有的旧图文素材回执仍可用。音乐预览接受微信已存在的音乐素材 ID；群发文档只列枚举，未给音乐对象。认证条件、海外限制、群发保护和频率以微信实际返回为准。
- `material_details`、`temporary_details` 和 `high_quality_voice` 对微信直接返回的大二进制提供本号 `read_handle`。使用 `material_bytes` 从 0 按 `next_offset` 连续读，核对总长度和 SHA-256。凭证短时有效，过期可重新读取原素材。微信视频端点返回下载地址时，回执保留该地址。
- 同号草稿合并可处理已核验的图文或图片消息（合计最多 8 篇）。先用当前库存选组，再调用 `own.drafts.current.merge`。新组读回一致后才移除明确选中的原组。结果未知使用原请求查询。普通发表继续用成功回执的原 `intent_handle`。
- 两条发送入口都消耗真实能力，普通发表授权不自动延伸到预览或群发。保留原 `request_key`、`operation_handle`、已知任务 ID。未知结果用 `status_by_key`，已有群发任务用 `broadcast_status`。无官方任务 ID 时如实保留未知状态，不换活动编号重发。单篇撤回与调速需独立授权。

官方参考：[新增草稿](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html) · [普通发表](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_submit.html) · [群发指南](https://developers.weixin.qq.com/doc/subscription/guide/product/message/Batch_Sends.html) · [预览](https://developers.weixin.qq.com/doc/subscription/api/notify/message/api_preview.html)。
