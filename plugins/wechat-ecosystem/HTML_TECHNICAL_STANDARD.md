# WCE HTML技术规范

本文件由 wce/html_technical_standard.py 自动生成，不手工维护数值。

版本：WCE_HTML_TECHNICAL_STANDARD_20261105_V1

规则SHA256：2e50b51e50c65fa2ad8de7f7e0527a79175ac5e5ed56f9b2500dd9059454aeb2

来源为2026-11-03封存的公开官方原文；2026-11-05未成功刷新。技术PASS不保证账号权限、网络、微信渲染或发表。

## OFFICIAL_DRAFT_TITLE · OFFICIAL

适用：draft/add:news.title

标题Unicode字符数不超过32；JSON直接传字符串。

修复：缩短标题并保持标题正文一致。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)；封存原文SHA256：a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5

## OFFICIAL_DRAFT_AUTHOR · OFFICIAL

适用：draft/add:news.author

作者Unicode字符数不超过16；具体署名由本号偏好决定。

修复：修订作者字段，不能用其他账号的署名。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)；封存原文SHA256：a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5

## OFFICIAL_DRAFT_DIGEST · OFFICIAL

适用：draft/add:news.digest

单图文摘要不超过120字，多图文摘要为空；未填写可能由平台提取。

修复：多篇传空摘要，内部保留自定义原文。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)；封存原文SHA256：a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5

## OFFICIAL_DRAFT_CONTENT · OFFICIAL

适用：draft/add:news.content

实际最终HTML含标签及真实URL，官方原文要求少于2万字符、小于1M；封存未定义1M的精确字节换算。自包含源文件大小不是此字段大小。

修复：核实际投影；不能猜URL长度、删正文或拆组过关。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)；封存原文SHA256：a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5

## OFFICIAL_DRAFT_SOURCE · OFFICIAL

适用：draft/add:content_source_url

原文URL官方原文要求不超过1 kb；封存未定义精确字节换算。

修复：使用合法完整原文链接，勿截断URL。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)；封存原文SHA256：a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5

## OFFICIAL_DRAFT_BODY_ORIGIN · OFFICIAL

适用：draft/add:news.content.img.src

正文图片必须为uploadimg返回的URL；域名或HTTP200本身不证明来源。

修复：复用同号原成功上传回执的完整URL；UNKNOWN查原key。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)；封存原文SHA256：a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5

## OFFICIAL_DRAFT_COVER · OFFICIAL

适用：draft/add:news.thumb_media_id

news封面必须使用永久素材media_id；newspic分支另有合同，本版本不将其限制套在news。

修复：使用同号永久封面上传成功回执，不填临时URL。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)；封存原文SHA256：a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5

## OFFICIAL_BODY_IMAGE · OFFICIAL

适用：media/uploadimg:media

正文图片仅JPEG/PNG，官方原文要求1MB以下；封存未定义1MB的精确字节换算。

修复：保留源图；选择符合真实限制的传输副本并验证差异，勿默默降质。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_uploadimage.html)；封存原文SHA256：a84f0f51b2a8cc747589fc5264fcc8a755bef335970f0bb5b7a2a2e6526cd023

## OFFICIAL_PERMANENT_IMAGE · OFFICIAL

适用：material/add_material:type=image

永久图片支持bmp/png/jpeg/jpg/gif，官方原文大小为10M；未定义精确字节换算，不是type=thumb的64KB规则。

修复：按接口区分限制；当前WCE解码/传输支持范围另列兼容规则。

[官方来源](https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_addmaterial.html)；封存原文SHA256：41b2a5d5d6ae7b558b0ec29f65687ec0417bc3563d93d8f65025c526faae1fa6

## WCE_WIRE_BYTE_UNITS · WCE_COMPATIBILITY

适用：wire byte-unit interpretation

现行实现将正文1M及正文图片1MB换算为1000000字节的严格小于，将永久图片10M换算为10000000字节上限、原文URL 1 kb换算为1024 UTF8字节；这些是既有实现解释，尚未取得官方精确字节定义，不标为官方额外额度。

修复：报告具体接口与实现边界；保留原件，不凭未核单位扩大或缩紧阈值，不删正文、拆组或静默降质。

## WCE_HTML_CODEC · WCE_COMPATIBILITY

适用：normal prepare / imported HTML

本版本自包含HTML、PNG/JPEG与有限HTML/CSS语法由normal_html_import/html_document/import_styles/import_images实际实现校验；不执行JS，不请求外部图片/样式。font等价展开沿同一规范化器。

修复：定位到语法/样式，保全原HTML；不把未实现兼容报成微信禁止。

## WCE_ARTICLE_TOKEN · WCE_COMPATIBILITY

适用：normal prepare:article_id

原生schema的短字母数字article_id为WCE内部token，非微信业务ID要求；生产者自动稳定映射并记录原业务ID。

修复：使用本流程稳定映射，不要求用户改业务ID或再确认。

## WCE_UPLOAD_CODEC · WCE_COMPATIBILITY

适用：own.assets.receive / own.uploads.execute

本版支持PNG/JPEG及现行有界解码、源角色绑定和传输校验；既有传输封套不是微信封面官方限额。

修复：兼容不支持时报告真实实现边界，不能扩大平台权限或消耗旧预算。

## ACCOUNT_EDITORIAL · ACCOUNT_PREFERENCE

适用：own.production.rules.read:effective

作者内容、选题、文风、布局、图数/比例/审美取本号有效规则；偏好不能关闭官方硬要求。

修复：完整读取本号有效版本；已冻结稿/原key继续原有效流程。

