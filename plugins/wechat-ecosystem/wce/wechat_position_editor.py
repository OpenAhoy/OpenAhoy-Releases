"""Focused account-positioning controls backed by the existing rules draft."""

SCRIPT = r'''
function OAWechatPositionEditor(ui, area, inherit, source, onEdit, returnToOverview, groups, showGroup){
 const make=tag=>document.createElement(tag);
 const panel=make('section');panel.id='rulesPositionEditor';
 const main=make('div');main.className='wx-position-main';
 const advanced=make('details');advanced.className='wx-position-advanced';
 const advancedLabel=make('summary');ui.set(advancedLabel,'更多定位设置');
 const scopeSlot=make('div');scopeSlot.className='wx-position-scope';
 const suggestions=make('details'),suggestionsLabel=make('summary'),suggestionSlot=make('div');
 ui.set(suggestionsLabel,'查看可选方案和词条');suggestions.append(suggestionsLabel,suggestionSlot);
 const original=make('details'),originalLabel=make('summary');
 ui.set(originalLabel,'查看或编辑规则原文');original.append(originalLabel);
 const scoped=make('p');scoped.className='wx-position-state';scoped.append(source);
 const controls=make('div');controls.className='wx-position-actions';
 const back=make('button');back.type='button';ui.set(back,'返回配置总览');
 back.onclick=returnToOverview;
 const group=make('select');ui.attr(group,'aria-label','切换规则分组');
 for(const [index,title] of groups.entries()){const option=make('option');ui.set(option,index===0?'切换设置':title);group.append(option);}
 group.onchange=()=>showGroup(group.selectedIndex);
 controls.append(group,back);
 const inheritance=make('label');inheritance.className='wx-position-inherit';
 inheritance.append(inherit,ui.label('使用默认内容'));
 const context=make('div');context.className='wx-position-context';context.append(scoped);
 const example=make('p');example.className='wx-position-state';
 ui.set(example,'例如，写家庭录音的入门方法，给刚开始录音的人看。');
 const legacy=make('p');legacy.className='wx-position-state';legacy.hidden=true;
 ui.set(legacy,'已保留其他原有规则，可在「更多定位设置」中查看原文。');
 const keys=['主题','读者','内容形式','目标'];
 const editors=[];
 let projected='',locked=true,editing=null;
 function entries(text){
   return text.split('\n').map(line=>{
     const match=line.match(/^([ \t]*(主题|读者|内容形式|目标)[ \t]*[：:][ \t]*)(.*)$/u);
     return {line,key:match?.[2],prefix:match?.[1],value:match?.[3]};
   });
 }
 for(const [index,key] of keys.entries()){
   const label=make('label'),input=make('textarea');
   input.rows=1;input.autocomplete='off';
   ui.attr(input,'placeholder','未设置');
   label.append(ui.label(index===0?'写什么':index===1?'写给谁':key),input);
   (index<2?main:scopeSlot).append(label);
   editors.push({key,input});
   input.addEventListener('input',()=>{
     if(locked)return;
     const rows=entries(inherit.checked?projected:area.value);
     const last=rows.findLastIndex(row=>row.key===key);
     const values=input.value.split('\n').filter(value=>value.trim());
     const prefix=key+'：',next=[];
     let index=0;
     for(const [i,row] of rows.entries()){
       if(row.key!==key)next.push(row.line);
       else if(index<values.length)next.push(row.prefix+values[index++]);
       if(i===last)while(index<values.length)next.push(row.prefix+values[index++]);
     }
     if(last<0&&values.length){
       if(next.at(-1)==='')next.pop();
       next.push(...values.map(value=>prefix+value));
     }
     input.rows=Math.min(3,Math.max(1,input.value.split('\n').length));
     const updated=next.join('\n');
     if(updated===(inherit.checked?projected:area.value))return;
     area.value=updated;
     editing=input;
     try{onEdit();}finally{editing=null;}
   });
 }
 advanced.append(advancedLabel,scopeSlot,inheritance,suggestions,original);
 panel.append(context,example,main,legacy,advanced);
 function render(value,disabled,available,pending){
   projected=value;locked=disabled;
   const rows=entries(value);
   inheritance.hidden=inherit.hidden;
   for(const {key,input} of editors){
     const matches=rows.filter(row=>row.key===key);
     const value=matches.map(row=>row.value).join('\n');
     if(input!==editing){
       if(input.value!==value)input.value=value;
       input.rows=Math.min(3,Math.max(1,matches.length));
     }
     input.disabled=locked;
     ui.attr(input,'placeholder',pending?'保存后读取继承值':available?'未设置':'等待读取');
   }
   legacy.hidden=!rows.some(row=>row.line.trim()&&!row.key);
 }
 return {panel,controls,scopeSlot,suggestionSlot,original,render,reset(){
   advanced.open=false;suggestions.open=false;original.open=false;group.selectedIndex=0;
 }};
}
'''

STYLE = r'''
#rulesPositionEditor{display:grid;gap:14px}
.wx-position-main,.wx-position-scope{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
#rulesPositionEditor :is(.wx-position-main,.wx-position-scope) label{display:grid;gap:6px;margin:0;font-size:14px;font-weight:600;min-width:0}
#rulesPositionEditor :is(.wx-position-main,.wx-position-scope) textarea{
 box-sizing:border-box;width:100%;min-height:42px;margin:0;font-size:14px;font-weight:400;line-height:1.45;resize:vertical
}
.wx-position-controls,.wx-position-context,.wx-position-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.wx-position-context{justify-content:space-between}
.wx-position-state{margin:0;color:var(--muted);font-size:13px;line-height:1.5}
#rulesPositionEditor .wx-position-inherit{display:flex;align-items:center;gap:6px;margin:0}
.wx-position-inherit[hidden]{display:none!important}
.wx-position-advanced{padding-block:9px;border-block-start:1px solid var(--line)}
.wx-position-advanced>summary{cursor:pointer;font-weight:600}
.wx-position-advanced[open]>:not(summary){margin-block-start:12px}
.wx-position-scope>.rules-context{grid-column:1/-1}
#rulesPositionEditor .rule-input{min-height:125px}
#rulesPositionEditor .oa-choice-custom-value,#rulesPositionEditor .oa-choice-editor>details{display:none}
.wx-position-actions select{max-width:150px}
@media(max-width:540px){
 .wx-position-main,.wx-position-scope{grid-template-columns:1fr;gap:9px}
 #rulesPositionEditor{gap:10px}
 .wx-position-actions select{max-width:108px}
}
@media(max-width:400px){
 #rulesPositionEditor{gap:7px}
 .wx-position-advanced{padding-block:5px}
}
'''
