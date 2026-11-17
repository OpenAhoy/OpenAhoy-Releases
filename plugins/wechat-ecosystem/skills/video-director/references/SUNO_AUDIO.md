# Suno 歌曲与视频配乐

本插件的 Suno 是官方 MCP Beta，OAuth 由本人授权。授权状态、可见工具、额度和正式生成分别核验。打开「媒体工坊 → 音频」可只读刷新 Suno 连接与曲库，并把歌曲构思、视频配乐交给当前 Codex 聊天。只有当前委托明确授权实际生成时，才使用官方工具。单独协助打开官方入口不授权付费生成或上传。

## 创作和恢复

先把 brief、目标项目、用户本轮授权和唯一请求标识保存在项目。使用官方已读回的 `audio-create` 字段 `title`、`style`、`lyrics`、`instrumental`，必要时明确 `vocal_gender`；标题与歌词分开。使用本轮固定 `idempotency_key`。在原回执登记所有变体 ID。用 `audio-wait`（`until: complete`）及 `audio-retrieve` 查原 ID，未知不可换键重发。调用 `audio-download` 仅按本轮已有下载授权，读真实返回类型。只能取得试听地址时，保留原 ID，等待本人从官方导入。媒体下载、商用权利和后续平台发表分别核对。

用 `media.library.prepare` 取得统一音频库目标和目录。有明确来源项目时传其已登记的 `source_project_id`；有明确目标账号时，可在原音频 attempt 下传平台和连接 ID，未指定就留空。核对现有 MP3/WAV/M4A 的 SHA‑256，再用 `audio.project.import`。若原文件仍位于登记项目，传该原 `source_project_id` 和项目相对路径。Suno 原件按实传 `provider: suno` 和原 `provider_id`。下载后也可导入本人批准的本机音轨，省略 provider 字段。音频页播放与下载保存的原字节。本机需要已安装的 FFmpeg 和 FFprobe；插件不会自动安装。

## 给现有视频配乐

用 `audio.project.video.inspect` 绑定项目、成片版本和 SHA，读取时长、宽高和实际音轨。第一次传 `include_audio_evidence: true`。无音轨时写明；有音轨时只把第一条音轨的 500 ms RMS 和数字静音段当作信号电平证据，对白位置需独立证据。工具若缺本机解码器或音轨未解出，记作未知。

传 `frame_start`（8 fps 索引）取得最多四张 JPEG，图片和对应的 `timecodes_ms` 一起返回。按开头、动作变化、结束选多个区段，只有能从图片确认的事实才作为观察。配乐单逐条写时间码、画面或音轨证据、音乐动作和原声处理。给出可走本机混音的入点、截取位置、增益、淡入淡出以及有独立证据时的压低段。保留音乐意图与实际观测的来源。默认纯器乐。

用 `audio.project.mix` 指定原视频、原曲、一个新的本机混音 attempt 和毫秒参数 `video_start_ms`、`music_offset_ms`、`fade_in_ms`、`fade_out_ms`、`volume_percent`、`keep_original`。以统一库作为混音输出时，原视频或歌曲位于其他登记项目，就分别传 `video_project_id` 和 `song_project_id`。已有歌曲混音在本机执行，创作不同版本用新本机混音 attempt。音频页可在原片和配乐版之间切换并导出 MP4。将配乐单摘要传作 score_plan。已确认有对白或需保留环境声时，以 timeline.duck 提供不重叠的时间段，每段用 start_ms、end_ms 和 gain_percent 指定压低幅度。使用 audio.project.cover_video 可把项目内 PNG/JPEG 封面和曲目合成为 H.264/AAC MP4。平台发文沿相应已授权入口。
