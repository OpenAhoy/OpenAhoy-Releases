"""Render the installed editorial sample with the current account's layout."""
from base64 import b64encode
from functools import lru_cache
from pathlib import Path
import re

from .content_templates import Templates


@lru_cache(maxsize=1)
def html():
    templates = Templates()
    featured = templates.catalog()['templates'][0]
    _, _, files = templates.materials(featured['id'], featured['version'])
    content = files['example/source.html'].decode().split('<body',1)[1].split('>',1)[1].split('</body>',1)[0]
    cover = Path(__file__).resolve().parents[1]/'assets/management/wechat-example-cover.webp'
    src = 'data:image/webp;base64,'+b64encode(cover.read_bytes()).decode()
    content = content.replace('../assets/cover.jpg',src)
    content = re.sub(r'<img src="\.\./assets/process\.jpg"[^>]*>','',content)
    content = re.sub(r'(<img src="data:image/[^"]+"[^>]*>)',
                     r'<figure>\1<figcaption>灵感手记 · 文章配图示例</figcaption></figure>',content)
    content = re.sub(r'<p[^>]+>演示文章 · [^<]+</p>',
                     '<h2 class="wx-sample-title">一页笔记如何长成一篇文章</h2>'
                     '<p class="wx-sample-byline" id="wechatSampleAuthor">Jiusera 编辑部</p>',content,count=1)
    return ('<aside id="wechatSetupPreview" aria-labelledby="wechatSampleTitle">'
            '<div class="wx-sample-head"><h2 id="wechatSampleTitle">示例文章</h2>'
            '<p id="wechatSampleState"></p></div>'
            '<article id="wechatSampleArticle">'+content+'</article></aside>')


SCRIPT = r'''
function OAWechatSetupPreview(rules){
 const $=id=>document.getElementById(id),ui=globalThis.OAUI;
 const surface=$('wechatConfigurationSurface'),button=$('wechatSampleToggle'),article=$('wechatSampleArticle');
 function open(show){
   surface.toggleAttribute('data-show-sample',show);button.setAttribute('aria-expanded',String(show));
   ui.set(button,show?'返回配置':'看示例文章');
 }
 button.onclick=()=>open(!surface.hasAttribute('data-show-sample'));
 function render(){
   const values=rules.preview();
   const author=values?.fields.author.trim();
   ui.set($('wechatSampleAuthor'),author||'Jiusera 编辑部');
   const layout=values?.fields.visual_layout||'';
   const size=layout.match(/(?:正文字号|字号)\s*[:：]?\s*(1[4-9]|2[0-2])\s*px/i);
   const spaced=/(留白舒展|宽松|舒展)/.test(layout);
   const dense=/(紧凑|紧密)/.test(layout);
   const selected=values?.fields.additional_notes.includes('[OpenAhoy template:openahoy-editorial-notebook@')||false;
   article.style.setProperty('--sample-text',size?size[1]+'px':'16px');
   article.style.setProperty('--sample-line',spaced?'2.04':dense?'1.56':'1.82');
   article.toggleAttribute('data-template',selected);
   ui.set($('wechatSampleState'),values?.dirty?'预览未保存更改':values?.available?'使用本号已保存配置':'标准版式示例');
 }
 return {render,close:()=>open(false)};
}
'''

STYLE = r'''
#wechatConfigurationSurface{display:grid;grid-template-columns:minmax(0,1fr) minmax(310px,390px);gap:clamp(16px,2vw,32px);min-height:0;flex:1;padding:3px 4px}
#wechatSetupColumn{min-width:0;min-height:0;display:flex;flex-direction:column;overflow:auto;scrollbar-width:thin;padding:1px 6px 10px}
#wechatSetupColumn #wechatSetupHome,#wechatSetupColumn .wx-manual-index{max-width:none;padding-inline:0}
#wechatSetupColumn :is(.wx-setup-features,.wx-manual-index){gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}
#wechatSetupColumn .wx-setup-feature{grid-template-columns:minmax(55px,26%) minmax(0,1fr);min-width:0}
#wechatSetupColumn .wx-setup-feature-copy{min-width:0;overflow-wrap:anywhere}
#wechatSetupPreview{min-width:0;min-height:0;align-self:start;max-height:100%;overflow:auto;scrollbar-width:thin;
 background:var(--surface);border-radius:16px;box-shadow:var(--oh-press);padding:12px;box-sizing:border-box}
.wx-sample-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px;padding:3px 3px 11px}
.wx-sample-head h2{font-size:14px;margin:0}
.wx-sample-head p{font-size:12px;margin:0;color:var(--muted)}
#wechatSampleArticle {--sample-accent:#214f43;min-width:0;background:#fff;color:#233733;border-radius:9px;overflow:hidden}
#wechatSampleArticle[data-template]{--sample-accent:#236251}
#wechatSampleArticle[data-template] section{background:#f7fbf8!important}
#wechatSampleArticle section{padding:16px 15px!important}
#wechatSampleArticle section p:not(.wx-sample-byline){font-size:var(--sample-text)!important;line-height:var(--sample-line)!important}
#wechatSampleArticle section h2{color:var(--sample-accent)!important}
#wechatSampleArticle .wx-sample-title{font-size:24px!important;line-height:1.24;margin:0 0 8px}
#wechatSampleArticle .wx-sample-byline{margin:0 0 15px;font-size:12px;color:#64766e}
#wechatSampleArticle figure{margin:0 0 14px}
#wechatSampleArticle figure img{margin:0!important}
#wechatSampleArticle figcaption{font-size:11px;color:#64766e;text-align:center;margin:6px 0}
#wechatSampleToggle{display:none}
#wechatSettings[data-desk-view] #wechatConfigurationSurface{display:flex;overflow:auto}
#wechatSettings[data-desk-view] #wechatSetupColumn{width:100%;overflow:visible}
#wechatSettings[data-desk-view] :is(#wechatSampleToggle,#wechatSetupPreview,#wechatManualToolbar){display:none}
@media(max-width:1099px){
 #wechatConfigurationSurface{display:flex;flex-direction:column;gap:8px;overflow:auto}
 #wechatSetupColumn{overflow:visible;flex:none}
 #wechatSampleToggle{display:block;align-self:end;order:-1;margin-inline:0}
 #wechatSetupPreview,#wechatConfigurationSurface[data-show-sample] #wechatSetupColumn{display:none}
 #wechatConfigurationSurface[data-show-sample] #wechatSetupPreview{display:block;align-self:center;width:min(100%,390px);max-height:none}
}
@media(max-width:740px){
 #wechatSetupColumn :is(.wx-setup-features,.wx-manual-index){grid-template-columns:minmax(0,1fr);gap:10px}
}
'''
