"""Read-only route inventory derived from shipped adapters and reviewed docs.

An implementation row is not an assertion of permission for a selected account.
No entry probes Tencent, loads credentials, or dispatches business operations.
"""
from html import escape
from .html_technical_standard import CAPTURE_DATE, SOURCES
from .publication_wire import METHODS
from .upload_wire import ENDPOINTS

DOC_ROOT = 'https://developers.weixin.qq.com/doc/subscription/'


def rows():
    return (
        ('账号接入', '账号连接验证', 'POST /cgi-bin/stable_token', '已接入',
         '用本号已有授权验证连接。账号类型、白名单和权限以微信响应为准。',
         'guide/dev/api/'),
        ('账号接入', '第三方平台扫码授权', 'component / authorizer', '未接入',
         '当前绑定方式是自有公众号 AppID 与 AppSecret，不提供扫码 OAuth。',
         'guide/dev/'),
        ('图文制作', '封面永久素材', 'POST '+ENDPOINTS['permanent_cover'], '已接入',
         '上传本号封面素材，沿用已保存的素材标识。', SOURCES['permanent_image']['url']),
        ('图文制作', '正文图片上传', 'POST '+ENDPOINTS['article_body'], '已接入',
         '上传图文中的图片，返回真实微信图片地址。', SOURCES['body_image']['url']),
        ('图文制作', '永久素材读取', 'material.batchget_material / get_material', '已接入 · 受限恢复',
         '「素材与发布」可读取本号列表、数量及单项详情，原未知素材仍可沿旧恢复通路查回。',
         'api/material/permanent/api_batchgetmaterial.html'),
        ('图文制作', '临时与永久素材', 'media.upload / material.add_material', '已接入',
         '支持图片、语音、视频及临时缩略图，调用内嵌上传时适用 700 KB 本地内联限制。',
         'api/material/temporary/api_uploadtempmedia.html'),
        ('图文制作', '商品卡片数据', 'channels/ec/service/product/getcardinfo', '已接入',
         '按官方返回的商品 key 或 DOM 使用。不同内容和账号的卡片资格由平台判断。',
         'api/draftbox/shop/api_ecsgetproductcardinfo.html'),
        ('草稿与发表', '草稿保存与独立读回', 'draft.add / draft.get', '已接入',
         '按原顺序每组1–8篇保存，独立读取原草稿。', SOURCES['draft_add']['url']),
        ('草稿与发表', '草稿列表', 'draft.batchget', '已接入',
         '读取图文及图片消息的现有草稿，保留每组原顺序。',
         'api/draftbox/draftmanage/api_draft_batchget.html'),
        ('草稿与发表', '图片消息', 'draft.add / draft.update / draft.get', '已接入',
         '使用 1–20 张本号永久图，首图为封面。已保存草稿可查回并使用原回执普通发表。',
         'api/draftbox/draftmanage/api_draft_add.html'),
        ('草稿与发表', '草稿修改与分组维护', 'draft.update / draft.delete', '已接入 · 专项流程',
         '已存在的修改、恢复和分组维护入口分别处理原对象，不在本页执行。',
         'api/draftbox/draftmanage/api_draft_update.html'),
        ('草稿与发表', '普通发表', 'POST '+METHODS['freepublish.submit'][0], '已接入',
         '从原保存回执提交一次官方发表；普通发表不推送粉丝。',
         'api/public/api_freepublish_submit.html'),
        ('草稿与发表', '发表状态与文章链接', 'POST '+METHODS['freepublish.get'][0], '已接入',
         '查询原微信发表任务，取得终态和逐篇真实文章链接。',
         'api/public/api_freepublish_get.html'),
        ('草稿与发表', '已发表全文与历史列表', 'freepublish.batchget / getarticle / delete', '已接入',
         '按页读本号历史和单篇正文，明确指定时可以撤下单篇。',
         'api/public/api_freepublish_batchget.html'),
        ('运营能力', '预览与粉丝群发', 'mass.preview / mass.sendall / mass.get', '已接入 · 本地协议已验',
         '单人预览、标签和全部关注者使用独立入口。音乐可构造预览请求，群发文档缺少音乐对象。',
         'api/notify/message/api_sendall.html'),
        ('运营能力', '原创声明与自动精选留言', '公众号编辑器设置', '未接入',
         '作者署名和留言基础字段随草稿处理；不将署名或本机意向当作原创已开启。',
         'guide/product/publish.html'),
        ('运营能力', '用户、菜单与消息', '用户管理 / 自定义菜单 / 消息回调', '未接入',
         '不因绑定公众号自动获得粉丝资料或消息读取能力。', 'api/'),
        ('运营能力', '数据分析与流量结算', '阅读数据 / 广告运营', '未接入',
         '当前需在微信后台查看；接口目录展示不代表结算资格或收益。', 'api/'),
    )


def render_html():
    sections, current = [], None
    for group, title, endpoint, state, purpose, document in rows():
        if group != current:
            if current is not None: sections.append('</div>')
            sections.append('<div class="route-group"><h3>'+escape(group)+'</h3>')
            current = group
        url = document if document.startswith('https://') else DOC_ROOT + document
        if not url.startswith('https://developers.weixin.qq.com/'):
            raise ValueError('OFFICIAL_DOC_ORIGIN_REQUIRED')
        sections.append('<article class="route-row"><div><strong>'+escape(title)+'</strong><p>'+escape(purpose)
            +'</p><code>'+escape(endpoint)+'</code></div><div class="route-aside"><span class="'
            +('implemented' if state.startswith('已接入') else '')+'">'+escape(state)+'</span><a href="'
            +escape(url,quote=True)+'" target="_blank" rel="noreferrer noopener" referrerpolicy="no-referrer">官方文档 ↗</a></div></article>')
    sections.append('</div>')
    return ('<h2>官方通路</h2><p class="help">这里区分插件实现状态与账号权限。查看本页不会连接微信或测试接口；本号权限仍需实际官方响应核对。</p>'
            +''.join(sections)+'<p class="help">技术格式沿原快照（'+CAPTURE_DATE
            +'），内容端点另于 2026-11-22 核对微信开发文档。</p>')
