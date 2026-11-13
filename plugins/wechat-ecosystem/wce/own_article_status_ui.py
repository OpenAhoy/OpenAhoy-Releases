"""Article/data panels for the existing management App. Local reads only."""
HTML='''<section class="card" id="articlePanel" hidden style="margin-top:24px">
<div class="card-head"><div><h2>文章记录</h2><p>本机保存与发表记录，不代表当前微信在线库存；删除和后台修改情况未查询。</p></div></div>
<div class="actions"><select id="articleAccount" aria-label="文章记录公众号"></select>
<select id="articleView" aria-label="记录类型"><option value="drafts">保存记录</option><option value="publications">发表记录</option></select>
<button id="articleLoad" disabled>读取本机记录</button></div>
<p id="articleStatus" class="help" role="status">选择公众号后读取已有记录，不执行微信请求。</p>
<p id="articleObserved" class="help"></p><div id="articleRows"></div><button id="articleMore" hidden>继续读取</button>
</section>
<section class="card" id="dataPanel" hidden style="margin-top:24px">
<div class="card-head"><div><h2>数据</h2><p>本机操作记录与微信官方统计分别显示。</p></div></div>
<div class="actions"><select id="dataAccount" aria-label="数据公众号"></select><button id="dataLoad" disabled>读取本机数据</button></div>
<p id="dataStatus" class="help" role="status">尚未读取。</p><p id="dataObserved" class="help"></p>
<div id="localMetrics"></div><h3 style="margin-top:20px">微信官方统计</h3>
<p class="help">暂无已接入的官方统计缓存，未请求粉丝、阅读或分享接口；未获取不表示 0。</p><div id="officialMetrics"></div>
</section>'''

JS=r'''
const WCEArticleStatus=(()=>{
  const PROFILE='LOCAL_ARTICLE_JOURNAL_V1',READ='wce.settings.articles.read';
  const words={SUCCEEDED:'已保存 · 本机记录',RESULT_UNKNOWN:'保存结果未知',READY:'待发表',
    SUBMIT_CLAIMED:'已登记发表请求，结果待确认',UNKNOWN:'发表结果未知',ACCEPTED:'已受理',PROCESSING:'处理中',
    PUBLISHED:'已发表 · 已有回执',PUBLISHED_URLS_INCOMPLETE:'已发表 · 链接未完整获取',PLATFORM_FAILED:'平台处理失败',
    DENIED:'权限拒绝',PLATFORM_REJECTED:'平台拒绝',TASK_CONFLICT:'原任务需核对',PLATFORM_DELETED:'平台回执：已删除',
    PLATFORM_BLOCKED:'平台回执：已屏蔽',PREPARED:'已准备',HOLD:'待核对',CANCELLED_BEFORE_SUBMIT:'提交前已取消'};
  const record=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
  const time=v=>typeof v==='number'&&Number.isFinite(v)&&v>0?new Date(v*1000).toLocaleString('zh-CN'):'未获取';
  const metric=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('zh-CN'):'未获取';
  function url(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&u.hostname==='mp.weixin.qq.com'&&!u.username&&!u.password&&(!u.port||u.protocol==='http:'&&u.port==='80'||u.protocol==='https:'&&u.port==='443')&&/^\/s\/[A-Za-z0-9_-]+$/.test(u.pathname)&&(!u.hash||u.hash==='#rd');}catch(_){return false;}}
  function mount(bridge,resize=()=>{}){
    const $=id=>document.getElementById(id);let ready=false,busy=false,selected='',generation=0,nextBefore=null,loadedView=null;
    const controls=()=>{
      for(const id of ['articleLoad','dataLoad'])$(id).disabled=!ready||!selected||busy;
      $('articleMore').disabled=!ready||!selected||busy;};
    const reset=()=>{generation++;busy=false;nextBefore=null;loadedView=null;
      $('articleRows').replaceChildren();$('localMetrics').replaceChildren();$('officialMetrics').replaceChildren();
      $('articleMore').hidden=true;$('articleObserved').textContent='';$('dataObserved').textContent='';
      $('articleStatus').textContent='尚未读取当前公众号的本机记录。';$('dataStatus').textContent='尚未读取当前公众号的数据。';controls();};
    function choose(cid){if(cid===selected)return;selected=cid;$('articleAccount').value=cid;$('dataAccount').value=cid;reset();}
    async function tool(args){
      const response=await bridge(READ,args);const value=response?.structuredContent;
      if(!record(response)||response.isError||!record(value)||value.profile!==PROFILE||
          value.connection_id!==args.connection_id||value.view!==args.view||value.provenance!=='LOCAL_VALIDATED_JOURNAL'||
          value.remote_inventory_state!=='NOT_QUERIED'||typeof value.observed_at!=='number'||!Number.isFinite(value.observed_at))
        throw new Error('ARTICLE_STATUS_RESPONSE_UNAVAILABLE');
      if(value.state==='UNAVAILABLE')throw new Error(typeof value.error_code==='string'&&/^[A-Z0-9_]+$/.test(value.error_code)?value.error_code:'ARTICLE_STATUS_UNAVAILABLE');
      return value;
    }
    function row(item){
      if(!record(item)||typeof item.id!=='string'||typeof item.state!=='string'||!Array.isArray(item.articles)||
          item.articles.some(a=>!record(a)||!Number.isInteger(a.index)||a.index<1||typeof a.title!=='string'||
            !(a.url===null||typeof a.url==='string'&&['PUBLISHED','PUBLISHED_URLS_INCOMPLETE'].includes(item.state)&&url(a.url))))throw new Error('ARTICLE_STATUS_RESPONSE_UNAVAILABLE');
      const card=document.createElement('div');card.className='account';
      const content=document.createElement('div');content.className='account-body';
      const badge=document.createElement('p');badge.className='status';badge.textContent=(words[item.state]||'状态待核对')+(Number.isInteger(item.source_order)?' · 原列表第 '+item.source_order+' 组':'');content.append(badge);
      if(!item.articles.length){const missing=document.createElement('p');missing.className='account-title';missing.textContent='文章标题未获取';content.append(missing);}
      for(const article of item.articles){
        const title=document.createElement('p');title.className='account-title';title.textContent=article.index+'. '+article.title;content.append(title);
        if(article.url){const link=document.createElement('a');link.href=article.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='查看已有发表链接';content.append(link);}
      }
      const details=document.createElement('p');details.className='help';
      details.textContent='本机记录时间：'+time(item.last_recorded_at)+'；发表日期：'+time(item.published_at)+
        (item.readback_state===null?'':'；正文严格读回：'+(item.readback_state==='MATCHED'?'匹配':'未验证'));
      content.append(details);
      if(item.error_reason||Number.isInteger(item.error_code)){const problem=document.createElement('p');problem.className='help';
        const causes={TRANSPORT_UNDETERMINED:'响应未能确认',RESPONSE_UNDETERMINED:'响应未能确认',NOT_RECORDED:'诊断信息未获取',PLATFORM_ERROR:'平台返回错误',NON_SUCCESS_HTTP:'请求未成功',SUBMIT_RESULT_UNDETERMINED:'发表请求结果待确认',QUERY_RESULT_UNDETERMINED:'原任务查询结果待确认'};
        problem.textContent='最近记录原因：'+(causes[item.error_reason]||'请按已有状态核对')+(Number.isInteger(item.error_code)?'；平台错误码 '+item.error_code:'');content.append(problem);}
      card.append(content);return card;
    }
    async function articles(more=false){
      if(!ready||busy||!selected)return;
      const view=$('articleView').value;if(!['drafts','publications'].includes(view))return;
      if(more&&(!nextBefore||loadedView!==view))return;
      const epoch=++generation,cid=selected,args={connection_id:cid,view,...(more?{before:nextBefore}:{})};busy=true;controls();
      $('articleStatus').textContent='正在读取本机记录，不请求微信。';
      try{
        const value=await tool(args);if(epoch!==generation||cid!==selected)return;
        if(!['AVAILABLE','NOT_ACQUIRED'].includes(value.state)||!Array.isArray(value.items)||
            !(value.next_before===null||typeof value.next_before==='string'))throw new Error('ARTICLE_STATUS_RESPONSE_UNAVAILABLE');
        const cards=value.items.map(row);
        if(!more)$('articleRows').replaceChildren();$('articleRows').append(...cards);
        nextBefore=value.next_before;loadedView=view;$('articleMore').hidden=nextBefore===null;
        $('articleObserved').textContent='本机读取时间：'+time(value.observed_at)+'；来源为已有操作记录，未查询在线库存。';
        $('articleStatus').textContent=value.state==='NOT_ACQUIRED'?'未获取该号的本机发表记录；没有初始化或查询微信。':
          value.items.length?'已读取本机记录。'+(nextBefore?'可继续读取下一页。':'已读完本次可得记录。'):'本机已验证记录中暂无此类条目；不代表微信在线库存为空。';resize();
      }catch(error){if(epoch===generation)$('articleStatus').textContent='本次读取未完成，已读取内容与时间保留：'+error.message;}
      finally{if(epoch===generation){busy=false;controls();}}
    }
    function renderMetrics(target,items){const nodes=[];for(const [label,value]of items){const p=document.createElement('p');p.className='help';p.textContent=label+'：'+metric(value);nodes.push(p);}target.replaceChildren(...nodes);}
    async function data(){
      if(!ready||busy||!selected)return;
      const epoch=++generation,cid=selected;busy=true;controls();$('dataStatus').textContent='正在读取本机记录中的数据。';
      try{
        const value=await tool({connection_id:cid,view:'summary'});if(epoch!==generation||cid!==selected)return;
        if(value.state!=='AVAILABLE'||!record(value.metrics)||!Array.isArray(value.sources))throw new Error('ARTICLE_STATUS_RESPONSE_UNAVAILABLE');
        const m=value.metrics;
        const fields=['local_saved_groups','local_unknown_saves','local_readback_matched','local_published_groups','official_followers','official_reads','official_shares'];
        if(fields.some(k=>!(m[k]===null||Number.isInteger(m[k])&&m[k]>=0))||m.official_metrics_state!=='NOT_ACQUIRED'||
            ['official_followers','official_reads','official_shares'].some(k=>m[k]!==null))throw new Error('ARTICLE_STATUS_RESPONSE_UNAVAILABLE');
        renderMetrics($('localMetrics'),[['本机成功保存记录',m.local_saved_groups],['本机结果未知的保存记录',m.local_unknown_saves],
          ['本机严格读回匹配记录',m.local_readback_matched],['本机已获取的已发表记录',m.local_published_groups]]);
        renderMetrics($('officialMetrics'),[['粉丝数',m.official_followers],['阅读量',m.official_reads],['分享量',m.official_shares]]);
        $('dataObserved').textContent='本机读取时间：'+time(value.observed_at)+'；最近可得本机记录时间：'+time(value.last_recorded_at);
        $('dataStatus').textContent=value.sources.some(s=>s.state!=='AVAILABLE')?'本机记录覆盖不完整；未获取来源和官方指标不补 0。':'已读取本机记录；微信官方统计未获取。';resize();
      }catch(error){if(epoch===generation)$('dataStatus').textContent='本次读取未完成，已读取内容与时间保留：'+error.message;}
      finally{if(epoch===generation){busy=false;controls();}}
    }
    for(const id of ['articleAccount','dataAccount'])$(id).addEventListener('change',()=>choose($(id).value));
    $('articleView').addEventListener('change',()=>{reset();});
    $('articleLoad').addEventListener('click',()=>articles(false));$('articleMore').addEventListener('click',()=>articles(true));$('dataLoad').addEventListener('click',data);
    return {articles,data,choose,setReady(value){ready=value===true;controls();},
      accounts(accounts,names){
        const ids=accounts.map(a=>a.connection_id);for(const id of ['articleAccount','dataAccount']){
          const options=[];for(const cid of ids){const option=document.createElement('option');option.value=cid;option.textContent=names.get(cid)||'公众号';options.push(option);}$(id).replaceChildren(...options);
        }
        const next=ids.includes(selected)?selected:ids[0]||'';
        if(next!==selected)choose(next);else{$('articleAccount').value=selected;$('dataAccount').value=selected;controls();}
      }};
  }
  return {mount};
})();
'''
