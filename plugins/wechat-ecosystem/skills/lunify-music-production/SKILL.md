---
name: lunify-music-production
description: "Plan or produce songs in Jiusera L-unify. Turn the user's brief into a Suno prompt, keep existing lyrics and song versions, and return authorized audio or stems to the selected project and song."
metadata:
  short-description: L-unify 歌曲创作与归档
---

# L-unify 歌曲创作

从聊天需求或 L-unify 歌曲卡发起。先分清写稿、生成、续查、归档、分轨和进入 L-unify IMW。仅写稿时直接交稿。需要提交或归档时，先读回实际登记的项目、歌曲和版本，核对用户意图与卡片交接的稳定 ID。新歌登记后读回其 ID。日常创作及归档可从歌曲列表完成。

1. 复用已确认的标题、原词、乐句、署名和现有版本。需要创作或修订时读[制作稿约定](references/prompt.md)。将原词和用于演唱的带段落标签版本分别保留。
2. 用 `own.music.production` 在同一项目登记或读取原请求。按[歌卡字段与回填](references/jiusera.md)提交真实支持的字段，取得原请求和幂等键。卡片和聊天沿同一操作。
3. 执行官方 Suno 操作及接收结果时读[生成、下载与分轨](references/suno.md)。首次确认的扣费范围、下载授权、分轨以及公开发行各有独立用途。用户已明确只写词、只看提示词或只试免费链路时，以该范围执行。
4. 将可合法取得的每个 take 先通过 `audio.project.import` 登记，再用 `own.music.production` 关联原请求。从原卡读回项目、歌曲、版本、配套歌词和可读取的资产。分轨按原 take 及分组读回。告诉用户哪些已经可听或入库，哪些仍在生成、待接收、需要下载额度或只有部分分轨。卡片入口跳转与媒体保存结果分别核验。

成曲后，用户说「用这版做 MV」或歌曲列表选中「用这版做 MV」时，沿当前 Codex 对话接续。已选的 Suno、ACE、本地分轨、完整混音和 IMW 输出母带均保留原版本。使用 `own.music.production` 的 `start_mv`，传 `project/song/version`，以及 `window: "whole_song"` 或歌曲绝对毫秒 `{start_ms,end_ms}`。它会读回本机音频并新建或恢复此版本、此范围的 IMW 视频作品。入口已返回 `work_id` 时直接读这件作品的时间线并保留手工调整。只有供应商曲目页或未取得可剪辑音频时，标明待归档，沿现有下载资格处理。随后用同一件作品继续分镜、镜头候选和剪辑。
