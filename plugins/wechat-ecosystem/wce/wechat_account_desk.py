"""Account navigation and a local menu designer over the original WeChat contract."""

PAGES = ('monitor','settings','profile','articles','media','readers','messages','comments',
         'menu','shop','coupons','stores','channels','web','operations','publish')

HTML = r'''
<section id="wechatAccountDesk" hidden aria-labelledby="wechatDeskTitle">
 <h2 id="wechatDeskTitle"></h2>
 <nav id="wechatDeskSubviews" aria-label="当前账号工具"></nav>
 <p id="wechatDeskState" role="status"></p>
 <div id="wechatDeskBody"></div>
</section>'''

STYLE = r'''
#wechatAccountDesk{min-width:0;overflow:auto;overscroll-behavior:contain;padding:4px 5px 18px}
#wechatAccountDesk h2{margin:0 0 8px}
#wechatDeskSubviews{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
#wechatDeskSubviews button[aria-current=page]{box-shadow:var(--oh-press);color:var(--accent)}
#wechatDeskState:empty{display:none}
.wx-menu-designer{display:grid;grid-template-columns:minmax(220px,320px) minmax(0,520px);gap:15px}
.wx-menu-preview,.wx-menu-fields{min-width:0;background:var(--surface);box-shadow:var(--oh-press);border-radius:14px;padding:12px}
.wx-menu-preview{display:flex;min-height:210px;flex-direction:column;justify-content:space-between}
.wx-menu-preview ul{margin:0;display:flex;list-style:none;padding:0;gap:5px;flex-wrap:wrap}
.wx-menu-preview li{min-width:0}
.wx-menu-preview button{max-width:155px;white-space:normal;overflow-wrap:anywhere}
.wx-menu-fields label{display:grid;gap:4px;margin:8px 0}
.wx-menu-fields .actions{margin-block:8px;flex-wrap:wrap}
.wx-desk-entrypoints{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 4px}
#wechatSettings[data-desk-view="readers"] #wxOpsAdmin>section:not(:has(#wxOpsTagsRead)),
#wechatSettings[data-desk-view="channels"] #wxOpsAdmin>section:not(:has(#wxOpsChannelMake)),
#wechatSettings[data-desk-view="comments"] #wxOpsMenuRead,
#wechatSettings[data-desk-view="comments"] #wxOpsMenuRows{display:none}
@media(max-width:720px){.wx-menu-designer{grid-template-columns:minmax(0,1fr)}}
'''

SCRIPT = r'''
function OAWechatAccountDesk(tool,openOfficial,go){
 const $=id=>document.getElementById(id),ui=globalThis.OAUI,make=tag=>document.createElement(tag);
 const body=$('wechatDeskBody'),subviews=$('wechatDeskSubviews'),head=$('wechatDeskTitle');
 const status=(text,...args)=>ui.set($('wechatDeskState'),text,...args);
 const services={menu:['自定义菜单',15],shop:['微信小店',5],coupons:['微信卡券',8],stores:['微信门店',13],
  channels:['渠道二维码',3],web:['网页授权',4],messages:['私信会话',1]};
 const groups={menu:['menu','shop','coupons','stores'],readers:['readers','messages','comments'],profile:['profile','channels','web']};
 const names={...Object.fromEntries(Object.entries(services).map(([key,value])=>[key,value[0]])),
  readers:'读者与标签',comments:'文章留言',profile:'资料与权限'};
 let account=null,view='',currentKey='',run=0,edit=null,mask=null,busy=false,selection=[0],observed=false,plan=null,request=null;
 const key=()=>account?'jiusera-wechat-menu-v1:'+account.connection_id+':'+account.binding_revision:'';
 const same=token=>run===token&&account;
 function button(text,action){const b=make('button');b.type='button';ui.set(b,text);b.onclick=action;return b;}
 function caption(text){const p=make('p');ui.set(p,text);return p;}
 function fields(label,value,onchange,choice=null){
   const node=make('label'),input=make(choice?'select':'input');
   if(choice)for(const [key,text] of choice){
     const option=make('option');option.value=key;ui.set(option,text);input.append(option);
   }
   input.value=value;input.oninput=()=>onchange(input.value);
   node.append(ui.label(label),input);return node;
 }
 async function call(action,args={}){
   const current=account,reply=await tool('own.wechat.content',{action,connection_id:current.connection_id,...args});
   if(reply.isError||!reply.structuredContent)throw Error(reply.structuredContent?.error||'UNAVAILABLE');
   return reply.structuredContent;
 }
 function local(value=null){
   if(!account)return null;
   try{
     if(value)localStorage.setItem(key(),JSON.stringify(value));
     return JSON.parse(localStorage.getItem(key())||'null');
   }catch(_){return null;}
 }
 function stage(){local({buttons:edit,request});}
 function mark(){plan=null;}
 function menuGroups(rows){return JSON.stringify(rows.map(n=>n.sub_button?
   [n.name,menuGroups(n.sub_button)]:[n.name,n.type,n.url||n.key||'']));}
 async function readMenu(){
   const token=run;
   try{
     const current=await call('read_menu',{menu:'programmed'});
     if(!same(token))return;
     if(current.error_code!==undefined&&current.error_code!==46003){status('微信菜单读取失败（{0}）',current.error_code);return;}
     observed=true;
     mask=current.editable_items??(current.error_code===46003?[]:null);
     if(!edit)edit=mask===null?[]:structuredClone(mask);
     selection=[0];renderMenu();
     status(mask===null?'现有菜单含需要在微信后台维护的按钮。':
       current.conditional_count?'已读取常规菜单。条件菜单仍在微信后台管理。':'已读取本号微信菜单。');
   }catch(_){if(same(token))status('本号菜单暂时无法读取，可打开微信后台查看。');}
 }
 async function publishMenu(){
   if(!account||busy||!edit?.length||mask===null&&!request)return;
   const token=run;busy=true;
   try{
     if(request){
       const result=await call('status_by_key',{request_key:request.key});
       if(!same(token))return;
       const read=await call('read_menu',{menu:'programmed'});
       if(!same(token))return;
       if(Array.isArray(read.editable_items)&&menuGroups(read.editable_items)===menuGroups(request.buttons)){
         request=null;stage();status('已从微信读回同一份菜单。');
       }else status('原同步结果：{0}。当前微信菜单尚未匹配。',result.state);
       return;
     }
     if(!plan){
       const value=await call('plan_menu',{buttons:edit});
       if(!same(token))return;
       if(value.error_code!==undefined){status('微信菜单读取失败（{0}）',value.error_code);return;}
       plan=value;renderMenu();status('请核对预览，确认后同步到当前公众号。');return;
     }
     request={key:'menu-'+crypto.randomUUID(),buttons:plan.proposed};stage();
     const result=await call('update_menu',{request_key:request.key,confirm:true,
       buttons:plan.proposed,expected_menu_sha256:plan.expected_menu_sha256});
     if(!same(token))return;
     if(result.state==='COMPLETED'){
       const read=await call('read_menu',{menu:'programmed'});
       if(!same(token))return;
       if(Array.isArray(read.editable_items)&&menuGroups(read.editable_items)===menuGroups(request.buttons)){
         request=null;stage();status('已同步到微信并独立读回本号菜单。');
       }else status('微信已受理，当前菜单尚未匹配。');
     }else if(['REJECTED','SOURCE_CHANGED'].includes(result.state)){
       request=null;plan=null;stage();status('微信菜单未同步（{0}）',result.state);
     }else status('结果待确认，请查询原同步。');
   }catch(_){if(same(token))status(request?'结果待确认，请查询原同步。':'请检查菜单名称、动作和目标。');}
   finally{if(same(token)){busy=false;renderMenu();}}
 }
 function renderMenu(){
   body.replaceChildren();
   const grid=make('div'),phone=make('section'),controls=make('section'),actions=make('div'),nodes=make('ul');
   grid.className='wx-menu-designer';phone.className='wx-menu-preview';controls.className='wx-menu-fields';actions.className='actions';
   phone.append(caption(account?.label||'手机菜单预览'),nodes);
   const items=edit||[];
   const names=rows=>menuGroups(rows||[]).replace(/[\[\]"]/g,'');
   items.forEach((node,i)=>{
     const li=make('li');li.append(button(node.name||'未命名',()=>{selection=[i];renderMenu();}));
     for(const [j,child] of (node.sub_button||[]).entries())
       if(i===selection[0])li.append(button(child.name||'未命名',()=>{selection=[i,j];renderMenu();}));
     nodes.append(li);
   });
   const parent=items[selection[0]];
   const item=selection.length===2?parent?.sub_button?.[selection[1]]:parent;
   const mutable=observed&&mask!==null&&!request;
   if(mutable&&item){
     const siblings=selection.length===2?parent.sub_button:items,at=selection.at(-1);
     controls.append(fields('菜单名称',item.name,value=>{item.name=value;mark();const caption=nodes.children[selection[0]]?.children[selection.length===1?0:selection[1]+1];if(caption)caption.textContent=value;}));
     if(!item.sub_button){
       controls.append(fields('动作',item.type,value=>{delete item.url;delete item.key;item.type=value;item[value==='view'?'url':'key']='';mark();renderMenu();},[['view','网页链接'],['click','关键词事件']]));
       const key=item.type==='view'?'url':'key';
       controls.append(fields('目标',item[key]||'',value=>{item[key]=value;mark();}));
     }
     const shift=direction=>{const next=at+direction;if(next<0||next>=siblings.length)return;
       [siblings[next],siblings[at]]=[siblings[at],siblings[next]];selection[selection.length-1]=next;mark();renderMenu();};
     actions.append(button('向前移动',()=>shift(-1)),button('向后移动',()=>shift(1)),
       button('移除当前按钮',()=>{siblings.splice(at,1);if(parent?.sub_button?.length===0)Object.assign(parent,{type:'view',url:''}),delete parent.sub_button;selection=[0];mark();renderMenu();}));
     if(selection.length===1&&(parent.sub_button?.length||0)<5)actions.append(button('添加子菜单',()=>{
       if(!parent.sub_button){parent.sub_button=[];delete parent.type;delete parent.url;delete parent.key;}
       parent.sub_button.push({name:'子菜单',type:'view',url:''});selection=[selection[0],parent.sub_button.length-1];mark();renderMenu();
     }));
   }
   if(mutable&&items.length<3)actions.append(button('添加一级菜单',()=>{
     edit??=[];edit.push({name:'菜单',type:'view',url:''});selection=[edit.length-1];mark();renderMenu();
   }));
   controls.append(actions);
   const save=button('保存到本机',()=>{stage();status('已保存本号菜单草稿。');});save.disabled=!mutable||!edit?.length;
   const sync=button(request?'查询原同步':plan?'确认同步到微信':'对比并同步到微信',()=>void publishMenu());
   sync.disabled=busy||(!request&&(!mutable||!edit?.length));
   controls.append(button('读取微信菜单',()=>void readMenu()),save,sync);
   if(plan)controls.append(caption(ui.format('微信当前：{0} · 本次设计：{1}',[names(plan.current),names(plan.proposed)])));
   grid.append(phone,controls);body.append(grid);
 }
 function renderCapability(key){
   const permission=services[key]?.[1],grant=account?.component_grant;
   const checked=grant?.state==='ACTIVE',granted=checked&&grant.permissions?.includes(permission);
   body.replaceChildren();
   status(!account?'请选择一个公众号。':!checked?'本号实际授权待核验。':granted?
     '已读取本号授权。此处的业务可用性还需按微信实际资格或接口确认。':'本号未授予对应权限。');
   if(key==='messages')body.append(caption('私信和多人客服需要该号接通已验签的消息事件；在可用前，可到微信后台处理会话。'));
   if(key==='web')body.append(caption('网页授权域名、独占状态和实际活动需在该公众号下核对。'));
   body.append(button('打开微信公众平台',()=>void openOfficial('https://mp.weixin.qq.com/')));
 }
 function nav(key,node=subviews){
   const group=Object.values(groups).find(routes=>routes.includes(key))||[];
   node.replaceChildren(...group.map(route=>{
     const b=button(names[route],()=>go(route));
     if(route===key)b.setAttribute('aria-current','page');
     return b;
   }));
 }
 return {
   nav,
   target(next,key){
     const identity=next?.connection_id+'|'+next?.binding_revision+'|'+key;
     if(identity===currentKey)return;
     currentKey=identity;account=next;view=key;run++;busy=false;
     if(!key)return;
     status('');nav(key);ui.set(head,names[key]||'当前账号');
     if(key==='menu'){
       const saved=local();edit=saved?.buttons||null;request=saved?.request||null;observed=false;plan=null;selection=[0];
       renderMenu();if(account)void readMenu();
     }else renderCapability(key);
   },
 };
}
'''
