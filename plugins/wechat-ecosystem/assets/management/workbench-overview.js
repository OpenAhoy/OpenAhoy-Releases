function JiuseraOverview({readActivity,openActivity}){
  const byId=id=>document.getElementById(id);
  const feature=byId('wbHomeFeature');
  const slides=[...feature.querySelectorAll('.jho-hero-copy')];
  const activity=byId('wbHomeActivityRows'),status=byId('wbHomeActivityState');
  const retry=byId('wbHomeActivityRetry'),accountsStatus=byId('wbHomeConnections');
  const identity=byId('wbHomeIdentity'),profile=document.querySelector('#wbProfile .wb-entry-card>p');
  const id=/^[A-Za-z0-9_][A-Za-z0-9_-]{0,95}$/;
  const canvasFields=['project_id','work_id','scene_id','shot_id','revision_id'];
  function validEvent(item){
    if(!item||!Number.isFinite(item.time)||item.time<=0||item.time>Date.now()/1000||
       !['title','project_name'].every(key=>typeof item[key]==='string'&&item[key]))return false;
    if(item.type==='video-request')
      return typeof item.work_name==='string'&&canvasFields.every(key=>/^[a-f0-9]{32}$/.test(item.scope?.[key]||''));
    return ['generated','archived'].includes(item.type)&&
      ['project','song','version'].every(key=>id.test(item[key]||''))&&typeof item.version_name==='string';
  }
  let slide=0,visible=false,pending=false,snapshot=null,failure=false;
  const setFeature=direction=>{
    slide=(slide+direction+slides.length)%slides.length;
    feature.dataset.feature=slides[slide].dataset.feature;
    slides.forEach((item,index)=>item.hidden=index!==slide);
  };
  byId('wbHomeFeaturePrevious').onclick=()=>setFeature(-1);
  byId('wbHomeFeatureNext').onclick=()=>setFeature(1);

  function renderActivity(){
    const items=snapshot?.items||[];
    const date=new Intl.DateTimeFormat(document.documentElement.lang,{
      month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Shanghai',hourCycle:'h23'
    });
    activity.replaceChildren(...items.map(item=>{
      const row=document.createElement('li'),button=document.createElement('button');
      const mark=document.createElement('span'),text=document.createElement('span');
      const label=document.createElement('strong'),source=document.createElement('small');
      const time=document.createElement('time'),arrow=document.createElement('span');
      button.type='button';
      mark.className='jho-activity-mark';
      mark.setAttribute('aria-hidden','true');
      text.className='jho-activity-copy';
      label.textContent=item.title;
      const video=item.type==='video-request';
      const labelKey=video?'画布视频任务 · {0} · {1}':item.type==='archived'?'Studio 入库 · {0} · {1}':'Studio 生成 · {0} · {1}';
      source.textContent=OAUI.format(labelKey,[item.project_name,video?item.work_name:item.version_name]);
      time.dateTime=new Date(item.time*1000).toISOString();
      time.textContent=date.format(item.time*1000);
      time.title=OAUI.format('{0}（北京时间）',[time.textContent]);
      arrow.textContent='›';arrow.setAttribute('aria-hidden','true');
      text.append(label,source);
      button.append(mark,text,time,arrow);
      button.onclick=()=>openActivity(item);
      row.append(button);
      return row;
    }));
    renderActivityState();
  }
  function renderActivityState(){
    const key=pending?(snapshot?.items.length?'':'正在读取工作区记录…'):
      failure?(snapshot?.items.length?'工作区记录读取失败，保留上次内容。':'暂时无法读取工作区记录。'):
      snapshot?.partial?'部分工作区记录暂不可读。':
      snapshot?.items.length?'':'暂无可定位的带时间活动记录。';
    OAUI.set(status,key);
    status.hidden=!key;
    retry.hidden=!failure&&!snapshot?.partial;
    retry.disabled=pending;
  }
  async function refresh(){
    if(pending)return;
    pending=true;
    renderActivityState();
    try{
      const value=await readActivity();
      if(!Array.isArray(value?.items)||typeof value.partial!=='boolean')throw Error('HOME_ACTIVITY_INVALID');
      snapshot={partial:value.partial,items:value.items.filter(validEvent).slice(0,6)};
      failure=false;
      renderActivity();
    }catch(_){failure=true;}
    finally{pending=false;renderActivityState();}
  }
  retry.onclick=refresh;
  function renderIdentity(){if(profile)OAUI.raw(identity,profile.textContent.trim());}
  OAUI.onChange(()=>{renderIdentity();if(snapshot)renderActivity();});
  return {
    show(on){
      if(on&&!visible){renderIdentity();void refresh();}
      visible=on;
    },
    accounts(count,failed){
      OAUI.set(accountsStatus,failed?(count===null?'平台账号暂不可读':'部分平台账号暂不可读 · 已读到 {0} 个账号'):
        count?'已绑定 {0} 个平台账号':'尚未绑定平台账号',count);
    }
  };
}
