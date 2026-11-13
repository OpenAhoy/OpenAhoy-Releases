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
         '用于原未知素材的只读核对，不是通用素材管理器。',
         'api/material/permanent/api_batchgetmaterial.html'),
        ('草稿与发表', '草稿保存与独立读回', 'draft.add / draft.get', '已接入',
         '按原顺序每组1–8篇保存，独立读取原草稿。', SOURCES['draft_add']['url']),
        ('草稿与发表', '草稿列表', 'draft.batchget', '已接入',
         '读取当前草稿列表；完整性和账号权限以实际结果为准。',
         'api/draftbox/draftmanage/api_draft_batchget.html'),
        ('草稿与发表', '草稿修改与分组维护', 'draft.update / draft.delete', '已接入 · 专项流程',
         '已存在的修改、恢复和分组维护入口分别处理原对象，不在本页执行。',
         'api/draftbox/draftmanage/api_draft_update.html'),
        ('草稿与发表', '普通发表', 'POST '+METHODS['freepublish.submit'][0], '已接入',
         '从原保存回执提交一次官方发表；普通发表不推送粉丝。',
         'api/public/api_freepublish_submit.html'),
        ('草稿与发表', '发表状态与文章链接', 'POST '+METHODS['freepublish.get'][0], '已接入',
         '查询原微信发表任务，取得终态和逐篇真实文章链接。',
         'api/public/api_freepublish_get.html'),
        ('草稿与发表', '已发表全文与历史列表', 'freepublish.batchget / getarticle', '未接入',
         '当前可读取原发表任务的结果；全量历史列表和全文读取仍未接入。',
         'api/public/api_freepublish_batchget.html'),
        ('运营能力', '粉丝群发', 'mass.sendall / mass.get', '仅协议 · 未开放日常入口',
         '已有协议编码不代表可直接群发，需单独委托和平台权限。',
         'guide/product/message/Batch_Sends.html'),
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
            +''.join(sections)+'<p class="help">文档依据为项目核对的官方资料（'+CAPTURE_DATE
            +'）与当前源码。本次官方站点未能在线复核，链接不代表文档已刷新。</p>')
