"""Documented model catalog and account setup controls for the native video view."""
import json

from .video_minimax import H3_MODELS, SUBJECT_MODEL, V1_MODELS
from .video_seedance import ARK_MODELS

ARK_DOC = 'https://console.volcengine.com/ark/region:cn-beijing/docs/video-generation-tutorial'



def directory():
    ack = {'official': 'DOCUMENTED', 'account': 'UNVERIFIED', 'first_generation': 'UNVERIFIED'}
    ark = [dict(ack, id=model, version='v3', client='SUPPORTED',
                modes=modes, duration=[start, end], resolutions=res, audio=audio)
           for model, (modes, start, end, res, audio) in ARK_MODELS.items()]
    minimax = [dict(ack, id=model, version='v2', client='SUPPORTED',
                    modes=['text', 'first', 'last', 'frames', 'reference'], duration=[start, 15], resolutions=res)
               for model, (start, res) in H3_MODELS.items()]
    minimax.extend(dict(ack, id=model, version='v1', client='SUPPORTED', modes=list(modes),
                        resolutions=list(dict.fromkeys(size for sizes in modes.values() for size in sizes)))
                   for model, modes in V1_MODELS.items())
    minimax.append(dict(ack, id=SUBJECT_MODEL, version='v1', client='SUPPORTED', modes=['subject']))
    return {'documentation_checked': '2026-11-17', 'ark': ark, 'minimax': minimax}


STYLE = '''
.oa-provider-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:10px;align-items:start}
.oa-provider-grid>.panel{margin:0!important;min-width:0}
.oa-provider-grid h2{margin:0 0 4px;font-size:16px}
.oa-provider-actions{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}
.oa-provider-cost{margin:8px 0}
.oa-provider-grid [data-catalog] select{width:100%;font-size:12px;min-width:0;padding-inline:6px}
.oa-provider-grid .oa-provider-meta{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;font-size:11px;margin:6px 0}
.oa-provider-meta dd{margin:0;overflow-wrap:anywhere}
.oa-provider-grid input{min-width:0}
#videoProviderCopy{width:100%;min-height:64px}
@media(max-width:560px){.oa-provider-grid{grid-template-columns:minmax(0,1fr)}}
'''

_BODY = r'''
const OAVideoProviders=(send,openLink,canSend)=>{
 const $=id=>document.getElementById(id);
 const catalog=__CATALOG__,selected=new Map();
 const msg=$('videoProviderNotice'),copy=$('videoProviderCopy');
 const known={
  ark:{name:'火山方舟',region:'中国站 / 北京',
       console:'https://console.volcengine.com/ark/region:cn-beijing/overview',
       model:'https://console.volcengine.com/ark/region:cn-beijing/docs/video-generation-tutorial',
       billing:'https://console.volcengine.com/finance/bill/detail'},
  cn:{name:'MiniMax',region:'中国站',console:'https://platform.minimax.cn/',
      model:'https://platform.minimax.cn/docs/api-reference/video-generation-v2-create',
      billing:'https://platform.minimax.cn/user-center/payment/balance'},
  global:{name:'MiniMax',region:'国际站',console:'https://platform.minimax.io/',
      model:'https://platform.minimax.io/docs/api-reference/video-generation-v2-create',
      billing:'https://platform.minimax.io/user-center/payment/balance'}
 };
 for(const channel of ['ark','cn','global']){
   const parent=document.querySelector('[data-catalog='+channel+']'),label=document.createElement('label'),sel=document.createElement('select'),details=document.createElement('dl');
   label.append(OAUI.label('官方模型'),sel);details.className='oa-provider-meta';
   const items=channel==='ark'?catalog.ark:catalog.minimax;
   for(const item of items)sel.add(new Option(item.id,item.id));
   parent.append(label,details);
   function describe(){
     const item=items.find(row=>row.id===sel.value);
     selected.set(channel,item);
     details.replaceChildren();
     for(const [key,value] of [
       ['官方目录',OAUI.message('已列出 {0}',item.version)],
       ['当前账号',OAUI.message('未核验')],
       ['插件支持',OAUI.message(item.client==='SUPPORTED'?'参数已接入':'待接入')],
       ['首次生成',OAUI.message('未核验')],
       ['文档核对日期',catalog.documentation_checked],
       ...(item.duration?[['时长与清晰度',item.duration.join('–')+' s · '+item.resolutions.join(' / ')]]:[])
     ]){
       const name=document.createElement('dt'),text=document.createElement('dd');OAUI.set(name,key);
       OAUI.set(text,'{0}',value);details.append(name,text);
     }
   }
   sel.onchange=describe;describe();
 }
 const label=()=>document.documentElement.lang==='zh-CN';
 for(const button of document.querySelectorAll('[data-provider-control]'))button.onclick=async()=>{
   if(button.disabled)return;
   const channel=button.dataset.providerControl, env=known[channel];
   const row=selected.get(channel),action=button.dataset.action;
   button.disabled=true;copy.hidden=true;copy.value='';OAUI.set(msg,'');
   try{
     if(action!=='assist'&&action!=='usage'){
       const legacy={text:'t2v',first:'i2v',frames:'fl2v',subject:'s2v'};
       const url=action==='model'&&row.version==='v1'?
         env.model.replace('v2-create',legacy[row.modes[0]]):env[action==='official'?'console':action];
       await openLink(url);return;
     }
     const ref=crypto.randomUUID();
     const usage=label()?
       '请只读核对这个站点的官方套餐额度和按量账单可见性。仅用已确认属于该站点和我的账号的连接。分别报告来源及未能查到的项目。':
       'Check the official plan quota and pay-as-you-go billing visibility. Use a verified connection belonging to my account on this site. Report the source and any unavailable fields separately.';
     const setup=label()?
       '请协助核对官方账号的模型开通状态，打开官方控制台。先只读；任何授权、开通、购买或生成由我明确指定后进行。':
       'Help me check official model access and open the official console. Start read-only. Ask before authorization, activation, purchasing, or generation.';
     const instruction=(action==='usage'?usage:setup)+'\n'+[env.name,env.region,row.id,row.version,ref].join(' · ');
     if(!canSend()){copy.value=instruction;copy.hidden=false;copy.focus();copy.select();return;}
     await send(instruction);OAUI.set(msg,'已发到当前 Codex 聊天。');
   }catch(_){OAUI.set(msg,action==='assist'||action==='usage'?'无法确认聊天收到请求。':'宿主未能打开官方页面。');}
   finally{button.disabled=false;}
 };
};
'''

SCRIPT = _BODY.replace('__CATALOG__',json.dumps(directory(),ensure_ascii=False))
