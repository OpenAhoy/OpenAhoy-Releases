# Seedance 首尾帧视频

在 Jiusera「设置 → 模型管理 → 画布 · 视频」打开火山方舟卡，由本人填写并保存中国站 API Key。钥匙串已保存和模型开通是两个状态。聊天、项目文件、MCP 工具和反馈都不接收 API Key。

实际出片需要本次明确的计费授权。首尾帧使用同一已登记项目内的两张原始 PNG/JPEG，保留生成工具提供的源文件和顺序。若源文件在该项目之外，通过 Codex 可用的真实文件交接复制原始字节到本项目并核对 SHA-256。使用本聊天实际项目的 `project_id`，不从插件目录猜测。聊天工具默认生成 5 秒、720p、自适应画幅、无声 MP4。Seedance 2.5 可传 `duration: 4` 到 `duration: 30` 的整数，或传 `-1` 由模型决定时长。其余已接入模型沿用插件的 5 秒设置。方舟要求单张图片小于 30 MB、请求体最多 64 MB；使用本地图片时，Base64 编码也计入请求体。

## 为分镜准备画面

- 严格锚定首尾时，即使是 30 秒也只准备两张同画幅图，按 `first_frame`、`last_frame` 提交。先确认首尾姿态、镜头方向和景物变化，再在提示词里描述段落动作。
- Jiusera 的 Seedance 2.5 工具支持双图首尾帧、文生视频和 1–30 张多图参考。文生视频传空的 `paths`。多图参考采用输入顺序，沿用顶层 `reference_images` 时每张传绝对路径和 SHA-256。
- 复杂镜头可先准备分镜，再选少量素材作全模态参考。方舟最多接受 30 张参考图，参考图和严格首尾帧属于互斥模式。提示词可以分时段引导，接口没有给每张参考图指定秒数的参数。
- 中间画面需要严格对齐时，在转场处分段，相邻段共用衔接帧。核对主体、服装、道具、光线、画幅和运动方向，生成后检查衔接与成片。
- Seedance 2.5 的首尾帧、文字、参考图和延长镜头可选 4–30 秒或自动。修改画面用自动时长跟随源片。以实际 MP4 的可播放性与时长核对结果，方舟回执的整数时长可能省略小数。

- 省略 `model` 时沿用 `doubao-seedance-2-5-260628`。
- 使用 Seedance 2.0 标准版时显式传 `doubao-seedance-2-0-260128`。
- 使用 Seedance 2.0 Mini 时显式传 `doubao-seedance-2-0-mini-260615`。
- 已在方舟开通 Seedance 1.0 Pro 且仍可使用时，可显式传 `doubao-seedance-1-0-pro-250528`。
- Key 保存成功或模型出现在列表中，都不能证明本账号已开通可计费生成。按本次授权选定模型，无自动降级或重试。

1. `video.ark.connection.status` 检查 Key 配置。保存状态不代表付费生成已验证。
2. `video.ark.generation.submit` 传 `generation_attempt_id`、`project_id`、提示词和本模式的原图。首尾帧传 `first_frame` 与 `last_frame`，多图参考传 `reference_images`。要设置生成模式、分辨率和音频，按下节使用 `configuration`。已经返回 `SUBMIT_UNKNOWN` 且无远端 ID 时保留原尝试，不自动换键提交。
3. `video.ark.generation.status` 用原 ID 和项目 ID。默认读本机回执，`poll: true` 查询原任务并核对回执中的模型，完成后收取文件。临时下载失效或失败时继续查同一任务。只有 `ASSET_READY` 和可读的本机 MP4 才能交付。用实际视频确认首尾内容。
4. 在明确授权的目标 X 账号复用 `x.media.upload`，以 MP4 资产路径作为历史字段 `image_path`，等待原上传就绪。用同账号 `x.posts.create` 的原上传 ID 发布一次。用户要标记 AI 媒体时显式传 `made_with_ai: true`。最后用 `x.posts.readback` 核原帖，打开真实链接确认可以播放。失败或未知时查原任务，复用本机视频。

## Codex 显式生成参数

在 `video.ark.generation.submit` 传入 `configuration` 时，将模式、时长、分辨率、音频和素材集中在这个对象内。保留外层的尝试 ID、项目 ID、提示词和可选模型。素材用同项目内的相对 PNG/JPEG 路径，插件验证文件及内容散列。

- `mode: frames` 传先首、后尾两条 `paths`，`reference` 传 1–30 条，`text` 传空列表。设置 `duration`、`resolution`（480p、720p 或 1080p）和 `audio`（布尔值）。
- 修改画面用 `mode: edit`、`duration: -1`。续写用 `mode: extend` 和 `direction: before` 或 `after`。两者都传空的 `paths`，以及同项目已完成方舟源片的 `source_attempt_id`、`source_sha256`。先用原任务状态取得资产散列；原素材不可用时可提供已有的 `reference_asset`。
- 已完成的 Codex 视频可在「视频生成」中点击「刷新成片」读取。连接配置从「设置 → 模型管理 → 画布 · 视频」进入。

收到 `SUBMIT_REJECTED` 时，按原尝试和项目 ID 读取回执。新版回执的 `rejection` 可能包含 HTTP 状态、已知方舟错误码和方舟请求 ID，可用于排查或联系方舟。旧回执若无诊断，无法从本机回填。按证据处理原因，读取回执不会重新提交。

收到 `FAILED` 时查看 `failure.ark_error_code`。旧失败回执无此字段时，可以用原 ID 及项目 ID 传 `poll: true`，查询同一方舟任务的错误码。若方舟返回版权限制，请改用原创或明确授权的素材，避免原样重试。

「视频生成」按已登记项目显示原片和派生版本。修改及续写使用 Seedance 2.5 和原任务的方舟素材。若源片已不可用，可使用已有的方舟视频素材 ID。向后续写实测返回独立片段，页面可按方向连播源片与片段。下载对应当前选中版本。
