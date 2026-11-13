# OpenAhoy HTML 输入

正常内容制作每篇交付一个含真实配图的自包含 HTML。使用 `own.documents.prepare` 的 `html_sources` 分支，有序传入本组各篇的 `absolute_path`、`expected_sha256`、`article_id`，以及需要的 `metadata_title/metadata`；不要同时传 `document`。原请求键保持稳定，不将整组拆成多条单篇草稿。

图片以 PNG/JPEG dataURI 嵌入 HTML。插件按显示顺序提取并核验原字节，取得同号真实资产引用；首图同时用作封面，重复显示位置和 alt 保持。无需额外交付 image_specs、图片附件、Word 或 PDF。HTML 不得选择其他本机文件、抓取外部图片或声明授权。

本版本组稿入口每组为 1–8 篇；这不是每号、每日或时段额度。超过8篇按原顺序分组，尾组不等满8。正常入口没有固定配图数量、12K/24K HTML、512 DOM 节点、账号累计图片或缓存数量的业务上限。最终实际正文（包括标签和微信返回的真实图片URL）的官方字符/UTF8边界由随包自动生成的HTML_TECHNICAL_STANDARD.md及共享校验器规定；原始自包含HTML里的dataURI大小不冒充最终正文长度。

制作时保留原图，按所用接口的官方约束、当前WCE兼容支持及本号有效偏好处理合规传输副本；正文图与永久封面规则分开，不能将某个账号的小图偏好变成所有用户的官方封面限制。检查副本的实际格式、字节数、尺寸与可读性，再嵌入HTML，不因压缩丢图或改变内容含义。源图、传输副本及原哈希分开记；新副本不能复用旧素材的哈希或远端证明。有限 PNG/JPEG 解码及 HTML/CSS 兼容范围仍逐项校验，不承诺任意网页/图片编码都可直接使用。

多篇组的每篇 `metadata.digest` 为空；自定义摘要保在制作记录，待单独编辑时用 `editorial_intent.summary=manual_required`。微信补默认摘要不算用户要求的空白或自定义摘要已满足，不填默认前段、不可见字符或拆组绕过。作者与样式来自当前本号有效生产规则，未冻结制作按安全点更新，冻结稿不自动重写。

HTML可使用有限的网页壳、内嵌样式和受支持的手机布局，转换为安全内联片段。未知标签/样式、外部资源、事件/脚本或不支持的编码明确报错，不静默清洗后称视觉相同。源HTML、规范投影、原图片/传输副本和微信实际GET是不同证据；本地预览不能代替微信读回或真实手机质量验收。

prepare只做本地接收及整组准备。接续 `own.articles.read` 核对冻结manifest，按真实slot上传，整组一次 `own.drafts.save`、独立 `own.drafts.readback`；成功复用原对象，UNKNOWN查询原键。草稿委托不授普通发表或群发权。个人STDIO以串行读取、锁和背压承载连续调用，不设业务突发次数/每秒次数/累计使用额度。

完整制作与生产规则读取见 Skill 的 `references/CONTENT_PRODUCTION.md`。本通用分发版不提供私人旧格式恢复入口；正常含图HTML沿本规范处理。


## 同源技术标准与创作后复查（HTMLQA01）

随包 `HTML_TECHNICAL_STANDARD.md` 由 `wce/html_technical_standard.py` 实际构建自动生成；管理页只读技术规范及prepare/最终发送校验消费同一registry与SHA256。先读取该规范，再读本号有效偏好；OFFICIAL硬要求、WCE_COMPATIBILITY语法/内部token条件、ACCOUNT_PREFERENCE分开，不能用偏好关闭官方校验。该规范注明官方封存日期，不宣称本次已在线刷新。

未冻结稿必须按 [完整生产流程](skills/wechat-ecosystem/references/CONTENT_PRODUCTION.md)先完成创作后AI内容与格式审查，发现问题回修后复查受影响部分，再正式prepare。审查不要求用户marker、逐篇确认或caller QA布尔；插件仍独立检查实际HTML/图片与最终真实URL的payload。已合格冻结稿继续原bundle/version/key，不能为本次流程补记而重prepare。

业务ID不是官方字段限制。新生产者使用同源 `article_token(connection_id, 原业务ID)` 自动生成稳定内部token，制作记录保存原业务ID、内部token及算法版本；已有token映射沿用，发现碰撞保留原记录并在本地显式处理，不要求用户改名。公开输入schema及其原来格式保持。
