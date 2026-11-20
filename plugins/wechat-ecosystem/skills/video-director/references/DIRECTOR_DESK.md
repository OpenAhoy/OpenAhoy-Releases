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

- 有实际生成委托时先保存在正确项目的图像分镜。形象参考用已登记版本和原图摘要，生成前用 preflight 核对适配器实际读取的角色和顺序。用 video.director.generation.submit 传精确 project/work/scene/shot/revision 和稳定 generation_attempt_id。工具从已锁修订构建请求，将尝试绑定原画布后沿原供应商提交一次。提交结果未知时通过 video.ark.generation.status 查询原项目和尝试。仅有项目定位的新尝试在该项目的「待归位」显示。没有原镜头关系的历史视频可用「关联已有成片」明确选择。
- 已有项目本地剪辑 MP4 用 `video.director.edit action=register_work_video` 登记作品成片，提供准确 project/work 与同项目相对路径、原文件 SHA-256。用 `video.director.read action=deliveries` 读回作品节点。继续使用回执中的 `chat_path` 展示同一份本地成片。作品成片与镜头原片各自保留。
- `deliveries` 返回镜头的已关联候选和采用状态。同一镜头的候选可在画布节点播放、暂停和拖进度，切换预览仅改变当前观看内容。「采用此视频」保存该镜头的精确候选。Codex 代用户采用时，使用 `adopt_video`，提供同一 project/work/scene/shot、`candidate_id`、`sha256`，以及读到的 `expected_candidate_id`（已有采用时）。采用视频不修改剧本修订或历史。

### 形象资产库

在「形象资产库」按项目、系列和用途查找已登记的形象。分镜的「图片」中可选本项目的准确版本。选择其他已登记项目的版本时，点击「引入本项目」将原图按 SHA-256 复制到目标项目，再保存分镜。目标库保留来源项目、版本与摘要。Codex 在用户明确要引入该版本时，用 `video.director.edit action=character_import_version` 传目标 `project_id` 和来源 `origin`（`project_id`、`version_id`、`sha256`）。把回执中的 `version_id` 和 `file` 写入目标分镜。Codex 用 `video.director.read action=character_library` 读项目和资产版本。将返回的 `id` 作为修订图片条目的 `asset_version`，并保留同一行返回的 `file`。使用 `context` 读回。后续设为当前的版本供新选择使用，已有镜头沿用其原版。

用户提供项目索引时，先确认原文件和版本状态。将索引 JSON 放在已登记项目内，使用页面「导入索引 → 从项目目录选择」或 `character_import_preview`。在页面选中子目录的索引后，会自动保留项目相对路径并预览。索引中的图片路径仍相对于项目根。调用提供项目 ID 和 `source` 对象，含索引的项目相对路径 `path` 及 `sha256`。确认预览中的缺图、版本冲突和确认状态后，用同一 `source`、`project_id` 和预览的 `revision` 作为 `expected_revision` 调用 `character_import`。返回 `UNCHANGED` 表示相同版本已登记。设置当前参考用 `character_set_current`，传 `project_id`、`version_id` 和现有指针 `expected_current`，原用途未设当前时省略 `expected_current`。

索引示例。将示例文件名、角色 ID、用途、版本和摘要替换为原项目实际值。用途支持 `full_body`、`face`、`expression`、`pose`、`style`（风格／质感）。已明确采用的来源可标 `current`，待确认用 `candidate`，已有历史用 `historical`。每个角色的每种用途分别维护当前指针。

```json
{
  "schema": 1,
  "assets": [
    {
      "id": "aria-v1",
      "character": {"id": "aria", "name": "阿岚", "series": "港口篇", "aliases": ["Aria"]},
      "use": "full_body",
      "initial_status": "candidate",
      "label": "v01 三视图",
      "description": "",
      "source": "港口篇角色设定",
      "path": "references/aria-v1.png",
      "sha256": "<项目原图的 64 位小写 SHA-256>"
    }
  ]
}
```
