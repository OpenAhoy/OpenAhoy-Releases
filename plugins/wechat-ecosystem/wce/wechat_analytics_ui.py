"""Account-scoped analytics in the main WeChat workspace."""

HTML = """
<section id="wechatAnalytics" aria-labelledby="wxStatsTitle" hidden>
 <header class="wx-stats-header">
  <div><h2 id="wxStatsTitle">数据监控</h2><p id="wxStatsAccount"></p></div>
  <div class="actions"><button type="button" id="wxStats7" aria-pressed="true">近 7 天</button>
  <button type="button" id="wxStats30" aria-pressed="false">近 30 天</button><button type="button" id="wxStatsRefresh">刷新数据</button></div>
 </header>
 <p id="wxStatsStatus" role="status" aria-live="polite"></p>
 <div id="wxStatsResult" hidden>
  <div id="wxStatsTotals" class="wx-stats-totals"></div>
  <div class="wx-stats-trends"><section><h3>关注趋势</h3><div id="wxStatsFans"></div></section>
  <section><h3>内容趋势</h3><div id="wxStatsContent"></div></section></div>
  <section class="wx-stats-articles"><h3>近期已发表文章</h3><p id="wxStatsArticleStatus"></p><div id="wxStatsArticles"></div></section>
 </div>
</section>
"""

STYLE = """
#wechatAnalytics[hidden],#wechatAnalytics [hidden]{display:none!important}
#wechatAnalytics{display:grid;flex:none;gap:10px;margin:12px 0 18px;min-width:0}
#wechatAnalytics h2,#wechatAnalytics h3,#wechatAnalytics p{margin:0}
#wechatAnalytics h2{font-size:18px}#wechatAnalytics h3{font-size:13px}
.wx-stats-header,.wx-stats-article-head{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
#wxStatsAccount,#wxStatsStatus,#wxStatsArticleStatus,#wechatAnalytics small{font-size:12px;color:var(--muted)}
#wxStatsStatus:empty,#wxStatsArticleStatus:empty{display:none}
#wechatAnalytics button[aria-pressed=true]{background:var(--tint);color:var(--accent)}
#wxStatsResult{display:grid;gap:8px}
.wx-stats-totals,.wx-stats-trends{display:grid;gap:8px}
.wx-stats-totals{grid-template-columns:repeat(4,minmax(0,1fr))}
.wx-stats-trends{grid-template-columns:repeat(2,minmax(0,1fr))}
.wx-stats-totals>div,.wx-stats-trends>section,.wx-stats-articles{border:1px solid var(--line);border-radius:10px;background:var(--surface);min-width:0;padding:9px 10px}
.wx-stats-totals strong{display:block;font-size:19px;font-variant-numeric:tabular-nums}
.wx-stats-totals span{color:var(--muted);font-size:12px}
.wx-stats-trends [data-chart]{height:62px;display:flex;gap:2px;align-items:end;margin:6px 0 3px}
.wx-stats-trends [data-chart]>span{display:flex;flex:1 1 0;min-width:0;height:100%;align-items:end;gap:1px}
.wx-stats-trends i{flex:1;border-radius:2px 2px 0 0;background:var(--accent);min-width:1px}
.wx-stats-trends i:nth-child(2){background:#bd677e}
.wx-stats-trends i:nth-child(3){background:#4b9e8c}
.wx-stats-trends table{width:100%;border-collapse:collapse;text-align:end;font-size:11px;margin-top:5px}
.wx-stats-trends td,.wx-stats-trends th{padding:2px 3px}
.wx-stats-trends th:first-child,.wx-stats-trends td:first-child{text-align:start}
.wx-stats-trends details{margin-top:5px}
.wx-stats-trends summary,#wxStatsArticles summary{font-size:12px;cursor:pointer}
.wx-stats-articles>p{margin-top:5px!important}
#wxStatsArticles>article{border-top:1px solid var(--line);margin-top:6px;padding-top:6px;min-width:0}
.wx-stats-article-head strong{overflow-wrap:anywhere}
#wxStatsArticles details div{display:flex;gap:4px 12px;flex-wrap:wrap;font-size:12px;padding-top:5px}
@media(min-width:800px) and (min-height:600px){
 .oa-management #nativeWorkspace:has(#wechatAnalytics:not([hidden])){overflow-y:auto}
 .oa-management #nativeWorkspace:has(#wechatAnalytics:not([hidden])) #settingsPanel{flex:none;min-height:520px}
}
@media(max-width:650px){.wx-stats-totals{grid-template-columns:repeat(2,minmax(0,1fr))}.wx-stats-trends{grid-template-columns:minmax(0,1fr)}}
"""

SCRIPT = r'''
const OAWechatAnalytics=(invoke,openLink)=>{
 const $=id=>document.getElementById(id), root=$('wechatAnalytics'),out=$('wxStatsResult');
 const f=(value)=>Number.isFinite(value)?new Intl.NumberFormat().format(value):'—';
 const states={PERMISSION:'接口权限不足',DELAYED:'微信数据尚未就绪',UNAVAILABLE:'暂时无法读取',EMPTY:'暂无统计记录'};
 const accounts=new Map();
 let target='',binding='',days=7,epoch=0,busy=false;
 const element=(tag,text)=>{const el=document.createElement(tag);if(text)OAUI.set(el,text);return el;};
 function stat(parent,label,value,note){
   const box=element('div'),caption=element('span',label),text=element('strong');
   OAUI.raw(text,f(value));box.append(caption,text);
   if(note){const help=element('small');OAUI.raw(help,note);box.append(help);}
   parent.append(box);
 }
 const metrics={
  new_user:'新增关注',cancel_user:'取消关注',read_user:'阅读人数',share_user:'分享人数',
  collection_user:'收藏人数',like_user:'拇指赞人数',zaikan_user:'爱心赞人数',comment_count:'留言条数',
  read_subscribe_user:'读后关注',read_finish_rate:'阅读完成率',read_avg_activetime:'平均阅读时长'
 };
 function labelsFor(keys){return keys.map(key=>OAUI.message(metrics[key]));}
 function chart(node,rows,keys){
   const graph=element('div');graph.dataset.chart='';graph.setAttribute('aria-hidden','true');
   const maximum=Math.max(1,...rows.flatMap(row=>keys.map(key=>Number.isFinite(row[key])?row[key]:0)));
   for(const row of rows){
     const series=element('span');series.title=[row.date,...keys.map(key=>OAUI.format(metrics[key])+': '+f(row[key]))].join(' · ');
     for(const key of keys){
       const bar=element('i');
       bar.style.height=Number.isFinite(row[key])?(row[key]===0?'2px':Math.max(2,Math.round(row[key]/maximum*100))+'%'):'0';
       series.append(bar);
     }
     graph.append(series);
   }
   const legend=element('small');OAUI.set(legend,'{0}',labelsFor(keys));
   const details=element('details'),summary=element('summary','逐日数据'),table=element('table'),
    head=element('thead'),columns=element('tr'),body=element('tbody');
   columns.append(element('th','日期'),...keys.map(key=>element('th',metrics[key])));head.append(columns);
   for(const row of rows){
     const line=element('tr'),date=element('th');date.scope='row';OAUI.raw(date,row.date);
     line.append(date);
     for(const key of keys){const data=element('td');OAUI.raw(data,f(row[key]));line.append(data);}
     body.append(line);
   }
   table.append(head,body);details.append(summary,table);node.replaceChildren(graph,legend,details);
 }
 function statusLine(value){
   const feeds={getusersummary:'关注变化',getusercumulate:'累计关注',getbizsummary:'内容趋势',getarticletotaldetail:'单篇文章'};
   const lines=[];
   for(const [kind,feed] of Object.entries(value.status)){
     for(const state of feed.states||[]){
       if(states[state])lines.push(OAUI.message('{0} · {1}',OAUI.message(feeds[kind]),OAUI.message(states[state])));
     }
   }
   const base=value.latest_data?OAUI.message('统计截至 {0}（北京时间）',value.latest_data):OAUI.message('暂无可展示的统计日');
   const checked=Number.isFinite(value.read_at)?new Intl.DateTimeFormat(undefined,{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Shanghai'}).format(new Date(value.read_at*1000)):'';
   if(checked)lines.unshift(OAUI.message('刷新于 {0}（北京时间）',checked));
   OAUI.set($('wxStatsStatus'),'{0}',[base,...lines]);
 }
 function render(value){
   out.hidden=false;statusLine(value);
   const rows=value.timeline,known=[...rows].reverse();
   const latest=key=>known.find(row=>Number.isFinite(row[key]));
   const fanTotal=latest('cumulate_user'),read=latest('read_user'),shared=latest('share_user');
   const coverage=rows.filter(row=>Number.isFinite(row.new_user)&&Number.isFinite(row.cancel_user));
   const net=coverage.length?coverage.reduce((sum,row)=>sum+row.new_user-row.cancel_user,0):null;
   const totals=$('wxStatsTotals');totals.replaceChildren();
   stat(totals,'累计关注',fanTotal?.cumulate_user,fanTotal?.date);
   const partial=coverage.length>0&&coverage.length<rows.length;
   stat(totals,partial?'已报告日期净增':'期间净增',net,
        partial?coverage.length+' / '+rows.length:'');
   stat(totals,'最近日阅读',read?.read_user,read?.date);
   stat(totals,'最近日分享',shared?.share_user,shared?.date);
   chart($('wxStatsFans'),rows,['new_user','cancel_user']);
   chart($('wxStatsContent'),rows,['read_user','share_user','collection_user']);
   OAUI.set($('wxStatsArticleStatus'),value.articles.length?'最近 {0} 个发表日 · 单篇为累计数据':'本次查询暂无单篇记录',value.article_dates);
   const articles=$('wxStatsArticles');articles.replaceChildren();
   for(const item of value.articles){
     const card=element('article'),head=element('div'),title=element('strong'),counts=element('small');
     head.className='wx-stats-article-head';OAUI.raw(title,item.title);head.append(title);
     if(item.url){
       try{
         const url=new URL(item.url);
         if(url.origin==='https://mp.weixin.qq.com'&&(/^\/s(?:\/|$)/).test(url.pathname)){
           const link=element('button','打开文章');link.type='button';
           link.onclick=event=>{if(event.isTrusted)void openLink(url.href).catch(()=>OAUI.set($('wxStatsArticleStatus'),'宿主未能打开官方页面。'));};
           head.append(link);
         }
       }catch(_){}
     }
     const row=element('p');OAUI.set(counts,'{0}',[item.published,...['read_user','share_user','collection_user']
        .filter(key=>Number.isFinite(item[key])).map(key=>OAUI.message('{0} {1}',OAUI.message(metrics[key]),f(item[key])))]);
     row.append(counts);card.append(head,row);
     const more=element('details'),label=element('summary','单篇数据与来源'),details=element('div');
     function fact(key,value){const part=element('span');OAUI.set(part,'{0} · {1}',OAUI.message(key),value);details.append(part);}
     if(item.stat_date)fact('累计统计日',item.stat_date);
     for(const key of ['like_user','zaikan_user','comment_count','read_subscribe_user','read_finish_rate','read_avg_activetime']){
       if(!Number.isFinite(item[key]))continue;
       const text=key==='read_finish_rate'?new Intl.NumberFormat(undefined,{style:'percent',maximumFractionDigits:1}).format(item[key]):
          key==='read_avg_activetime'?OAUI.message('{0} 分钟',Number(item[key].toFixed(2))):f(item[key]);
       fact(metrics[key],text);
     }
     for(const source of item.sources||[]){const part=element('span');OAUI.raw(part,source.name+' · '+f(source.value));details.append(part);}
     more.append(label,details);if(details.childElementCount)card.append(more);
     articles.append(card);
   }
 }
 function reset(){
   out.hidden=true;
   for(const id of ['wxStatsTotals','wxStatsFans','wxStatsContent','wxStatsArticles'])$(id).replaceChildren();
 }
 async function read(refresh=false){
   if(!target)return;
   const id=target, generation=binding, period=days,ticket=++epoch;
   const current=()=>epoch===ticket&&target===id&&binding===generation&&days===period;
   const key=JSON.stringify([id,generation,period]);
   const saved=accounts.get(key);
   if(saved)render(saved);
   else reset();
   busy=true;$('wxStatsRefresh').disabled=true;
   if(!saved)OAUI.set($('wxStatsStatus'),'正在读取本号统计…');
   try{
     const value=await invoke({connection_id:id,days:period,refresh});
     if(!current())return;
     if(value?.connection_id!==id||value?.days!==period||!Array.isArray(value.timeline)||
        !Array.isArray(value.articles)||!value.status)throw new Error('WECHAT_ANALYTICS_UNAVAILABLE');
     accounts.set(key,value);render(value);
   }catch(_){
     if(current()){
       if(saved)OAUI.set($('wxStatsStatus'),'刷新失败，保留本号上次的统计。');
       else OAUI.set($('wxStatsStatus'),'暂时无法读取本号统计。');
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
   root.hidden=!id;
   if(id===target&&identity===binding){if(id)OAUI.raw($('wxStatsAccount'),label);return;}
   const prior=target, previousBinding=binding;
   target=id;binding=identity;++epoch;busy=false;reset();OAUI.set($('wxStatsStatus'),'');
   if(prior===id&&previousBinding!==identity)accounts.clear();
   OAUI.raw($('wxStatsAccount'),label||'');
   if(id)void read();
 }};
};
'''
