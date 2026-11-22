"""Presentation messages for the native management workspace."""
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
import json

from .own_branding import _PACKAGE


@lru_cache(maxsize=1)
def messages():
    return json.loads((_PACKAGE / 'assets/management/en.json').read_text(encoding='utf-8'))


class _Chrome(HTMLParser):
    """Mark known labels in the trusted, static workspace template only."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.ignored = []
        self.keys = messages()

    def handle_starttag(self, tag, attrs):
        source = self.get_starttag_text()
        if not self.ignored and tag not in ('style', 'svg', 'script', 'pre'):
            markers = ''.join(
                f' data-oa-copy-{name}="{escape(value, quote=True)}"'
                for name, value in attrs
                if name in ('aria-label', 'placeholder', 'title') and value in self.keys
            )
            if markers:
                end = -2 if source.endswith('/>') else -1
                source = source[:end] + markers + source[end:]
        if tag in ('style', 'svg', 'script', 'pre', 'textarea'):
            self.ignored.append(tag)
        self.parts.append(source)

    def handle_startendtag(self, tag, attrs):
        self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.ignored and self.ignored[-1] == tag:
            self.ignored.pop()
        self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        label = data.strip()
        if not self.ignored and label in self.keys:
            self.parts.append('<!--oa-copy-->')
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append(f'&{name};')

    def handle_charref(self, name):
        self.parts.append(f'&#{name};')

    def handle_comment(self, data):
        self.parts.append(f'<!--{data}-->')

    def handle_decl(self, decl):
        self.parts.append(f'<!{decl}>')


def mark_chrome(html):
    marker = _Chrome()
    marker.feed(html)
    marker.close()
    return ''.join(marker.parts)


def script():
    return SCRIPT.replace('__MESSAGES__', json.dumps(messages(), ensure_ascii=False).replace('<', '\\u003c'))


SCRIPT = r'''
globalThis.OAUI=(()=>{
 const en=__MESSAGES__,storageKey='openahoy.management.language';
 const nodes=new Map(),attributes=new Map();
 const listeners=new Set();
 const toggle=document.getElementById('oaLocale');
 let cleanupPending=false;
 let language='en';
 const message=(key,...values)=>({key,values});
 const list=keys=>keys.map(key=>message(key));
 const display=value=>Array.isArray(value)?value.map(display).join(' · '):value&&typeof value==='object'?format(value.key,value.values):String(value);
 try{
  const choice=localStorage.getItem(storageKey);
  if(choice==='zh-CN'||choice==='en')language=choice;
 }catch(_){}
 function format(key,values=[]){
  return (language==='en'&&Object.hasOwn(en,key)?en[key]:key)
    .replace(/\{(\d+)\}/g,(match,i)=>i<values.length?display(values[i]):match);
 }
 function cleanup(){
  if(cleanupPending)return;cleanupPending=true;
  queueMicrotask(()=>{cleanupPending=false;for(const registry of [nodes,attributes])for(const node of registry.keys())if(!node.isConnected)registry.delete(node);});
 }
 function set(node,key,...values){
  if(!node)return;
  // Emptying an element invalidates any earlier presentation binding.
  if(!key){nodes.delete(node);node.textContent='';return;}
  nodes.set(node,{key,values});node.textContent=format(key,values);cleanup();
 }
 function raw(node,value){nodes.delete(node);node.textContent=value;}
 function attr(node,name,key,...values){
  const fields=attributes.get(node)||{};fields[name]=message(key,...values);attributes.set(node,fields);
  node.setAttribute(name,format(key,values));cleanup();
 }
 function label(key,...values){const node=document.createTextNode('');set(node,key,...values);return node;}
 function scan(root){
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_COMMENT);
  for(let n=walker.nextNode();n;n=walker.nextNode()){
   if(n.data==='oa-copy'&&n.nextSibling?.nodeType===Node.TEXT_NODE&&!nodes.has(n.nextSibling)){
    const text=n.nextSibling;nodes.set(text,{key:text.data.trim(),values:[]});
   }
  }
  for(const name of ['aria-label','title','placeholder']){
   for(const el of root.querySelectorAll('[data-oa-copy-'+name+']')){
    const fields=attributes.get(el)||{};
    fields[name]=message(el.getAttribute('data-oa-copy-'+name));attributes.set(el,fields);
   }
  }
 }
 function render(){
  document.documentElement.lang=language;
  document.title=format('Jiusera · 工作台');
  for(const [node,{key,values}]of nodes){
   if(!node.isConnected)nodes.delete(node);
   else node.textContent=format(key,values);
  }
  for(const [node,fields]of attributes){
   if(!node.isConnected)attributes.delete(node);
   else for(const [name,value]of Object.entries(fields))node.setAttribute(name,display(value));
  }
  if(toggle){
   toggle.dataset.language=language;
   const action=language==='en'?'切换到中文':'Switch to English';
   toggle.setAttribute('aria-label',action);toggle.title=action;
  }
 }
 function select(value,save=true){
  if(language===value)return;
  language=value;
  if(save)try{localStorage.setItem(storageKey,value);}catch(_){}
  render();
  for(const notify of listeners)notify(language);
 }
 scan(document);
 if(toggle)toggle.addEventListener('click',event=>{
  event.stopPropagation();
  select(language==='en'?'zh-CN':'en');
 });
 window.addEventListener('storage',event=>{
  if(event.key===storageKey&&(event.newValue==='zh-CN'||event.newValue==='en'))select(event.newValue,false);
 });
 render();
 return {set,raw,attr,label,format,message,list,onChange(notify){listeners.add(notify);},scan(root){scan(root);render();}};
})();
'''

# The plain local safety view shares controls but may not load the locale selector.
FALLBACK = r''';globalThis.OAPlainUI ??= {
 set(node,text,...values){node.textContent=this.format(text,values);},
 raw(node,value){node.textContent=value;},
 message(key,...values){return this.format(key,values);},
 list(keys){return keys.join(' · ');},
 attr(node,name,key,...values){node.setAttribute(name,this.format(key,values));},
 label(text,...values){return document.createTextNode(this.format(text,values));},
 format(text,values=[]){return text.replace(/\{(\d+)\}/g,(match,i)=>i<values.length?String(values[i]):match);}
};
'''
