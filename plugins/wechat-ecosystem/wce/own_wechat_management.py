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
    from .wechat_setup_home import html as setup_html
    from .wechat_setup_preview import html as preview_html
    return ('<section id="wechatSettings" hidden data-platform-id="' + WECHAT + '">'
        '<div id="wechatConfigurationSurface"><div id="wechatSetupColumn">'
        + setup_html(templates=templates)
        + '<details id="wechatSetupAdvanced" open><summary>手动配置与工具</summary>'
        '<div id="wechatManualIndex" class="wx-manual-index">'
        '<button type="button" data-wechat-manual="position"><strong>写什么、写给谁</strong><span>选题和读者</span></button>'
        '<button type="button" data-wechat-manual="voice"><strong>改文风和署名</strong><span>文章怎么写、署谁的名</span></button>'
        '<button type="button" data-wechat-manual="visual"><strong>改配图和排版</strong><span>用什么图、文章怎么排</span></button>'
        '<button type="button" data-wechat-manual="content"><strong>管理素材与发布</strong><span>素材、草稿、发布和留言</span></button>'
        '<details class="wx-manual-more" open><summary>更多工具</summary><div>'
        '<button type="button" data-wechat-manual="delivery">设置交付偏好</button>'
        '<button type="button" data-wechat-manual="notes">补充写作要求</button>'
        '<button type="button" data-wechat-manual="pictures">制作图片消息</button>'
        + ('<button type="button" data-wechat-manual="templates">浏览文章模板</button>' if templates else '')
        + '<button type="button" data-wechat-manual="routes">查看微信官方通路</button>'
        '<button type="button" data-wechat-manual="technical">查看文章格式</button>'
        '<button id="wechatManualProject" type="button">项目与技能</button>'
        '</div></details></div>'
        '<div id="wechatManualToolbar" hidden><button id="wechatManualBack" type="button">返回配置总览</button></div>'
        '<div class="oa-tabs" role="tablist" aria-label="公众号平台设置" hidden>'
        '<button id="settings-rules" role="tab" aria-selected="true">生产规则</button>'
        '<button id="settings-pictures" role="tab" aria-selected="false">图片消息</button>'
        '<button id="settings-content" role="tab" aria-selected="false">素材与发布</button>'
        + ('<button id="settings-templates" role="tab" aria-selected="false">创作模板</button>' if templates else '') +
        '<button id="settings-routes" role="tab" aria-selected="false">官方通路</button>'
        '<button id="settings-technical" role="tab" aria-selected="false">技术格式</button>'
        '<button id="wechatOpenProjectSettings" type="button">项目与 Skills</button></div>' + rules
        + '<section id="officialRoutes" class="panel" hidden>' + routes().replace('微信公众号', '公众号') + '</section>'
        + '<section id="technicalPanel" class="panel" hidden>'
        + technical.replace('<details id="htmlTechnicalStandard">', '<details id="htmlTechnicalStandard" open>')
        + '</section>' + picture_html + content_html + (template_html if templates else '') + '</details></div>'
        '<button id="wechatSampleToggle" aria-expanded="false" aria-controls="wechatSetupPreview">看示例文章</button>'
        + preview_html() + '</div></section>')


def settings_script(*, compact=False):
    from .own_production_rules_ui import JS
    from .content_templates_ui import SCRIPT as template_script
    from .wechat_picture_ui import SCRIPT as picture_script
    from .wechat_content_ui import SCRIPT as content_script
    from .wechat_setup_home import script as setup_script
    from .wechat_setup_preview import SCRIPT as preview_script
    # Storage scope "global" remains WeChat-only; this is a presentation name.
    script = JS.replace('全局默认', '公众号默认规则').replace('全局版本', '公众号默认版本')
    return script + template_script + picture_script + content_script + setup_script() + preview_script + r'''
const OAPlatformSettings = {
 wechat_official_account: {
   mount(call,onNavigation=()=>{},host={}){
     const operations={'own.production.rules.read':'READ_RULES',
       'wce.settings.production.save':'SAVE_RULES','wce.settings.production.restore':'RESTORE_RULES'};
     const $=id=>document.getElementById(id);
     const panel=$('wechatSettings'),advanced=$('wechatSetupAdvanced');
     let preview=null;
     const groups=['position','voice','visual','delivery','notes'];
     const inRules=selected=>groups.includes(selected);
     const rules=WCEProductionRules.mount((name,args)=>{
       if(!Object.hasOwn(operations,name))throw new Error('PLATFORM_OPERATION_UNSUPPORTED');
       return call(operations[name],args);
     },{compact:true,manual:{back:overview,preview:()=>preview?.render(),saved:()=>{
       overview();
       globalThis.OAUI.set($('wechatSetupStatus'),'已保存本号的内容定位。');
     },group:index=>enter(groups[index])}},host);
     const templates=host.templateCall?OACreativeTemplates.mount(rules,host):null;
     const pictures=host.templateCall?OAWechatPictures(host):null;
     const content=host.templateCall?OAWechatContentTools(host):null;
     const tabs=templates?['rules','pictures','content','templates','routes','technical']:['rules','pictures','content','routes','technical'];
     const surfaces={rules:'productionRules',pictures:'wechatPictures',content:'wxContentTools',templates:'creativeTemplates',routes:'officialRoutes',technical:'technicalPanel'};
     function setTab(name){
       for(const key of tabs){
         $('settings-'+key).setAttribute('aria-selected',String(name===key));
         $(surfaces[key]).hidden=name!==key;
       }
     }
     function overview(focus=true){
       delete panel.dataset.manualTask;
       setTab('');
       $('wechatManualIndex').hidden=false;
       $('wechatManualToolbar').hidden=true;
       advanced.open=true;
       advanced.querySelector('.wx-manual-more').open=true;
       setup.sync();
       const target=host.templateTarget?.();
       if(target&&rules.scope()!==target.connection_id)void rules.selectScope(target.connection_id,{isCurrent:target.isCurrent}).then(()=>setup.sync());
       if(focus)advanced.querySelector(':scope > summary').focus();
     }
     function enter(task,{read=true}={}){
       const isRule=inRules(task);
       advanced.open=true;
       panel.dataset.manualTask=task;
       $('wechatManualIndex').hidden=true;
       $('wechatManualToolbar').hidden=task==='position'||isRule;
       setTab(isRule||task==='creator'?'rules':task);
       if(isRule){rules.closeCreator();rules.showGroup(groups.indexOf(task));}
       if(task==='templates'&&read)templates?.show();
       if(task==='pictures')pictures?.refresh();
       if(task==='content')content?.refresh();
       panel.scrollTop=0;
       const heading=isRule?$('rulesSheetTitle'):$('wechatManualBack');
       heading.tabIndex=0;heading.focus({preventScroll:true});
     }
     for(const button of panel.querySelectorAll('[data-wechat-manual]'))
       button.onclick=()=>{onNavigation();enter(button.dataset.wechatManual);};
     for(const tab of tabs)$('settings-'+tab).onclick=()=>{onNavigation();enter(tab==='rules'?'position':tab);};
     const setup=OAWechatSetup(rules,templates,host,enter);
     preview=OAWechatSetupPreview(rules);
     $('wechatManualBack').onclick=()=>overview();
     $('rulesSheetClose').addEventListener('click',()=>overview());
     $('wechatManualProject').onclick=()=>$('wechatOpenProjectSettings').click();
     $('wechatOpenProjectSettings').onclick=()=>host.openProjectSettings?.();
     $('wechatSetupFiles').onclick=()=>{
       const target=host.templateTarget?.();if(!target)return;
       void rules.openCreator(target.connection_id,target.name,target.isCurrent).then(ok=>{if(ok)enter('creator');});
     };
     $('creatorBack').addEventListener('click',()=>{if(panel.dataset.manualTask==='creator')overview();});
     setTab('');
     return {...rules,
       setReady(value,options){templates?.setReady(value);const result=rules.setReady(value,options);pictures?.refresh();content?.refresh();setup.ready(value);return result;},
       targetChanged(){templates?.targetChanged();pictures?.refresh();content?.refresh();if(panel.dataset.deskView)content?.show(panel.dataset.deskView);if(panel.dataset.manualTask==='creator')overview(false);setup.sync();preview.close();preview.render();},
       showDesk(name){
         if(name&&panel.dataset.deskView!==name){enter('content');panel.dataset.deskView=name;content?.show(name);}
         else if(!name&&panel.dataset.deskView){delete panel.dataset.deskView;overview(false);}
       },
       async loadAccountScope(cid){const result=await rules.loadAccountScope(cid);setup.sync();preview.render();return result;},
       panelId:'wechatSettings',showRules(){enter('position');},
       showCreator(){enter('creator');},
       openBackend(){return host.openLink('https://mp.weixin.qq.com/');}};
   }
 }
};
'''
