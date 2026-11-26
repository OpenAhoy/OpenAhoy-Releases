"""Credential editor for VidMuse and the live catalog shared with the canvas."""
SCRIPT = r'''
function OAVidMuse(call,openLink,paintTile){
  const $=id=>document.getElementById('videoVidMuse'+id);
  const labels={CONNECTED:'VidMuse 已连接',CLI_MISSING:'尚未安装官方 VidMuse CLI',
    AUTH_REQUIRED:'请连接 VidMuse 账号',NO_MODEL:'当前 VidMuse 账号目录没有 MAGI-2',
    PARAMETERS_UNAVAILABLE:'目录暂未提供可核对的 MAGI-2 参数',
    CATALOG_UNAVAILABLE:'暂时无法读取 VidMuse 模型目录',
    CLI_UNAVAILABLE:'暂时无法连接 VidMuse',CLI_UNSAFE:'官方 VidMuse CLI 安装不可读',
    CLI_INTEGRITY:'官方 VidMuse CLI 文件校验失败',CLI_INSTALL_FAILED:'暂时无法安装 VidMuse CLI',
    CLI_PLATFORM_UNSUPPORTED:'当前系统没有支持的 VidMuse CLI 安装包',
    AWAITING_APPROVAL:'等待 VidMuse 设备授权',AUTH_UNAVAILABLE:'无法打开 VidMuse 设备授权',
    DEVICE_CANCELLED:'已取消 VidMuse 授权',DEVICE_EXPIRED:'本次 VidMuse 授权已过期',
    ACCOUNT_CHANGED:'VidMuse 账号已变化，请重新检查',ACCOUNT_UNAVAILABLE:'暂时无法核对 VidMuse 账号'};
  let pending=null, data=null, checking=null, shown=false, detailChecked=false;
  const text=key=>labels[key]||'暂时无法连接 VidMuse';
  function render(){
    const state=data?.state||'';
    OAUI.set($('State'),pending?text('AWAITING_APPROVAL'):state?text(state):'尚未检查 VidMuse 连接。');
    $('Install').hidden=state!=='CLI_MISSING'||!!pending;
    $('Connect').hidden=!(state==='AUTH_REQUIRED'||state==='DEVICE_EXPIRED'||state==='DEVICE_CANCELLED')||!!pending;
    $('Device').hidden=!pending;
    $('Code').textContent=pending?.code||'';
    const actual=data?.account?' · '+data.account:'';
    OAUI.raw($('Balance'),data?.balance!=null?OAUI.format('可用积分')+' '+data.balance+actual:
      data?.account?OAUI.format('暂时无法读取积分')+actual:'');
    const modes=$('Models');
    modes.replaceChildren();
    for(const route of data?.models||[]){
      const item=document.createElement('li');
      const parts=[OAUI.format(route.mode==='text'?'文字生成':'图片参考'),route.model_name,
                   route.resolution.join('/'),route.duration.join(', ')+' s',route.ratio.join(' / ')];
      item.textContent=parts.join(' · ');modes.append(item);
    }
    modes.hidden=!modes.childElementCount;
    if(state)paintTile('vidmuse',text(state),'',state);
  }
  function get(force=false){
    if(!force&&data)return Promise.resolve(data);
    if(!checking)checking=call({action:'status'}).then(result=>{data=result;render();return result;},error=>{
      data={state:error.message.replace(/^VIDMUSE_/,'')};render();return data;
    }).finally(()=>{checking=null;});
    return checking;
  }
  function bind(name,action){
    $(name).onclick=async()=>{
      $(name).disabled=true;
      try{await action();}
      catch(err){OAUI.set($('State'),text(err.message.replace(/^VIDMUSE_/,'')));}
      finally{$(name).disabled=false;}
    };
  }
  bind('Check',()=>get(true));
  bind('Install',async()=>{data=await call({action:'install'});render();});
  bind('Connect',async()=>{
    const result=await call({action:'device_start'});
    pending=result;render();$('Open').focus();
  });
  bind('Open',()=>pending&&openLink(pending.url));
  bind('Finish',async()=>{
    if(!pending)return;
    const result=await call({action:'device_finish',session:pending.session});
    if(result.state!=='AWAITING_APPROVAL'){pending=null;data=result;}
    render();
  });
  bind('Cancel',async()=>{
    if(!pending)return;
    data=await call({action:'device_cancel',session:pending.session});
    pending=null;render();$('Connect').focus();
  });
  OAUI.onChange(()=>{if(shown)render();});
  return {call,get,text,open(active){
    shown=active;
    if(active&&!detailChecked){detailChecked=true;get(false);}
  }};
}
'''
