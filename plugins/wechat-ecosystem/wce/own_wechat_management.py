"""WeChat-specific settings content, separate from the product shell."""
from .own_platform_catalog import WECHAT


def settings_html(*, templates=False):
    from .own_production_rules_ui import HTML
    from .html_technical_standard import render_html
    from .official_account_routes import render_html as routes
    raw_technical = render_html()
    technical = raw_technical.replace('微信公众号', '公众号')
    rules = HTML.removeprefix(raw_technical).replace('class="card" style="margin-top:24px"', 'class="panel"')
    rules = rules.replace('全局默认可按号覆盖', '公众号默认规则可按号覆盖')
    rules = rules.replace('<option value="">全局默认</option>', '<option value="">公众号默认规则</option>')
    from .content_templates_ui import HTML as template_html
    from .wechat_picture_ui import HTML as picture_html
    from .wechat_content_ui import HTML as content_html
    return ('<section id="wechatSettings" hidden data-platform-id="' + WECHAT + '">'
        '<div class="oa-tabs" role="tablist" aria-label="公众号平台设置">'
        '<button id="settings-rules" role="tab" aria-selected="true">生产规则</button>'
        '<button id="settings-pictures" role="tab" aria-selected="false">图片消息</button>'
        '<button id="settings-content" role="tab" aria-selected="false">素材与发布</button>'
        + ('<button id="settings-templates" role="tab" aria-selected="false">创作模板</button>' if templates else '') +
        '<button id="settings-routes" role="tab" aria-selected="false">官方通路</button>'
        '<button id="settings-technical" role="tab" aria-selected="false">技术格式</button></div>' + rules
        + '<section id="officialRoutes" class="panel" hidden>' + routes().replace('微信公众号', '公众号') + '</section>'
        + '<section id="technicalPanel" class="panel" hidden>'
        + technical.replace('<details id="htmlTechnicalStandard">', '<details id="htmlTechnicalStandard" open>')
        + '</section>' + picture_html + content_html + (template_html if templates else '') + '</section>')


def settings_script(*, compact=False):
    from .own_production_rules_ui import JS
    from .content_templates_ui import SCRIPT as template_script
    from .wechat_picture_ui import SCRIPT as picture_script
    from .wechat_content_ui import SCRIPT as content_script
    # Storage scope "global" remains WeChat-only; this is a presentation name.
    script = JS.replace('全局默认', '公众号默认规则').replace('全局版本', '公众号默认版本')
    if compact:
        script=script.replace('function mount(send, {compact=false}={}, {downloadFile=null}={})', 'function mount(send, {compact=true}={}, {downloadFile=null}={})')
    return script + template_script + picture_script + content_script + r'''
const OAPlatformSettings = {
 wechat_official_account: {
   mount(call,onNavigation=()=>{},host={}){
     const operations={'own.production.rules.read':'READ_RULES',
       'wce.settings.production.save':'SAVE_RULES','wce.settings.production.restore':'RESTORE_RULES'};
     const rules=WCEProductionRules.mount((name,args)=>{
       if(!Object.hasOwn(operations,name))throw new Error('PLATFORM_OPERATION_UNSUPPORTED');
       return call(operations[name],args);
     },{},host);
     const templates=host.templateCall?OACreativeTemplates.mount(rules,host):null;
     const pictures=host.templateCall?OAWechatPictures(host):null;
     const content=host.templateCall?OAWechatContentTools(host):null;
     const tabs=templates?['rules','pictures','content','templates','routes','technical']:['rules','pictures','content','routes','technical'];
     const setTab=name=>{for(const key of tabs){
       document.getElementById('settings-'+key).setAttribute('aria-selected',String(name===key));
       document.getElementById({rules:'productionRules',pictures:'wechatPictures',content:'wxContentTools',templates:'creativeTemplates',routes:'officialRoutes',technical:'technicalPanel'}[key]).hidden=name!==key;
     }};
     for(const name of tabs)document.getElementById('settings-'+name).addEventListener('click',()=>{onNavigation();rules.closeCreator();setTab(name);if(name==='templates')templates.show();if(name==='pictures')pictures?.refresh();if(name==='content')content?.refresh();});
     return {...rules,setReady(value,options){templates?.setReady(value);const result=rules.setReady(value,options);pictures?.refresh();content?.refresh();return result;},targetChanged(){templates?.targetChanged();pictures?.refresh();content?.refresh();},panelId:'wechatSettings',showRules(){rules.closeCreator();setTab('rules');},
       showCreator(){setTab('rules');},
       openBackend(){return host.openLink('https://mp.weixin.qq.com/');}};
   }
 }
};
'''
