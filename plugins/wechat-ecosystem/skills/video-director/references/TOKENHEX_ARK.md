# Token Hex · 方舟视频

Jiusera「视频生成 → 模型设置」有独立 Token Hex 卡片。地址为 `https://api.tokenhex.com`，专用 Token 在卡片输入并手动保存。点击「查询可见模型」使用同一 Token 执行只读 `GET /v1/models`。目录只列本插件已有请求契约的具体 Seedance ID，模型别名须先有站点契约并验证后才能接入。

从可见的受支持 Seedance 模型中选择一个并点「选用模型」。状态为「已选用模型，待实测」。目录只证明当前 Token 能看到这个模型。首次使用无需已有视频任务。成功生成、原任务查询与 MP4 入库后标为「视频通路已实测」。更换 Token 后重新读取目录和选用。

只有本次计费明确获授权时，使用 `video.tokenhex.generation.submit` 按明确选中的模型和有效 Seedance 模式提交一次。使用稳定的 `generation_attempt_id`，按原项目及 attempt 以 `video.ark.generation.status` 的 `poll: true` 查询。查询固定沿原身份和网关原 ID。遇到 UNKNOWN，先向站点核实原结果，不换提交路径或 attempt 重发。若返回可匿名下载的 HTTPS MP4，原成片会进入项目资产库。用量按站点回包，扣费以站点账单为准。

候选采用 [New API 文档中的 Doubao 原生路由](https://github.com/QuantumNous/new-api/blob/main/docs/plugin-api/v1.md)及[方舟 API 契约](https://console.volcengine.com/ark/region%3Acn-beijing/docs/create-video-generation-task-api)。真实站点如采用另一条路径、非标准模型 ID 或需鉴权的媒体交付格式，先取得该站点的脱敏契约。
