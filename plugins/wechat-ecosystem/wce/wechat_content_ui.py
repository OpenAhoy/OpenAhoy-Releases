"""Official material, published-article, and message tools in account settings."""

HTML = r'''
<section id="wxContentTools" class="panel" hidden>
 <nav id="wechatInlineDeskNavigation" aria-label="当前账号工具"></nav>
 <h2>素材与发布</h2>
 <p id="wxOpsAccount"></p>
 <div class="oa-tabs" role="tablist" aria-label="公众号内容工具">
  <button type="button" data-wx-pane="media" role="tab" aria-selected="true">素材</button>
  <button type="button" data-wx-pane="publish" role="tab" aria-selected="false">发表草稿</button>
  <button type="button" data-wx-pane="published" role="tab" aria-selected="false">已发表</button>
  <button type="button" data-wx-pane="reads" role="tab" aria-selected="false">菜单与留言</button>
  <button type="button" data-wx-pane="admin" role="tab" aria-selected="false">读者与入口</button>
  <button type="button" data-wx-pane="operations" role="tab" aria-selected="false">运营台账</button>
  <button type="button" data-wx-pane="message" role="tab" aria-selected="false">预览与群发</button>
 </div>
 <div id="wxOpsMedia">
  <div class="actions">
   <label>类型 <select id="wxOpsMediaType">
    <option value="image">图片</option><option value="voice">语音</option><option value="video">视频</option>
    <option value="news">图文素材</option></select></label>
   <button type="button" id="wxOpsMaterialList">读取永久素材</button>
   <button type="button" id="wxOpsMaterialCount">素材数量</button>
   <button type="button" id="wxOpsMaterialPrev" data-page-step hidden>上一页</button>
   <button type="button" id="wxOpsMaterialNext" data-page-step hidden>下一页</button>
  </div>
  <div class="actions">
   <label>有效期 <select id="wxOpsMediaLife"><option value="permanent">永久</option><option value="temporary">临时</option></select></label>
   <label>本地文件 <input id="wxOpsFile" type="file" accept="image/png,image/jpeg,image/gif,audio/mpeg,audio/amr,video/mp4"></label>
   <button type="button" id="wxOpsUpload">上传到本号</button>
  </div>
  <div id="wxOpsVideoFields" hidden>
   <label>视频标题 <input id="wxOpsVideoTitle"></label>
   <label>视频简介 <input id="wxOpsVideoDescription"></label>
  </div>
  <ol id="wxOpsMaterialRows"></ol>
  <div id="wxOpsMediaView"></div>
 </div>
 <div id="wxOpsPublish" hidden>
  <div class="actions">
   <button type="button" id="wxOpsPublishLoad">读取本号草稿</button>
   <button type="button" id="wxOpsPublishNext" hidden>下一组草稿</button>
   <label>草稿组 <select id="wxOpsPublishDraft" aria-label="选择本号草稿组"></select></label>
  </div>
  <div class="actions">
   <label>发表方式 <select id="wxOpsPublishMode">
    <option value="ordinary">普通发表</option><option value="notify">同时群发通知</option>
   </select></label>
   <button type="button" id="wxOpsPublishSend">普通发表</button>
   <button type="button" id="wxOpsPublishCheck" hidden>查询原发表</button>
   <button type="button" id="wxOpsPublishFallback" hidden>改为普通发表</button>
  </div>
  <p id="wxOpsPublishPermission" class="help"></p>
  <label id="wxOpsPublishConfirmRow" hidden><input type="checkbox" id="wxOpsPublishConfirm"> 确认将所选图文群发给当前公众号的全部关注者</label>
  <details id="wxOpsOriginality">
   <summary>逐篇核对原创状态</summary>
   <ol id="wxOpsOriginalityRows"></ol>
   <button id="wxOpsOriginalityOfficial" type="button">打开微信公众平台</button>
   <p class="help">在同一草稿组按篇次核对原创声明。插件只有在微信返回明确标识时才能核实。</p>
  </details>
  <ol id="wxOpsPublishLinks"></ol>
 </div>
 <div id="wxOpsPublished" hidden>
  <div class="actions">
   <button type="button" id="wxOpsPublishedList">读取本号已发表</button>
   <button type="button" id="wxOpsPublishedPrev" data-page-step hidden>上一页</button>
   <button type="button" id="wxOpsPublishedNext" data-page-step hidden>下一页</button>
  </div>
  <ol id="wxOpsPublishedRows"></ol>
  <article id="wxOpsPublishedBody" style="white-space:pre-wrap;overflow-wrap:anywhere"></article>
 </div>
 <div id="wxOpsReads" hidden>
  <div class="actions"><button type="button" id="wxOpsMenuRead">读取当前菜单</button></div>
  <ul id="wxOpsMenuRows"></ul>
  <section aria-labelledby="wxOpsArticleHeading">
   <h3 id="wxOpsArticleHeading">文章数据与留言</h3>
   <div class="actions">
    <label>发表日期 <input type="date" id="wxOpsArticleDay" min="2025-11-01"></label>
    <button type="button" id="wxOpsArticleRead">读取本号文章</button>
    <label>文章 <select id="wxOpsArticle"></select></label>
   </div>
   <p class="help" id="wxOpsArticleMetrics"></p>
  </section>
  <div class="actions">
   <label>群发图文数据 ID <input id="wxOpsCommentId" inputmode="numeric" maxlength="19" autocomplete="off" spellcheck="false"></label>
   <label>第几篇 <input id="wxOpsCommentIndex" type="number" min="1" max="8" value="1"></label>
   <button type="button" id="wxOpsCommentRead">读取留言</button>
   <button type="button" id="wxOpsCommentPrev" data-page-step hidden>上一页</button>
   <button type="button" id="wxOpsCommentNext" data-page-step hidden>下一页</button>
  </div>
  <p class="help">可选择本号文章，也可填写本号群发回执中的数据 ID 和篇次。</p>
  <div class="actions">
   <button type="button" id="wxOpsAutoCheck">读取自动回复状态</button>
   <button type="button" id="wxOpsAutoStart" hidden>为当前文章启用 Codex 自动回复</button>
   <button type="button" id="wxOpsAutoStop" hidden>暂停本号自动回复</button>
  </div>
  <p class="help" id="wxOpsAutoStatus" role="status"></p>
  <ol id="wxOpsCommentRows"></ol>
 </div>
 <div id="wxOpsAdmin" hidden>
  <h3>平台权限与本号授权</h3>
  <ul id="wxOpsGrantRows"></ul>
  <details>
   <summary>关注者标签</summary>
   <div class="actions"><button type="button" id="wxOpsTagsRead">读取本号标签</button>
    <label>新标签 <input id="wxOpsTagName" maxlength="30"></label>
    <button type="button" id="wxOpsTagMake">创建本号标签</button></div>
   <ul id="wxOpsTags"></ul>
  </details>
  <details>
   <summary>公众号菜单</summary>
   <p class="help">先读取当前菜单并预览差异，确认后更新微信。</p>
   <label>菜单名称 <input id="wxOpsMenuName" maxlength="30"></label>
   <label>入口链接 <input id="wxOpsMenuLink" type="url" autocomplete="off"></label>
   <div class="actions"><button type="button" id="wxOpsMenuPlan">对比本号菜单</button>
   <button type="button" id="wxOpsMenuApply" hidden>用预览中的菜单替换</button></div>
   <div id="wxOpsMenuPlanRows"></div>
  </details>
  <details>
   <summary>渠道二维码</summary>
   <p class="help">按微信服务号接口生成临时渠道码。扫码事件与按渠道统计需要回调服务。</p>
   <label>渠道标识 <input id="wxOpsChannelScene" maxlength="64" placeholder="release-2026"></label>
   <label>有效天数 <input id="wxOpsChannelDays" type="number" min="1" max="30" value="7"></label>
   <button type="button" id="wxOpsChannelMake">生成本号渠道码</button>
   <div id="wxOpsChannelResult"></div>
  </details>
 </div>
 <div id="wxOpsOperations" hidden>
  <div class="actions">
   <label>记录类型 <select id="wxOpsLedgerKind">
    <option value="work">作品与账号版本</option><option value="idea">留言选题</option>
    <option value="schedule">运营日历</option><option value="rights">版权与可售版本</option>
    <option value="deal">商务询盘与回款</option><option value="money">收入、结算与成本</option>
   </select></label>
   <label>筛选作品编号 <input id="wxOpsLedgerFilter" maxlength="120"></label>
   <button type="button" id="wxOpsLedgerRead">读取台账</button>
   <button type="button" id="wxOpsLedgerNew">新增记录</button>
   <button type="button" id="wxOpsCalendarAll">查看工作区多号日历</button>
  </div>
  <p class="help">按公众号分别登记。同一作品在不同公众号使用相同作品编号，可分别保存版本和链接。</p>
  <div id="wxOpsLedgerTotals"></div>
  <ol id="wxOpsCalendarRows"></ol>
  <details id="wxOpsLedgerImport" hidden>
   <summary>导入本号账单</summary>
   <p class="help">UTF-8 CSV，每次最多 100 行。日期为 YYYY-MM-DD，金额填人民币分。同一来源、流水类型与账单行编号去重。</p>
   <p><code>date,entry,source,external_ref,title,amount_cents,work_ref,notes</code></p>
   <p class="help">流水类型 revenue/settlement/received/refund/cost；来源 advertising/praise/affiliate/paid_content/brand/licensing/production/other。</p>
   <label>本号账单文件 <input type="file" id="wxOpsLedgerStatement" accept=".csv,text/csv"></label>
   <button type="button" id="wxOpsLedgerImportSave">导入账单</button>
  </details>
  <ol id="wxOpsLedgerRows"></ol>
  <button type="button" id="wxOpsLedgerMore" hidden>下一页</button>
  <div id="wxOpsLedgerEditor" hidden>
   <div class="actions" id="wxOpsLedgerProjectRow" hidden>
    <label>项目 <select id="wxOpsLedgerProject"></select></label>
    <button type="button" id="wxOpsIdeaToSources" hidden>将原文加入本号项目的信源库</button>
   </div>
   <div id="wxOpsLedgerFields"></div>
   <div class="actions"><button type="button" id="wxOpsLedgerSave">保存记录</button>
   <button type="button" id="wxOpsLedgerCancel">取消编辑</button></div>
  </div>
 </div>
 <div id="wxOpsMessage" hidden>
  <label>方式 <select id="wxOpsMode"><option value="preview">预览给一人</option>
    <option value="openid-preview">预览给一个 OpenID</option>
    <option value="tag">按标签群发</option><option value="all">全部关注者</option>
    <option value="openids">按 OpenID 群发（认证服务号）</option></select></label>
  <label id="wxOpsRecipientLabel"><span id="wxOpsRecipientText">微信号</span> <input id="wxOpsRecipient" autocomplete="off"></label>
  <label id="wxOpsOpenIDLabel" hidden>本号 OpenID 名单（每行一个，2–10,000 个）
   <textarea id="wxOpsOpenIDs" rows="3" autocomplete="off" spellcheck="false"></textarea></label>
  <label>消息类型 <select id="wxOpsMessageType"><option value="text">纯文本</option><option value="mpnews">图文</option>
   <option value="image">图片</option><option value="voice">语音</option><option value="mpvideo">视频</option>
   <option value="music">音乐（预览）</option><option value="wxcard">卡券</option></select></label>
  <label><span id="wxOpsMessageLabel">消息正文</span> <textarea id="wxOpsMessageBody" rows="3"></textarea></label>
  <div class="actions" id="wxOpsDraftPicker" hidden>
   <button type="button" id="wxOpsLoadDrafts">读取本号图文草稿</button>
   <select id="wxOpsDraft" aria-label="选择图文草稿"></select>
  </div>
  <p id="wxOpsDraftNotice" hidden>微信可能在图文群发成功后移除所用草稿。请核对受众并确认。</p>
  <label><input type="checkbox" id="wxOpsConfirm"> 我已核对当前账号、内容和接收范围</label>
  <div class="actions"><button type="button" id="wxOpsDeliver">发送预览</button>
   <button type="button" id="wxOpsMessageStatus">查原请求</button></div>
 </div>
 <p id="wxOpsStatus" aria-live="polite"></p>
</section>'''

SCRIPT = r'''
const OAWechatPublication={
 tool:action=>'own.publications.current.'+action,
 text(result){
   const status=({NOT_ATTEMPTED:'尚未提交',ACCEPTED:'微信已受理，等待平台结果',
     PROCESSING:'微信处理中',PUBLISHED:'微信已发表',PUBLISHED_URLS_INCOMPLETE:'已发表，链接待微信回传',
     AWAITING_ADMIN:'请在微信完成管理员确认，再查询原任务',
     BROADCAST_SENT:'微信确认群发成功',BROADCAST_FAILED:'微信返回群发失败，请核对原群发记录',
     BROADCAST_DELETED:'微信返回原群发已删除',UNKNOWN:'结果未知，保留原任务，请勿重新发送',
     NOT_SENT:'本次未群发，可以改为普通发表',PLATFORM_REJECTED:'微信拒绝本次发表',
     PLATFORM_FAILED:'微信返回本次发表失败'})[result.state]||result.state;
   const fields=[OAUI.message(status)];
   if(result.quota_state==='EXHAUSTED')fields.push(OAUI.message('微信返回本次群发额度已用完'));
   if(result.permission_state==='DENIED')fields.push(OAUI.message('微信拒绝本号本次群发权限'));
   if(result.error_code)fields.push(OAUI.message('微信返回 {0}',result.error_code));
   if(result.task_id)fields.push(OAUI.message('原群发任务 {0}',result.task_id));
   if(result.last_query?.error_code)fields.push(OAUI.message('最近查询微信返回 {0}',result.last_query.error_code));
   return fields;
 },
 links(list,result,open){
   list.replaceChildren();
   for(const [index,url] of result.article_urls||[]){
     const item=document.createElement('li'),link=document.createElement('button');
     link.type='button';OAUI.set(link,'查看第 {0} 篇',index);link.onclick=()=>open(url);
     item.append(link);list.append(item);
   }
 }
};
const OAWechatContentTools=host=>{
 const el=id=>document.getElementById('wxOps'+id),section=document.getElementById('wxContentTools');
 const make=tag=>document.createElement(tag),tool='own.wechat.content';
 let account='',busy=false,epoch=0,active='media',objectURL=null;
 const pageSize=20, pages={};
 let publication=null,publicationCursor=null,articleRows=[],autoStatus=null,ledger=null,ledgerEdit=null,menuPlan=null;
 const publishContext=target=>key(target,'last-publication');
 const publicationTool=OAWechatPublication.tool;
 const publishSelection=()=>JSON.parse(el('PublishDraft').value||'null');
 function publicationButtons(){
   const ready=!!account&&!busy,selected=publishSelection(),control=el('PublishMode'),
     sent=!!publication&&publication.state!=='NOT_ATTEMPTED';
   const notify=control.value==='notify',supportsNotify=!!selected?.news;
   const status=host.templateTarget()?.official_profile;
   OAUI.set(el('PublishPermission'), status?.state==='ACTIVE'?
     (status.permissions?.includes(7)?'本号已授予第三方平台权限集 7。群发额度由微信确认。':
      '本号未向第三方平台授予权限集 7。'):'本号群发权限与剩余额度由微信确认。');
   el('PublishDraft').disabled=!ready||el('PublishDraft').options.length===0;
   el('PublishNext').hidden=publicationCursor===null;
   control.disabled=!ready||!selected||sent;
   control.options[1].disabled=!supportsNotify;
   if(!supportsNotify&&notify)control.value='ordinary';
   el('PublishConfirmRow').hidden=control.value!=='notify'||sent;
   el('PublishConfirm').disabled=!ready;
   el('PublishSend').hidden=sent;
   el('PublishSend').disabled=!ready||!selected||control.value==='notify'&&!el('PublishConfirm').checked;
   OAUI.set(el('PublishSend'),control.value==='notify'?'提交群发':'普通发表');
   el('PublishCheck').hidden=!selected&&!sent&&(!account||!localStorage.getItem(
     publishContext({connection_id:account})));
   el('PublishFallback').hidden=!publication?.fallback_allowed;
   const option=el('PublishDraft').selectedOptions[0];
   const titles=selected?.titles||[];
   const fingerprint=option?.value||'';
   const originality=el('OriginalityRows');
   if(originality.dataset.selection!==fingerprint){
     originality.dataset.selection=fingerprint;
     originality.replaceChildren(...titles.map((title,index)=>{
       const item=make('li');OAUI.set(item,'第 {0} 篇 · {1} · 原创状态未核验',index+1,title);return item;
     }));
     if(!titles.length)el('Originality').open=false;
   }
   el('Originality').hidden=!titles.length;
 }
 function publicationResult(value){
   publication=value;
   note(OAWechatPublication.text(value));
   OAWechatPublication.links(el('PublishLinks'),value,url=>void host.openLink(url).catch(()=>note(copy('当前宿主无法打开链接'))));
   publicationButtons();
 }
 function loadPublicationDrafts(cursor){
   return run(async (read,target,call)=>{
     const value=await call('own.drafts.inventory',cursor?{cursor}:{});
     const hint=make('option');hint.value='';OAUI.set(hint,'选择本号草稿组');
     el('PublishDraft').replaceChildren(hint);
     for(const group of value.groups||[]){
       const option=make('option');option.textContent=group.titles.join('、');
       option.value=JSON.stringify({
         selection:{inventory_handle:value.inventory_handle,index:group.index,
           expected_projection_sha256:group.projection_sha256,article_count:group.article_count},
         news:(group.article_types||[]).every(type=>type==='news'),titles:group.titles
       });
       el('PublishDraft').append(option);
     }
     publicationCursor=value.cursor??null;
     publication=null;el('PublishConfirm').checked=false;el('PublishMode').value='ordinary';
     el('PublishLinks').replaceChildren();
     note(copy(el('PublishDraft').options.length>1?'已读取本号草稿组':'本页没有草稿'));
   });
 }
 el('PublishLoad').onclick=()=>loadPublicationDrafts(null);
 el('OriginalityOfficial').onclick=()=>void host.openLink('https://mp.weixin.qq.com/').catch(()=>note(copy('当前宿主无法打开链接')));
 el('PublishNext').onclick=()=>loadPublicationDrafts(publicationCursor);
 el('PublishMode').onchange=()=>{el('PublishConfirm').checked=false;publicationButtons();};
 el('PublishConfirm').onchange=publicationButtons;
 el('PublishDraft').onchange=()=>{
   publication=null;el('PublishConfirm').checked=false;el('PublishMode').value='ordinary';
   el('PublishLinks').replaceChildren();publicationButtons();
   const selected=publishSelection();
   if(selected)void run(async (read,target,call)=>{
     publicationResult(await call(publicationTool('status'),{selection:selected.selection}));
   });
 };
 function requestPublication(fallback=false){
   return run(async (read,target,call)=>{
     const selected=publishSelection();
     const source=fallback&&publication?.intent_handle?{intent_handle:publication.intent_handle}:
       selected?{selection:selected.selection}:null;
     if(!source)return;
     const mode=fallback?'ordinary':el('PublishMode').value;
     if(mode==='notify'&&(!selected.news||!el('PublishConfirm').checked))return;
     localStorage.setItem(publishContext(target),JSON.stringify(source));
     el('PublishConfirm').checked=false;
     try{
       publicationResult(await call(publicationTool('dispatch'),
         {...source,mode,...(fallback?{fallback_from_notify:true}:{})}));
     }catch(error){
       const original=await call(publicationTool('status'),source);
       if(original.state==='NOT_ATTEMPTED')throw error;
       publicationResult(original);
     }
   });
 }
 el('PublishSend').onclick=()=>requestPublication();
 el('PublishFallback').onclick=()=>requestPublication(true);
 function checkPublication(poll=true){
   return run(async (read,target,call)=>{
     const selected=publishSelection(),source=publication?.intent_handle?{intent_handle:publication.intent_handle}:
       selected?{selection:selected.selection}:JSON.parse(localStorage.getItem(publishContext(target))||'null');
     if(!source)return;
     const value=await call(publicationTool('status'),source);
     const queryable=!['NOT_ATTEMPTED','NOT_SENT'].includes(value.state)&&
       (value.route!=='MASS_SENDALL'||!!value.task_id);
     publicationResult(poll&&queryable?await call(publicationTool('poll'),{intent_handle:value.intent_handle}):value);
   });
 }
 el('PublishCheck').onclick=()=>checkPublication();
 const key=(target,action)=>'jiusera.wechat.content.'+target.connection_id+'.'+action;
 const copy=(key,...values)=>OAUI.message(key,...values);
 const note=text=>OAUI.set(el('Status'),text?'{0}':'',text);
 const valid=target=>target?.isCurrent()&&target.connection_id===account;
 function buttons(){
   for(const control of section.querySelectorAll('button[id]'))control.disabled=!account||busy;
   for(const control of el('CommentRows').querySelectorAll('button'))control.disabled=!account||busy;
   publicationButtons();
   renderAuto();
 }
 function refresh(){
   const target=host.templateTarget(),id=target?.connection_id||'';
   if(id!==account){
     account=id;epoch++;busy=false;
     for(const name of ['MaterialRows','MediaView','PublishedRows','PublishedBody','MenuRows','CommentRows'])el(name).replaceChildren();
     for(const name of ['File','Recipient','OpenIDs','MessageBody','VideoTitle','VideoDescription'])el(name).value='';
     el('CommentId').value='';el('CommentIndex').value='1';
     articleRows=[];autoStatus=null;el('Article').replaceChildren();el('ArticleMetrics').textContent='';
     el('AutoStatus').textContent='';
     ledger=null;ledgerEdit=null;el('LedgerFilter').value='';
     el('LedgerRows').replaceChildren();el('LedgerTotals').replaceChildren();el('LedgerEditor').hidden=true;
     el('LedgerMore').hidden=true;el('CalendarRows').replaceChildren();el('LedgerStatement').value='';
     el('LedgerProjectRow').hidden=true;el('LedgerProject').replaceChildren();
     menuPlan=null;el('MenuApply').hidden=true;
     for(const name of ['Tags','MenuPlanRows','ChannelResult'])el(name).replaceChildren();
     for(const name of ['TagName','MenuName','MenuLink','ChannelScene'])el(name).value='';
     for(const name of ['Material','Published','Comment'])clearPage(name);
     el('Draft').replaceChildren();el('PublishDraft').replaceChildren();el('PublishLinks').replaceChildren();
     publication=null;publicationCursor=null;el('PublishMode').value='ordinary';el('PublishConfirm').checked=false;
     if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
     el('Confirm').checked=false;note('');
   }
   if(active==='admin')paintGrants(target);
   if(target?.name)OAUI.raw(el('Account'),target.name);
   else OAUI.set(el('Account'),'先选择一个公众号');
   buttons();
 }
 async function run(task){
   const target=host.templateTarget();if(!valid(target)||busy)return;
   const start=epoch;busy=true;buttons();
   const call=async (name,args)=>{
     if(!valid(target))throw Error('公众号已切换');
     const reply=await host.templateCall(name,{connection_id:target.connection_id,...args});
     if(!valid(target))throw Error('公众号已切换');
     if(reply.isError||!reply.structuredContent)throw Error(reply.structuredContent?.error||'未取得结果，请查原请求');
     return reply.structuredContent;
   };
   const invoke=(action,args={})=>call(tool,{action,...args});
   try{await task(invoke,target,call);}
   catch(error){if(valid(target))note(copy(error.message));}
   finally{if(start===epoch){busy=false;buttons();}}
 }
 function status(value){
   if(value.error_code!==undefined){
     const code=value.error_code;
     if([48001,48002,48004,50001,88000].includes(code))return copy('本号暂无此权限（微信 {0}）',code);
     if([40001,40014,41001,42001].includes(code))return copy('本号凭据无效或已过期（微信 {0}）',code);
     if([45009,45011].includes(code))return copy('微信限制了本次请求（{0}）',code);
     return copy('微信返回 {0}',code);
   }
   return copy({OBSERVED:'已读回',ACCEPTED:'微信已受理，等待平台结果',PREVIEW_ACCEPTED:'微信已受理预览',UNKNOWN:'结果未知，保留原请求',
     SOURCE_CHANGED:'草稿已变化，请重新读取并确认',
     MEDIA_READY:'已上传',COMPLETED:'已完成'}[value.state]||value.state);
 }
 function resultButton(label,action){
   const b=make('button');b.type='button';OAUI.set(b,label);b.onclick=action;return b;
 }
 function clearPage(name){
   delete pages[name];
   el(name+'Prev').hidden=el(name+'Next').hidden=true;
 }
 function pager(name,fetchPage){
   for(const [step,direction] of [['Prev',-1],['Next',1]]){
     el(name+step).onclick=()=>{
       const page=pages[name];
       if(!page)return;
       const offset=direction<0?Math.max(0,page.offset-pageSize):page.next;
       if(offset!==null)void fetchPage(offset,page.query);
     };
   }
 }
 function commitPage(name,value,offset,query){
   const size=value.items?.length||0, total=value.total_count;
   const confirmed=Number.isSafeInteger(total)&&total>=0;
   const next=Object.hasOwn(value,'next_offset')?value.next_offset:
     size&&(confirmed?offset+size<total:size===pageSize)?offset+size:null;
   pages[name]={offset,query,next};
   el(name+'Prev').hidden=offset===0;
   el(name+'Next').hidden=next===null;
   note(size===0?copy('当前页没有可读内容'):[status(value),
     copy('第 {0}–{1} 条',offset+1,offset+size)]);
 }
 function tab(name){
   active=name;
   for(const t of section.querySelectorAll('[data-wx-pane]')){
     const id=t.dataset.wxPane,shown=id===active;
     t.setAttribute('aria-selected',String(shown));
     el(id.charAt(0).toUpperCase()+id.slice(1)).hidden=!shown;
   }
 }
 for(const t of section.querySelectorAll('[data-wx-pane]'))t.onclick=()=>{
   tab(t.dataset.wxPane);
   if(active==='reads'&&account)void run(readAuto);
   if(active==='operations'&&account)void readLedger();
   if(active==='admin')paintGrants(host.templateTarget());
   if(active==='publish'&&!publishSelection()&&account&&localStorage.getItem(publishContext({connection_id:account})))
     void checkPublication(false);
 };
 el('MaterialCount').onclick=()=>run(async call=>{
   const result=await call('material_counts'),c=result.counts||{};
   note(result.error_code!==undefined?status(result):[status(result),
     copy('图片 {0} · 语音 {1} · 视频 {2} · 图文 {3}',c.image_count??'—',c.voice_count??'—',c.video_count??'—',c.news_count??'—')]);
 });
 async function materialBlob(value,read){
   const parts=[],limit=10*1024*1024;
   const decode=src=>Uint8Array.from(atob(src),x=>x.charCodeAt(0));
   if(!Number.isSafeInteger(value.bytes)||value.bytes<1||value.bytes>limit)throw Error('素材大小无法核对');
   if(value.base64)parts.push(decode(value.base64));
   else{
     let offset=0;
     while(offset<value.bytes){
       const result=await read('material_bytes',{read_handle:value.read_handle,offset});
       const bytes=decode(result.base64),next=offset+bytes.length;
       if(result.offset!==offset||!bytes.length||next>value.bytes||
         result.next_offset!==(next===value.bytes?null:next)||result.sha256!==value.sha256||result.bytes!==value.bytes)
         throw Error('素材分段校验失败，请重新读取');
       parts.push(bytes);offset=next;
     }
   }
   const blob=new Blob(parts,{type:value.mime_type});
   if(blob.size!==value.bytes)throw Error('素材大小无法核对');
   if(crypto.subtle){
     const sum=new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()));
     if(Array.from(sum,b=>b.toString(16).padStart(2,'0')).join('')!==value.sha256)throw Error('素材摘要不匹配');
   }
   return blob;
 }
 async function showMaterial(value,read){
   const view=el('MediaView'),generation=epoch;
   let media,blob;
   if(value.mime_type&&(value.base64||value.read_handle)){
     media=make(value.mime_type.startsWith('image/')?'img':value.mime_type.startsWith('audio/')?'audio':'video');
     blob=await materialBlob(value,read);
   }else if(value.details){
     media=make('p');
     const description=value.details.title||value.details.description;
     if(description)OAUI.raw(media,description);else OAUI.set(media,'微信已返回素材信息');
   }
   if(generation!==epoch)return;
   if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
   view.replaceChildren();
   if(blob){
     objectURL=URL.createObjectURL(blob);
     media.src=objectURL;media.controls=true;media.style.maxWidth='100%';
     if(media.tagName==='IMG')OAUI.attr(media,'alt','微信素材原件');
   }
   if(media)view.append(media);
   note(status(value));
 }
 const materials=(offset,mediaType)=>run(async call=>{
   const result=await call('list_materials',{media_type:mediaType,offset,count:pageSize});
   if(el('MediaType').value!==mediaType)return;
   if(result.error_code!==undefined){note(status(result));return;}
   const box=el('MaterialRows');box.replaceChildren();
   for(const asset of result.items||[]){
     const row=make('li');row.textContent=asset.name||asset.media_id;
     if(asset.media_id)row.append(' ',resultButton('查看',()=>run(async read=>{
       await showMaterial(await read('material_details',{media_id:asset.media_id}),read);
     })));
     box.append(row);
   }
   commitPage('Material',result,offset,mediaType);
 });
 pager('Material',materials);el('MaterialList').onclick=()=>materials(0,el('MediaType').value);
 function syncMedia(){
   el('VideoFields').hidden=el('MediaType').value!=='video'||el('MediaLife').value!=='permanent';
 }
 el('MediaType').onchange=()=>{
   clearPage('Material');el('MaterialRows').replaceChildren();el('MediaView').replaceChildren();
   if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
   syncMedia();
 };
 el('MediaLife').onchange=syncMedia;
 el('Upload').onclick=()=>run(async (call,target)=>{
   const file=el('File').files[0],type=el('MediaType').value,lifetime=el('MediaLife').value;
   if(!file||!file.size||file.size>700*1024||type==='news')throw Error('请选择 700 KB 以内的本地图片、语音或视频');
   const bytes=new Uint8Array(await file.arrayBuffer());let text='';
   for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));
   const req=crypto.randomUUID();localStorage.setItem(key(target,'media'),req);
   const result=await call('upload_media',{request_key:req,media_type:type,lifetime,mime_type:file.type,base64:btoa(text),
     ...(type==='video'&&lifetime==='permanent'?{video_description:{title:el('VideoTitle').value,introduction:el('VideoDescription').value}}:{})});
   note([status(result),copy('素材回执 {0}',result.operation_handle)]);
   if(result.state==='MEDIA_READY'&&lifetime==='temporary'){
     const handle={operation_handle:result.operation_handle};
     const preview=(title,action)=>resultButton(title,()=>run(async read=>showMaterial(await read(action,handle),read)));
     const buttons=el('MaterialRows');const row=make('li');
     row.append(preview('查看此临时素材','temporary_details'));
     if(type==='voice')row.append(' ',preview('读取高清语音','high_quality_voice'));
     buttons.prepend(row);
   }
 });
 function articleLink(row){
   try{
     const url=new URL(row.url);
     return ['http:','https:'].includes(url.protocol)&&url.host==='mp.weixin.qq.com'&&
       !url.username&&!url.password&&(url.pathname==='/s'||url.pathname.startsWith('/s/'))?
       url.href.replace(/^http:/,'https:'):null;
   }catch(_){return null;}
 }
 function plainArticle(html){
   const inert=make('template');inert.innerHTML=html;
   for(const node of inert.content.querySelectorAll('script,style,template'))node.remove();
   for(const node of inert.content.querySelectorAll('br,p,section,li,h1,h2,h3,blockquote,div'))
     node.after(document.createTextNode('\n'));
   return inert.content.textContent.trim();
 }
 const published=offset=>run(async call=>{
   const value=await call('list_published',{offset,count:pageSize});
   if(value.error_code!==undefined){note(status(value));return;}
   const list=el('PublishedRows');list.replaceChildren();el('PublishedBody').replaceChildren();
   for(const group of value.items||[]){
     (group.content?.news_item||[]).forEach((row,i)=>{
       const item=make('li');
       if(row.title)OAUI.raw(item,row.title);else OAUI.set(item,'已发表作品');
       item.append(' ',resultButton('读全文',()=>run(async read=>{
         const parts=[];let cursor=0,sha=null;
         while(cursor!==null){
           const result=await read('read_published',{article_id:group.article_id,index:i+1,content_offset:cursor,
             ...(sha?{content_sha256:sha}:{})});
           if(result.error_code!==undefined){note(status(result));return;}
           const next=result.next_content_offset;
           if(typeof result.content!=='string'||!/^([a-f0-9]{64})$/.test(result.content_sha256)||
              (sha&&sha!==result.content_sha256)||
              (next!==null&&(!Number.isSafeInteger(next)||next<=cursor||next>2097152)))
             throw Error('正文读取期间已变化，请重新打开');
           sha=result.content_sha256;parts.push(result.content);cursor=next;
         }
         el('PublishedBody').textContent=plainArticle(parts.join(''));note(copy('已读回正文'));
       })));
       const url=articleLink(row);
       if(url)item.append(' ',resultButton('打开原文',()=>void host.openLink(url).catch(()=>note(copy('当前宿主无法打开链接')))));
       list.append(item);
     });
   }
   commitPage('Published',value,offset,null);
 });
 pager('Published',published);el('PublishedList').onclick=()=>published(0);
 el('MenuRead').onclick=()=>run(async call=>{
   const value=await call('read_menu'),list=el('MenuRows');
   if(value.error_code!==undefined){note(status(value));return;}
   const menuItem=menu=>{
     const item=make('li');item.textContent=menu.name;
     if(menu.children?.length){
       const child=make('ul');child.append(...menu.children.map(menuItem));item.append(child);
     }
     return item;
   };
   list.replaceChildren(...(value.items||[]).map(menuItem));
   note(value.enabled?status(value):copy('本号菜单未开启'));
 });
 const txt=(key,...values)=>OAUI.format(key,values);
 const cstYesterday=new Date(Date.now()+8*3600000-86400000).toISOString().slice(0,10);
 el('ArticleDay').value=el('ArticleDay').max=cstYesterday;
 const queryComment=()=>({msg_data_id:el('CommentId').value.trim(),index:Number(el('CommentIndex').value)-1});
 const validComment=q=>/^[1-9][0-9]{0,18}$/.test(q.msg_data_id)&&Number.isInteger(q.index)&&q.index>=0&&q.index<8;
 const sameComment=(a,b)=>a?.msg_data_id===b.msg_data_id&&a?.index===b.index;
 function renderAuto(){
   el('AutoStart').hidden=!autoStatus||autoStatus.enabled||!validComment(queryComment());
   el('AutoStop').hidden=!autoStatus?.enabled;
   const states={OFF:'未启用',ACTIVE:'已启用',IDLE:'已启用，等待新留言',
     PERMISSION_STOPPED:'权限已失效，自动回复已停止',AUTHORIZATION_CHANGED:'授权已变更，请重新核对',
     MANUAL_REVIEW:'有留言留待人工处理',COMPLETED:'上次自动回复已完成',
     WECHAT_AUTO_CODEX_UNAVAILABLE:'Codex 暂不可用，当前留言等待处理',
     UNKNOWN:'上次发送结果未知，已保留原记录'};
   el('AutoStatus').textContent=autoStatus?
     txt('本号自动回复：{0}',txt(states[autoStatus.status]||autoStatus.status)):'';
   if(autoStatus?.enabled&&autoStatus.target)
     el('AutoStatus').append(' · ',txt('文章数据 ID {0}，第 {1} 篇',autoStatus.target.msg_data_id,autoStatus.target.index+1));
 }
 async function readAuto(call){
   autoStatus=await call('comment_auto_status');renderAuto();
 }
 el('AutoCheck').onclick=()=>run(readAuto);
 el('AutoStart').onclick=()=>run(async call=>{
   const target=queryComment();
   if(!validComment(target)||!autoStatus||autoStatus.enabled)return;
   if(!window.confirm(txt('启用后，Codex 会回复当前公众号此篇文章的新留言。是否继续？')))return;
   const value=await call('comment_auto_enable',{target,expected_revision:autoStatus.revision,confirm:true});
   if(value.error_code!==undefined){note(status(value));return;}
   autoStatus=value;renderAuto();
 });
 el('AutoStop').onclick=()=>run(async call=>{
   if(!autoStatus?.enabled)return;
   autoStatus=await call('comment_auto_disable',{expected_revision:autoStatus.revision,confirm:true});
   renderAuto();
 });
 const metrics={read_user:'阅读人数',share_user:'分享人数',like_user:'点赞人数',zaikan_user:'爱心赞人数',
   comment_count:'留言数',collection_user:'收藏人数',praise_money:'赞赏金额',read_subscribe_user:'读后关注',
   read_finish_rate:'读完率',read_delivery_rate:'阅读送达率',read_avg_activetime:'平均阅读时长'};
 function metricAmount(key,value){
   if(key==='praise_money')return ledgerMoney(value);
   if(key.endsWith('_rate'))return (value*100).toFixed(1)+'%';
   if(key==='read_avg_activetime')return txt('{0} 分钟',value.toFixed(1));
   return value;
 }
 el('ArticleRead').onclick=()=>run(async call=>{
   const day=el('ArticleDay').value;
   if(!day||!el('ArticleDay').validity.valid)throw Error('请选择可用的发表日期');
   const value=await call('article_stats',{begin_date:day,end_date:day});
   if(el('ArticleDay').value!==day)return;
   if(value.error_code!==undefined){note(status(value));return;}
   articleRows=value.items||[];
   const hint=make('option');hint.value='';OAUI.set(hint,'选择文章');
   el('Article').replaceChildren(hint,...articleRows.map((row,i)=>{
     const entry=make('option');entry.value=String(i);
     entry.textContent=row.title||txt('第 {0} 篇',row.index+1);
     return entry;
   }));
   el('ArticleMetrics').textContent=value.delayed?txt('微信统计有延迟'):
     articleRows.length?'':txt('当天没有读到本号文章');
 });
 el('ArticleDay').onchange=()=>{articleRows=[];el('Article').replaceChildren();el('ArticleMetrics').textContent='';};
 el('Article').onchange=()=>{
   const row=el('Article').value===''?null:articleRows[Number(el('Article').value)];
   el('ArticleMetrics').textContent='';
   if(!row)return;
   el('CommentId').value=row.msg_data_id;el('CommentIndex').value=String(row.index+1);
   const latest=row.latest;
   el('ArticleMetrics').textContent=latest?[txt('累计截至 {0}',latest.stat_date),
     ...Object.entries(metrics).filter(([k])=>Object.hasOwn(latest.metrics,k)).map(([k,label])=>
       txt(label)+' '+metricAmount(k,latest.metrics[k])),
     ...(latest.read_sources?.length?[txt('阅读来源')+' '+latest.read_sources.map(source=>
       source.scene+' '+source.read_user).join(' / ')]:[])].join(' · '):
       txt('微信尚无这篇文章的统计快照');
   comments(0,queryComment());
 };
 async function renderComments(call,offset,query){
   if(!validComment(query))throw Error('请填写本号群发图文数据 ID 和篇次');
   const value=await call('list_comments',{...query,offset,count:pageSize});
   if(!sameComment(query,queryComment()))return;
   if(value.error_code!==undefined){note(status(value));return;}
   const items=(value.items||[]).map(comment=>{
     const item=make('li'),actions=make('div');actions.className='actions';
     const source=articleRows.find(row=>sameComment(row,query))?.url;
     if(source)actions.append(resultButton('记为选题',()=>{
       tab('operations');el('LedgerKind').value='idea';
       void run(async (read,target)=>{
         paintLedger(await read('ops_list',ledgerQuery()));
         const catalog=await availableProjects();
         if(valid(target))await editLedger({title:comment.content.slice(0,120),article_url:source,
           comment_ref:query.msg_data_id+':'+query.index+':'+comment.id},catalog);
       });
     }));
     item.textContent=comment.content;
     if(comment.reply){const reply=make('blockquote');reply.textContent=comment.reply;item.append(reply);}
     const request=(action,payload={})=>run(async requestCall=>{
       if(!sameComment(query,queryComment()))return;
       const result=await requestCall(action,{...query,comment_id:comment.id,request_key:crypto.randomUUID(),
         confirm:true,...(action==='comment_take_over'?{}:{observed_offset:offset}),...payload});
       if(result.error_code!==undefined||result.state==='UNKNOWN'){note(status(result));return;}
       await renderComments(requestCall,offset,query);
       note(copy(result.state==='TAKEN_OVER'?'该留言已改由人工处理':'已回查本条留言'));
     });
     if(comment.comment_type===0||comment.comment_type===1){
       const featured=comment.comment_type===1;
       actions.append(resultButton(featured?'取消精选':'精选',()=>
         request(featured?'unfeature_comment':'feature_comment')));
     }
     if(!comment.reply){
       const editor=make('textarea'),replyActions=make('div');
       editor.rows=2;editor.maxLength=600;editor.setAttribute('aria-label',txt('回复内容'));
       replyActions.hidden=true;replyActions.append(editor,resultButton('发送回复',()=>{
         const content=editor.value.trim();
         if(content)request('reply_comment',{content});
       }));
       actions.append(resultButton('回复',()=>{replyActions.hidden=!replyActions.hidden;if(!replyActions.hidden)editor.focus();}),
         resultButton('人工接管',()=>request('comment_take_over')));
       item.append(actions,replyActions);
     }else item.append(actions);
     return item;
   });
   el('CommentRows').replaceChildren(...items);
   commitPage('Comment',value,offset,query);
   renderAuto();
 }
 const comments=(offset,query)=>run(call=>renderComments(call,offset,query));
 const ledgerFields={
   work:{title:'作品标题',project_ref:'项目编号',work_ref:'作品编号',version_ref:'版本编号',
         source_ref:'源稿或素材引用',draft_ref:'本号草稿引用',article_url:'微信文章链接'},
   idea:{title:'选题标题',work_ref:'作品编号',article_url:'微信文章链接',comment_ref:'原留言编号',notes:'笔记'},
   schedule:{title:'日历事项',work_ref:'作品编号',date:'计划日期',channel:'栏目',audience:'受众或标签',notes:'笔记'},
   rights:{title:'可售作品',work_ref:'作品编号',version_ref:'版本编号',rights_basis:'权利依据',
           license_scope:'授权范围',expires_on:'授权到期日',offer_url:'作品或询价页面'},
   deal:{title:'商务事项',work_ref:'作品编号',date:'跟进日期',stage:'当前进度',
         external_ref:'询盘或订单引用',amount_cents:'金额（元）',notes:'笔记'},
   money:{title:'对账事项',work_ref:'作品编号',date:'发生日期',entry:'流水类型',source:'收入或成本来源',
          external_ref:'账单行编号',amount_cents:'金额（元）',notes:'账单出处与说明'}
 };
 const ledgerRequired={
   work:['title','project_ref','work_ref','version_ref'],idea:['title','article_url','comment_ref'],
   schedule:['title','date','channel'],rights:['title','work_ref','version_ref','rights_basis','license_scope'],
   deal:['title','date','stage'],money:['title','date','entry','source','external_ref','amount_cents']
 };
 const ledgerLabels={
   stage:{inquiry:'询盘',quoted:'已报价',delivery:'履约',invoice:'待回款',paid:'已回款',closed:'已结束'},
   entry:{revenue:'确认收入',settlement:'已结算',received:'已到账',refund:'退款',cost:'直接成本'},
   source:{advertising:'流量主广告',praise:'赞赏',affiliate:'返佣',paid_content:'付费内容',
     brand:'品牌合作',licensing:'作品授权',production:'制作',other:'其他'}
 };
 function ledgerMoney(cents){return (cents/100).toLocaleString(undefined,{style:'currency',currency:'CNY'});}
 function ledgerLabel(field,value){
   return field==='amount_cents'?ledgerMoney(value):ledgerLabels[field]?.[value]?txt(ledgerLabels[field][value]):value;
 }
 async function editLedger(row={},catalog){
   const kind=el('LedgerKind').value;
   ledgerEdit=row.id||null;
   const form=el('LedgerFields');
   form.replaceChildren(...Object.entries(ledgerFields[kind]).map(([key,label])=>{
     const line=make('label'),options=ledgerLabels[key],field=make(options?'select':key==='notes'?'textarea':'input');
     OAUI.set(line,label);field.dataset.ledgerField=key;
     field.required=ledgerRequired[kind].includes(key);field.maxLength=key==='notes'||key.endsWith('_url')?1024:280;
     if(options) for(const [value,text] of Object.entries(options)){
       const option=make('option');option.value=value;OAUI.set(option,text);field.append(option);
     }
     if(key==='date'||key==='expires_on')field.type='date';
     if(key==='amount_cents'){field.type='number';field.min='0';field.max='10000000000';field.step='0.01';}
     if(Object.hasOwn(row,key))field.value=key==='amount_cents'?row[key]/100:row[key];
     line.append(' ',field);return line;
   }));
   const project=el('LedgerProject'),selector=el('LedgerProjectRow');
   selector.hidden=!['idea','work','rights'].includes(kind)||!catalog?.projects?.length;
   el('IdeaToSources').hidden=kind!=='idea';
   if(!selector.hidden){
     const option=make('option');option.value='';OAUI.set(option,'选择现有项目');
     project.replaceChildren(option,...catalog.projects.map(row=>{
       const item=make('option');item.value=row.id;item.textContent=row.name||row.title||row.id;return item;
     }));
     const ref=form.querySelector('[data-ledger-field="project_ref"]');
     project.value=ref?.value||'';
     project.onchange=()=>{if(ref&&project.value)ref.value=project.value;};
   }
   el('LedgerEditor').hidden=false;form.querySelector('input,select,textarea')?.focus();
 }
 function paintLedger(value){
   ledger=value;
   el('LedgerMore').hidden=value.next_offset===null;
   const rows=el('LedgerRows'),totals=el('LedgerTotals');
   rows.replaceChildren(...value.items.map(row=>{
     const item=make('li'),title=make('strong'),details=make('p');
     title.textContent=row.title;
     details.textContent=Object.keys(ledgerFields[row.kind]).filter(k=>k!=='title'&&Object.hasOwn(row,k))
       .map(k=>txt(ledgerFields[row.kind][k])+' '+ledgerLabel(k,row[k])).join(' · ');
     item.append(title,details,resultButton('编辑记录',()=>run(async (_read,target)=>{
       const catalog=await availableProjects();
       if(valid(target))await editLedger(row,catalog);
     })));return item;
   }));
   totals.replaceChildren();
   if(!value.record_count){const empty=make('p');OAUI.set(empty,'本号没有这类记录');totals.append(empty);}
   el('LedgerImport').hidden=el('LedgerKind').value!=='money';
   if(el('LedgerImport').hidden)return;
   for(const [days,window] of Object.entries(value.accounting)){
     const item=make('p');
     item.textContent=window.record_count?[
       txt('近 {0} 天 · 已录入 {1} 笔',days,window.record_count),
       ...Object.entries(window.entries_cents).map(([type,amount])=>txt(ledgerLabels.entry[type])+' '+ledgerMoney(amount)),
       txt('贡献（收入扣退款和直接成本）')+' '+ledgerMoney(window.contribution_cents),
       txt('未分配作品的收入')+' '+ledgerMoney(window.unassigned_revenue_cents)
     ].join(' · '):txt('近 {0} 天暂无录入账单',days);
     totals.append(item);
   }
 }
 function ledgerQuery(offset=0){
   const work_ref=el('LedgerFilter').value.trim();
   return {kind:el('LedgerKind').value,offset,...(work_ref?{work_ref}:{})};
 }
 const readLedger=(offset=0)=>run(async call=>paintLedger(await call('ops_list',ledgerQuery(offset))));
 async function availableProjects(call){
   try{return await call('wce.ui.projects.action',{operation:'CATALOG',arguments:{}});}
   catch(_){return null;}
 }
 el('CalendarAll').onclick=()=>run(async (read,target)=>{
   const accounts=host.templateConnections();
   const values=await Promise.allSettled(accounts.map(async candidate=>{
     const result=await host.templateCall(tool,{action:'ops_list',kind:'schedule',connection_id:candidate.connection_id});
     if(result.isError||result.structuredContent?.state!=='OBSERVED')throw Error('CALENDAR_UNAVAILABLE');
     return {name:candidate.name,...result.structuredContent};
   }));
   if(!valid(target))return;
   const all=values.flatMap((value,index)=>value.status==='fulfilled'?
      value.value.items.map(row=>({...row,account:accounts[index].name})):
      [{account:accounts[index].name,title:txt('本号日历暂不可读'),date:''}]);
   all.sort((a,b)=>a.date.localeCompare(b.date));
   for(const [i,value] of values.entries())if(value.status==='fulfilled'&&value.value.next_offset!==null)
     all.push({account:accounts[i].name,title:txt('另有历史记录，请切到本号翻页'),date:''});
   el('CalendarRows').replaceChildren(...all.map(item=>{
     const li=make('li');li.textContent=[item.date,item.account,item.title].filter(Boolean).join(' · ');return li;
   }));
   if(!all.length){const empty=make('li');OAUI.set(empty,'工作区没有已登记日历事项');el('CalendarRows').append(empty);}
 });
 el('IdeaToSources').onclick=()=>run(async (_read,target)=>{
   const project=el('LedgerProject').value;
   const url=el('LedgerFields').querySelector('[data-ledger-field="article_url"]')?.value.trim();
   const title=el('LedgerFields').querySelector('[data-ledger-field="title"]')?.value.trim();
   if(!project||!url||!title){note(copy('请先选择项目并填写选题和原文链接'));return;}
   const result=await host.templateCall('own.sources.library',{action:'add',project_id:project,
     connection_id:target.connection_id,url,origin:'user',name:title.slice(0,160),kind:'website'});
   if(!valid(target))return;
   if(result.isError)throw Error(result.structuredContent?.error||'未能加入本号信源库');
   note(copy('原文已加入本号信源库'));
 });
 el('LedgerRead').onclick=()=>readLedger();
 el('LedgerKind').onchange=()=>{el('LedgerEditor').hidden=true;readLedger();};
 el('LedgerMore').onclick=()=>readLedger(ledger?.next_offset||0);
 el('LedgerNew').onclick=()=>run(async (read,target)=>{
   if(!ledger)paintLedger(await read('ops_list',ledgerQuery()));
   const catalog=await availableProjects();
   if(valid(target))await editLedger({},catalog);
 });
 el('LedgerImportSave').onclick=()=>run(async call=>{
   const file=el('LedgerStatement').files?.[0];
   if(!ledger||!file)return;
   if(file.size>120000)throw Error('导入文件超过大小限制');
   const statement_csv=await file.text();
   const result=await call('ops_import_money',{expected_revision:ledger.revision,statement_csv});
   el('LedgerStatement').value='';
   paintLedger(await call('ops_list',ledgerQuery()));
   note(copy('已导入 {0} 笔，跳过 {1} 笔重复记录',result.added,result.repeated));
 });
 el('LedgerCancel').onclick=()=>{el('LedgerEditor').hidden=true;el('LedgerNew').focus();};
 el('LedgerSave').onclick=()=>run(async call=>{
   if(!ledger)return;
   const record={kind:el('LedgerKind').value};
   for(const field of el('LedgerFields').querySelectorAll('[data-ledger-field]')){
     const text=field.value.trim();
     if(!field.reportValidity())return;
     if(text)record[field.dataset.ledgerField]=field.dataset.ledgerField==='amount_cents'?Math.round(Number(text)*100):text;
   }
   await call('ops_put',{expected_revision:ledger.revision,record,...(ledgerEdit?{record_id:ledgerEdit}:{})});
   el('LedgerEditor').hidden=true;
   paintLedger(await call('ops_list',ledgerQuery()));
   note(copy('记录已保存并读回'));
 });
 pager('Comment',comments);
 el('CommentRead').onclick=()=>comments(0,queryComment());
 for(const name of ['CommentId','CommentIndex'])el(name).oninput=()=>{
   el('Article').value='';el('ArticleMetrics').textContent='';
   clearPage('Comment');el('CommentRows').replaceChildren();renderAuto();
 };
 const grantRows=[
   [1,'读者私信与关键词','需要接收微信消息事件'],
   [2,'关注者标签','从本号读取和创建标签'],
   [3,'渠道二维码','资格以微信服务号接口返回为准'],
   [4,'报名、会员与课程网页','需要配置本号网页授权域名'],
   [5,'微信小店','另核商家账号及小店经营资格'],
   [6,'多人客服与人工接管','须另核微信客服消息路由'],
   [7,'逐篇统计、留言与通知','群发需要确认目标号及受众'],
   [8,'微信卡券','资格以本号卡券控制台为准'],
   [11,'素材与草稿','素材与草稿按公众号隔离'],
   [13,'微信门店','须在微信核实本号门店资格'],
   [15,'自定义菜单','提供本号菜单预览及显式更新']
 ];
 function paintGrants(target){
   const info=target?.component_grant||target?.official_profile;
   const grants=info?.state==='ACTIVE'&&Array.isArray(info.permissions)?info.permissions:null;
   el('GrantRows').replaceChildren(...grantRows.map(([id,label,detail])=>{
     const row=make('li'),title=make('strong');
     OAUI.set(title,'{0}（{1}）',copy(label),id);
     row.append(title,OAUI.label(' · {0} · {1}',
       copy(grants?(grants.includes(id)?'本号已授予':'本号尚未授予'):'本号权限待核对'),copy(detail)));
     return row;
   }));
 }
 function readTags(call){
   return call('list_tags').then(value=>{
     if(value.error_code!==undefined){note(status(value));return;}
     el('Tags').replaceChildren(...value.items.map(tag=>{
       const li=make('li');li.textContent=tag.name+' · '+tag.id;
       if(Number.isSafeInteger(tag.count))li.append(' · '+tag.count);
       const delivery=resultButton('用于按标签通知',()=>{
         el('Mode').value='tag';el('Recipient').value=String(tag.id);syncDelivery();tab('message');
       });
       li.append(' ',delivery);return li;
     }));
   });
 }
 el('TagsRead').onclick=()=>run(readTags);
 el('TagMake').onclick=()=>run(async call=>{
   const name=el('TagName').value.trim();
   if(!name)return;
   const value=await call('create_tag',{name,request_key:crypto.randomUUID(),confirm:true});
   note(status(value));if(value.state==='COMPLETED'){el('TagName').value='';await readTags(call);}
 });
 function menuNames(rows){
   return rows.map(n=>[n.name,...(n.sub_button||[]).map(child=>child.name)].join(' / ')).join(' · ');
 }
 for(const key of ['MenuName','MenuLink'])el(key).oninput=()=>{
   menuPlan=null;el('MenuApply').hidden=true;el('MenuPlanRows').replaceChildren();
 };
 el('MenuPlan').onclick=()=>run(async call=>{
   const name=el('MenuName').value.trim(),url=el('MenuLink').value.trim();
   if(!name||!el('MenuLink').reportValidity()||!/^https:\/\//.test(url))return;
   const buttons=[{name,type:'view',url}];
   const value=await call('plan_menu',{buttons});
   if(value.error_code!==undefined){note(status(value));return;}
   menuPlan={buttons,expected_menu_sha256:value.expected_menu_sha256};
   OAUI.set(el('MenuPlanRows'),'原菜单 {0} · 新菜单 {1}',menuNames(value.current)||copy('无'),menuNames(value.proposed));
   el('MenuApply').hidden=false;
 });
 el('MenuApply').onclick=()=>run(async call=>{
   if(!menuPlan||!window.confirm(txt('确认替换当前公众号菜单？')))return;
   const value=await call('update_menu',{...menuPlan,confirm:true,request_key:crypto.randomUUID()});
   menuPlan=null;el('MenuApply').hidden=true;note(status(value));
   if(value.state==='COMPLETED')OAUI.set(el('MenuPlanRows'),'公众号菜单已更新，请读回微信当前菜单。');
 });
 el('ChannelMake').onclick=()=>run(async call=>{
   const scene=el('ChannelScene').value.trim(),days=Number(el('ChannelDays').value);
   if(!/^[a-zA-Z0-9_.:-]{1,64}$/.test(scene)||!Number.isInteger(days)||days<1||days>30)
     throw Error('请输入渠道标识和有效天数');
   const value=await call('create_channel_qr',{scene,expires_in:days*86400,
     request_key:crypto.randomUUID(),confirm:true});
   note(status(value));
   el('ChannelResult').replaceChildren();
   if(value.state==='COMPLETED'&&/^https:\/\/mp\.weixin\.qq\.com\/cgi-bin\/showqrcode\?ticket=/.test(value.result.url)){
     el('ChannelResult').append(resultButton('查看微信渠道码',()=>void host.openLink(value.result.url)));
   }
 });

 function syncDelivery(){
   const mode=el('Mode').value,kind=el('MessageType').value;
   const preview=mode==='preview'||mode==='openid-preview';
   OAUI.set(el('RecipientText'),mode==='preview'?'微信号':mode==='openid-preview'?'OpenID':mode==='tag'?'标签 ID':'');
   el('RecipientLabel').hidden=mode==='all'||mode==='openids';
   el('OpenIDLabel').hidden=mode!=='openids';
   OAUI.set(el('Deliver'),preview?'发送预览':'提交群发');
   el('DraftPicker').hidden=kind!=='mpnews';
   el('DraftNotice').hidden=kind!=='mpnews'||preview||!el('Draft').value;
   el('MessageLabel').parentElement.hidden=kind==='mpnews'&&!!el('Draft').value;
   OAUI.set(el('MessageLabel'),kind==='text'?'消息正文':kind==='music'?'微信音乐素材 ID':
       kind==='wxcard'?'卡券 ID':kind==='image'&&!preview?'图片素材回执（每行一个）':'本号素材回执');
 }
 el('LoadDrafts').onclick=()=>run(async (read,target,call)=>{
   const value=await call('own.drafts.inventory',{});
   const hint=make('option');hint.value='';OAUI.set(hint,'选择草稿或输入已有图文素材回执');
   el('Draft').replaceChildren(hint);
   for(const group of value.groups||[]){
     if(group.article_types?.some(type=>type!=='news'))continue;
     const option=make('option');option.textContent=group.titles.join('、');
     option.value=JSON.stringify({inventory_handle:value.inventory_handle,index:group.index,
       expected_projection_sha256:group.projection_sha256,article_count:group.article_count});
     el('Draft').append(option);
   }
   el('Confirm').checked=false;syncDelivery();
   note(copy(el('Draft').options.length>1?'已读取本页图文草稿':'本页没有可选图文草稿'));
 });
 el('Mode').onchange=el('MessageType').onchange=el('Draft').onchange=()=>{el('Confirm').checked=false;syncDelivery();};
 for(const control of ['Recipient','OpenIDs','MessageBody'])el(control).oninput=()=>{el('Confirm').checked=false;};
 el('Deliver').onclick=()=>run(async (call,target)=>{
   if(!el('Confirm').checked)throw Error('请先核对接收范围');
   const mode=el('Mode').value,kind=el('MessageType').value,text=el('MessageBody').value.trim();
   const preview=mode==='preview'||mode==='openid-preview', action=preview?'preview_message':'send_broadcast';
   if(kind==='music'&&!preview)throw Error('官方群发文档未给出音乐消息对象');
   const input=el('Recipient').value.trim();
   if(mode!=='all'&&mode!=='openids'&&!input)throw Error('请填写接收者或标签 ID');
   if(mode==='tag'&&!/^\d+$/.test(input))throw Error('标签 ID 必须是数字');
   const openids=mode==='openids'?el('OpenIDs').value.trim().split(/\s+/):null;
   if(openids&&(openids.length<2||openids.length>10000||new Set(openids).size!==openids.length))
     throw Error('请填写 2–10,000 个不同的本号 OpenID');
   const draft=kind==='mpnews'&&el('Draft').value;
   const message=kind==='text'?{kind,text}:kind==='music'?{kind,music_media_id:text}:kind==='wxcard'?{kind,card:{card_id:text}}:
     kind==='image'&&!preview?{kind,image_handles:text.split(/\s+/)}:
     {kind,media:draft?{draft_selection:JSON.parse(draft)}:{media_handle:text}};
   const previous=localStorage.getItem(key(target,'delivery'));
   if(previous){
     let row;
     try{row=await call('status_by_key',{request_key:previous});}
     catch(error){if(error.message!=='CURRENT_DRAFT_OPERATION_NOT_FOUND')throw error;}
     if(row?.state==='UNKNOWN'||row?.state==='PREPARED')throw Error('请先查回原请求，结果未知时不重复发送');
   }
   const req=crypto.randomUUID();localStorage.setItem(key(target,'delivery'),req);el('Confirm').checked=false;
   const result=await call(action,{request_key:req,confirm:true,message,...(mode==='preview'?
     {recipient:{wechat_name:input}}:mode==='openid-preview'?{recipient:{openid:input}}:
     {campaign:req,audience:mode==='all'?{all_followers:true}:mode==='openids'?{openids}:{tag_id:Number(input)}})});
   note(status(result));
   if(result.state==='ACCEPTED')el('OpenIDs').value='';
 });
 el('MessageStatus').onclick=()=>run(async (call,target)=>{
   const request_key=localStorage.getItem(key(target,'delivery'));
   if(!request_key)throw Error('本号暂无预览或群发请求');
   const result=await call('status_by_key',{request_key});
   if(result.kind==='send_broadcast'&&result.state==='ACCEPTED'){
     const final=await call('broadcast_status',{operation_handle:result.operation_handle});
     const outcome={SEND_SUCCESS:'发送成功',SENDING:'发送中',SEND_FAIL:'发送失败',DELETE:'已撤下'}[final.status];
     note(outcome?copy(outcome):status(final));return;
   }
   note(status(result));
 });
 syncDelivery();
 return {refresh,show(name){
   const view={media:'media',readers:'admin',channels:'admin',comments:'reads',operations:'operations',publish:'publish'}[name];
   const control=view&&section.querySelector('[data-wx-pane="'+view+'"]');
   if(control&&active!==view)control.click();
   if(name==='media'&&!el('MaterialRows').childElementCount&&account&&!busy)el('MaterialList').click();
   if(name==='readers')el('TagsRead').closest('details').open=true;
   if(name==='channels')el('ChannelMake').closest('details').open=true;
 }};
};
'''
