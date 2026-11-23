# X 多账号官方接入

以当前原生工具实际暴露为准；未加载 x.* 不用SDK、cookie、浏览器脚本或私有请求代替业务调用。OAuth由本人在X官方页面完成；public Native App只需公开Client ID，不索取Client Secret、API Key、token、code或PKCE verifier。app-only x.ui.action仅供真实内嵌页面；模型不能代替本人配置或授权。

## 绑定与读取

内嵌管理页选择 X，点击「绑定 X 账号」，填写本人 X Developer Console 中启用读写的 Native App 的名称和公开 OAuth 2.0 Client ID，然后由本人在 X 官网页面授权。回调地址以页面显示为准。已有账号从对应卡片的「X Developer Console」进入本号开发者设置，可查看连接状态、进入官方控制台或展开账单与余额。连接或更换开发者应用时可展开「手动配置 Client ID 和回调」，再授权同一账号。授权后的凭据保存在本机钥匙串，按 Client ID 和 X 用户 ID 隔离。

需要新建或配置开发者应用时，点「让 Codex 协助创建 X 应用」，或在聊天使用 `$wechat-ecosystem:x-developer-app-setup`。Skill 随 Jiusera 安装和升级，使用 Codex 内置浏览器协助填写 X 官方控制台。

选择X即显示该平台已实现能力与实际条件，不依赖是否绑定。授权等待期间页面自动检查本地状态，返回页面时自动刷新；成功后更新账号与头像。切到其他平台或关闭页面停止界面检查，不取消已发官方授权。手动“检查授权结果”保留作恢复入口；失败/取消/过期不自动重发授权或业务。

“项目与 Skills”可关联既有项目、查看 AGENTS/Skill 原文、选择方法和保存主题/筛选/写作/回复风格偏好。选定真实 X connection_id 后，按 [项目规则与 Skills](PROJECT_CONTEXT.md) 读取 `own.projects.read` 的 effective 及全部来源分块后用于创作；未关联沿原流程。配置不自动开启回复/选贴或创建任务，不改变模型或原公众号偏好，实际互动能力仍按当前工具及官方条件。

「账单与余额」按需使用所选账号自带应用的授权查询 X 的开发者账户余额，同一开发者账户下的应用可能共用额度。金额为 USD，预付余额可为负。没有官方到期日时显示缺失。旧共享应用不展示余额。充值、账单明细、项目用量和消费上限在 X Developer Console 处理。发帖遇到 `X_HTTP_402` 先核对所用应用的开发者账户，不自行重试或换用共享额度。

完整回调为 `http://127.0.0.1:62197/x/callback`。只请求 tweet.read、users.read、tweet.write、media.write、offline.access。OAuth 成功、平台读写和账单查询分别核验。

`x.connections.list {}` 只读本机连接，不启动OAuth或API；使用真实 `x-<user_id>`，不要猜X身份。`x.profile.read`读取该绑定账号实际资料，`x.posts.list`读取本人一页帖子，返回next_token时才按需要续读。`x.posts.read`独立读取post_id。资料来自X API，名称与头像不是手工标签或其他平台身份。

只读帖子返回 `PARTIAL` 时可引用已核对的帖子，并说明媒体或上下文缺口。列表的 `FAILED`、局部错误页或重复游标不能用来认定零条或统计完成。仅用未见过的 `next_token` 续读。发表结果仍沿原 `x.posts.readback`、`x.replies.readback` 或文章状态独立验收。

## 多账号与会话隔离

同一电脑可绑定多个不同 X 账号，平台页顶部全部显示为可点击卡片，窄屏换行。选择只属于当前面板，不设后台全局当前账号；每次业务、媒体、规则和定时操作必须显式使用本次选定的 connection_id。不同项目/聊天可同时使用不同账号；不得从显示名称、第一条连接或上轮选择猜目标。

绑定完成按本次官方返回身份刷新全部账号。若等待授权期间本人已经切换账号/平台，刷新账号列表但保留本人后选目标。授权会话句柄只保留在发起面板；另一面板不能接管或取消原授权。添加账号不会替换已绑定不同号，同号重新授权保留原身份与历史；指定账号重授权返回另一身份时停止且不改原号。

旧 schema 1 和 2 只读时原样保留。首次切换自带应用后，同一 connection_id、创作配置和定时键继续使用，旧授权留作原媒体处理状态和帖子读回。新发帖仅使用当前应用上传的附件。回退软件前先保存新增应用元数据和原配置。

## 纯文字与图文发表

### 当前 Codex 自动生产与发布

在 X 平台页选定真实账号后，“编辑内容配置”打开本号运营表单，按[X运营配置](X_CONFIGURATION.md)加载/填写/保存并生成完整Skill。原项目与 Skills 的继承和五项补充偏好继续保留，不另建数据库。生产读取effective.x_configuration的完整配置与skill.text；继承、未保存编辑和有效内容分开。回复风格仍是其他互动任务的旧偏好，不是本发文流程的回复指令。

本人点击“立即生产并发布”即委托当前聊天完成本轮一条新帖，不再逐项询问选题、图片和发帖许可。使用消息中的 connection_id 和启动请求ID，先原生核身份、读取 own.projects.read effective 及完整适用来源；按已保存的主题/选题/文案配图/其他偏好创作。未关联项目或可选字段为空时，Codex自主选择合适内容与表现，不强制关联开发AGENTS、不擅自改配置，不编造用户经历。需要公开事实时在制作中核官方依据；本轮需要配图时，用已具备的图像生成能力实际制作并查看新 PNG/JPEG，不能用占位图、旧成功稿或图片生成指令文本冒成品。

沿消息指定的原 media/post attempt 依次调用 x.media.upload、x.posts.create、x.posts.readback；同一启动请求已经执行或未知时，只查 x.attempt.status/原readback，不换key重发。一次只发本轮一条，返回实际新post_id及独立MATCHED链接后停止。工具/宿主确实缺能力则报告具体阶段，不改用浏览器或SDK绕过，不以消息已发送、生成成功或创建ACK代替独立读回。

“已交给当前Codex”是消息接收状态；“查看原任务结果”只读原post attempt，不重发模型消息或平台写入，只有已持久保存的MATCHED才显示完成。当前页面内禁止重复点击；页面重开后不承诺全局去重，先查看当前聊天及原任务，不因按钮重新可用就认定前次未执行。完成后开始下一条是新的明确点击委托，不静默连续发文。

“配置定时生产发布”打开本号时段表单，可设置每日/指定星期/多个启动时刻/IANA时区及单次，保存不启用。启用/更新/暂停/恢复经具体原请求交当前Codex使用正式原生heartbeat，真实任务ID及核对日期、最近实际运行分开显示；完整契约见[X 定时生产发布](X_SCHEDULE.md)。各轮按最新本号内容配置的栏目形式创作，使用各轮稳定原attempt，未知先查原任务；不另建调度器、模型服务或互动。

### 其他互动任务（仅另有明确委托）

按本人明确范围主动搜帖、读取上下文与拟回复，使用 [X 主动发现与回复](X_DISCOVERY.md) 的四类规则、官方搜索及单次回复工具。定时能力使用宿主任务，保存偏好不启动任务，未定频率或无实际自动回复资格不启用无人值守操作。

### 原生发帖执行顺序

纯文字帖只调用 `x.posts.create`，传同号 `connection_id`、稳定 `attempt_id` 和非空 `text`，省略两个上传参数和 `made_with_ai`。随后沿原 attempt 调用 `x.posts.readback` 核作者、正文及无媒体。图文沿以下步骤。

用户已明确授权的真实内容由Codex创作；插件只负责官方执行。使用本次独立 PNG/JPEG/WebP 原件或本人已授权的 GIF/视频素材，不跨用微信media_id。只做当前请求，不自行启动回复、私信、增长、定时任务、转帖或擅自切换本次未指定的账号。

1. `x.media.upload`传入connection_id、原attempt_id和明确的本机媒体绝对路径；兼容参数名仍为 `image_path`。支持 PNG/JPEG/WebP、GIF 及可识别的MP4/WebM/MPEG-TS/QuickTime，编码/格式/时长/尺寸/大小和账号权益由 X 实际接口判断，不把 API 套餐等同于 Premium，不自动转码、压缩、降质或截时长，也不新增业务额度。常规照片走原上传接口；GIF/视频沿官方 v2 initialize→append→finalize，单帧 GIF 使用 tweet_image，动画 GIF 使用 tweet_gif，视频使用 tweet_video。传输分块不是总文件额度。
   `UPLOADING` 是已确认进度后的可续传状态：相同账号、attempt及原路径再次调用 upload 继续原 session；不会重新 INIT。`PROCESSING` 或 `phase=FINALIZE_UNKNOWN` 时用原 `x.attempt.status` 加 `poll_media=true`，按 next_check_at/check_after_secs 继续官方 GET，直到 SUCCEEDED/明确失败；默认 status 仍只读本地。不要把待处理标成失败或重新上传。INIT/APPEND 结果 UNKNOWN 不盲重放，FINALIZE UNKNOWN 只查询原 media_id，过期不替换媒体或换 key。原媒体字节及进度保存在该账号既有私有任务目录，不修改原件、不另启后台。
   仅 SUCCEEDED 且未过期的本账号媒体可用于新发帖；每帖最多四张照片，或单个动画 GIF 或视频，不混用其他账号/公众号素材。处理失败、平台拒绝和未知阶段如实报告，未知原发帖只沿原 readback，不重复 POST。
2. 成功后 `x.posts.create` 使用同号、原创建attempt_id、实际 text 和按展示顺序填写的 `upload_attempt_ids`（一到四项）。每个附件各用原上传回执，全部就绪后一次提交。单附件也可沿用 `upload_attempt_id`，两参数二选一。不加审稿/QA许可。公开发表属于真实写入，须已有用户委托。
3. `x.posts.readback` 用原创建 attempt_id 独立 GET 核对真实账号、原帖子 ID、正文、媒体顺序和扩展附件。已有成功回执时一并请求 `note_post`。有全文时按 `note_post.text` 和全文自己的 URL 实证比较，预览不能覆盖全文的差异。字段缺失时仍须用返回文本证明原始完整正文。只有 MATCHED 才能报告实际链接。SUCCEEDED 创建 ACK 与独立读回 MATCHED 分别表述。

上传或创建RESULT_UNKNOWN时，先 `x.attempt.status` 查询原请求；带媒体帖还可用 `x.posts.readback` 通过原账号时间线核对原媒体。纯文字帖缺少原响应的帖子 ID 时保持 UNKNOWN，时间线里的同文不能证明归属。无唯一匹配保持UNKNOWN，不换key重发，不以“没看到”推定失败。已有成功在重启后沿原attempt续接。读回MISMATCH保留原发布，报告实际差异，不重复发帖或删帖。

X可能对读写收取官方费用，实际应用资格、权限、余额和平台错误分别核对；未经本人授权不充值、开自动充值或购买新资源。刷新未知须重新走官方授权，不盲重放旧refresh token。密钥只在X专用系统钥匙串；微信两号的绑定、秘密、规则和历史不改。

## 当前聊天缺少 X 工具时

先用宿主当前实际提供的按需工具发现，按 Jiusera 和所需工具的名称查找。最初没看到的工具可能按需出现。预检的 `SERVER_CATALOG` 表示插件声明了工具，最终以本聊天可调用的入口为准。若发现功能缺失、搜索后仍缺或宿主明确拒绝，报告当前阶段及确实缺少的具体工具名。文字发帖需 `x.posts.create`，带媒体还需 `x.media.upload`；按原任务查询并核对读回分别使用 `x.attempt.status` 和 `x.posts.readback`。宿主拒绝后沿原回执报告，不换接口执行写入。

只看到 `x.connections.list` 时，已开放恢复参数的会话可通过它查询，例如 `{"recovery":{"tool":"x.attempt.status","arguments":{"connection_id":"x-123","kind":"post","attempt_id":"原任务ID"}}}`，也可通过同一入口独立读回已知帖子。X 面板的「查询原 X 任务」也只做查询。

由面板发起的未完成请求，在对应账号的「发布、定时与账号 → 接续原 X 请求」可查看账号和原上传、发帖 ID，复制指令到正常具备 X 工具的聊天。先查两个原回执，保留原账号、内容和 ID。未知或原聊天可能仍在执行时只查询；查无本地回执不能证明原请求已停止。确认原执行已结束且未提交后，按原有委托与已核对的源素材继续尚未执行的步骤。已成功上传的媒体沿用原回执。

## 原生长文（X Articles）

需要保留封面、正文图和段落结构时，按用户本轮指定的 X 账号制作原生 Articles。使用 `x.media.upload` 分别上传封面与每张正文图，保留同号的成功上传回执。依正文顺序调用 `x.articles.draft.create`，用 `blocks` 描述段落、标题、列表、引用及图片位置。图块填 `upload_attempt_id`，可选 `caption`。封面单独填 `cover_upload_attempt_id`。平台决定可用媒体和文章限制。

有明确发表委托时用 `x.articles.publish` 传原 `draft_attempt_id`。工具从原回执取得真实 Article ID，发表回包中的 Post ID 另存。用 `x.articles.status` 和原 `draft_attempt_id` 回查，打开 `readback` 时独立读取该 Post ID。账号、标题、封面及正文图的可见字段按真实回包核对。文章专属链接仅在回包给出时报告，帖子链接单独标明。出现 `INCOMPLETE` 或 `MISMATCH`，保留原结果并说明差项。

缺少草稿 ID 或发表 Post ID 时查看同一原回执，保持结果未知。X 当前公开 Articles API 提供建草稿和发表。回包丢失时，已有本地内容、相同标题或搜索结果不足以确认原请求，继续使用原尝试编号查询，不换号或换编号重发。[X Articles 官方文档](https://docs.x.com/x-api/articles/introduction)
