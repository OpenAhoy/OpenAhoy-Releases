# MiniMax H3 视频

在 OpenAhoy「媒体工坊 → 视频 → 模型设置」打开对应的 MiniMax 中国站或 MiniMax 国际站卡，使用该站的开放平台按量 API Key。Key 只填写在插件内。两站及方舟分别保存；任务回执保留原站点，查询沿原站点执行。

- 标准 MiniMax H3 生成 4–15 秒，支持 768P、2K。文本模式显式选画幅，首帧、尾帧和首尾帧按素材自适应。参考图支持自动或显式画幅。
- 文字生成无图片，单首帧和单尾帧用一张，严格首尾帧两张，多图参考用 1–9 张。参照实际剧情选图。视频可能包含模型生成的音频，使用提示词描述声音。当前工作区接受项目内 PNG/JPEG。
- 用户要锁定中间画面时拆段。需多图参考时，在提示词中按输入顺序说明各图提供的人物、场景、位置或道具。
- 生成得到本地 `generation_attempt_id` 和远端原任务号。授权范围内调用 `video.minimax.generation.submit`，传站点、项目 ID、模式、时长、清晰度、画幅和相对项目路径。用 `video.ark.generation.status` 回读相同尝试及项目 ID。提交未知时返回原记录。
- 页面用供应商回执显示用量。国际站的刊例估算使用实际输出秒数和输入图片数量，实际结算请查看本账号账单。模型设置状态只表示本机有凭据。

[MiniMax 创建任务](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) · [查询任务](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)

高速度、Lite、Max 分别按实际模型 ID 传 model。三档均使用 480P/768P，Max 从 5 秒开始，Lite 多图参考要显式给画幅。旧版 Hailuo 2.3、Hailuo-02、T2V-01 和 I2V-01 走 V1，使用对应型号支持的模式、6/10 秒配对分辨率和 adaptive 画幅。V1 随本机任务保存模型与站点，使用 V1 查询原 task 并按返回 file_id 取视频。

## S2V-01 单主体参考

沿同一个 `video.minimax.generation.submit` 传 `model: S2V-01`、`mode: subject`、`subject_image_url`、提示词（最多 2000 字符）、项目、尝试 ID 和 API Key 所属站点。使用本人已授权交给 MiniMax 的公开 HTTPS 图片地址。保持单一主体；服务端以 `subject_reference[0].type: character` 和 `image: [URL]` 接收。请求只有 S2V 文档定义的字段，无需传 `paths`、时长、画幅或分辨率。插件不自动把本地图上传到图床。任务继续按原尝试 ID 查询，成片按供应商返回的 file_id 检查并保存。

[中国站主体参考](https://platform.minimax.cn/docs/api-reference/video-generation-s2v) · [国际站主体参考](https://platform.minimax.io/docs/api-reference/video-generation-s2v)
