# 项目导演台与 Codex 往返

- 通过 `video.director.read` 的 `projects` 找到已登记的真实项目，`overview` 查询作品、场与镜头，`context` 使用页面传来的 project_id、work_id、scene_id、shot_id、revision_id 读取原修订。项目未登记先按插件的项目上下文流程关联当前实际项目。实体名称不是唯一 ID。
- 构思作品后，用 `video.director.edit` 依次创建作品、场和镜。文字修订可只提交本次改动的字段，使用当前镜头的 `head_revision` 作为 `base_revision`，并指定 `origin: "codex"`。每次新动作使用新的 32 位小写十六进制 operation_id，同一动作回查沿原 ID。若原明确要求基于某修订，而它已经过时，读回差异后再处理，不自动覆盖。
- 图片先由 Codex 现有图像工具生成，或按用户要求使用已取得的项目图片。保存到登记根内，核对实际 PNG/JPEG 和 SHA-256。修订的 `images` 是有序数组，每项为 `{"role":"composition","file":{"project_id":"…","path":"相对路径","sha256":"…"}}`。修改该数组时保留本次仍采用的其他图片与角色。纯构图使用 composition，生成输入才用 first、last、subject、environment 或 reference。
- 保存后用同一 project_id、work_id、scene_id、shot_id 和返回的 revision_id 调用 `context`，确认实际回读的内容和素材。旧版继续存在，只有用户要求采用时才切换采用指针。
- 按需使用 [同源提示词卡](SHOT_CARDS.json)，或经 `video.director.read` 的 `cards` 查询目录与具体卡。卡片 ID 与 version 可直接附到修订。目录的原创示例属于写作参照；供应商实测须有独立证据。
- 完整提示词、供应商模型、模式和输入角色保存到镜头修订。使用 `preflight` 按现有适配器验证参数与本机输入。白模计划使用相机路径、主体动线和关键点；已确认的短 MP4 可导入当前项目用于预演。准备或预检不创建生成尝试。只有本次实际生成另获授权，才调用原供应商工具并沿原回执查成片。

作品画布可放入文字卡、独立图片和关联到原媒体回执的资产。原项目、媒体类型、attempt 和 SHA-256 一起标识素材。配乐合成品可能保存在音频工具回执中，却以视频播放。配乐和成片跨项目时，沿原回执里的关系双向查看。移动和移出画布卡片只修改作品布局。

### Jiusera 视频引擎与交付

在画布选择精确型号和渠道，保存镜头配置。使用 `video.director.read` 的 `models` 查看同一目录，并以镜头 `context` 核对实际修订。Token Hex 的账号可见目录通过 `refresh_tokenhex: true` 明确读取，镜头配置和已有连接选择各自保存。AutoDL 使用工作流的有序公开图片、音频链接，MiniMax S2V-01 使用一个公开主体图链接。

- 有实际生成委托时先对准确镜头修订执行 `preflight`，为这个已授权任务确定原 attempt。用 `video.director.edit action=track_generation` 绑定该 attempt 和同一 project/work/scene/shot/revision 后，沿原渠道提交并查询原单。画布根据原回执显示可取得的阶段，保留聊天里的原播放交付。没有既有镜头关系的历史视频，可在镜头版本中用「关联已有成片」明确选定原视频。
- 已有项目本地剪辑 MP4 用 `video.director.edit action=register_work_video` 登记作品成片，提供准确 project/work 与同项目相对路径、原文件 SHA-256。用 `video.director.read action=deliveries` 读回作品节点。继续使用回执中的 `chat_path` 展示同一份本地成片。作品成片与镜头原片各自保留。
