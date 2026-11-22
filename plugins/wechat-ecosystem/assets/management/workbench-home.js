'use strict';

function JiuseraWorks(root,{render,meta,t}) {
  const feature=root.querySelector('[data-home-feature]');
  const list=root.querySelector('[data-home-list]');
  const prev=root.querySelector('[data-home-prev]');
  const next=root.querySelector('[data-home-next]');
  const count=root.querySelector('[data-home-count]');
  const gallery=feature.parentElement;
  let items=[],selected='',shown=null,manuallySelected=false;
  const rows=new Map();
  const node=(tag,text)=>{
    const element=document.createElement(tag);
    if(text!==undefined)element.textContent=text;
    return element;
  };

  function buildList(){
    rows.clear();
    const controls=items.map(item=>{
      const option=node('button');
      option.type='button';
      option.className='jh-work-option';
      option.title=item.title;
      const title=node('span',item.title),info=node('small',meta(item));
      info.className='jh-work-option-meta';
      option.append(title,info);
      option.onclick=()=>select(item.id,false,true);
      rows.set(item.id,option);
      return option;
    });
    list.replaceChildren(...controls);
  }

  function select(id,focus=false,manual=false){
    const index=items.findIndex(item=>item.id===id);
    const item=items[index];
    const snapshot=item?JSON.stringify(item):null;
    if(shown!==snapshot){
      feature.querySelector('video')?.pause();
      feature.replaceChildren();
      if(item)feature.append(render(item));
      shown=snapshot;
    }
    selected=item?.id||'';
    if(manual&&item)manuallySelected=true;
    for(const [id,option] of rows){
      if(id===selected)option.setAttribute('aria-current','true');
      else option.removeAttribute('aria-current');
    }
    count.textContent=item?(index+1)+' / '+items.length:'';
    for(const control of [prev,next])control.hidden=items.length<2;
    prev.setAttribute('aria-label',t('上一件作品'));
    next.setAttribute('aria-label',t('下一件作品'));
    gallery.hidden=!items.length;
    const active=rows.get(selected);
    if(active){
      const a=active.getBoundingClientRect(),container=list.getBoundingClientRect();
      if(a.top<container.top||a.bottom>container.bottom)list.scrollTop+=a.top-container.top;
      if(a.left<container.left||a.right>container.right)list.scrollLeft+=a.left-container.left;
      if(focus)active.focus({preventScroll:true});
    }
  }

  function step(direction,focus=false){
    if(!items.length)return;
    const index=items.findIndex(item=>item.id===selected);
    select(items[(index+direction+items.length)%items.length].id,focus,true);
  }
  prev.onclick=()=>step(-1);
  next.onclick=()=>step(1);
  list.onkeydown=event=>{
    const offset={ArrowLeft:-1,ArrowRight:1,ArrowUp:-1,ArrowDown:1}[event.key];
    if(!offset)return;
    event.preventDefault();
    step(offset,true);
  };
  return {
    setItems(nextItems){
      const before=list.contains(document.activeElement);
      const ids=items.map(item=>item.id).join('\0');
      items=nextItems;
      if(ids!==items.map(item=>item.id).join('\0'))buildList();
      else for(const item of items)rows.get(item.id).querySelector('.jh-work-option-meta').textContent=meta(item);
      manuallySelected=manuallySelected&&items.some(item=>item.id===selected);
      select(manuallySelected?selected:items[0]?.id,before);
    },
    pause(){feature.querySelector('video')?.pause();}
  };
}

function JiuseraRank(items,start,end) {
  const inPeriod=items.filter(item=>item.published>=start&&item.published<=end);
  const known=inPeriod.filter(item=>Number.isFinite(item.traffic));
  known.sort((first,next)=>next.traffic-first.traffic||
    next.published.localeCompare(first.published)||first.id.localeCompare(next.id));
  return {known,missing:inPeriod.filter(item=>!Number.isFinite(item.traffic))};
}

function JiuseraPlatformWorks(root,{render,meta,t,openMissing}) {
  const grid=root.querySelector('[data-platform-works]');
  const prev=root.querySelector('[data-platform-prev]');
  const next=root.querySelector('[data-platform-next]');
  const controls=prev.parentElement;
  const groups=new Map();
  function button(text){
    const node=document.createElement('button');
    node.type='button';node.textContent=text;
    return node;
  }
  function updateArrows(){
    const end=Math.max(0,grid.scrollWidth-grid.clientWidth);
    controls.hidden=end<3;
    prev.disabled=grid.scrollLeft<2;
    next.disabled=grid.scrollLeft>=end-2;
  }
  prev.setAttribute('aria-label',t('上一组平台'));
  next.setAttribute('aria-label',t('下一组平台'));
  prev.onclick=()=>grid.scrollBy({left:-grid.clientWidth-8});
  next.onclick=()=>grid.scrollBy({left:grid.clientWidth+8});
  grid.addEventListener('scroll',updateArrows,{passive:true});
  new ResizeObserver(updateArrows).observe(grid);
  grid.addEventListener('play',event=>{
    for(const media of grid.querySelectorAll('video'))if(media!==event.target)media.pause();
  },true);
  function makeGroup(platform){
    const card=document.createElement('section');
    card.className='jh-platform-work';
    const header=document.createElement('header');
    const title=document.createElement('h3');
    title.textContent=platform.label;
    const state=document.createElement('p');
    state.className='jh-empty';
    const info=document.createElement('details');
    info.className='jh-account-menu jh-rank-scope';
    const summary=document.createElement('summary'),notes=document.createElement('div');
    info.append(summary,notes);
    const nav=document.createElement('div');
    nav.className='jh-works-nav';
    const previous=button('‹'),following=button('›'),count=document.createElement('output');
    previous.className=following.className='jh-work-step';
    previous.dataset.homePrev=following.dataset.homeNext=count.dataset.homeCount='';
    count.setAttribute('aria-live','polite');
    nav.append(previous,count,following);
    header.append(title,info,nav);
    const body=document.createElement('div'),feature=document.createElement('div'),list=document.createElement('div');
    body.className='jh-gallery';
    feature.className='jh-feature';feature.dataset.homeFeature='';
    list.className='jh-work-list';list.dataset.homeList='';
    list.setAttribute('aria-label',t('作品排行'));
    body.append(feature,list);
    card.append(header,body,state);
    return {card,title,list,gallery:JiuseraWorks(card,{render,meta,t}),state,info,summary,notes};
  }
  return {
    setPlatforms(platforms){
      prev.setAttribute('aria-label',t('上一组平台'));
      next.setAttribute('aria-label',t('下一组平台'));
      const existing=new Set(platforms.map(row=>row.id));
      for(const [id,group] of groups){
        if(!existing.has(id)){group.gallery.pause();group.card.remove();groups.delete(id);}
      }
      platforms.forEach((platform,index)=>{
        let group=groups.get(platform.id);
        if(!group){group=makeGroup(platform);groups.set(platform.id,group);}
        if(grid.children[index]!==group.card)grid.insertBefore(group.card,grid.children[index]||null);
        const {card,title,list,gallery,state,info,summary,notes}=group;
        const {known,missing}=platform;
        title.textContent=platform.label;
        list.setAttribute('aria-label',t('作品排行'));
        card.toggleAttribute('data-many',known.length>1);
        gallery.setItems(known);
        state.hidden=known.length>0;state.textContent=platform.empty||'';
        info.hidden=!platform.note&&!missing.length;
        summary.textContent=missing.length?t('未回报')+' '+missing.length:t('覆盖');
        notes.replaceChildren();
        if(platform.note){
          const copy=document.createElement('p');
          copy.textContent=platform.note;
          notes.append(copy);
        }
        for(const item of missing){
          if(openMissing){
            const open=button(item.title);
            open.onclick=()=>{info.open=false;openMissing(item,summary);};
            notes.append(open);
          }else{
            const title=document.createElement('p');
            title.textContent=item.title;
            notes.append(title);
          }
        }
      });
      grid.hidden=!platforms.length;
      updateArrows();
    },
    pause(){for(const group of groups.values())group.gallery.pause();}
  };
}
