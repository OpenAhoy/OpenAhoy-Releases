# MiniMax H3 视频

在 OpenAhoy「视频生成 → 模型设置」选择 MiniMax 中国站或国际站，使用该站的开放平台按量 API Key。Key 只填写在插件内。两站及方舟分别保存；任务回执保留原站点，查询沿原站点执行。

- 标准 MiniMax H3 生成 4–15 秒，支持 768P、2K。文本模式显式选画幅，首帧、尾帧和首尾帧按素材自适应。参考图支持自动或显式画幅。
- 文字生成无图片，单首帧和单尾帧用一张，严格首尾帧两张，多图参考用 1–9 张。参照实际剧情选图。视频可能包含模型生成的音频，使用提示词描述声音。当前工作区接受项目内 PNG/JPEG。
- 用户要锁定中间画面时拆段。需多图参考时，在提示词中按输入顺序说明各图提供的人物、场景、位置或道具。
- 生成得到本地 `generation_attempt_id` 和远端原任务号。授权范围内调用 `video.minimax.generation.submit`，传站点、项目 ID、模式、时长、清晰度、画幅和相对项目路径。用 `video.ark.generation.status` 回读相同尝试及项目 ID。提交未知时返回原记录。
- 页面用供应商回执显示用量。国际站的刊例估算使用实际输出秒数和输入图片数量，实际结算请查看本账号账单。模型设置状态只表示本机有凭据。

[MiniMax 创建任务](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) · [查询任务](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)
