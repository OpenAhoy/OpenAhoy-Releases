# 生成、下载与分轨

从实际工具目录发现本会话授权的 Suno 官方工具。用户已有已归档音频时，优先用原存档。某个工具不可用时保留原任务，在有权限的正常入口继续。

## 生成和恢复

- 用冻结的 `title`、`style`、`singing_lyrics`（Suno 的 `lyrics`）、`negative_style` 与已保存的 `suno_settings`，以原操作的稳定幂等键调用 `audio_create` 一次。保留全部 `clip_ids` 和各自顺序，任何条件未变的恢复围绕原请求、同键、同账号。原请求未知时先查业务记录和原 clip，避免二次生成。
- 已有多个 ID 用 `audio_wait` 的 `ids` 整批查，完成文件用 `until: complete`；`audio_retrieve` 可逐项对账。streaming 可试听，`complete` 才进入最终文件取回阶段。把提供方真实错误及缺失 take 按项记录。
- 原卡写入关联生成时的歌词、出品设置、原 clip 和所选音频版本。外部回执本身不等于已写入歌卡。重复同 clip 或同 take 时回查已有版本。

## 归档与额度

- 读取原卡已有合法原件。没有则优先通过 `own.music.production` 的 `suno_download`，用官方 `audio_download` 检查实际归属并取回已完成 clip。插件首调省略 `confirm`，格式按用户实际所需。processing 沿同一 clip 和格式续查，尊重提示及至少一秒间隔。通过正常导入入口校验实际文件并归档。
- `requires_credit` 单独记在该 clip/格式上。只有用户知情同意这项支出时才传 `confirm: true`。额度不足、权限不足与暂未生成分别报告。付费结果未知先读回原下载或额度状态，暂不能核实则保留未知。
- 复用用户已经合法取得的官方导出文件。旧两份 M4A 无下载额变动仅为历史观测；新业务走经授权的官方下载、官方导出或已保存的原件。生成器、播放器和私有文件按来源识别。保留文件类型及摘要，后台临时链接、令牌和播放授权留在原授权工具，回执只存稳定标识与结果。

## 分轨

- 若已有分轨，按原 clip ID 与原 `group_id` 调 `audio_stems_retrieve`。新拆分用 `audio_stems_create` 对实际来源一次提交，精确记录模式、同一幂等键和返回分组。当前工具说明 `two` 与 `twelve` 有各自用量，提交前核真实账号/模式的当次费用授权。
- 按实际 `take`、轨名与音频 ID 关联，不把两次 take 混在一版。partial 保留已授权取得的轨、列明失败和未知；回查原分组，勿暗中再拆。普通生成、音频下载和新分轨是三个独立的计费动作。
- 逐个读回原歌卡及 Studio 版本。仅在分轨实存且正常编辑器读取后报告已导入 Studio。

[Suno MCP](https://help.suno.com/en/articles/14551361) · [下载额度](https://help.suno.com/en/articles/13876865) · [官方 Studio 导出](https://help.suno.com/en/articles/13925249)
