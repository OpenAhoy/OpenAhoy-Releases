"""Embedded preference editor. All user text is text, never executable markup."""
from .account_starter_ui import entry as starter_entry
from .html_technical_standard import render_html
from .management_workspace_ui import workspace, SCRIPT as WORKSPACE_SCRIPT
from .wechat_position_editor import SCRIPT as POSITION_SCRIPT, STYLE as POSITION_STYLE

HTML = render_html() + '''<style>
#rulesCreator{display:flex;flex-direction:column;gap:12px;min-width:0}
#rulesCreator .drawer-head{display:flex;align-items:center;justify-content:space-between;gap:16px;flex:none}
#rulesCreator .drawer-head h2{margin:0;font-size:18px;line-height:1.4}
#rulesCreator>.help{font-size:12px;line-height:1.6;margin:0;flex:none}
#creatorSteps{display:flex;align-items:center;gap:4px;overflow-x:auto;flex:none;padding:4px;border-radius:9px;background:var(--soft,#f2f4f7);scrollbar-width:thin}
#creatorSteps button{flex:1;min-height:34px;padding:6px 10px;white-space:nowrap;background:transparent;border:1px solid transparent;border-radius:6px;box-shadow:none;color:var(--muted,#627084)}
#creatorSteps button[aria-selected=true]{background:var(--surface,#fff);border-color:var(--line,#e3e7ee);color:var(--accent,#3768c8);font-weight:600}
#creatorFields{min-width:0;flex:1;min-height:0;overflow:auto;padding:3px}
#rulesCreator .configuration-group{border:0;padding:0;margin:0;min-inline-size:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
#rulesCreator .configuration-group[data-field-count="1"]{grid-template-columns:1fr}
#rulesCreator .configuration-group[hidden]{display:none}
#rulesCreator legend{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);margin:0;padding:0}
#rulesCreator label{display:flex;flex-direction:column;min-width:0;margin:0;gap:6px;font-size:14px}
#rulesCreator label strong{font-size:14px;font-weight:600}
#rulesCreator label>.help{font-size:12px;line-height:1.6;margin:0;min-height:38px}
#rulesCreator textarea{box-sizing:border-box;width:100%;min-height:220px;margin:0;padding:10px 12px;border:1px solid var(--line,#e3e7ee);border-radius:8px;font:400 14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;resize:vertical;background:var(--surface,#fff);color:var(--ink,#202833)}
#rulesCreator textarea[data-creator-field="author"]{min-height:44px;height:44px;resize:vertical}
#rulesCreator .configuration-choices{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 0}
#rulesCreator .configuration-choices button{font-size:12px;min-height:30px;padding:4px 8px;border-color:var(--line,#e3e7ee);background:var(--surface,#fff)}
#rulesCreator>.actions{display:flex;gap:8px;flex-wrap:wrap;flex:none;border-top:1px solid var(--line,#e3e7ee);padding-top:12px;margin:0}
#creatorStatus{font-size:12px;line-height:1.6;color:var(--muted,#627084);overflow-wrap:anywhere;margin:0;min-height:20px;flex:none}
#rulesCreator .wx-file-inherit{margin-block:7px;display:flex;flex-direction:row;align-items:center;gap:6px}
#creatorImportReview{margin:0;padding-inline-start:20px;font-size:13px;line-height:1.45}
@media(min-width:800px) and (min-height:600px){#creatorFields{min-height:180px}#rulesCreator textarea{max-height:40vh}}
@media(max-width:799px),(max-height:599px){#rulesCreator .configuration-group{grid-template-columns:1fr}#rulesCreator .drawer-head{align-items:flex-start}#rulesCreator textarea{min-height:150px;font-size:16px}#rulesCreator>.actions{position:static;background:var(--surface,#fff);padding:12px 0 4px}#creatorFields{overflow:visible}#creatorSteps button{flex:none;min-height:40px}#rulesCreator label>.help{min-height:0}}
</style><section class="card" style="margin-top:24px" id="productionRules"><div id="rulesEditing"><div class="rules-body">
<h2>内容生产规则</h2><p class="help">仅影响后续创作，不修改旧稿或账号权限。请勿填写密钥。</p>
<div class="rules-context"><div class="oa-scope-tabs" role="group" aria-label="生效范围"><button id="rulesAccountScope" type="button">本账号</button><button id="rulesDefaultScope" type="button">平台默认</button><select id="rulesScope" hidden aria-label="内部设置范围"><option value="">全局默认</option></select></div>
<p id="rulesStatus" role="status">正在连接本地规则工具。</p></div><div id="rulesFields"></div>

<details><summary>当前有效规则预览</summary><pre id="rulesPreview"></pre></details>
<details><summary>恢复以前版本</summary><select id="rulesHistory"></select><div class="actions"><button id="rulesMore" disabled>读取历史</button><button id="rulesRestore" disabled>恢复选中版本</button></div></details></div><div class="actions"><button id="rulesSave" class="primary" disabled>保存规则</button><button id="rulesReload" disabled>读取最新版并保留编辑</button><button id="rulesCreate" disabled>快速创建配置</button></div>
</div><section id="rulesCreator" hidden aria-labelledby="creatorTitle">
<div class="drawer-head"><h2 id="creatorTitle">创建生产配置</h2><button id="creatorBack" type="button">返回规则设置</button></div>
<p class="help">可下载本号的创作配置，或先查看文件会改哪些项目，再保存。只有覆盖项的空值会清空本号设置。</p>
<ul id="creatorImportReview" hidden aria-label="导入变更"></ul>
<div id="creatorSteps" role="tablist" aria-label="生产配置分区"></div><div id="creatorFields"></div>
<div class="actions"><button id="creatorSave" class="primary" type="button">保存到此公众号</button><button id="creatorDownload" type="button">下载配置文件</button><button id="creatorFill" type="button">用配置文件填写</button><button id="creatorReset" type="button">用最新规则重新填写</button></div>
<p id="creatorStatus" role="status" aria-live="polite"></p>
<input id="creatorConfigFile" type="file" accept=".json,application/json" hidden>
</section>
<input id="rulesConfigFile" type="file" accept=".json,application/json" hidden>
</section>'''
# Shared presentation around the original fields and existing action IDs.
_start = HTML.index('<div id="rulesEditing">')
_end = HTML.index('<section id="rulesCreator"', _start)
_fields = '<div class="rules-body"><div class="rules-context"><div class="oa-scope-tabs" role="group" aria-label="生效范围"><button id="rulesAccountScope" type="button">本账号</button><button id="rulesDefaultScope" type="button">平台默认</button><select id="rulesScope" hidden aria-label="内部设置范围"><option value="">全局默认</option></select></div></div><div id="rulesFields"></div><details><summary>当前有效规则预览</summary><pre id="rulesPreview"></pre></details><details><summary>恢复以前版本</summary><select id="rulesHistory"></select><div class="actions"><button id="rulesMore" disabled>读取历史</button><button id="rulesRestore" disabled>恢复选中版本</button></div></details></div>'
_actions = '<p id="rulesStatus" class="notice" role="status">正在读取配置…</p><button id="rulesSave" class="primary" disabled>保存并应用</button>'
_tools = '<details class="oa-task-menu"><summary>导入 / 下载</summary><div class="actions"><button id="rulesCreate" disabled>创建、导入与下载配置</button><button id="rulesReload" disabled>读取最新版并保留编辑</button></div></details>'
_context = '<p class="help">只影响后续创作，原文、账号权限和任务保留。</p><button type="button" data-workspace-project>项目与 Skills</button>'
HTML = HTML[:_start] + '<div id="rulesEditing">' + workspace('rules', '配置公众号的内容定位、表达风格、图文版式与创作偏好。', starter_entry('rules') + _fields, _actions, _tools, _context) + '</div>' + HTML[_end:]

JS = r'''
(() => {
  'use strict';
  const fields = ['audience_topics','author','voice','image_preferences','visual_layout','content_qa','delivery_publication','additional_notes'];
  const labels = ['选题与受众','作者署名','文风与结构','图源与图片内容','视觉与版式','内容审核要求','交付与普通发表偏好','补充规则（Markdown）'];
  const encoder = new TextEncoder();
  const hash = async text => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(text))),b=>b.toString(16).padStart(2,'0')).join('');
  const operation = () => 'rules-'+Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
  const split = text => {const points=Array.from(text), parts=[];for(let i=0;i<points.length;i+=8192)parts.push(points.slice(i,i+8192).join(''));return parts;};
  const templateReferences=text=>[...text.matchAll(/\[OpenAhoy template:([a-z0-9-]+)@([0-9]+\.[0-9]+\.[0-9]+)#([a-f0-9]{64})\]/g)]
    .map(([,id,version,manifest_sha256])=>({id,version,manifest_sha256}));
  function configurationEnvelope(raw, accountName, {cid='',unique=true}={}) {
    const fail=(code='RULES_CONFIG_INVALID')=>{throw new Error(code);};
    let value;try{value=JSON.parse(raw);}catch(_){fail('RULES_CONFIG_JSON');}
    // JSON.parse validates syntax; this token walk only rejects ambiguous keys.
    const stack=[];
    for(const token of raw.match(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g)||[]){
      if(token==='{'||token==='['){stack.push({object:token==='{',key:true,seen:new Set()});continue;}
      if(token==='}'||token===']'){stack.pop();continue;}
      const top=stack.at(-1);if(!top?.object)continue;
      if(token===','){top.key=true;continue;}
      if(token.startsWith('"')&&top.key){const key=JSON.parse(token);if(top.seen.has(key))fail('RULES_CONFIG_DUPLICATE');top.seen.add(key);top.key=false;}
    }
    const exact=(obj,keys)=>obj&&typeof obj==='object'&&!Array.isArray(obj)&&Object.keys(obj).length===keys.length&&keys.every(key=>Object.hasOwn(obj,key));
    if(!value||typeof value!=='object')fail('RULES_CONFIG_KEYS');
    if(value.format!=='openahoy.production-preferences')fail('RULES_CONFIG_FORMAT');
    if(![1,2].includes(value.schema_version))fail('RULES_CONFIG_VERSION');
    const legacy=value.schema_version===1;
    const keys=['format','schema_version','platform','account_name','fields'];
    if(!exact(value,legacy?keys:[...keys,'account_ref','source','project','templates']))fail('RULES_CONFIG_KEYS');
    if(value.platform!=='wechat_official_account')fail('RULES_CONFIG_PLATFORM');
    if(typeof value.account_name!=='string'||!exact(value.fields,fields))fail('RULES_CONFIG_FIELDS');
    if(!accountName||(legacy?(value.account_name!==accountName||!unique):(!cid||value.account_ref!==cid)))fail('RULES_CONFIG_ACCOUNT_MISMATCH');
    const result={legacy,fields:{},inherit:{}};
    if(!legacy){
      if(!exact(value.source,['store_revision','scope_revision','global_revision'])||
         Object.values(value.source).some(v=>!Number.isSafeInteger(v)||v<0))fail();
      const id=s=>typeof s==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(s);
      const sha=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
      const project=value.project;
      if(project!==null&&(!exact(project,['id','source_digest','skills'])||!id(project.id)||!sha(project.source_digest)||
        !Array.isArray(project.skills)||project.skills.some(s=>!exact(s,['id','sha256'])||!id(s.id)||!sha(s.sha256))||
        new Set(project.skills.map(s=>s.id)).size!==project.skills.length))fail();
      result.project=project;result.source=value.source;
    }
    for(const field of fields){
      const item=value.fields[field];
      if(!legacy&&(!exact(item,['mode','text'])||!['inherit','override'].includes(item.mode)))fail('RULES_CONFIG_FIELDS');
      const text=legacy?item:item.text;
      if(typeof text!=='string')fail('RULES_CONFIG_FIELDS');
      if(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/.test(text)||[...text].some(c=>{const n=c.codePointAt(0);return n>=0xd800&&n<=0xdfff;}))fail('RULES_CONFIG_TEXT');
      if(/(?:appsecret|access[_ -]?token|api[_ -]?key|password|密码|密钥)\s*[:=：]\s*\S+/i.test(text))throw new Error('RULES_SECRET_NOT_ALLOWED');
      result.fields[field]=text;
      result.inherit[field]=!legacy&&item.mode==='inherit';
    }
    const refs=templateReferences(result.fields.additional_notes);
    if(!legacy&&(!Array.isArray(value.templates)||value.templates.length!==refs.length||
      value.templates.some((ref,i)=>!exact(ref,['id','version','manifest_sha256'])||Object.keys(refs[i]).some(key=>ref[key]!==refs[i][key]))))fail();
    return {...result,templates:refs};
  }
  const parseConfiguration=(raw,accountName)=>configurationEnvelope(raw,accountName).fields;
  function mount(send, {compact=false,manual=null}={}, {downloadFile=null,configurationSources=null}={}) {
    const $=id=>document.getElementById(id), editors={}, inherited={}, sources={}, summaries={}, buffers=new Map();
    const ui=globalThis.OAUI||globalThis.OAPlainUI;
    let workspace=null, starter=null,position=null,positionStarter=null,positionActive=false;
    const fieldRows={},choiceEditors={};
    const definitions=[['内容定位',['audience_topics']],['表达与署名',['author','voice']],['配图与版式',['image_preferences','visual_layout']],['制作与交付',['content_qa','delivery_publication']],['项目与 Skill',['additional_notes']]];
    const choiceGroups={audience_topics:['主题','读者','内容形式','目标'],voice:['表达'],image_preferences:['配图'],visual_layout:['版式']};
    const loaded=new Map(),verifications=new Map();let accountNames=new Map(),accountBindings=new Map(),configAccounts=new Set(),importRequest=null,selectionEpoch=0,cardAccount='';
    const creations=new Map(),creatorEditors={},creatorInherits={},creatorChoices=[];let creator=null,creatorEpoch=0,fillRequest=null,lastRead=null;
    let pendingRestore=null,readTask=null;
    let ready=false, selected='', selectedBinding, generation=0, busy=false, meta=null, before=null, pendingSave=null, historyEnded=false;
    // A saved override masks its fallback in the effective read. Show that
    // fallback only after a save and readback when inheritance is newly enabled.
    const awaitingInheritance=field=>!!meta&&inherited[field].checked&&lastRead?.effective.fields[field]?.source==='account';
    const displayed=field=>!meta||awaitingInheritance(field)?'':inherited[field].checked?lastRead.combined[field]:editors[field].value;
    function showPosition(){
      if(!position)return;
      const field='audience_topics';
      position.render(displayed(field),!ready||busy||!meta||!!pendingSave||!!pendingRestore,!!meta,awaitingInheritance(field));
      ui.set(sources[field],!meta?'等待读取':awaitingInheritance(field)?'保存后使用默认内容':
        inherited[field].checked?(displayed(field).trim()?'正在使用默认内容':'还没有设置'):'当前公众号的内容');
    }
    const summarize=field=>{
      if(field==='audience_topics')showPosition();
      workspace?.refresh();
      if(summaries[field]){
        const text=displayed(field).trim().replace(/\s+/g,' ').slice(0,48);
        if(text)ui.raw(summaries[field],text);
        else ui.set(summaries[field],awaitingInheritance(field)?'保存后读取继承值':'未设置');
      }
      manual?.preview?.();
    };
    const scopeStatus='{0} 已读取版本 {1}；默认版本 {2}。';
    const status=(text,...values)=>{
      const message=$('rulesStatus');
      message.toggleAttribute('data-scope-status',text===scopeStatus);
      ui.set(message,text,...values);
    };
    const base=()=>({connection_id:selected,scope:selected?'account':'global'});
    const inputs=()=>Object.fromEntries(fields.map(field=>[field,{text:editors[field].value,inherit:inherited[field].checked}]));
    const scopeKey=(cid=selected)=>cid?JSON.stringify([cid,cid===selected?selectedBinding:accountBindings.get(cid)]):'';
    const scopeCurrent=()=>!selected||selectedBinding===accountBindings.get(selected);
    const remember=()=>{if(meta)buffers.set(scopeKey(),inputs());};
    for(let i=0;i<fields.length;i++) {
      const field=fields[i], row=document.createElement('label'), title=document.createElement('span');ui.set(title,labels[i]);row.append(title);
      const source=document.createElement('span');source.className='rule-source';sources[field]=source;row.append(source);
      const toggle=document.createElement('input');toggle.type='checkbox';ui.attr(toggle,'aria-label','继承默认规则：{0}',ui.message(labels[i]));
      const help=document.createElement('span');ui.set(help,' 继承现有账号偏好 / 全局默认');help.className='help';
      const area=document.createElement('textarea');area.rows=field==='additional_notes'?8:3;area.className='rule-input';ui.attr(area,'aria-label',labels[i]);area.setAttribute('data-field',field);
      inherited[field]=toggle;editors[field]=area;row.append(toggle,help);
      let body=row;
      if(compact&&globalThis.OAAccountStarter&&choiceGroups[field]){
        const choices=OAAccountStarter.choices(area,choiceGroups[field],{
          showCustom:!manual,
          canEdit:()=>!!meta&&!toggle.disabled&&!awaitingInheritance(field),
          read:()=>displayed(field),
          beforeEdit:()=>{if(toggle.checked)area.value=displayed(field);},
          commit:()=>{toggle.checked=false;area.disabled=false;summarize(field);remember();}
        });
        choiceEditors[field]=choices;
        body=document.createElement('div');
        if(manual&&field!=='audience_topics')row.append(area);
        body.append(row,choices.root);
      }else row.append(area);
      if(field==='audience_topics'&&manual){
        position=OAWechatPositionEditor(ui,area,toggle,source,()=>{
          toggle.checked=false;area.disabled=false;choiceEditors[field]?.refresh();summarize(field);remember();buttons();
        });
        position.original.append(area);
        if(choiceEditors[field])position.suggestionSlot.append(choiceEditors[field].root);
        position.scopeSlot.append($('rulesScope').closest('.rules-context'));
        fieldRows[field]=position.panel;$('rulesFields').append(position.panel);
        area.addEventListener('input',()=>choiceEditors[field]?.refresh());
      }else if(manual){
        fieldRows[field]=body;$('rulesFields').append(body);
      }else if(compact){
        const detail=document.createElement('details'),summary=document.createElement('summary'),caption=document.createElement('strong'),preview=document.createElement('span');
        detail.className='rule-editor';fieldRows[field]=detail;ui.set(caption,labels[i]);preview.className='rule-summary';summaries[field]=preview;
        summary.append(caption,preview);detail.append(summary,body);$('rulesFields').append(detail);
      }else{fieldRows[field]=row;$('rulesFields').append(row);}
      area.addEventListener('input',()=>{summarize(field);remember();});
      toggle.addEventListener('change',()=>{area.disabled=toggle.checked;choiceEditors[field]?.refresh();summarize(field);remember();});
    }
    if(compact&&globalThis.OAAccountStarter&&$('rulesStarter')){
      starter=OAAccountStarter.mount($('rulesStarter'),'wechat',{
        autoOpen:!manual,
        read:field=>({text:editors[field].value,inherit:inherited[field].checked}),
        write:(field,value)=>{editors[field].value=value.text;inherited[field].checked=value.inherit;},
        empty:(field,value)=>!value.text.trim()&&(!value.inherit||!lastRead?.combined[field]?.trim())&&
          (!loaded.get(scopeKey())?.[field]?.text.trim()),
        onChange:()=>{remember();buttons();workspace?.refresh();}
      });
    }
    if(position){
      const shell=$('rulesWorkspace');
      const anchor=document.createComment('scope');
      const scope=position.scopeSlot.querySelector('.rules-context');
      $('rulesFields').before(anchor);
      const fallback=document.createComment('history');
      const historyPanel=$('rulesHistory').closest('details');
      historyPanel.before(fallback);
      const previewPanel=$('rulesPreview').closest('details');
      const previewAnchor=document.createComment('preview');
      previewPanel.before(previewAnchor);
      const starterSlot=document.createElement('div');
      position.suggestionSlot.prepend(starterSlot);
      positionStarter=OAAccountStarter.mount(starterSlot,'wechat',{
        allowedFields:['audience_topics'],autoOpen:false,
        read:field=>({text:editors[field].value,inherit:inherited[field].checked}),
        write:(field,value)=>{editors[field].value=value.text;inherited[field].checked=value.inherit;},
        empty:field=>!displayed(field).trim(),onChange:()=>{remember();buttons();workspace?.refresh();}
      });
      const cancel=document.createElement('button');cancel.type='button';cancel.id='rulesPositionCancel';
      ui.set(cancel,'取消修改');
      cancel.onclick=()=>{
        if(busy||pendingSave||pendingRestore)return;
        const current=loaded.get(scopeKey())?.audience_topics;
        if(current){
          editors.audience_topics.value=current.text;inherited.audience_topics.checked=current.inherit;
          summarize('audience_topics');remember();buttons();
        }
        manual.back();
      };
      $('rulesSave').before(cancel);
      function place(focused){
        positionActive=focused;
        shell.toggleAttribute('data-position-editor',focused);
        if(focused){
          position.scopeSlot.append(scope,historyPanel,previewPanel);
        }else{
          anchor.after(scope);fallback.after(historyPanel);previewAnchor.after(previewPanel);
        }
        showPosition();
      }
      position.place=place;
    }
    if(globalThis.OATaskWorkspace){
      workspace=OATaskWorkspace.mount('rules',definitions.map(([title,keys])=>({title,
        summary:()=>keys.map(k=>displayed(k).trim().replace(/\s+/g,' ')).filter(Boolean).join(' · ')||['未设置'],
        show:shown=>{
          if(keys.includes('audience_topics'))position?.place(shown);
          for(const k of keys){if(fieldRows[k]){fieldRows[k].hidden=!shown;if(fieldRows[k] instanceof HTMLDetailsElement)fieldRows[k].open=shown;}}
        }
      })));
    }
    function buttons(){for(const name of ['rulesSave','rulesReload','rulesMore','rulesRestore'])$(name).disabled=!ready||busy||!meta;$('rulesMore').disabled||=historyEnded;$('rulesReload').disabled=!ready||busy;
      $('rulesSave').disabled||=!!pendingRestore;$('rulesRestore').disabled||=!!pendingSave;
      const locked=!ready||busy||!!pendingSave||!!pendingRestore;
      $('rulesHistory').disabled=locked;
      $('rulesAccountScope').disabled=locked||!cardAccount||!accountNames.has(cardAccount);$('rulesDefaultScope').disabled=locked;
      $('rulesAccountScope').setAttribute('aria-pressed',String(!!selected));$('rulesDefaultScope').setAttribute('aria-pressed',String(!selected));
      for(const field of fields){inherited[field].disabled=locked;editors[field].disabled=locked||!meta||inherited[field].checked;}
      $('rulesCreate').disabled=!ready||busy||!selected||!configAccounts.has(selected)||!!pendingSave||!!pendingRestore;
      for(const choice of Object.values(choiceEditors))choice.refresh();
      starter?.update(meta?scopeKey():'',locked||!meta);
      positionStarter?.update(meta?scopeKey():'',locked||!meta);
      if(position){
        $('rulesPositionCancel').disabled=busy||!!pendingSave||!!pendingRestore;
        showPosition();
      }
      creatorButtons();
    }
    async function tool(name,args) {
      // Sequential await plus the existing storage locks provide backpressure.
      const result=await send(name,args);
      if(!result || result.isError || !result.structuredContent) {
        const error=new Error(result?.structuredContent?.error || 'RULES_HOST_UNAVAILABLE');throw error;
      }
      return result.structuredContent;
    }
    async function content(manifest, target, epoch, chunks=new Map()) {
      const values={},current=()=>epoch===generation&&scopeCurrent();
      for(const [field,item] of Object.entries(manifest.fields)) {
        let text='';
        for(let index=0;index<item.chunks;index++) {
          if(!current())return null;
          const key=JSON.stringify([item.version_id,field,index]);
          if(!chunks.has(key)){
            const part=await tool('own.production.rules.read',{...target,view:'chunk',version_id:item.version_id,field,index});
            if(!current())return null;
            if(part.version_id!==item.version_id||part.field!==field||part.index!==index||await hash(part.text)!==part.sha256)throw new Error('RULES_CHUNK_CHANGED');
            chunks.set(key,part.text);
          }
          text+=chunks.get(key);
        }
        if(await hash(text)!==item.sha256 || Array.from(text).length!==item.unicode_length || encoder.encode(text).length!==item.utf8_bytes)throw new Error('RULES_INCOMPLETE');
        values[field]=text;
      }
      return values;
    }
    function load(keepEdits=true,{navigation=false}={}) {
      if(readTask)return readTask.promise;
      if(!ready||busy)return;
      if(!scopeCurrent()&&!pendingSave&&!pendingRestore&&
          (!accountBindings.has(selected)||!changeScope(selected,false)))return;
      const task={navigation:navigation&&scopeCurrent()&&!pendingSave&&!pendingRestore};
      readTask=task;
      task.promise=readRules(keepEdits).finally(()=>{if(readTask===task)readTask=null;});
      return task.promise;
    }
    async function readRules(keepEdits) {
      const identity=scopeKey();
      if(!keepEdits){starter?.forget(identity);positionStarter?.forget(identity);}
      const epoch=++generation, target=base();busy=true;buttons();
      status(scopeCurrent()?'正在读取当前规则与有效预览。':'账号绑定已变化。正在核对原操作。');
      const currentRead=()=>epoch===generation&&scopeCurrent();
      try {
        const pending=pendingSave||pendingRestore;
        if(pending){
          const original=await tool('own.production.rules.read',{...(pending.target||target),view:'operation',operation_id:pending.id});
          if(original.state!=='COMMITTED'){status('原操作结果尚未确认；编辑与操作号已保留，请继续原保存或恢复。');return;}
          if(pending.configuration)verifications.set(identity,pending.configuration);
          pendingSave=null;pendingRestore=null;settleBuffer(pending.configuration,identity);keepEdits=!!pending.configuration?.editorBuffer;
        }
        if(!currentRead())return;
        const current=await tool('own.production.rules.read',{...target,view:'summary'});
        if(!currentRead())return;
        const effective=await tool('own.production.rules.read',{...target,view:'effective'});
        if(!currentRead())return;
        if(current.store_revision!==effective.store_revision)throw new Error('RULES_VERSION_CONFLICT');
        const chunks=new Map();
        const own=await content(current,target,epoch,chunks), combined=await content(effective,target,epoch,chunks);
        if(!currentRead()||!own||!combined)return;
        lastRead={connection_id:target.connection_id,current,effective,own,combined};
        meta=current;
        // Textarea normalizes line endings; compare visible drafts against the
        // same normalization, while imported storage retains the file's text.
        loaded.set(identity,Object.fromEntries(fields.map(field=>[field,{text:(own[field]??combined[field]??'').replace(/\r\n?/g,'\n'),inherit:!!selected&&!Object.hasOwn(own,field)}])));
        const saved=keepEdits?buffers.get(identity):null;
        for(const field of fields) {
          editors[field].value=saved?.[field]?.text??(own[field]??combined[field]??'');
          editors[field].setAttribute('data-source',effective.fields[field].source);
          ui.set(sources[field],'当前生效来源：{0}',ui.message(({'global':'全局默认','account':'本号覆盖','legacy-editor':'现有账号偏好','default':'未设置'}[effective.fields[field].source]||'当前规则')));
          inherited[field].hidden=!selected;if(inherited[field].nextSibling.nodeType===Node.ELEMENT_NODE)inherited[field].nextSibling.hidden=!selected;
          inherited[field].checked=!!selected && (saved?.[field]?.inherit??!Object.hasOwn(own,field));
          editors[field].disabled=inherited[field].checked;summarize(field);
        }
        $('rulesPreview').textContent=fields.map((field,i)=>labels[i]+' ['+({'global':'全局默认','account':'本号覆盖','legacy-editor':'现有账号偏好','default':'未设置'}[effective.fields[field].source]||'当前规则')+']\n'+combined[field]).join('\n\n');
        $('rulesHistory').replaceChildren();before=null;historyEnded=false;
        const scopeMessage=target.scope==='account'
          ? ui.message('正在编辑本号「{0}」；未覆盖项继承现有偏好或公众号默认规则。',accountNames.get(target.connection_id)||ui.message('所选公众号'))
          : ui.message('正在编辑公众号默认规则；本号单独保存的内容不会显示在此范围。');
        if(saved&&positionActive)status('未保存的修改已保留。');
        else status(saved?'{0} 已读取版本 {1}；默认版本 {2}。未保存编辑已保留。':scopeStatus,scopeMessage,current.scope_revision,effective.global_revision);
        const verification=verifications.get(identity);
        if(verification){
          const complete=readbackMatches(lastRead,verification);
          status(complete?(verification.verifyField?'内容定位已保存并读回。':'已为「{0}」加载配置，八项有效规则已完整读回。'):'原配置保存已提交，但八项有效规则读回不匹配；请查看原账号版本，不要重复导入。',verification.name);
          if(complete){
            verifications.delete(identity);const draft=creations.get(identity);
            if(draft&&verification.creatorDraft===draft){
              draft.saved=creatorFingerprint({fields:verification.fields,inherit:verification.inherited});
              draft.revision=creatorValues(lastRead).revision;
            }
          }
        }
        return lastRead;
      } catch(error){
        if(currentRead())status('规则未能确认读取：'+error.message+'；已有编辑不会被覆盖。');
        else if(epoch===generation&&(pendingSave||pendingRestore))status('账号绑定已变化。原编辑与操作已保留。');
      }
      finally{if(epoch===generation){busy=false;buttons();}}
    }
    async function save(configuration=null) {
      if(!ready||busy||!meta||!scopeCurrent())return;
      if(configuration?.kind!=='configuration')configuration=null;
      const epoch=generation,target=base(),identity=scopeKey(),values=configuration?Object.fromEntries(fields.map(field=>[field,{text:configuration.fields[field],inherit:configuration.inherited?.[field]??false}])):inputs();busy=true;buttons();$('rulesSave').setAttribute('aria-busy','true');
      let op=pendingSave,begun=false,keepEdits=!!configuration?.editorBuffer,confirmed=false,failure='';const resuming=!!op,outcome={confirmed:false,verified:false,pending:false,failure:''};
      const checkImport=()=>{if(!scopeCurrent())throw new Error('RULES_BINDING_CHANGED');const context=op?.configuration||configuration;if(context&&!context.valid())throw new Error('RULES_CONFIG_TARGET_CHANGED');};
      const committed=()=>{confirmed=true;if(op.configuration)verifications.set(identity,op.configuration);else verifications.delete(identity);};
      try {
        // Any uncertain commit is only queried, never sent again.
        if(op?.commitAttempted){
          const original=await tool('own.production.rules.read',{...op.target,view:'operation',operation_id:op.id});
          if(original.state==='COMMITTED'){committed();pendingSave=null;settleBuffer(op.configuration,identity);}
          else status('原配置提交结果尚未确认；只查询原操作，不会再次提交。');
          return outcome;
        }
        if(!op) {
          const manifest=[],chunks={};
          for(const field of fields)if(!target.connection_id||!values[field].inherit) {
            const text=values[field].text;chunks[field]=split(text);
            manifest.push({name:field,chunks:chunks[field].length,unicode_length:Array.from(text).length,utf8_bytes:encoder.encode(text).length,sha256:await hash(text)});
          }
          checkImport();
          op={id:operation(),manifest,chunks,store:configuration?.revision?.store_revision??meta.store_revision,scope:configuration?.revision?.scope_revision??meta.scope_revision,target,commitAttempted:false};
          if(configuration)op.configuration={name:configuration.name,fields:configuration.fields,inherited:configuration.inherited,valid:configuration.valid,editorBuffer:configuration.editorBuffer,verifyField:configuration.verifyField,creatorDraft:configuration.creatorDraft};
          pendingSave=op;
        }
        status(positionActive?'正在保存内容定位…':'正在分块保存规则；不修改任何文章。');
        checkImport();
        await tool('wce.settings.production.save',{...target,action:'begin',operation_id:op.id,expected_store_revision:op.store,expected_scope_revision:op.scope,fields:op.manifest});
        begun=true;
        for(const [field,parts]of Object.entries(op.chunks))for(let index=0;index<parts.length;index++){
          checkImport();
          await tool('wce.settings.production.save',{...target,action:'chunk',operation_id:op.id,field,index,text:parts[index]});
        }
        checkImport();op.commitAttempted=true;
        const result=await tool('wce.settings.production.save',{...target,action:'commit',operation_id:op.id});
        if(result.state!=='COMMITTED')throw new Error('RULES_SAVE_RESULT_UNKNOWN');
        committed();
        if(epoch===generation){pendingSave=null;settleBuffer(op.configuration,identity);status('保存已提交，正在独立读回。');}
      } catch(error) {
        failure=error.message;
        if(epoch===generation) {
          if((op?.configuration||configuration)&&error.message==='RULES_CONFIG_TARGET_CHANGED'&&!op?.commitAttempted){
            pendingSave=null;keepEdits=true;remember();status('选择已变化，配置没有提交；保留编辑及原范围。');
          }else if(op) {
            try {
              const original=await tool('own.production.rules.read',{...target,view:'operation',operation_id:op.id});
              if(original.state==='COMMITTED'){committed();pendingSave=null;settleBuffer(op.configuration,identity);status('原保存已确认提交，正在读回。');}
              else if(error.message==='RULES_VERSION_CONFLICT'&&original.state==='STAGED'){
                pendingSave=null;remember();keepEdits=true;status('版本已变化，原保存未提交；正在读取新版本并保留编辑。');
              }
              else status('原保存尚未完成；再次保存会接续同一操作。'+error.message);
            }catch(_){
              if(error.message==='RULES_VERSION_CONFLICT'&&!resuming&&!begun){pendingSave=null;remember();keepEdits=true;status('版本冲突，未创建保存；正在读取新版本并保留编辑。');}
              else status('保存结果待确认；保留原操作与全部编辑。'+error.message);
            }
          }else status('保存未完成：'+error.message);
        }
      } finally {
        $('rulesSave').removeAttribute('aria-busy');
        if(epoch===generation){busy=false;buttons();if(!pendingSave){
          const context=op?.configuration||configuration;
          const read=scopeCurrent()?await load(keepEdits||!!context?.editorBuffer):null;
          if(!scopeCurrent())void loadAccountScope(target.connection_id);
          outcome.verified=!!(confirmed&&context&&read&&readbackMatches(read,context));
        }}
        Object.assign(outcome,{confirmed,pending:!!pendingSave,failure});
      }
      if(failure==='RULES_CONFIG_TARGET_CHANGED'&&!confirmed&&!pendingSave&&scopeCurrent()&&scopeKey()===identity)status(configMessage(failure));
      return outcome;
    }
    async function history() {
      if(!ready||busy||!meta||historyEnded)return;const epoch=generation,target=base();busy=true;buttons();
      try {
        const result=await tool('own.production.rules.read',{...target,view:'history',...(before===null?{}:{before})});
        if(epoch!==generation||!scopeCurrent())return;
        for(const row of result.items){const option=document.createElement('option');option.value=row.id;ui.set(option,row.restore_from?'版本 {0}（恢复）':'版本 {0}',row.scope_revision);$('rulesHistory').append(option);}
        before=result.next_before;historyEnded=before===null;status(before===null?'已读到该范围最早版本。':'已读取一页历史，可继续读取。');
      }catch(error){if(scopeCurrent())status('历史读取失败：'+error.message);}finally{busy=false;buttons();if(!scopeCurrent())void loadAccountScope(target.connection_id);}
    }
    async function restore() {
      if(!ready||busy||!meta||!$('rulesHistory').value)return;const epoch=generation,target=base();busy=true;buttons();
      const resuming=!!pendingRestore;
      const identity=scopeKey();
      const attempt=pendingRestore||{id:operation(),target,version:$('rulesHistory').value,store:meta.store_revision,scope:meta.scope_revision};
      pendingRestore=attempt;let confirmed=false,conflict=false,attempted=resuming;
      try {
        const candidate=await tool('own.production.rules.read',{...target,view:'version',version_id:attempt.version});
        const preview=await content(candidate,target,epoch);
        if(epoch!==generation||!preview)throw new Error('RULES_TARGET_CHANGED');
        $('rulesPreview').textContent='正在恢复历史版本 '+candidate.scope_revision+'（旧版本保留）\n'+fields.map((f,i)=>labels[i]+'\n'+(preview[f]||'')).join('\n\n');
        if(!scopeCurrent())throw new Error('RULES_BINDING_CHANGED');
        attempted=true;
        const result=await tool('wce.settings.production.restore',{...target,operation_id:attempt.id,version_id:attempt.version,
          expected_store_revision:attempt.store,expected_scope_revision:attempt.scope});
        confirmed=result.state==='COMMITTED';if(!confirmed)throw new Error('RULES_SAVE_RESULT_UNKNOWN');
      }catch(error){
        if(attempted)try{const original=await tool('own.production.rules.read',{...target,view:'operation',operation_id:attempt.id});confirmed=original.state==='COMMITTED';}catch(_){}
        if(!confirmed&&(!attempted||(error.message==='RULES_VERSION_CONFLICT'&&!resuming))){pendingRestore=null;conflict=true;remember();}
        if(!confirmed)status('恢复结果待确认，保留原操作；再次恢复只查询或接续该操作。'+error.message);
      }finally{
        busy=false;buttons();
        if(epoch===generation&&confirmed){
          pendingRestore=null;buffers.delete(identity);
          if(scopeCurrent()){
            await load(false);
            if(scopeCurrent())status('恢复为新版本并独立读回完成，旧版本保留。');
          }
        }else if(epoch===generation&&conflict&&scopeCurrent()){
          await load(true);if(scopeCurrent())status('版本冲突，未执行本次恢复；已读取新版本并保留编辑。');
        }
        if(!scopeCurrent()&&!pendingRestore)void loadAccountScope(target.connection_id);
      }
    }
    const dirty=cid=>{const identity=scopeKey(cid),value=cid===selected&&meta?inputs():buffers.get(identity);return !!value&&loaded.has(identity)&&JSON.stringify(value)!==JSON.stringify(loaded.get(identity));};
    const configMessage=code=>({RULES_CONFIG_ACCOUNT_MISMATCH:'配置名称与所选账号不一致，请选择该账号自己的配置文件。',RULES_CONFIG_ACCOUNT_UNAVAILABLE:'账号名称当前无法唯一确认，请先核对账号显示资料。',RULES_SECRET_NOT_ALLOWED:'配置包含疑似秘密；只能填写非秘密生产偏好。',RULES_CONFIG_INVALID:'配置格式、版本、平台或字段不正确。',RULES_CONFIG_JSON:'文件不是有效 JSON，请修正语法后重试。',RULES_CONFIG_DUPLICATE:'JSON 含重复字段，请移除重复项后重试。',RULES_CONFIG_KEYS:'配置根字段不正确；只能包含 format、schema_version、platform、account_name 和 fields。',RULES_CONFIG_FORMAT:'文件不是 Jiusera 生产偏好配置。',RULES_CONFIG_VERSION:'配置版本不兼容，当前仅支持 schema_version 1。',RULES_CONFIG_PLATFORM:'配置不属于公众号平台。',RULES_CONFIG_FIELDS:'fields 必须包含标准的八个字段，并且每项都是字符串。',RULES_CONFIG_TEXT:'配置含无效 Unicode 或不支持的控制字符。',RULES_CONFIG_ENCODING:'文件无法读取或不是有效 UTF-8 编码。',RULES_CONFIG_TARGET_CHANGED:'选择或填写已变化，原规则与草稿已保留，请重新选择文件。',RULES_CONFIG_DIRTY:'本号有未保存编辑，请先保存后再加载；全部编辑已保留。',RULES_VERSION_CONFLICT:'规则版本已变化，当前填写已保留；可用最新规则重新填写。'}[code]||'配置未能完成，原规则与填写已保留。');
    const copied=value=>JSON.parse(JSON.stringify(value));
    function readbackMatches(read,context){
      const own=read.own;
      if(context.verifyField){
        const key=context.verifyField;
        return context.inherited?.[key]?!Object.hasOwn(own,key):own[key]===context.fields[key];
      }
      return fields.every(key=>context.inherited?.[key]?!Object.hasOwn(own,key):
        own[key]===context.fields[key]&&read.combined[key]===context.fields[key]);
    }
    function settleBuffer(context,identity){starter?.forget(identity);positionStarter?.forget(identity);if(context?.editorBuffer)buffers.set(identity,copied(context.editorBuffer));else buffers.delete(identity);}
    async function readConfigurationFile(file){
      try{return new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer()).replace(/^\uFEFF/,'');}
      catch(_){throw new Error('RULES_CONFIG_ENCODING');}
    }
    const creatorNote=(text,...values)=>ui.set($('creatorStatus'),text,...values);
    function creatorCurrent(d=creator){return !!d&&creator===d&&ready&&configAccounts.has(d.cid)&&accountNames.get(d.cid)===d.name&&selected===d.cid&&scopeCurrent()&&d.identity===scopeKey()&&d.isCurrent();}
    function creatorButtons(){
      const valid=creatorCurrent(),locked=!valid||busy||!!pendingSave||!!pendingRestore;
      for(const area of Object.values(creatorEditors))area.disabled=locked;
      for(const choice of Object.values(creatorInherits))choice.disabled=locked;
      for(const button of creatorChoices)button.disabled=locked;
      $('creatorSave').disabled=!valid||busy||!!pendingRestore||!!pendingSave&&pendingSave.target.connection_id!==creator?.cid;
      ui.set($('creatorSave'),pendingSave?.commitAttempted?'查询原保存结果':pendingSave?'继续原保存':'保存到此公众号');
      for(const id of ['creatorFill','creatorReset'])$(id).disabled=locked;
      $('creatorDownload').disabled=!valid||busy||!!creator?.downloading;
      ui.set($('creatorDownload'),creator?.downloadPending?'查询上次导出结果':'下载配置文件');
    }
    const guidance=[
      '读者、领域、选题、参考信源及排除主题。可自由填写，不必设置封闭信源名单。',
      '文章署名；署名不代表原创声明或账号认证。',
      '希望怎样表达、组织文章，以及希望避免的措辞。篇幅由你决定。',
      '图片内容、素材来源、真实或生成偏好、版权和注明要求。',
      '按需要说明配色、字号、间距、图片比例；也可以不指定。',
      '事实、来源和图文一致性的创作复查，不生成新的发表审批。',
      '交付及普通发表偏好；实际发表和日程仍按当前有效委托。',
      '其他文本或 Markdown 偏好；请勿填写秘密、脚本或工具命令。'];
    const choices=[['面向入门读者','面向专业读者'],[],['简洁直接','自然叙述','避免夸张宣传'],['优先真实素材','可使用原创生成配图','注明素材来源'],['留白舒展','清晰的小标题','移动端易读'],['核对关键事实与出处','检查图文一致性'],['交付完整含图 HTML','按本次委托处理发表'],[]];
    for(const [title,indexes]of [['账号定位',[0,1]],['写作方式',[2]],['配图与排版',[3,4]],['创作复查与交付',[5,6]],['补充说明',[7]]]){
      const group=document.createElement('fieldset'),legend=document.createElement('legend'),tab=document.createElement('button');
      const groupIndex=$('creatorSteps').children.length;group.id='creator-group-'+groupIndex;group.className='configuration-group';group.dataset.fieldCount=String(indexes.length);group.hidden=groupIndex!==0;group.setAttribute('role','tabpanel');
      ui.set(legend,title);legend.id='creator-group-title-'+groupIndex;group.setAttribute('aria-labelledby',legend.id);group.append(legend);
      tab.type='button';ui.set(tab,title);tab.setAttribute('role','tab');tab.setAttribute('aria-controls',group.id);tab.setAttribute('aria-selected',String(groupIndex===0));tab.tabIndex=groupIndex===0?0:-1;
      const selectGroup=()=>{for(const item of $('creatorSteps').children){const active=item===tab;item.setAttribute('aria-selected',String(active));item.tabIndex=active?0:-1;$(item.getAttribute('aria-controls')).hidden=!active;}};
      tab.addEventListener('click',selectGroup);tab.addEventListener('keydown',event=>{const tabs=[...$('creatorSteps').children],index=tabs.indexOf(tab);let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();tabs[next].click();tabs[next].focus();});$('creatorSteps').append(tab);
      for(const index of indexes){
        const field=fields[index],label=document.createElement('label'),caption=document.createElement('strong'),help=document.createElement('p'),area=document.createElement('textarea');
        ui.set(caption,labels[index]);help.className='help';ui.set(help,guidance[index]);area.rows=index===1?2:4;ui.attr(area,'aria-label','创建配置：{0}',ui.message(labels[index]));area.dataset.creatorField=field;
        const mode=document.createElement('input'),modeLabel=document.createElement('label');
        mode.type='checkbox';modeLabel.className='wx-file-inherit';
        modeLabel.append(mode,ui.label('使用默认内容'));
        creatorEditors[field]=area;creatorInherits[field]=mode;
        const block=document.createElement('div');
        label.append(caption,help,area);block.append(label,modeLabel);group.append(block);
        area.addEventListener('input',()=>{if(creator){
          creator.fields[field]=area.value;creator.inherit[field]=false;mode.checked=false;
          creator.editRevision++;creatorNote('当前填写尚未保存到公众号配置。');manual?.preview?.();
        }});
        mode.addEventListener('change',()=>{if(creator){
          creator.inherit[field]=mode.checked;creator.editRevision++;
          creatorNote('当前填写尚未保存到公众号配置。');manual?.preview?.();
        }});
        if(choices[index].length){
          const shortcuts=document.createElement('div');shortcuts.className='configuration-choices';shortcuts.setAttribute('aria-label',labels[index]+'快捷文字');
          for(const text of choices[index]){const button=document.createElement('button');button.type='button';ui.set(button,text);creatorChoices.push(button);shortcuts.append(button);
            button.addEventListener('click',()=>{if(!creatorCurrent()||busy||pendingSave||pendingRestore)return;const old=creator.fields[field];creator.fields[field]=old?old+'\n'+text:text;creator.inherit[field]=false;mode.checked=false;creator.editRevision++;area.value=creator.fields[field];creatorNote('已加入快捷文字，可继续自定义；尚未保存。');manual?.preview?.();});}
          label.append(shortcuts);
        }
      }
      $('creatorFields').append(group);
    }
    function renderCreator(){
      if(!creator)return;ui.set($('creatorTitle'),'为「{0}」创建生产配置',creator.name);
      for(const field of fields){
        creatorEditors[field].value=creator.fields[field];
        creatorInherits[field].checked=creator.inherit[field];
      }
      const review=$('creatorImportReview');
      review.replaceChildren(...(creator.review||[]).map(message=>{
        const row=document.createElement('li');ui.set(row,...message);return row;
      }));
      review.hidden=!review.childElementCount;
      $('rulesEditing').hidden=true;$('rulesCreator').hidden=false;creatorButtons();
      manual?.preview?.();
    }
    function closeCreator(){creatorEpoch++;fillRequest=null;creator=null;$('creatorConfigFile').value='';$('rulesCreator').hidden=true;$('rulesEditing').hidden=false;}
    async function openCreator(cid,name,isCurrent=()=>true){
      if(!ready||busy||pendingRestore||!scopeCurrent()){status('请先在原范围接续保存或恢复，已有填写已保留。');return false;}
      if(!cid||!configAccounts.has(cid)||accountNames.get(cid)!==name){status(configMessage('RULES_CONFIG_ACCOUNT_UNAVAILABLE'));return false;}
      if(pendingSave){
        const draft=creations.get(scopeKey(cid));
        if(!draft||pendingSave.configuration?.creatorDraft!==draft||pendingSave.target.connection_id!==cid||selected!==cid||!isCurrent()){
          status('请先在原账号接续保存，原填写和操作已保留。');return false;
        }
        if(!pendingSave.commitAttempted&&!fields.every(f=>draft.fields[f]===pendingSave.configuration.fields[f]&&draft.inherit[f]===pendingSave.configuration.inherited?.[f])){
          status('原保存使用另一份快照，请先在原规则范围处理，当前填写已保留。');return false;
        }
        creatorEpoch++;draft.name=name;draft.isCurrent=isCurrent;creator=draft;renderCreator();
        if(!pendingSave.commitAttempted){
          // Explicitly reopening the same immutable draft may resume STAGED;
          // retain the original op, chunks and CAS versions, only renew its UI fence.
          const epoch=creatorEpoch,selection=selectionEpoch;
          pendingSave.configuration.valid=()=>creator===draft&&creatorEpoch===epoch&&creatorCurrent(draft)&&selectionEpoch===selection;
        }
        creatorNote('原保存结果待确认；请查询或接续原操作，不会另建提交。');return true;
      }
      const epoch=++creatorEpoch;remember();
      const changed=cid!==selected;
      if(!await selectScope(cid,{keepCreator:true,isCurrent:()=>isCurrent()&&epoch===creatorEpoch})||!isCurrent()||epoch!==creatorEpoch||!meta)return false;
      const read=changed&&lastRead?.connection_id===cid?lastRead:await load(true);
      if(!read||!isCurrent()||epoch!==creatorEpoch||selected!==cid||!configAccounts.has(cid)||accountNames.get(cid)!==name)return false;
      let draft=creations.get(scopeKey(cid));
      if(!draft){draft={cid,name,identity:scopeKey(),...creatorValues(read),editRevision:0};draft.saved=creatorFingerprint(draft);creations.set(draft.identity,draft);}
      const renamed=draft.name!==name;draft.name=name;
      draft.isCurrent=isCurrent;creator=draft;renderCreator();
      creatorNote((renamed?'账号显示名称已更新，原填写已保留。':'')+(draft.revision.store_revision!==meta.store_revision||draft.revision.scope_revision!==meta.scope_revision?'规则已更新，原填写已保留；保存不会覆盖新版本，可用最新规则重新填写。':'已读取本号完整有效规则。当前填写尚未保存；原规则页未保存编辑会保留。'));
      return true;
    }
    const creatorValues=read=>({
      fields:copied(read.combined),inherit:Object.fromEntries(fields.map(f=>[f,!Object.hasOwn(read.own,f)])),
      revision:{store_revision:read.current.store_revision,scope_revision:read.current.scope_revision,
        global_revision:read.effective.global_revision},
    });
    const uniqueName=name=>[...accountNames.values()].filter(value=>value===name).length===1;
    const creatorFingerprint=d=>JSON.stringify([d.fields,d.inherit]);
    async function configurationSnapshot(d,file=false){
      if(!creatorCurrent(d))throw new Error('RULES_CONFIG_TARGET_CHANGED');
      const value={format:'openahoy.production-preferences',schema_version:2,platform:'wechat_official_account',
        account_name:d.name,account_ref:d.cid,source:copied(d.revision),
        fields:Object.fromEntries(fields.map(f=>[f,{mode:d.inherit[f]?'inherit':'override',text:d.fields[f]}])),
        project:null,templates:templateReferences(d.fields.additional_notes)};
      const snapshot=configurationEnvelope(JSON.stringify(value),d.name,{cid:d.cid});
      if(file){
        const sources=await configurationSources?.(d.cid,value.templates);
        if(!creatorCurrent(d))throw new Error('RULES_CONFIG_TARGET_CHANGED');
        value.project=sources?.project??null;
        configurationEnvelope(JSON.stringify(value),d.name,{cid:d.cid});
      }
      return {...snapshot,value};
    }
    async function saveCreator(){
      const d=creator,epoch=creatorEpoch;if(!creatorCurrent(d)||busy)return;
      if(pendingSave&&pendingSave.configuration?.creatorDraft!==d){creatorNote('请先在原规则范围处理原保存，当前创建草稿已保留。');return;}
      fillRequest=null;$('creatorConfigFile').value='';
      try{
        if(verifications.has(d.identity)&&!pendingSave){
          const expected=verifications.get(d.identity);
          if(expected.creatorDraft!==d){creatorNote('另一份配置已提交且正在等待读回，请先在规则设置读取原结果；当前创建草稿已保留。');return;}
          const read=await load(true);
          if(creator===d&&epoch===creatorEpoch){
            if(read&&readbackMatches(read,expected)){
              d.saved=creatorFingerprint({fields:expected.fields,inherit:expected.inherited});
              d.revision=creatorValues(read).revision;
              creatorNote(d.saved===creatorFingerprint(d)?'原保存的八项有效规则已完整读回。':'原保存已完整读回；之后修改的填写尚未保存。');
            }else creatorNote('原保存已提交，但完整读回尚未确认；当前填写已保留，不会再次提交。');
          }
          return;
        }
        const snapshot=await configurationSnapshot(d),selection=selectionEpoch;
        const editorBuffer=dirty(d.cid)?copied(inputs()):null;
        const result=await save({kind:'configuration',name:d.name,fields:snapshot.fields,inherited:snapshot.inherit,
          revision:d.revision,editorBuffer,creatorDraft:d,
          valid:()=>creator===d&&creatorEpoch===epoch&&creatorCurrent(d)&&selectionEpoch===selection});
        if(creator!==d||creatorEpoch!==epoch)return;
        if(result?.verified){
          Object.assign(d,creatorValues(lastRead),{review:[]});d.saved=creatorFingerprint(d);
          renderCreator();creatorNote('已保存到「'+d.name+'」，八项有效规则已完整读回。'+(editorBuffer?'原规则页未保存编辑已保留。':''));
        }
        else if(result?.confirmed)creatorNote('保存已提交，八项完整读回尚未确认；再次点击只读取原结果。');
        else if(result?.pending)creatorNote('原保存结果待确认，填写与原操作已保留；请接续原保存，不会另建提交。');
        else{if(!editorBuffer){buffers.delete(d.identity);await load(false);}creatorNote(configMessage(result?.failure));}
      }catch(error){if(creator===d&&creatorEpoch===epoch)creatorNote(configMessage(error.message));}
      finally{creatorButtons();}
    }
    function configurationFilename(name){
      let stem=name.replace(/[\\/<>:"|?*\x00-\x1f\x7f]/g,'_').replace(/^\.+|[. ]+$/g,'')||'公众号配置';
      const suffix='.jiusera.json';while(encoder.encode(stem+suffix).length>255)stem=Array.from(stem).slice(0,-1).join('');return stem+suffix;
    }
    async function downloadCreator(){
      const d=creator,epoch=creatorEpoch;if(!creatorCurrent(d)||busy||d.downloading)return;
      d.downloading=true;creatorButtons();
      try{
        const querying=!!d.downloadPending,revision=d.editRevision,snapshot=querying?null:await configurationSnapshot(d,true),
          raw=querying?'':JSON.stringify(snapshot.value,null,2)+'\n',filename=configurationFilename(d.name);
        let result;
        if(downloadFile)result=await downloadFile(raw,filename,{connection_id:d.cid,queryOnly:querying});
        else{const url=URL.createObjectURL(new Blob([raw],{type:'application/json;charset=utf-8'})),link=document.createElement('a');try{link.href=url;link.download=filename;link.click();}finally{setTimeout(()=>URL.revokeObjectURL(url),0);}}
        d.downloadPending=result?.state==='CONFIG_EXPORT_PENDING';
        if(creator!==d||creatorEpoch!==epoch)return;
        if(d.downloadPending){creatorNote('本机导出结果待确认，原快照已保留；再次点击只查询原文件，不会新写。公众号配置未修改。');return;}
        if(result?.state==='CONFIG_EXPORT_NOT_FOUND'){creatorNote('上次导出未找到完整文件；填写已保留。可再次点击下载当前填写，公众号配置未修改。');return;}
        if(result?.state==='CONFIG_EXPORTED'&&result.destination==='Downloads'&&typeof result.filename==='string'&&result.filename){creatorNote('已保存到本机“下载”文件夹（~/Downloads）：'+result.filename+'。文件已完整读回核对。'+(result.from_query?'这是上次导出快照；之后的填写不包含在内，可再次下载当前填写。':d.editRevision!==revision?'这是点击时的快照，之后的填写未包含。':d.saved===creatorFingerprint(snapshot)?'内容与已保存的本号配置一致。':'当前填写尚未保存到公众号配置。'));return;}
        creatorNote('已请求下载「'+filename+'」。'+(d.editRevision!==revision?'文件为点击时的快照，之后的填写未包含。':d.saved===creatorFingerprint(snapshot)?'内容与已完整读回的本号配置一致。':'当前填写尚未保存到公众号配置。'));
      }catch(error){if(creator===d&&creatorEpoch===epoch)creatorNote(error.message==='RULES_DOWNLOAD_UNAVAILABLE'?'当前宿主未提供文件下载能力，填写已保留；未保存到公众号配置。':error.message==='RULES_DOWNLOAD_FAILED'?'宿主未完成下载，填写已保留；未保存到公众号配置。':error.message==='RULES_DOWNLOAD_UNKNOWN'?'宿主下载结果待确认，请查看下载目录；不会换通路重试，公众号配置未修改。':error.message==='CONFIG_EXPORT_INVALID'?'配置内容不符合非秘密文件格式，填写已保留。':error.message==='CONFIG_EXPORT_ACCOUNT_MISMATCH'?'账号名称与当前选择无法匹配，填写已保留。':configMessage(error.message));}
      finally{d.downloading=false;creatorButtons();}
    }
    $('creatorBack').addEventListener('click',closeCreator);$('creatorSave').addEventListener('click',saveCreator);$('creatorDownload').addEventListener('click',downloadCreator);
    $('creatorReset').addEventListener('click',async()=>{
      const d=creator,epoch=creatorEpoch;if(!creatorCurrent(d)||busy||pendingSave||pendingRestore)return;
      fillRequest=null;$('creatorConfigFile').value='';
      const read=await load(true);if(!read||creator!==d||creatorEpoch!==epoch||!creatorCurrent(d))return;
      Object.assign(d,creatorValues(read),{review:[]});d.editRevision++;d.saved=creatorFingerprint(d);verifications.delete(d.identity);renderCreator();creatorNote('已用最新有效规则替换当前填写，尚未保存。');
    });
    $('creatorFill').addEventListener('click',()=>{
      if(!creatorCurrent()||busy||pendingSave||pendingRestore)return;
      fillRequest={draft:creator,epoch:creatorEpoch,revision:creator.editRevision};$('creatorConfigFile').value='';$('creatorConfigFile').click();
    });
    $('creatorConfigFile').addEventListener('cancel',()=>{fillRequest=null;$('creatorConfigFile').value='';creatorNote('已取消文件填写，原草稿与规则保持不变。');});
    $('creatorConfigFile').addEventListener('change',async()=>{
      const req=fillRequest,file=$('creatorConfigFile').files?.[0];if(!req)return;
      try{
        if(!file)return;const raw=await readConfigurationFile(file);
        if(fillRequest!==req)return;
        if(busy||pendingSave||pendingRestore||creator!==req.draft||creatorEpoch!==req.epoch||creator.editRevision!==req.revision||!creatorCurrent())throw new Error('RULES_CONFIG_TARGET_CHANGED');
        const draft=creator,value=configurationEnvelope(raw,draft.name,{cid:draft.cid,unique:uniqueName(draft.name)});
        const sources=await configurationSources?.(draft.cid,value.templates);
        if(fillRequest!==req||creator!==draft||creatorEpoch!==req.epoch||draft.editRevision!==req.revision||!creatorCurrent())
          throw new Error('RULES_CONFIG_TARGET_CHANGED');
        draft.review=fields.flatMap((field,index)=>draft.inherit[field]===value.inherit[field]&&draft.fields[field]===value.fields[field]?[]:[
          [value.inherit[field]?'{0}：使用当前默认内容':value.fields[field]?'{0}：使用文件中的值':'{0}：清空本号值',ui.message(labels[index])]]);
        if(value.legacy)draft.review.push(['旧版文件无继承信息，八项会按本号值恢复。']);
        if(value.source?.global_revision!==undefined&&value.source.global_revision!==draft.revision.global_revision)
          draft.review.push(['默认规则已更新，使用默认内容的项目以当前规则为准。']);
        if(!value.legacy&&JSON.stringify(value.project)!==JSON.stringify(sources?.project??null))
          draft.review.push(['文件中的项目或 Skill 与现在不同。可在项目设置重新关联。']);
        Object.assign(draft,{fields:value.fields,inherit:value.inherit});draft.editRevision++;
        renderCreator();creatorNote('已预览文件中的配置，点击保存才会应用到本号。');
      }catch(error){if(fillRequest===req&&creator===req.draft&&creatorEpoch===req.epoch)creatorNote(configMessage(error.message));}
      finally{if(fillRequest===req){fillRequest=null;$('creatorConfigFile').value='';}}
    });
    $('rulesCreate').addEventListener('click',()=>openCreator(selected,accountNames.get(selected)));
    function clearScopeDisplay(){
      meta=null;lastRead=null;before=null;historyEnded=false;
      $('rulesPreview').textContent='';$('rulesHistory').replaceChildren();
      for(const field of fields){
        editors[field].value='';editors[field].setAttribute('data-source','');
        inherited[field].hidden=!selected;if(inherited[field].nextSibling.nodeType===Node.ELEMENT_NODE)inherited[field].nextSibling.hidden=!selected;
        inherited[field].checked=!!selected;ui.set(sources[field],'');summarize(field);
      }
      buttons();
    }
    function changeScope(cid,keepCreator){
      if(busy)return false;
      if(cid===selected&&scopeCurrent()){if(cid)cardAccount=cid;buttons();return true;}
      if(pendingSave||pendingRestore){status('原操作结果待确认，请先在原范围接续。');return false;}
      if(cid)cardAccount=cid;
      if(!keepCreator)closeCreator();
      position?.reset();
      remember();selectionEpoch++;generation++;selected=cid;selectedBinding=accountBindings.get(cid);$('rulesScope').value=cid;
      clearScopeDisplay();
      return true;
    }
    async function selectScope(cid,{keepCreator=false,isCurrent=()=>true}={}){
      // An explicit action can wait for a read, but cannot retarget the
      // editor after a different account was selected in the meantime.
      const intent=selectionEpoch,binding=accountBindings.get(cid);
      const valid=()=>ready&&intent===selectionEpoch&&binding===accountBindings.get(cid)&&isCurrent();
      while(readTask&&valid())await readTask.promise;
      if(!valid()||!changeScope(cid,keepCreator))return false;
      const accepted=selectionEpoch;
      if(!meta)await load();
      return ready&&accepted===selectionEpoch&&binding===accountBindings.get(cid)&&isCurrent();
    }
    function cancelNavigationRead(){
      if(!readTask?.navigation)return;
      generation++;readTask=null;busy=false;
    }
    async function stageAccountScope(cid,isCurrent){
      // Only a passive navigation read can be superseded. Originals from
      // save/restore and explicit editor reads retain their original scope.
      while(readTask&&!readTask.navigation)await readTask.promise;
      if(!isCurrent())return null;
      if(cid!==selected||!scopeCurrent())cancelNavigationRead();
      if(cid===selected&&readTask?.navigation)return true;
      return changeScope(cid,false);
    }
    async function loadAccountScope(cid){
      if(selected!==cid||meta)return;
      const binding=accountBindings.get(cid), changed=!scopeCurrent();
      if(changed&&readTask)await readTask.promise;
      const valid=()=>ready&&selected===cid&&!meta&&binding===accountBindings.get(cid)&&
        (!cid||accountBindings.has(cid));
      if(!valid())return;
      const result=await load(true,{navigation:true});
      if(changed&&valid()&&!scopeCurrent()&&!pendingSave&&!pendingRestore)
        return load(true,{navigation:true});
      return result;
    }
    function chooseConfiguration(cid,name,isCurrent=()=>true){
      if(!ready||busy||pendingSave||pendingRestore){status('请先接续原规则操作，当前编辑已保留。');return false;}
      if(!configAccounts.has(cid)){status(configMessage('RULES_CONFIG_ACCOUNT_UNAVAILABLE'));return false;}
      if(!cid||accountNames.get(cid)!==name||!isCurrent()){status(configMessage('RULES_CONFIG_TARGET_CHANGED'));return false;}
      if(cid===selected&&!scopeCurrent()&&!changeScope(cid,false))return false;
      if(dirty(cid)){status(configMessage('RULES_CONFIG_DIRTY'));return false;}
      remember();
      const req={cid,name,isCurrent,epoch:generation,scope:selected,binding:accountBindings.get(cid)};
      // Start the readonly snapshot, but open the picker synchronously while
      // this actual button click still owns browser user activation.
      req.snapshot=tool('own.production.rules.read',{connection_id:cid,scope:'account',view:'summary'}).then(value=>({value}),()=>({error:true}));
      importRequest=req;status('选择文件后将替换本号八项规则，空白项会显式清空；其他账号与平台默认不变。');$('rulesConfigFile').value='';$('rulesConfigFile').click();return true;
    }
    $('rulesConfigFile').addEventListener('cancel',()=>{importRequest=null;$('rulesConfigFile').value='';status('已取消加载，没有修改规则。');});
    $('rulesConfigFile').addEventListener('change',async()=>{
      const req=importRequest,file=$('rulesConfigFile').files?.[0];
      if(!req)return;
      const current=()=>importRequest===req&&req.isCurrent()&&configAccounts.has(req.cid)&&accountNames.get(req.cid)===req.name;
      const before=()=>current()&&generation===req.epoch&&selected===req.scope;
      let writeEpoch=null;
      try{
        if(!file){status('已取消加载，没有修改规则。');return;}
        const raw=await readConfigurationFile(file);
        if(!before())throw new Error('RULES_CONFIG_TARGET_CHANGED');
        const values=configurationEnvelope(raw,req.name,{cid:req.cid,unique:uniqueName(req.name)}),snapshot=await req.snapshot;
        await configurationSources?.(req.cid,values.templates);
        if(!before())throw new Error('RULES_CONFIG_TARGET_CHANGED');
        if(snapshot.error||snapshot.value.connection_id!==req.cid)throw new Error('RULES_CONFIG_READ_FAILED');
        if(dirty(req.cid))throw new Error('RULES_CONFIG_DIRTY');
        if(!await selectScope(req.cid,{isCurrent:current})||!meta)throw new Error('RULES_CONFIG_READ_FAILED');
        if(!current()||selected!==req.cid)throw new Error('RULES_CONFIG_TARGET_CHANGED');
        if(meta.store_revision!==snapshot.value.store_revision||meta.scope_revision!==snapshot.value.scope_revision)throw new Error('RULES_VERSION_CONFLICT');
        if(dirty(req.cid))throw new Error('RULES_CONFIG_DIRTY');
        writeEpoch=selectionEpoch;
        const identity=scopeKey();
        for(const field of fields){editors[field].value=values.fields[field];inherited[field].checked=values.inherit[field];summarize(field);}
        remember();
        const result=await save({kind:'configuration',name:req.name,fields:values.fields,inherited:values.inherit,
          valid:()=>req.isCurrent()&&configAccounts.has(req.cid)&&accountNames.get(req.cid)===req.name&&selected===req.cid&&selectionEpoch===writeEpoch});
        if(result&&!result.confirmed&&!result.pending&&current()&&
            selected===req.cid&&selectionEpoch===writeEpoch&&scopeKey()===identity){
          // A known noncommit keeps the old visible edit buffer; STAGED rows
          // may exist, but no effective head has been replaced.
          buffers.delete(identity);await load(false);
          if(current()&&selectionEpoch===writeEpoch&&scopeKey()===identity)status(configMessage(result.failure));
        }
      }catch(error){if(req.binding===accountBindings.get(req.cid))status(configMessage(error.message));}
      finally{if(importRequest===req){importRequest=null;$('rulesConfigFile').value='';}}
    });
    $('rulesScope').addEventListener('change',async()=>{if(busy||pendingSave||pendingRestore){$('rulesScope').value=selected;status('原操作尚在处理或结果待确认，请先在原范围接续。');return;}await selectScope($('rulesScope').value);});
    $('rulesAccountScope').addEventListener('click',()=>cardAccount&&selectScope(cardAccount));
    $('rulesDefaultScope').addEventListener('click',()=>selectScope(''));
    $('rulesSave').addEventListener('click',async()=>{
      if(!positionActive){await save();return;}
      if(pendingSave||!lastRead){const result=await save();if(result?.verified)manual.saved();return;}
      if(pendingRestore||busy)return;
      const field='audience_topics',values=inputs(),identity=scopeKey(),selectedAtSave=selected;
      const draft=values[field],fields={...lastRead.combined,[field]:draft.text};
      const inherited=Object.fromEntries(Object.keys(values).map(key=>[key,
        !!selected&&(key===field?draft.inherit:!Object.hasOwn(lastRead.own,key))]));
      delete values[field]; // Keep edits in other groups without committing them here.
      const result=await save({kind:'configuration',name:accountNames.get(selected)||'',fields,inherited,
        editorBuffer:values,verifyField:field,valid:()=>scopeKey()===identity&&selected===selectedAtSave&&scopeCurrent()});
      if(result?.verified)manual.saved();
    });
    $('rulesReload').addEventListener('click',()=>{remember();if(scopeCurrent())void load();else void loadAccountScope(selected);});
    $('rulesMore').addEventListener('click',history);$('rulesRestore').addEventListener('click',restore);
    async function applyTemplate(material,{connection_id:cid,name,isCurrent}){
      if(!ready||busy||pendingSave||pendingRestore)throw new Error('RULES_OPERATION_PENDING');
      if(!cid||!accountBindings.has(cid)||accountNames.get(cid)!==name||!isCurrent())throw new Error('RULES_CONFIG_TARGET_CHANGED');
      if(dirty(cid))throw new Error('RULES_CONFIG_DIRTY');
      if(!await selectScope(cid,{isCurrent})||!meta||!lastRead)throw new Error('RULES_CONFIG_READ_FAILED');
      if(!isCurrent()||selected!==cid||dirty(cid))throw new Error('RULES_CONFIG_TARGET_CHANGED');
      const values={...lastRead.combined},inherit=Object.fromEntries(fields.map(field=>[field,!Object.hasOwn(lastRead.own,field)]));
      const marker='[OpenAhoy template:'+material.id+'@'+material.version+'#'+material.manifest_sha256+']';
      if(values.additional_notes.includes(marker))return {alreadyApplied:true};
      for(const field of ['voice','image_preferences','visual_layout']){
        const text=material.supplements[field];if(typeof text!=='string'||!text)throw new Error('TEMPLATE_INVALID_MATERIAL');
        if(!values[field].includes(text)){values[field]+=(values[field]?'\n\n':'')+text;inherit[field]=false;}
      }
      // Remove only the machine reference to an older version of this same
      // template, keeping every custom paragraph and even its whitespace.
      values.additional_notes=values.additional_notes.replace(/\[OpenAhoy template:([a-z0-9-]+)@([0-9]+\.[0-9]+\.[0-9]+)#([a-f0-9]{64})\]/g,(whole,id)=>id===material.id?'':whole);
      values.additional_notes+=(values.additional_notes?'\n\n':'')+marker;inherit.additional_notes=false;
      const targetEpoch=selectionEpoch;
      return save({kind:'configuration',name,fields:values,inherited:inherit,
        revision:{store_revision:meta.store_revision,scope_revision:meta.scope_revision},
        valid:()=>isCurrent()&&selected===cid&&selectionEpoch===targetEpoch&&accountBindings.has(cid)&&accountNames.get(cid)===name});
    }
    async function applyStarter(material,{connection_id:cid,name,isCurrent}){
      if(!ready||busy||pendingSave||pendingRestore)throw Error('RULES_OPERATION_PENDING');
      if(!cid||!accountBindings.has(cid)||!isCurrent()||dirty(cid))throw Error('RULES_CONFIG_TARGET_CHANGED');
      if(!await selectScope(cid,{isCurrent})||!meta||!lastRead||dirty(cid))throw Error('RULES_CONFIG_READ_FAILED');
      const values={...lastRead.combined},inherit=Object.fromEntries(fields.map(k=>[k,!Object.hasOwn(lastRead.own,k)]));
      const changed=[];
      for(const [key,text] of Object.entries(material)){
        if(!Object.hasOwn(values,key)||Object.hasOwn(lastRead.own,key)||values[key].trim()||typeof text!=='string'||!text.trim())continue;
        values[key]=text;inherit[key]=false;changed.push(key);
      }
      if(!changed.length)return {alreadyApplied:true,changed};
      const targetEpoch=selectionEpoch;
      const result=await save({kind:'configuration',name,fields:values,inherited:inherit,
        revision:{store_revision:meta.store_revision,scope_revision:meta.scope_revision},
        valid:()=>isCurrent()&&selected===cid&&selectionEpoch===targetEpoch&&accountBindings.has(cid)});
      return {...result,changed};
    }
    function compactSummary(cid){
      if(!cid||cid!==selected||!meta||!lastRead)return null;
      return {scope_revision:meta.scope_revision,combined:{...lastRead.combined},pending:!!pendingSave||!!pendingRestore};
    }
    return {preview(){
        const available=!!meta&&!!selected&&scopeCurrent()&&lastRead?.connection_id===selected;
        if(!available)return null;
        if(creatorCurrent()){
          const values=Object.fromEntries(fields.map(f=>[f,creator.inherit[f]?displayed(f):creator.fields[f]]));
          return {available,dirty:creator.saved!==creatorFingerprint(creator),fields:values};
        }
        return {available,dirty:dirty(selected),fields:Object.fromEntries(fields.map(f=>[f,displayed(f)]))};
      },
      setReady(value,{deferRead=false}={}){ready=value;if(!value)selectionEpoch++;buttons();if(ready&&!deferRead)return load();},
      accounts(rows,choices){
        const bindings=new Map(rows.map(row=>[row.connection_id,JSON.stringify([row.account_id,row.binding_revision])]));
        const changed=selected&&accountBindings.get(selected)!==bindings.get(selected);
        if(changed){
          remember();selectionEpoch++;cancelNavigationRead();closeCreator();clearScopeDisplay();
          status('账号绑定已变化。原编辑与操作已保留。');
        }
        accountBindings=bindings;
        const current=selected;const box=$('rulesScope');box.replaceChildren();const global=document.createElement('option');global.value='';ui.set(global,'全局默认');box.append(global);
        accountNames=new Map(choices);configAccounts=new Set();
        for(const row of rows){
          const name=choices.get(row.connection_id),p=row.presentation;
          const automatic=p?.state==='MISSING'&&p.name_source==='REGISTRY_LABEL'&&typeof row.account_id==='string'&&name==='未命名公众号 · '+row.account_id.slice(-8);
          if(p&&!automatic&&['SAVED','MISSING','LEGACY'].includes(p.state)&&
            (['LOCAL_USER','REGISTRY_LABEL'].includes(p.name_source)||row.binding_provider==='WECHAT_THIRD_PARTY'&&row.state==='BOUND_IDLE')&&
            p.display_name===name&&typeof name==='string'&&name.trim())configAccounts.add(row.connection_id);
          const item=document.createElement('option');item.value=row.connection_id;item.textContent=name||'公众号';box.append(item);
        }
        if(current&&!rows.some(row=>row.connection_id===current)){const missing=document.createElement('option');missing.value=current;ui.set(missing,'原选择当前不可用');missing.disabled=true;box.append(missing);}box.value=current;buttons();},
      scope(){return selected;},selectScope,stageAccountScope,loadAccountScope,chooseConfiguration,openCreator,closeCreator,load,save,history,restore,applyTemplate,applyStarter,compactSummary,showGroup(index){if(index===0)position?.reset();workspace?.show(index);}};
  }
  globalThis.WCEProductionRules={mount,split,parseConfiguration};
})();
'''

JS = WORKSPACE_SCRIPT + POSITION_SCRIPT + JS
