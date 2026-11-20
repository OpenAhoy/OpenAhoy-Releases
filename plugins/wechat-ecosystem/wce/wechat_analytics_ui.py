"""Account-scoped analytics in the main WeChat workspace."""

HTML = """
<section id="wechatAnalytics" aria-labelledby="wechatMonitorTab" aria-describedby="wxStatsAccount" hidden>
 <header class="wx-stats-header">
  <div class="wx-stats-context"><span id="wxStatsAccount" class="wx-visually-hidden"></span><p id="wxStatsMeta"></p></div>
  <div class="wx-stats-controls">
   <div class="wx-stats-period" role="group" aria-label="统计范围">
    <button type="button" id="wxStats7" aria-pressed="true">近 7 天</button>
    <button type="button" id="wxStats30" aria-pressed="false">近 30 天</button>
   </div>
   <button type="button" id="wxStatsRefresh">刷新数据</button>
  </div>
 </header>
 <p id="wxStatsStatus" role="status" aria-live="polite"></p>
 <p id="wxStatsEmpty" class="empty">绑定并选择公众号后可查看统计。</p>
 <div id="wxStatsResult" hidden>
  <div id="wxStatsTotals" class="wx-stats-totals"></div>
  <div class="wx-stats-trends">
   <section aria-labelledby="wxStatsFansTitle"><h2 id="wxStatsFansTitle">关注趋势</h2><div id="wxStatsFans"></div></section>
   <section aria-labelledby="wxStatsContentTitle"><h2 id="wxStatsContentTitle">内容趋势</h2><div id="wxStatsContent"></div></section>
  </div>
  <section class="wx-stats-articles" aria-labelledby="wxStatsArticlesTitle">
   <header><h2 id="wxStatsArticlesTitle">近期已发表文章</h2><p id="wxStatsArticleStatus"></p></header>
   <div class="wx-article-grid wx-article-columns" aria-hidden="true" hidden>
    <span>文章</span><span>发表日</span><span>阅读</span><span>分享</span><span>收藏</span><span></span>
   </div>
   <div id="wxStatsArticles"></div>
  </section>
 </div>
</section>
"""

STYLE = """
#wechatAnalytics[hidden],#wechatAnalytics [hidden]{display:none!important}
#wechatAnalytics{
 display:flex;flex:1;flex-direction:column;gap:5px;min-width:0;min-height:0;
 width:100%;max-width:1240px;container:wechat-stats / inline-size;font-size:13px;line-height:1.4;
 --wx-series-1:light-dark(#566674,#a3b6c5);
 --wx-series-2:light-dark(#b25b78,#e397ac);
 --wx-series-3:light-dark(#448272,#7db8a4);
}
#wechatAnalytics :is(h2,p){margin:0}
#wechatAnalytics h2{font-size:15px;font-weight:650;line-height:1.35}
.wx-visually-hidden{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.wx-stats-header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:5px 12px}
.wx-stats-context{min-width:0;flex:1 1 310px}
.wx-stats-header,#wxStatsStatus{flex:none}
.wx-stats-controls{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.wx-stats-period{display:flex;align-items:center;gap:2px;padding:2px;border-radius:7px;background:var(--oa-fill)}
.oa-native #wechatAnalytics .wx-stats-period button{
 min-height:27px;padding:2px 8px;border-radius:5px;background:transparent;color:var(--muted);font-size:12px
}
.oa-native #wechatAnalytics .wx-stats-period button[aria-pressed=true]{
 background:var(--oa-selection);color:var(--oa-selected-ink);font-weight:600
}
.oa-native #wechatAnalytics #wxStatsRefresh{min-height:30px;padding:3px 9px;font-size:12px}
#wxStatsMeta,#wxStatsStatus,#wxStatsArticleStatus,#wechatAnalytics small{font-size:11.5px;color:var(--muted);overflow-wrap:anywhere}
#wxStatsStatus[data-state=notice]{padding:2px 6px;border-inline-start:2px solid var(--line)}
#wxStatsMeta:empty,#wxStatsStatus:empty,#wxStatsArticleStatus:empty{display:none}
#wxStatsResult{
 display:grid;align-content:start;gap:11px;min-width:0;min-height:0;overflow:auto;
 overscroll-behavior:contain;padding:2px 3px 8px
}
.wx-stats-totals{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:var(--soft);border-radius:9px}
.wx-stats-totals>div{padding:6px 12px;min-width:0}
.wx-stats-totals>div+div{border-inline-start:1px solid var(--line)}
.wx-stats-totals strong{display:block;font-size:18px;font-weight:650;font-variant-numeric:tabular-nums}
.wx-stats-totals span{font-size:12px;color:var(--muted)}
.wx-stats-totals strong[data-missing]{color:var(--muted)}
.wx-stats-totals small{display:block}
.wx-stats-trends{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.wx-stats-trends>section{min-width:0;padding:5px 5px 2px;border-block-start:1px solid var(--line)}
.wx-stats-plot{display:grid;grid-template-columns:minmax(20px,max-content) minmax(0,1fr);gap:2px 5px;margin-top:7px}
.wx-stats-scale{display:flex;flex-direction:column;justify-content:space-between;color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums;text-align:end}
.wx-stats-trends [data-chart]{
 height:48px;display:flex;gap:2px;align-items:end;min-width:0;
 border-block-end:1px solid var(--line);
 background:linear-gradient(var(--line),var(--line)) center / 100% 1px no-repeat
}
.wx-stats-trends [data-chart]>span{display:flex;flex:1 1 0;min-width:0;height:100%;align-items:end;justify-content:center;gap:1px}
.wx-stats-series{background:var(--wx-series-1)}
.wx-stats-series[data-series="1"]{background:var(--wx-series-2)}
.wx-stats-series[data-series="2"]{background:var(--wx-series-3)}
.wx-stats-trends [data-chart] i{flex:1 1 0;min-width:0;max-width:10px;border-radius:2px 2px 0 0}
.wx-stats-trends i[data-missing]{background:none}
.wx-stats-ticks{grid-column:2;display:flex;justify-content:space-between;gap:3px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.wx-stats-chart-footer{display:flex;flex-wrap:wrap;align-items:center;gap:2px 9px;margin-top:4px}
.wx-stats-legend{display:flex;flex-wrap:wrap;gap:2px 9px;font-size:11.5px;color:var(--muted)}
.wx-stats-legend>span{display:inline-flex;align-items:center;gap:4px}
.wx-stats-legend i{width:7px;height:7px;border-radius:2px}
.wx-stats-trends details{margin:2px 0 0;padding:0}
.wx-stats-trends summary{display:list-item;min-height:26px;padding:5px 1px;font-size:12px;cursor:pointer}
.wx-stats-trends table{width:100%;border-collapse:collapse;text-align:end;font-size:12px;font-variant-numeric:tabular-nums}
.wx-stats-trends :is(th,td){padding:3px 4px;border-block-end:1px solid var(--line);overflow-wrap:anywhere}
.wx-stats-trends :is(th,td):first-child{text-align:start}
.wx-stats-articles{border-block-start:1px solid var(--line)}
.wx-stats-articles>header{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:3px 10px;padding:7px 3px 4px}
.wx-article-grid{display:grid;grid-template-columns:minmax(0,1fr) 95px repeat(3,52px) 126px;gap:6px;align-items:center}
.wx-article-columns{background:var(--soft);border-radius:5px;padding:4px 6px;color:var(--muted);font-size:11.5px}
.wx-article-columns>span:nth-child(n+3):nth-child(-n+5){text-align:end}
#wxStatsArticles>article{min-width:0;border-block-end:1px solid var(--line)}
.wx-article-row{padding:3px 6px;min-height:38px}
.wx-article-row>strong{font-size:13px;font-weight:550;overflow-wrap:anywhere;min-width:0}
.wx-article-row>time{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.wx-article-metric{text-align:end;font-size:12px;font-variant-numeric:tabular-nums}
.wx-article-metric[data-missing]{color:var(--muted)}
.wx-article-metric-label{display:none}
.wx-article-actions{display:flex;gap:2px;justify-content:flex-end;min-width:0}
.oa-native #wechatAnalytics .wx-article-actions button{
 min-height:28px;min-width:0;padding:3px 6px;font-size:11.5px;background:transparent;color:var(--muted);
 text-decoration:underline;text-underline-offset:2px;white-space:nowrap
}
.oa-native #wechatAnalytics .wx-article-actions button:hover:not(:disabled){background:var(--oa-fill);color:var(--ink)}
.wx-article-facts{display:flex;gap:4px 14px;flex-wrap:wrap;padding:5px 8px 8px;font-size:12px;overflow-wrap:anywhere;background:var(--soft)}
@container wechat-stats (max-width:720px){
 .wx-article-columns{display:none}
 .wx-article-grid.wx-article-row{display:flex;flex-wrap:wrap;gap:2px 10px;padding:4px 3px}
 .wx-article-row>strong{flex:1 1 100%}
 .wx-article-metric-label{display:inline;color:var(--muted);font-size:11.5px}
 .wx-article-actions{margin-inline-start:auto}
}
@container wechat-stats (max-width:540px){
 .wx-stats-totals{grid-template-columns:repeat(2,minmax(0,1fr))}
 .wx-stats-totals>div:nth-child(3){border-inline-start:0}
 .wx-stats-totals>div:nth-child(n+3){border-block-start:1px solid var(--line)}
 .wx-stats-trends{grid-template-columns:minmax(0,1fr);gap:7px}
 .wx-stats-context{flex:1 1 100%}
 .wx-stats-context:has(#wxStatsMeta:empty){display:none}
}
"""

SCRIPT = r'''
const OAWechatAnalytics=(invoke,openLink)=>{
 const $=id=>document.getElementById(id),out=$('wxStatsResult');
 const f=(value)=>Number.isFinite(value)?new Intl.NumberFormat().format(value):'—';
 const states={PERMISSION:'接口权限不足',DELAYED:'微信数据尚未就绪',TIMEOUT:'微信接口响应超时',UNAVAILABLE:'暂时无法读取',EMPTY:'暂无统计记录'};
 const accounts=new Map();
 let target='',binding='',revision='',days=7,epoch=0,busy=false;
 const bindingErrors=new Set(['CONNECTION_DISCONNECTED','CONNECTION_NOT_BOUND','CONNECTION_POLICY_CHANGED',
   'CONNECTION_REGISTRY_CONFLICT','CONNECTION_NOT_COMMITTED','CONNECTION_COMMITTED_IDENTITY_CHANGED']);
 const element=(tag,text)=>{const el=document.createElement(tag);if(text)OAUI.set(el,text);return el;};
 function stat(parent,label,value,note){
   const box=element('div'),caption=element('span',label),text=element('strong');
   if(!Number.isFinite(value)){text.dataset.missing='';OAUI.attr(text,'aria-label','未报告');}
   OAUI.raw(text,f(value));box.append(caption,text);
   if(note){const help=element('small');OAUI.set(help,note.key,note.value);box.append(help);}
   parent.append(box);
 }
 const metrics={
  new_user:'新增关注',cancel_user:'取消关注',read_user:'阅读人数',share_user:'分享人数',
  collection_user:'收藏人数',like_user:'拇指赞人数',zaikan_user:'爱心赞人数',comment_count:'留言条数',
  read_subscribe_user:'读后关注',read_finish_rate:'阅读完成率',read_avg_activetime:'平均阅读时长'
 };
 function chart(node,rows,keys){
   const graph=element('div');graph.dataset.chart='';
   const maximum=Math.max(1,...rows.flatMap(row=>keys.map(key=>Number.isFinite(row[key])?row[key]:0)));
   const plot=element('div'),scale=element('div'),ticks=element('div');
   plot.className='wx-stats-plot';plot.setAttribute('aria-hidden','true');
   scale.className='wx-stats-scale';ticks.className='wx-stats-ticks';
   for(const number of [maximum,0]){const tick=element('span');OAUI.raw(tick,f(number));scale.append(tick);}
   for(const row of rows){
     const series=element('span');
     series.title=[row.date,...keys.map(key=>OAUI.format(metrics[key])+': '+f(row[key]))].join(' · ');
     keys.forEach((key,index)=>{
       const bar=element('i'),value=row[key];
       bar.className='wx-stats-series';bar.dataset.series=String(index);
       if(!Number.isFinite(value))bar.dataset.missing='';
       else if(value===0){bar.dataset.zero='';bar.style.height='2px';}
       else bar.style.height=Math.max(4,value/maximum*100)+'%';
       series.append(bar);
     });
     graph.append(series);
   }
   for(const index of new Set([0,Math.floor(rows.length/2),rows.length-1])){
     const date=rows[index]?.date;
     if(date){const tick=element('time');tick.dateTime=date;OAUI.raw(tick,date.slice(5));ticks.append(tick);}
   }
   plot.append(scale,graph,ticks);
   const caption=element('div'),legend=element('div');
   caption.className='wx-stats-chart-footer';legend.className='wx-stats-legend';
   keys.forEach((key,index)=>{
     const item=element('span'),swatch=element('i');
     swatch.className='wx-stats-series';swatch.dataset.series=String(index);swatch.setAttribute('aria-hidden','true');
     item.append(swatch,element('span',metrics[key]));legend.append(item);
   });
   caption.append(legend,element('small','基线短线为 0，留空为未报告'));
   const details=element('details'),summary=element('summary','逐日数据'),table=element('table'),
    head=element('thead'),columns=element('tr'),body=element('tbody');
   columns.append(element('th','日期'),...keys.map(key=>element('th',metrics[key])));head.append(columns);
   for(const row of rows){
     const line=element('tr'),date=element('th');date.scope='row';OAUI.raw(date,row.date);
     line.append(date);
     for(const key of keys){const data=element('td');OAUI.raw(data,f(row[key]));line.append(data);}
     body.append(line);
   }
   table.append(head,body);details.append(summary,table);node.replaceChildren(plot,caption,details);
 }
 function statusLine(value){
   const feeds={getusersummary:'关注变化',getusercumulate:'累计关注',getbizsummary:'内容趋势',getarticletotaldetail:'单篇文章'};
   const lines=[];
   for(const [kind,feed] of Object.entries(value.status)){
     const reported=feed.states||[];
     for(const state of reported){
       const label=state==='EMPTY'&&reported.includes('READY')?'部分日期未报告':states[state];
       if(label)lines.push(OAUI.message('{0} · {1}',OAUI.message(feeds[kind]),OAUI.message(label)));
     }
   }
   const checked=Number.isFinite(value.read_at)?new Intl.DateTimeFormat(undefined,{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Shanghai'}).format(new Date(value.read_at*1000)):'';
   const base=value.latest_data?OAUI.message('统计截至 {0}',value.latest_data):OAUI.message('暂无可展示的统计日');
   const meta=checked?[base,OAUI.message('更新 {0}',checked)]:[base];
   OAUI.set($('wxStatsMeta'),'{0}（北京时间）',meta);
   statsStatus(lines.length?'{0}':'',lines);
 }
 function statsStatus(key,...values){
   const status=$('wxStatsStatus');
   status.dataset.state=key?'notice':'';
   OAUI.set(status,key,...values);
 }
 function articleRow(item,index){
   const card=element('article'),row=element('div'),title=element('strong'),date=element('time');
   row.className='wx-article-grid wx-article-row';
   OAUI.raw(title,item.title);date.dateTime=item.published;OAUI.raw(date,item.published);row.append(title,date);
   for(const [key,label] of [['read_user','阅读'],['share_user','分享'],['collection_user','收藏']]){
     const cell=element('span'),labelNode=element('span',label),number=element('span');
     cell.className='wx-article-metric';cell.dataset.metric=key;labelNode.className='wx-article-metric-label';
     if(!Number.isFinite(item[key]))cell.dataset.missing='';
     OAUI.raw(number,f(item[key]));OAUI.attr(cell,'aria-label','{0} {1}',OAUI.message(metrics[key]),
          Number.isFinite(item[key])?f(item[key]):OAUI.message('未报告'));
     cell.append(labelNode,' ',number);row.append(cell);
   }
   const actions=element('div'),details=element('div');
   actions.className='wx-article-actions';details.className='wx-article-facts';
   function fact(key,value){const part=element('span');OAUI.set(part,'{0} · {1}',OAUI.message(key),value);details.append(part);}
   if(item.stat_date)fact('累计统计日',item.stat_date);
   for(const key of ['like_user','zaikan_user','comment_count','read_subscribe_user','read_finish_rate','read_avg_activetime']){
     if(!Number.isFinite(item[key]))continue;
     const text=key==='read_finish_rate'?new Intl.NumberFormat(undefined,{style:'percent',maximumFractionDigits:1}).format(item[key]):
        key==='read_avg_activetime'?OAUI.message('{0} 分钟',Number(item[key].toFixed(2))):f(item[key]);
     fact(metrics[key],text);
   }
   for(const source of item.sources||[]){const part=element('span');OAUI.raw(part,source.name+' · '+f(source.value));details.append(part);}
   if(details.childElementCount){
     const more=element('button','明细');more.type='button';
     details.id='wxArticleFacts-'+index;details.hidden=true;
     more.setAttribute('aria-controls',details.id);more.setAttribute('aria-expanded','false');
     OAUI.attr(more,'aria-label','{0}的单篇明细',item.title);
     more.onclick=()=>{details.hidden=!details.hidden;more.setAttribute('aria-expanded',String(!details.hidden));};
     actions.append(more);
   }
   if(item.url){
     try{
       const url=new URL(item.url);
       if(url.origin==='https://mp.weixin.qq.com'&&(/^\/s(?:\/|$)/).test(url.pathname)){
         const link=element('button','原文');link.type='button';
         OAUI.attr(link,'aria-label','打开原文：{0}',item.title);
         link.onclick=event=>{if(event.isTrusted)void openLink(url.href).catch(()=>OAUI.set($('wxStatsArticleStatus'),'宿主未能打开官方页面。'));};
         actions.append(link);
       }
     }catch(_){}
   }
   row.append(actions);card.append(row);
   if(details.childElementCount)card.append(details);
   return card;
 }
 function render(value){
   out.hidden=false;statusLine(value);
   const rows=value.timeline,known=[...rows].reverse();
   const latest=key=>known.find(row=>Number.isFinite(row[key]));
   const fanTotal=latest('cumulate_user'),read=latest('read_user'),shared=latest('share_user');
   const coverage=rows.filter(row=>Number.isFinite(row.new_user)&&Number.isFinite(row.cancel_user));
   const net=coverage.length?coverage.reduce((sum,row)=>sum+row.new_user-row.cancel_user,0):null;
   const totals=$('wxStatsTotals');totals.replaceChildren();
   const date=row=>row?.date&&row.date!==value.latest_data?{key:'{0}',value:row.date}:null;
   stat(totals,'累计关注',fanTotal?.cumulate_user,date(fanTotal));
   const partial=coverage.length>0&&coverage.length<rows.length;
   stat(totals,partial?'已报告日期净增':'期间净增',net,
        partial?{key:'已报告 {0} 天',value:coverage.length+' / '+rows.length}:null);
   stat(totals,'最近日阅读',read?.read_user,date(read));
   stat(totals,'最近日分享',shared?.share_user,date(shared));
   chart($('wxStatsFans'),rows,['new_user','cancel_user']);
   chart($('wxStatsContent'),rows,['read_user','share_user','collection_user']);
   OAUI.set($('wxStatsArticleStatus'),value.articles.length?'最近 {0} 个发表日 · 单篇为累计数据':'本次查询暂无单篇记录',value.article_dates);
   document.querySelector('#wechatAnalytics .wx-article-columns').hidden=!value.articles.length;
   $('wxStatsArticles').replaceChildren(...value.articles.map(articleRow));
 }
 function reset(){
   out.hidden=true;OAUI.set($('wxStatsMeta'),'');
   for(const id of ['wxStatsTotals','wxStatsFans','wxStatsContent','wxStatsArticles'])$(id).replaceChildren();
 }
 async function read(refresh=false){
   if(!target)return;
   const id=target, generation=binding, expected=revision,period=days,ticket=++epoch;
   const current=()=>epoch===ticket&&target===id&&binding===generation&&days===period;
   const key=JSON.stringify([id,generation,period]);
   const saved=accounts.get(key);
   if(saved)render(saved);
   else reset();
   busy=true;$('wxStatsRefresh').disabled=true;
   if(!saved)statsStatus('正在读取本号统计…');
   try{
     const value=await invoke({connection_id:id,days:period,refresh,
       ...(expected?{binding_revision:expected}:{})});
     if(!current())return;
     if(expected&&value?.binding_revision!==expected)throw new Error('CONNECTION_POLICY_CHANGED');
     if(value?.connection_id!==id||value?.days!==period||!Array.isArray(value.timeline)||
        !Array.isArray(value.articles)||!value.status)throw new Error('WECHAT_ANALYTICS_UNAVAILABLE');
     accounts.set(key,value);render(value);
   }catch(error){
     if(current()){
       if(bindingErrors.has(error.message)){
         for(const period of [7,30])accounts.delete(JSON.stringify([id,generation,period]));
         reset();statsStatus('账号绑定已变化，请刷新账号列表。');
       }else if(saved)statsStatus('刷新失败，保留本号上次的统计。');
       else statsStatus('暂时无法读取本号统计。');
     }
   }finally{if(current()){busy=false;$('wxStatsRefresh').disabled=false;}}
 }
 function setDays(next){
   if(!target||days===next)return;
   days=next;$('wxStats7').setAttribute('aria-pressed',String(days===7));$('wxStats30').setAttribute('aria-pressed',String(days===30));
   void read();
 }
 $('wxStats7').onclick=()=>setDays(7);$('wxStats30').onclick=()=>setDays(30);
 $('wxStatsRefresh').onclick=event=>{if(event.isTrusted&&!busy)void read(true);};
 return {target(row,label){
   const id=row?.connection_id||'';
   const identity=id?JSON.stringify([row.account_id,row.binding_revision]):'';
   $('wxStatsEmpty').hidden=!!id;
   $('wxStats7').disabled=$('wxStats30').disabled=!id;
   $('wxStatsRefresh').disabled=!id||busy;
   if(id===target&&identity===binding){if(id)OAUI.raw($('wxStatsAccount'),label);return;}
   const prior=target, previousBinding=binding;
   target=id;binding=identity;revision=id?row.binding_revision||'':'';++epoch;busy=false;reset();statsStatus('');
   if(prior===id&&previousBinding!==identity)accounts.clear();
   OAUI.raw($('wxStatsAccount'),label||'');
   if(id)void read();
 }};
};
'''
