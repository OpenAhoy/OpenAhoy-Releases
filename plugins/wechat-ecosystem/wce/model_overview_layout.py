"""Single-viewport shelves for installed models and editorial recommendations."""

STYLE = r'''
.oa-native #wbModels:not([hidden]){
 display:block;overflow:clip;padding-bottom:calc(var(--wb-dock) + 4px)
}
#wbModels .wb-settings-content{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr)}
#wbModels .wb-settings-heading{margin-bottom:12px}
.wb-model-layout{
 display:grid;grid-template-columns:auto minmax(0,1fr);gap:18px;
 grid-template-rows:minmax(0,1fr);height:100%;max-width:none;margin:0;min-height:0;align-items:stretch
}
.wb-model-layout:where([data-stacked]){grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr);gap:10px}
.wb-model-mode,.wb-model-pager{align-items:center;gap:7px}
.wb-model-mode:not([hidden]),.wb-model-pager:not([hidden]){display:flex}
.wb-model-mode{justify-content:flex-start}
.wb-model-mode>button{min-height:40px}
.wb-model-mode>button[aria-pressed=true]{box-shadow:var(--wb-dock-inset)}
.wb-model-shelf:not([hidden]),.wb-model-news-shelf:not([hidden]){
 display:grid;grid-template-rows:minmax(0,1fr) auto;min-width:0;min-height:0
}
.wb-model-shelf{width:var(--wb-model-span,0px);justify-self:start}
.wb-model-layout[data-stacked] .wb-model-shelf{justify-self:center}
#wbModels :is(.wb-model-pager,.wb-model-mode,.wb-model-shelf,.wb-model-news-shelf,.wb-model-card,.wb-model-promo,.wb-model-story)[hidden]{display:none}
#wbModelGrid{
 --wb-model-card-edge:var(--wb-model-edge,148px);
 width:100%;max-width:none;grid-template-columns:repeat(var(--wb-model-columns,2),minmax(0,1fr));
 grid-auto-rows:var(--wb-model-card-edge);gap:var(--wb-model-gap,10px);align-content:start;justify-content:start
}
#wbModelGrid .wb-model-card{width:100%;height:100%;aspect-ratio:1}
#wbModelGrid[data-dense] .wb-model-tile{padding:5px 7px 2px;gap:1px}
#wbModelGrid[data-dense] .wb-model-tile-main{gap:1px}
#wbModelGrid[data-dense] .wb-model-tile-main strong{font-size:12px}
#wbModelGrid[data-dense] :is(.wb-model-spec,.wb-model-category,.wb-model-tile-foot){font-size:10px}
#wbModelGrid[data-dense] .wb-model-credential:not(:has(code:not([hidden]))){display:none}
#wbModelGrid[data-dense] .wb-model-link{margin:0 4px 4px;padding:3px 5px;font-size:11px}
#wbModels .wb-model-pager{justify-content:center;padding-top:5px;min-height:42px}
#wbModels .wb-model-pager button{display:grid;place-items:center;min-width:44px;min-height:44px;padding:4px;font-size:18px}
#wbModels .wb-model-pager button[aria-disabled=true]{opacity:.42;box-shadow:none;cursor:default}
.wb-model-pager output{min-width:4ch;text-align:center;font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}
#wbModelNews.wb-model-news-shelf{position:relative;width:100%;min-height:0;justify-self:stretch;outline-offset:3px}
.wb-model-layout:not([data-stacked]) #wbModelNews{height:min(100%,var(--wb-promo-height,100%));align-self:start}
.wb-model-promos{display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(0,1fr);gap:11px;width:100%;height:100%;min-height:0}
.wb-model-promos[data-composition=wide]{
 grid-template-columns:minmax(0,1fr) minmax(0,var(--wb-promo-square,170px)) minmax(0,1fr) minmax(0,1.33fr);
 grid-template-rows:repeat(3,minmax(0,1fr))
}
.wb-model-promos[data-composition=wide]>[data-spotlight=hero]{grid-column:1/4;grid-row:1/3}
.wb-model-promos[data-composition=wide]>[data-spotlight="0"]{grid-column:4;grid-row:1/4}
.wb-model-promos[data-composition=wide]>[data-spotlight="1"]{grid-column:1;grid-row:3}
.wb-model-promos[data-composition=wide]>[data-spotlight="2"]{grid-column:2;grid-row:3}
.wb-model-promos[data-composition=wide]>[data-spotlight="3"]{grid-column:3;grid-row:3}
.wb-model-promos[data-composition=pair]{grid-template-columns:repeat(2,minmax(0,1fr))}
.wb-model-promos[data-composition=triptych]{
 grid-template-columns:repeat(8,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr))
}
.wb-model-promos[data-composition=triptych]>[data-spotlight=hero]{grid-column:1/6;grid-row:1}
.wb-model-promos[data-composition=triptych]>[data-spotlight="0"]{grid-column:6/9;grid-row:1/3}
.wb-model-promos[data-composition=triptych]>[data-spotlight="1"]{grid-column:1/6;grid-row:2}
#wbModelNews .wb-model-promo,#wbModelNews .wb-model-story{min-height:0;position:relative;isolation:isolate;overflow:hidden}
#wbModelNews .wb-model-promo{display:grid;align-items:end;padding:clamp(15px,2vw,30px)}
#wbModelNews .wb-model-hero-art,#wbModelNews .wb-model-story-art{
 position:absolute;inset:0;width:100%;height:100%;object-fit:cover;aspect-ratio:auto;z-index:-2;border-radius:0
}
#wbModelNews .wb-model-hero-art{object-position:50% 52%}
#wbModelNews .wb-model-promo::before{display:block;background:
 linear-gradient(17deg,#09121cfa 0%,#09121cd9 19%,#09121c50 60%,#09121c0a 100%),
 linear-gradient(90deg,#09121c6f 0%,transparent 73%)}
#wbModelNews .wb-model-promo-body{width:min(100%,345px);gap:6px;padding:0}
.wb-model-promo-copy{color:#eef2f8}
#wbModelNews .wb-model-story{
 display:grid;align-content:end;align-items:end;grid-template-columns:minmax(0,1fr);
 gap:0;padding:clamp(10px,1.2vw,16px);color:#fff;background:#262431;border-color:#65637770
}
#wbModelNews .wb-model-story::before{
 content:"";position:absolute;inset:0;z-index:-1;
 background:linear-gradient(0deg,#11151efa 0%,#11151eea 24%,#11151e68 54%,#11151e00 100%)
}
#wbModelNews [data-spotlight="0"] .wb-model-story-art{object-position:48% 52%}
#wbModelNews [data-spotlight="2"] .wb-model-story-art{object-position:58% 44%}
#wbModelNews .wb-model-story h3{font-size:clamp(13px,1.2vw,19px);line-height:1.14;color:#fff;text-wrap:balance}
#wbModelNews .wb-model-story p,#wbModelNews .wb-model-story-foot{color:#f3f5fb}
#wbModelNews .wb-model-story-body{gap:5px}
#wbModelNews .wb-model-story-actions{align-items:center;gap:4px 9px}
#wbModelNews .wb-model-story-meta{font-size:11px;line-height:1.2}
#wbModelNews .wb-model-external{color:#f0f5ff;font-weight:650}
#wbModelNews .wb-model-inline-setup{background:#f2f5fbe8;color:#162034;font-weight:700;
 padding-inline:7px;text-align:start;white-space:normal}
#wbModelNews .wb-model-story-foot{gap:3px}
#wbModelNews .wb-model-promos[data-composition=wide]>[data-spotlight]:not([data-spotlight="0"]) .wb-model-story-summary,
#wbModelNews .wb-model-promos[data-composition=triptych]>[data-spotlight="1"] .wb-model-story-summary,
#wbModelNews .wb-model-promos[data-brief] .wb-model-story-summary{display:none}
#wbModelNews .wb-model-story-note{line-height:1.25}
#wbModelNews .wb-model-promos[data-brief] .wb-model-story-note:not(.wb-model-availability){display:none}
#wbModelNews .wb-model-promos[data-brief] .wb-model-promo-copy{display:none}
#wbModelNews .wb-model-promos[data-brief] #wbModelPromoSetup{min-height:36px}
#wbModels :is(.wb-model-pager,.wb-model-mode) button:focus-visible{outline:2px solid var(--wb-dock-focus);outline-offset:2px}
@media(pointer:coarse){
 .wb-model-mode>button,#wbModelNews .wb-model-promos[data-brief] #wbModelPromoSetup{min-height:44px}
}
'''

SCRIPT = r'''
function OAModelLayout(){
 const root=document.getElementById('wbModelLayout'),grid=document.getElementById('wbModelGrid'),
       shelf=root.querySelector('.wb-model-shelf'),news=document.getElementById('wbModelNews'),
       promos=news.querySelector('.wb-model-promos'),tabs=root.querySelector('.wb-model-mode'),
       cards=[...grid.children],stories=[...promos.children];
 const page={models:0,promo:0};
 const buttons=[...tabs.querySelectorAll('button')];
 let section='models',activeSize=''; 
 const cap=(number,lower,upper)=>Math.max(lower,Math.min(upper,number));
 function pager(name,count){
   const bar=root.querySelector('[data-model-pager='+name+']');
   const [prev,next]=bar.querySelectorAll('button');
   bar.hidden=count<=1;
   prev.setAttribute('aria-disabled',String(page[name]<=0));
   next.setAttribute('aria-disabled',String(page[name]>=count-1));
   bar.querySelector('output').value=(page[name]+1)+' / '+count;
   prev.onclick=()=>{if(page[name]>0){page[name]--;paint();}};
   next.onclick=()=>{if(page[name]<count-1){page[name]++;paint();}};
 }
 function paint(provider){
   const rect=root.getBoundingClientRect();
   if(rect.width===0||rect.height===0)return;
   const stacked=rect.width<850;
   root.toggleAttribute('data-stacked',stacked);
   tabs.hidden=!stacked;
   shelf.hidden=stacked&&section!=='models';
   news.hidden=stacked&&section!=='promo';
   for(const button of buttons)button.setAttribute('aria-pressed',String(button.dataset.modelDisplay===section));
   const available=Math.floor(rect.height)-(stacked?tabs.offsetHeight+10:0);
   const gap=stacked?10:12;
   const columns=stacked?(rect.width>=248?2:1):4;
   const maxModels=stacked?(columns===2?Math.floor((rect.width-gap)/2):155):
     Math.min(180,Math.floor((rect.width-(rect.width>=1350?560:380)-18-gap*(columns-1))/columns));
   let edge=Math.max(118,maxModels);
   if(!stacked)edge=cap(Math.min(edge,Math.floor((available-gap*2)/3)),118,180);
   const rowsWithNoPager=Math.max(1,Math.floor((available+gap)/(edge+gap)));
   const capacity=rowsWithNoPager*columns>=cards.length?rowsWithNoPager*columns:
     Math.max(1,Math.floor((available-50+gap)/(edge+gap)))*columns;
   const pages=Math.ceil(cards.length/capacity);
   page.models=cap(page.models,0,pages-1);
   const requested=provider?cards.findIndex(card=>card.querySelector('[data-model-id]').dataset.modelId===provider):-1;
   if(requested>=0)page.models=Math.floor(requested/capacity);
   root.style.setProperty('--wb-model-edge',edge+'px');
   root.style.setProperty('--wb-model-columns',columns);
   root.style.setProperty('--wb-model-gap',gap+'px');
   root.style.setProperty('--wb-model-span',edge*columns+(columns-1)*gap+'px');
   grid.toggleAttribute('data-dense',edge<138);
   cards.forEach((card,index)=>card.hidden=Math.floor(index/capacity)!==page.models);
   pager('models',pages);
   const mediaWidth=stacked?rect.width:rect.width-edge*columns-(columns-1)*gap-18;
   const modelRows=Math.ceil(Math.min(capacity,cards.length)/columns);
   const mediaHeight=stacked?available:modelRows*edge+(modelRows-1)*gap;
   root.style.setProperty('--wb-promo-height',mediaHeight+'px');
   root.style.setProperty('--wb-promo-square',Math.max(0,(mediaHeight-22)/3)+'px');
   const promoCount=stacked?1:mediaWidth>=680&&mediaHeight>=450?5:mediaHeight>=370?3:2;
   const promoPages=Math.ceil(stories.length/promoCount);
   page.promo=cap(page.promo,0,promoPages-1);
   const first=page.promo*promoCount;
   const shown=Math.min(promoCount,stories.length-first);
   promos.dataset.composition=shown===5?'wide':shown===3?'triptych':shown===2?'pair':'single';
   promos.toggleAttribute('data-brief',available<450||(!stacked&&mediaWidth<500));
   stories.forEach((card,index)=>card.hidden=Math.floor(index/promoCount)!==page.promo);
   pager('promo',promoPages);
 }
 for(const button of buttons)button.onclick=()=>{
   section=button.dataset.modelDisplay;
   paint();
 };
 const observer=new ResizeObserver(entries=>{
   const {width,height}=entries[entries.length-1].contentRect;
   const size=width+'x'+height;
   if(size!==activeSize){activeSize=size;paint();}
 });
 observer.observe(root);
 return {paint};
}
'''
