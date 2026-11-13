"""One versioned registry for HTMLQA01, and pure shared checks. No IO/grant.

Official values bind the reviewed public snapshot, not a claim of fresh web
research or account permission. Renderers derive documentation and UI from this
registry. Human/editorial QA remains the production Skill's responsibility.
"""
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
from urllib.parse import urlsplit

VERSION = 'WCE_HTML_TECHNICAL_STANDARD_20261105_V1'
CAPTURE_DATE = '2026-11-03'
SOURCES = {
    'draft_add': {'url': 'https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html',
                  'body_sha256': 'a14ea15093eacfef822358b9951372004b92d07f9fe035097df95581b3e213c5'},
    'body_image': {'url': 'https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_uploadimage.html',
                   'body_sha256': 'a84f0f51b2a8cc747589fc5264fcc8a755bef335970f0bb5b7a2a2e6526cd023'},
    'permanent_image': {'url': 'https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_addmaterial.html',
                        'body_sha256': '41b2a5d5d6ae7b558b0ec29f65687ec0417bc3563d93d8f65025c526faae1fa6'},
}
# Existing wire unit conversions are implementation values, not exact byte
# definitions from the official snapshot (which states 1M/1MB/10M/1 kb).
# Keep their attribution separate; this registry introduces no business quota.
LIMITS = {'title_chars': 32, 'author_chars': 16, 'digest_chars': 120,
          'content_chars_exclusive': 20000, 'content_bytes_exclusive': 1000000,
          'source_url_bytes': 1024, 'body_image_bytes_exclusive': 1000000,
          'permanent_image_bytes': 10000000}
RULES = (
    ('OFFICIAL_DRAFT_TITLE', 'OFFICIAL', 'draft_add', 'draft/add:news.title', '标题Unicode字符数不超过{title_chars}；JSON直接传字符串。', '缩短标题并保持标题正文一致。'),
    ('OFFICIAL_DRAFT_AUTHOR', 'OFFICIAL', 'draft_add', 'draft/add:news.author', '作者Unicode字符数不超过{author_chars}；具体署名由本号偏好决定。', '修订作者字段，不能用其他账号的署名。'),
    ('OFFICIAL_DRAFT_DIGEST', 'OFFICIAL', 'draft_add', 'draft/add:news.digest', '单图文摘要不超过{digest_chars}字，多图文摘要为空；未填写可能由平台提取。', '多篇传空摘要，内部保留自定义原文。'),
    ('OFFICIAL_DRAFT_CONTENT', 'OFFICIAL', 'draft_add', 'draft/add:news.content', '实际最终HTML含标签及真实URL，官方原文要求少于2万字符、小于1M；封存未定义1M的精确字节换算。自包含源文件大小不是此字段大小。', '核实际投影；不能猜URL长度、删正文或拆组过关。'),
    ('OFFICIAL_DRAFT_SOURCE', 'OFFICIAL', 'draft_add', 'draft/add:content_source_url', '原文URL官方原文要求不超过1 kb；封存未定义精确字节换算。', '使用合法完整原文链接，勿截断URL。'),
    ('OFFICIAL_DRAFT_BODY_ORIGIN', 'OFFICIAL', 'draft_add', 'draft/add:news.content.img.src', '正文图片必须为uploadimg返回的URL；域名或HTTP200本身不证明来源。', '复用同号原成功上传回执的完整URL；UNKNOWN查原key。'),
    ('OFFICIAL_DRAFT_COVER', 'OFFICIAL', 'draft_add', 'draft/add:news.thumb_media_id', 'news封面必须使用永久素材media_id；newspic分支另有合同，本版本不将其限制套在news。', '使用同号永久封面上传成功回执，不填临时URL。'),
    ('OFFICIAL_BODY_IMAGE', 'OFFICIAL', 'body_image', 'media/uploadimg:media', '正文图片仅JPEG/PNG，官方原文要求1MB以下；封存未定义1MB的精确字节换算。', '保留源图；选择符合真实限制的传输副本并验证差异，勿默默降质。'),
    ('OFFICIAL_PERMANENT_IMAGE', 'OFFICIAL', 'permanent_image', 'material/add_material:type=image', '永久图片支持bmp/png/jpeg/jpg/gif，官方原文大小为10M；未定义精确字节换算，不是type=thumb的64KB规则。', '按接口区分限制；当前WCE解码/传输支持范围另列兼容规则。'),
    ('WCE_WIRE_BYTE_UNITS', 'WCE_COMPATIBILITY', None, 'wire byte-unit interpretation', '现行实现将正文1M及正文图片1MB换算为{content_bytes_exclusive}字节的严格小于，将永久图片10M换算为{permanent_image_bytes}字节上限、原文URL 1 kb换算为{source_url_bytes} UTF8字节；这些是既有实现解释，尚未取得官方精确字节定义，不标为官方额外额度。', '报告具体接口与实现边界；保留原件，不凭未核单位扩大或缩紧阈值，不删正文、拆组或静默降质。'),
    ('WCE_HTML_CODEC', 'WCE_COMPATIBILITY', None, 'normal prepare / imported HTML', '本版本自包含HTML、PNG/JPEG与有限HTML/CSS语法由normal_html_import/html_document/import_styles/import_images实际实现校验；不执行JS，不请求外部图片/样式。font等价展开沿同一规范化器。', '定位到语法/样式，保全原HTML；不把未实现兼容报成微信禁止。'),
    ('WCE_ARTICLE_TOKEN', 'WCE_COMPATIBILITY', None, 'normal prepare:article_id', '原生schema的短字母数字article_id为WCE内部token，非微信业务ID要求；生产者自动稳定映射并记录原业务ID。', '使用本流程稳定映射，不要求用户改业务ID或再确认。'),
    ('WCE_UPLOAD_CODEC', 'WCE_COMPATIBILITY', None, 'own.assets.receive / own.uploads.execute', '本版支持PNG/JPEG及现行有界解码、源角色绑定和传输校验；既有传输封套不是微信封面官方限额。', '兼容不支持时报告真实实现边界，不能扩大平台权限或消耗旧预算。'),
    ('ACCOUNT_EDITORIAL', 'ACCOUNT_PREFERENCE', None, 'own.production.rules.read:effective', '作者内容、选题、文风、布局、图数/比例/审美取本号有效规则；偏好不能关闭官方硬要求。', '完整读取本号有效版本；已冻结稿/原key继续原有效流程。'),
)


def registry():
    return {'version': VERSION, 'captured_at': CAPTURE_DATE,
            'freshness': 'PINNED_PUBLIC_SNAPSHOT_NOT_20261105_REFRESH',
            'sources': SOURCES, 'limits': LIMITS,
            'rules': [{'id': rid, 'category': category, 'source': source, 'field': field,
                       'criterion': criterion.format(**LIMITS), 'repair': repair}
                      for rid, category, source, field, criterion, repair in RULES]}


def fingerprint():
    return sha256(json.dumps(registry(), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def reject(rule_id, field, observed=None):
    from .contracts import WCEError
    rule = next(row for row in registry()['rules'] if row['id'] == rule_id)
    error = WCEError('HTMLQA_' + rule_id)
    # Only bounded counts/indices and registry-authored strings; never source
    # text, URLs, account IDs, tokens, or image bytes. Existing wire shapes stay.
    error.technical_rule = {'id': rule_id, 'category': rule['category'],
                            'field': field, 'observed': observed,
                            'criterion': rule['criterion'], 'repair': rule['repair']}
    raise error


def _length(value, rule_id, field, maximum, *, nonempty=False, utf8=False):
    if type(value) is not str:
        reject(rule_id, field)
    try:
        raw = value.encode('utf-8')
        size = len(raw) if utf8 else len(value)
    except UnicodeError:
        reject(rule_id, field)
    if size > maximum or (nonempty and not value):
        reject(rule_id, field, size)


def validate_metadata(article, *, article_count=1, prefix='article'):
    _length(article.get('title'), 'OFFICIAL_DRAFT_TITLE', prefix+'.title', LIMITS['title_chars'], nonempty=True)
    _length(article.get('author', ''), 'OFFICIAL_DRAFT_AUTHOR', prefix+'.author', LIMITS['author_chars'])
    _length(article.get('digest', ''), 'OFFICIAL_DRAFT_DIGEST', prefix+'.digest', LIMITS['digest_chars'])
    if article_count > 1 and article.get('digest'):
        reject('OFFICIAL_DRAFT_DIGEST', prefix+'.digest', len(article['digest']))
    _length(article.get('content_source_url', article.get('source_url', '')),
            'WCE_WIRE_BYTE_UNITS', prefix+'.content_source_url', LIMITS['source_url_bytes'], utf8=True)


def validate_content(value, *, field='content'):
    _length(value, 'OFFICIAL_DRAFT_CONTENT', field, LIMITS['content_chars_exclusive']-1, nonempty=True)
    _length(value, 'WCE_WIRE_BYTE_UNITS', field, LIMITS['content_bytes_exclusive']-1, utf8=True)
    return value


class _Images(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'iframe', 'object', 'embed'} or any(name.lower().startswith('on') for name, _ in attrs):
            reject('WCE_HTML_CODEC', 'content')
        if tag.lower() == 'img':
            sources = [value for name, value in attrs if name.lower() == 'src']
            if len(sources) != 1 or type(sources[0]) is not str:
                reject('OFFICIAL_DRAFT_BODY_ORIGIN', 'content.img.src')
            self.urls.append(sources[0])

    handle_startendtag = handle_starttag


def validate_payload(payload, *, uploaded_image_urls=None):
    """Pure final serialized news checks; source proof remains the trusted caller.

    When mappings are available, compare complete URLs to the independently
    validated original upload results. No host-name based provenance inference.
    Restored official GET rows retain their original provenance/authority path.
    """
    if type(payload) is not dict or type(payload.get('articles')) is not list or not payload['articles']:
        reject('WCE_HTML_CODEC', 'articles')
    rows = payload['articles']
    for index, row in enumerate(rows):
        prefix = 'articles['+str(index)+']'
        if type(row) is not dict or row.get('article_type', 'news') != 'news':
            reject('WCE_HTML_CODEC', prefix+'.article_type')
        validate_metadata(row, article_count=len(rows), prefix=prefix)
        validate_content(row.get('content'), field=prefix+'.content')
        cover = row.get('thumb_media_id')
        if type(cover) is not str or not cover or cover.startswith(('http:', 'https:', 'data:')):
            reject('OFFICIAL_DRAFT_COVER', prefix+'.thumb_media_id')
        parser = _Images()
        parser.feed(row['content']); parser.close()
        for position, url in enumerate(parser.urls):
            try:
                parts = urlsplit(url)
                valid = parts.scheme in ('https', 'http') and bool(parts.hostname) and parts.username is None and parts.password is None
            except ValueError:
                valid = False
            if not valid or (uploaded_image_urls is not None and url not in uploaded_image_urls):
                reject('OFFICIAL_DRAFT_BODY_ORIGIN', prefix+'.content.img['+str(position)+'].src')
    return payload


def validate_upload(purpose, mime, data):
    if purpose == 'article_body':
        if mime not in {'image/png', 'image/jpeg'} or type(data) is not bytes or not data:
            reject('OFFICIAL_BODY_IMAGE', 'media', len(data) if type(data) is bytes else None)
        if len(data) >= LIMITS['body_image_bytes_exclusive']:
            reject('WCE_WIRE_BYTE_UNITS', 'media', len(data))
    elif purpose == 'permanent_cover':
        if mime not in {'image/bmp', 'image/png', 'image/jpeg', 'image/gif'} or type(data) is not bytes or not data:
            reject('OFFICIAL_PERMANENT_IMAGE', 'media', len(data) if type(data) is bytes else None)
        if len(data) > LIMITS['permanent_image_bytes']:
            reject('WCE_WIRE_BYTE_UNITS', 'media', len(data))
    else:
        reject('WCE_UPLOAD_CODEC', 'purpose')


def render_markdown():
    spec = registry()
    lines = ['# WCE HTML技术规范', '', '本文件由 wce/html_technical_standard.py 自动生成，不手工维护数值。',
             '', '版本：'+VERSION, '', '规则SHA256：'+fingerprint(), '',
             '来源为2026-11-03封存的公开官方原文；2026-11-05未成功刷新。技术PASS不保证账号权限、网络、微信渲染或发表。', '']
    for rule in spec['rules']:
        lines += ['## '+rule['id']+' · '+rule['category'], '', '适用：'+rule['field'], '', rule['criterion'], '', '修复：'+rule['repair'], '']
        if rule['source']:
            source = SOURCES[rule['source']]
            lines += ['[官方来源]('+source['url']+')；封存原文SHA256：'+source['body_sha256'], '']
    return '\n'.join(lines)+'\n'


def render_html():
    sections = []
    for rule in registry()['rules']:
        source = SOURCES.get(rule['source'])
        citation = ('<p><a href="'+escape(source['url'],quote=True)+'">官方封存来源</a> · 原文SHA256 '+source['body_sha256']+'</p>') if source else ''
        sections.append('<li><strong>'+escape(rule['id']+' · '+rule['category'])+'</strong><p>'+escape(rule['criterion'])+'</p><p>'+escape(rule['repair'])+'</p>'+citation+'</li>')
    return ('<details id="htmlTechnicalStandard"><summary>插件技术规范（官方 / 兼容 / 本号偏好）</summary>'
            '<p>只读技术标准；本号偏好仍由下方编辑。'+escape(VERSION)+' · SHA256 '+fingerprint()+'</p>'
            '<p>官方来源封存于2026-11-03，本次未取得2026-11-05刷新。实际微信渲染/权限/发表另验。</p><ul>'+''.join(sections)+'</ul></details>')


def article_token(connection_id, business_id):
    """Producer-side stable adapter only; no tool schema or business-ID change."""
    if type(connection_id) is not str or not connection_id or type(business_id) is not str or not business_id:
        reject('WCE_ARTICLE_TOKEN', 'article_id')
    raw = json.dumps([connection_id, business_id], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return sha256(raw).hexdigest()[:16]


def safe_diagnostic(value, code):
    """Closed error sidecar. Rebuild all prose from the immutable local registry.

    This is an observation codec, never a permit or a caller-provided QA record.
    Both ends validate it. Unknown fields/IDs, bool-as-int, or reflected strings
    fail closed instead of travelling through the existing error channel.
    """
    import re
    if type(value) is not dict or set(value) != {'id', 'category', 'field', 'observed', 'criterion', 'repair'}:
        return None
    if type(value['id']) is not str:
        return None
    matches = [row for row in registry()['rules'] if row['id'] == value['id']]
    if len(matches) != 1:
        return None
    row = matches[0]
    allowed_codes = {'HTMLQA_'+row['id']}
    if row['id'] in {'OFFICIAL_DRAFT_CONTENT', 'WCE_WIRE_BYTE_UNITS'}:
        allowed_codes.add('OWN_CONSERVATIVE_NEWS_LIMIT')
    if type(code) is not str or code not in allowed_codes:
        return None
    for key in ('category', 'criterion', 'repair'):
        if type(value[key]) is not str or value[key] != row[key]:
            return None
    observed = value['observed']
    if observed is not None and (type(observed) is not int or not 0 <= observed <= 2**31-1):
        return None
    field = value['field']
    if type(field) is not str or len(field) > 96:
        return None
    suffix = {'OFFICIAL_DRAFT_TITLE':'title', 'OFFICIAL_DRAFT_AUTHOR':'author',
              'OFFICIAL_DRAFT_DIGEST':'digest', 'OFFICIAL_DRAFT_SOURCE':'content_source_url',
              'OFFICIAL_DRAFT_COVER':'thumb_media_id'}.get(row['id'])
    article = r'(?:article|articles\[[0-7]\])'
    if suffix:
        valid = re.fullmatch(article+r'\.'+suffix,field) is not None
    elif row['id'] == 'OFFICIAL_DRAFT_CONTENT':
        valid = re.fullmatch(r'(?:content|'+article+r'\.content)',field) is not None
    elif row['id'] == 'OFFICIAL_DRAFT_BODY_ORIGIN':
        match = re.fullmatch(r'articles\[[0-7]\]\.content\.img\[([0-9]{1,5})\]\.src',field)
        valid = field == 'content.img.src' or bool(match and int(match[1]) < LIMITS['content_chars_exclusive'])
    elif row['id'] in ('OFFICIAL_BODY_IMAGE','OFFICIAL_PERMANENT_IMAGE'):
        valid = field == 'media'
    elif row['id'] == 'WCE_WIRE_BYTE_UNITS':
        valid = field in {'media','content'} or re.fullmatch(article+r'\.(?:content|content_source_url)',field) is not None
    elif row['id'] == 'WCE_HTML_CODEC':
        valid = field in {'articles','content'} or re.fullmatch(article+r'\.article_type',field) is not None
    elif row['id'] == 'WCE_ARTICLE_TOKEN':
        valid = field == 'article_id'
    elif row['id'] == 'WCE_UPLOAD_CODEC':
        valid = field == 'purpose'
    else:
        valid = False
    if not valid:
        return None
    return {'id':row['id'], 'category':row['category'], 'field':field,
            'observed':observed, 'criterion':row['criterion'], 'repair':row['repair']}
