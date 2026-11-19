# 歌曲与视频配乐

开始任何需要新生成的歌曲或视频配乐前，用 `audio.music.provider.read` 读取本机当前默认。该设置适用于 OpenAhoy 在本机的所有窗口和项目。用户已明确指定供应商时，按本次指定执行。仅在工具返回 `READY` 时使用默认值，不用聊天记忆、其他项目设置、可见工具或此前版本的默认值代替。返回 `UNAVAILABLE` 时说明设置无法核对，请在Jiusera音频页核对。

- 返回 `suno` 或用户点名 Suno，使用 [Suno 歌曲与视频配乐](SUNO_AUDIO.md) 对应的官方 MCP。
- 返回 `ace-music` 或用户点名 ACE Music，使用 [ACE Music 歌曲与项目配乐](ACE_MUSIC.md) 对应的官方 MCP。
- 所选供应商未授权、账号不可用或会话缺少工具时，说明如何打开该供应商的连接入口，等待恢复。保持该选择，不切换供应商、不使用另一家的工具。
- 给出方案、当前供应商模型及费用。只有用户明确批准本次提交才生成。提交后沿原供应商和原任务 ID 查询，切换默认值不改变既有任务。提交结果未知时先对账原任务。

使用用户已选定的歌曲时，直接用它的本机素材和原任务关系混合，无需重新生成。对原片先核实画面、节奏与对白，再记录入点、素材截取、增益和淡入淡出。用 `audio.project.video.inspect` 读取原视频，按需要带 `include_audio_evidence` 及 `frame_start` 核对可验证的时间码。用 `audio.project.mix` 引用原视频、已就绪的原曲与新混音 attempt，给出 `video_start_ms`、`music_offset_ms`、`fade_in_ms`、`fade_out_ms`、`volume_percent`、`keep_original`。原素材在不同项目时提供实际的 `video_project_id`、`song_project_id`。有独立证据时用 `timeline.duck` 表明需保留对白或环境声的区段。

OpenAhoy 音频页是当前设置的可见入口。每次开始新创作时从工具读回。
