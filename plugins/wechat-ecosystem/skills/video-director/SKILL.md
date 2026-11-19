---
name: video-director
description: Plan and produce social videos in OpenAhoy. Use when Codex should turn a brief into a shot list, generate or select image assets, write Seedance or MiniMax H3 prompts, or render and review clips.
---

# OpenAhoy 视频导演

1. 从委托和项目规则确定发布平台、画幅、时长、受众、已有资产和最终交付。先说清观众第一眼看到什么、最后记住什么。按关键动作切分镜头，每个镜头承担一个主要变化。
2. 读 [分镜、镜头与提示词](references/DIRECTION.md)，根据控制要求选模式。开头和结尾必须对齐图片时用两张严格首尾帧。中间也必须对齐时拆段并共用边界帧。用多图参考复用人物、场景、道具或风格，每张图绑定一个可解释的用途，按上传顺序引用。时间码指导节奏。
3. Codex 先用当前可用的图像生成工具制作缺失资产。已确认的角色或产品以原参考图为准。按目标画幅生成，核对人物身份、服装、道具、运动方向、光线及相邻镜头衔接，再用所在项目的实际路径和 SHA-256 交给插件。
4. 为每段给出时长、模式、按顺序的素材、可直接提交的提示词和预期终点。使用 MiniMax 时读 [MiniMax H3 操作规则](references/MINIMAX_H3.md)。使用方舟时按 [Seedance 操作规则](../wechat-ecosystem/references/SEEDANCE.md) 调用插件。方舟可继续用 `first_frame`、`last_frame` 或 `reference_images`。需要指定分辨率、音频，或使用文生视频、修改画面、续写时，按方舟规则传 `configuration`。生成、选帧和提示词由 Codex 完成。内嵌页用于模型 API Key、项目成片和资产。仅在本次生成已获授权时提交；结果未知时查原任务。
- AutoDL · MiniMax H3 的账号设置、显式工作流字段及原任务查询见 [MINIMAX_H3_RELAY.md](references/MINIMAX_H3_RELAY.md)。
- 用户明确要求制作动图时，已配置 OpenAI 动图 Key 就默认使用 GPT‑Image‑2.6 Flare，按[OpenAI 动图](references/OPENAI_GIF.md)选择项目静态参图、提交一次、读回原 GIF。
- 创作新歌曲或新视频配乐时，先按 [歌曲与视频配乐](references/MUSIC_WORKFLOW.md) 读取本机默认音乐供应商。用户本次明确点名时使用该选择。现有歌曲按原资产混音，既有任务按原供应商查询。
- Token Hex 通过[独立方舟视频中转](references/TOKENHEX_ARK.md)调用。
5. 读回原片并看实际视频，检查开头、动作变化、片尾、字幕安全区、声画以及拼接点。从可见缺陷回修具体资产或提示词。仅按本次委托交付或发布。

## 导演画布

在媒体工坊打开已登记的项目与作品。使用 [导演台说明](references/DIRECTOR_DESK.md) 读回准确的镜头和修订。独立文字卡、原图和既有音视频资产可以关联同一镜头。生成或修改图片时，用原镜头的 `project_id`、`scene_id`、`shot_id` 和当前修订作为基底，保存新修订后按原回执读回。
