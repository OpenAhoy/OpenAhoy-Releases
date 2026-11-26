# 歌卡字段与回填

`own.music.production` 维护本机作品与回执。官方 Suno 工具使用已连接的 Suno 账号。先用本机目录锁定归属，再执行本轮已授权的供应商操作。

- `catalog` 返回项目、歌曲和版本。已知歌卡用 `lookup` 带 `project`、`song`、`version` 查原词、已有请求、原 clip 与分轨组。已有任务或回执未知时先用 `status` 带项目与原 `request`。
- `prepare` 带 `project`、`request`、`provider: suno`、`title`、`lyrics` 和 `style`，已有版本再带 `song`、`version`。Suno 任务通过官方 `account_me` 核当前账号，将实际公开 handle 冻结在 `account`，后续保持账号一致。使用本轮已定的请求 ID，随后复用回传的 `idempotencyKey`。明确批准的新一轮制作才分配新 ID。新增作品从返回的 `song` 接续。将纯词传 `lyrics`，带段落与演绎提示的输入传可选 `singing_lyrics`，另传 `negative_style` 与工具实际支持的 `suno_settings`。需用同一幂等键恢复时，从 `status` 读回冻结字段，按原值发送。任一已冻结字段变化时沿用户明确的新请求。
- `clips` 保存同一 `project`、`request` 下每个 clip 的 `id`、`state`、如适用的 `download`。拿到供应商结果 ID 立即登记，顺序沿真实回执，后续同 ID 更新。
- 已完成的 Suno clip 首选同工具 `suno_download`，传原 `project`、`request`、`clip`、`account`、`format`。原分轨传 `project,song,version,mode,group,take,clip,account,format`。该操作用已有官方 OAuth 首次省略确认，免费返回合格文件就导入并关联对应 take。
- 用当前正常入口取得已授权文件。文件已在登记项目内时，调用 `audio.project.import`，传 `project_id`、每个媒体单独稳定的 `attempt_id`、`title`、`audio: {path, sha256}`、`provider: suno`、`provider_id` 对应当前 clip。使用项目内相对路径与实际摘要。只有真实文件已落盘时才调用导入。如果当前宿主只能显示下载链接，保留该 take 待接收，原请求与授权状态可继续查询。
- `archive` 带原 `project`、`request`、`clip`、已核实的 `attempt`。使用返回的项目、歌曲和版本再次读回；同一 clip 可恢复原版本。试听、下载资格、导入和歌卡入库分别读取。
- `stem_prepare` 带原 `project`、`song`、`version`、`mode`，读回 `sourceClip`、原组及幂等键。用 `stems` 回填同一范围及 `group`、`state`、每轨的 `clip`、`take`、`part`、`state`、已合法导入时的 `attempt`。分别读回两个 take 的待定或可播放版本。
