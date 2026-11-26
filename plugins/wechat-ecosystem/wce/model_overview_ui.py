"""Provider cards for the managed credential editors."""
from base64 import b64encode
from functools import cache

from .own_branding import _PACKAGE
from . import video_sand as sand
from . import video_vidmuse as vidmuse

PROVIDERS = (
    ('ark', 'video', '火山方舟', 'Seedance', 'key'),
    ('ark_global', 'video', '方舟国际站', 'Dreamina Seedance', 'key'),
    (sand.PROVIDER, 'video', 'Sand AI', 'MAGI-2', 'key'),
    (vidmuse.PROVIDER, 'video', 'VidMuse', 'MAGI-2', 'oauth'),
    ('cn', 'video', 'MiniMax 中国站', 'MiniMax H3', 'key'),
    ('global', 'video', 'MiniMax 国际站', 'MiniMax H3', 'key'),
    ('relay', 'video', 'AutoDL', 'MiniMax H3', 'token'),
    ('tokenhex', 'video', 'Token Hex', 'Seedance', 'token'),
    ('openai_gif', 'gif', 'OpenAI', '', 'key'),
    ('suno', 'music', 'Suno', '', 'oauth'),
    ('ace-music', 'music', 'ACE Music', '', 'oauth'),
)
GROUPS = {'video': '画布 · 视频', 'gif': '通用 API', 'music': 'L-unify · 音乐'}
LINKS = {
    'ark': ('获取 API Key', 'https://ark.volcengine.com/region:cn-beijing/apikey'),
    'ark_global': ('获取 API Key', 'https://ai.byteplus.com/ark/region:ap-southeast-1/apikey'),
    sand.PROVIDER: ('获取 API Key', sand.KEYS_URL),
    vidmuse.PROVIDER: ('官方接入指南', vidmuse.DOC_URL),
    'cn': ('获取 API Key', 'https://platform.minimax.cn/console/keys'),
    'global': ('获取 API Key', 'https://platform.minimax.io/console/keys'),
    'relay': ('获取 API Key', 'https://api.autodl.com/docs/port/'),
    'tokenhex': ('获取 API Key', 'https://api.tokenhex.com/console/token'),
    'openai_gif': ('获取 API Key', 'https://platform.openai.com/api-keys'),
    'suno': ('获取 API Key', 'https://help.suno.com/en/articles/14551425'),
    'ace-music': ('获取 API Key', 'https://acemusic.ai/help/articles/connect-ace-music-to-your-ai-assistant/'),
}
PROMOTED_MODEL_KINDS = frozenset({'video', 'animated-gif', 'music-generation'})
MODEL_RECOMMENDATION = (
    'video', 'ark_global', 'Dreamina Seedance 2.5',
    '用文字、首尾帧或参考图在 Jiusera 画布生成视频。',
    '配置 BytePlus ModelArk', 'seedance-hero.webp',
)
MODEL_NEWS = (
    ('video', 'MAGI-2', 'Sand AI', '2026-11-24',
     'Sand AI 发布 MAGI-2，原生生成带同步声音的 1080p 视频。',
     'Jiusera 已接入文字和项目图片参考，需组织授权。', 'magi-2-story.webp',
     (sand.PROVIDER, '配置 Sand AI'), sand.ANNOUNCEMENT_URL),
    ('video', 'Dreamina Seedance 2.5 Flash', 'BytePlus ModelArk', '2026-11',
     '官方新增 480p 和 720p 视频型号，支持首尾帧、多参考生成、剪辑与延长。',
     'Jiusera 的方舟国际站暂未支持此型号', 'motion-still.webp', None,
     'https://docs.byteplus.com/en/docs/modelark/model-release-announcement?redirect=1'),
    ('animated-gif', 'GPT-Image-2.6 Flare', 'OpenAI', '2026-11-04',
     'OpenAI 发布 GPT-Image-2.6，Images API 可直接输出动态 GIF。',
     'Jiusera 已接入 Flare 参图生成，需项目权限。', 'gif-story.webp', ('openai_gif', '配置 OpenAI'),
     'https://developers.openai.com/api/docs/changelog'),
)
MODEL_MUSIC_PICK = (
    'music-generation', 'Suno 歌曲生成', '音乐生成推荐', None,
    '用文字描述或自带歌词生成歌曲，并将可下载音频归档至 L-unify。',
    'Jiusera 已接入，使用 Suno 账号授权。', 'suno-story.webp', ('suno', '配置 Suno'),
    'https://help.suno.com/en/articles/14551361',
)
LOGOS = {
    'ark': 'models/ark.svg',
    'ark_global': 'models/byteplus-modelark.svg',
    sand.PROVIDER: 'models/sand-ai.svg',
    vidmuse.PROVIDER: 'models/vidmuse.png',
    'cn': 'models/minimax-icon.png',
    'global': 'models/minimax-icon.png',
    'relay': 'models/autodl.png',
    'tokenhex': 'models/tokenhex.jpg',
    'openai_gif': 'models/openai-black.svg',
    'suno': 'management/suno-favicon.ico',
    'ace-music': 'models/ace-music.png',
}
IMAGE_TYPES = {'svg': 'svg+xml', 'png': 'png', 'jpg': 'jpeg', 'ico': 'x-icon', 'webp': 'webp'}


@cache
def image_source(path):
    image_type = IMAGE_TYPES[path.rsplit('.', 1)[1]]
    data = b64encode((_PACKAGE / 'assets' / path).read_bytes()).decode('ascii')
    return f'data:image/{image_type};base64,{data}'


def logo_html(provider):
    mark = f'<img src="{image_source(LOGOS[provider])}" alt="">'
    if provider == 'openai_gif':
        mark += f'<img class="wb-model-logo-dark" src="{image_source("models/openai-white.svg")}" alt="">'
    return f'<span class="wb-model-symbol" aria-hidden="true">{mark}</span>'


def model_art(filename, css_class):
    source = image_source(f'models/promo/{filename}')
    return f'<img class="{css_class}" src="{source}" alt="" decoding="async">'


def model_promo_html():
    kind, provider, name, purpose, setup, art = MODEL_RECOMMENDATION
    if kind not in PROMOTED_MODEL_KINDS:
        return ''
    return f'''<div class="wb-model-promo" data-spotlight="hero">
 {model_art(art, 'wb-model-hero-art')}
 {logo_html(provider)}
 <div class="wb-model-promo-body">
  <p class="wb-model-eyebrow">接入推荐</p>
  <h3>{name}</h3>
  <p class="wb-model-promo-copy">{purpose}</p>
  <button type="button" id="wbModelPromoSetup" data-promo-provider="{provider}"
   aria-haspopup="dialog" aria-controls="wbModelDialog">
   <span>{setup}</span><span aria-hidden="true">→</span>
  </button>
 </div>
</div>'''


def model_story_html(index, story):
    _, name, publisher, date, summary, support, art, setup, url = story
    published = f'<time datetime="{date}">{date}</time>' if date else ''
    setup_button = (
        f'<button type="button" class="wb-model-inline-setup" data-promo-provider="{setup[0]}"'
        f' aria-haspopup="dialog" aria-controls="wbModelDialog">{setup[1]}</button>'
        if setup else ''
    )
    link_label = '官方原文' if date else '官方说明'
    note_kind = ' wb-model-availability' if index == 1 else ''
    return f'''<article class="wb-model-story" data-spotlight="{index}">
 {model_art(art, 'wb-model-story-art')}
 <div class="wb-model-story-body">
  <p class="wb-model-story-meta"><span>{publisher}</span>{published}</p>
  <h3 id="wbModelStory-{index}">{name}</h3>
  <p class="wb-model-story-summary">{summary}</p>
  <div class="wb-model-story-foot"><span class="wb-model-story-note{note_kind}">{support}</span>
   <div class="wb-model-story-actions">
    {setup_button}<a class="wb-model-external" href="{url}" target="_blank" rel="noopener noreferrer"
     aria-labelledby="wbModelSource-{index} wbModelStory-{index}">
     <span id="wbModelSource-{index}">{link_label}</span> <span aria-hidden="true">↗</span></a>
   </div>
  </div>
 </div>
</article>'''


def shelf_pager(kind, label):
    return f'''<nav class="wb-model-pager" data-model-pager="{kind}" aria-label="{label}" hidden>
 <button type="button" aria-label="上一页"><span aria-hidden="true">‹</span></button>
 <output aria-live="polite"></output>
 <button type="button" aria-label="下一页"><span aria-hidden="true">›</span></button>
</nav>'''


def model_news_html():
    stories = ''.join(model_story_html(index, story)
                      for index, story in enumerate((*MODEL_NEWS, MODEL_MUSIC_PICK))
                      if story[0] in PROMOTED_MODEL_KINDS)
    return f'''<aside id="wbModelNews" class="wb-model-news-shelf" aria-labelledby="wbModelNewsTitle" tabindex="-1">
 <h2 id="wbModelNewsTitle">模型动态</h2>
 <div class="wb-model-promos">{model_promo_html()}{stories}</div>
 {shelf_pager('promo','推荐分页')}
</aside>'''


def overview_html():
    cards = []
    for provider, group, label, model, scheme in PROVIDERS:
        category = GROUPS[group]
        detail = ('MAGI-2 · 账号授权' if provider==vidmuse.PROVIDER else
                  '使用账号授权' if scheme == 'oauth' else
                  '由部署者提供中转 Token' if provider == 'relay' else model)
        secondary = f'<span class="wb-model-spec">{detail}</span>' if detail else ''
        identity = 'OAuth' if scheme == 'oauth' else 'Token' if scheme == 'token' else 'API Key'
        link_label, link_url = LINKS[provider]
        cards.append(f'''<div class="wb-model-card">
<button type="button" class="wb-model-tile" data-model-id="{provider}"
 data-model-group="{group}" aria-haspopup="dialog" aria-controls="wbModelDialog"
 aria-labelledby="wbModelName-{provider}" aria-describedby="wbModelStatus-{provider}">
 <span class="wb-model-tile-top">{logo_html(provider)}
  <span class="wb-model-category">{category}</span></span>
 <span class="wb-model-tile-main"><strong id="wbModelName-{provider}" data-model-name>{label}</strong>{secondary}</span>
 <span class="wb-model-tile-foot">
  <span id="wbModelStatus-{provider}" data-model-status>待核验</span>
  <span class="wb-model-credential">{identity}<code data-model-mask hidden></code></span>
 </span>
</button>
<a class="wb-model-link" href="{link_url}" target="_blank" rel="noopener noreferrer"
 aria-labelledby="wbModelLink-{provider} wbModelName-{provider}"><span id="wbModelLink-{provider}">{link_label}</span>
<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5"
 aria-hidden="true"><path d="M6 4H3v9h9v-3M8 3h5v5m0-5-6 6"/></svg></a>
</div>''')
    return (
        '<div id="wbModelLayout" class="wb-model-layout">'
        '<nav class="wb-model-mode" aria-label="模型管理视图" hidden>'
        '<button data-model-display="models" type="button" aria-pressed="true">模型</button>'
        '<button data-model-display="promo" type="button" aria-pressed="false">推荐</button></nav>'
        '<section class="wb-model-shelf" aria-label="模型"><div id="wbModelGrid" class="wb-model-grid">'
        + ''.join(cards) + '</div>' + shelf_pager('models','模型分页')
        + '</section>' + model_news_html() + '</div>'
    )
