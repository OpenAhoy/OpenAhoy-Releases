'use strict';

function JiuseraTrend(root,t) {
  const ns='http://www.w3.org/2000/svg';
  const hues=[166,226,332,35,280,195,100,12,250,46,304,154,215,76,355,187];
  const platformHues={wechat_official_account:[161,199,52,301,133,178,218],x:[248,38,224,288,185],xiaohongshu:[19,340,311,358,34]};
  const dashes=['','','','','','8 4','2 4','11 4 2 4','5 3','12 4'];
  const materialId=root.id+'-material';
  const appearance=new Map();
  const color=row=>{
    const order=appearance.get(row.styleKey||row.id)||0,family=platformHues[row.platform]||hues;
    const hue=family[order%family.length];
    return 'hsl('+hue+' 75% 47%)';
  };
  const dash=row=>dashes[(appearance.get(row.styleKey||row.id)||0)%dashes.length];
  const node=(tag,cls,text)=>{
    const element=document.createElement(tag);
    if(cls)element.className=cls;
    if(text!==undefined)element.textContent=text;
    return element;
  };
  const button=(cls,text)=>{
    const element=node('button',cls,text);
    element.type='button';
    return element;
  };
  const graphic=(tag,attrs)=>{
    const element=document.createElementNS(ns,tag);
    for(const [key,value] of Object.entries(attrs))element.setAttribute(key,value);
    return element;
  };
  function surface(width,height){
    const filter=graphic('filter',{id:materialId,x:0,y:0,width,height,filterUnits:'userSpaceOnUse',
      'color-interpolation-filters':'sRGB'});
    const light=graphic('feSpecularLighting',{in:'profile',surfaceScale:3,specularConstant:.61,
      specularExponent:19,'lighting-color':'#fff',result:'reflection'});
    light.append(graphic('feDistantLight',{azimuth:225,elevation:52}));
    filter.append(graphic('feGaussianBlur',{in:'SourceAlpha',stdDeviation:.85,result:'profile'}),light,
      graphic('feComposite',{in:'reflection',in2:'SourceAlpha',operator:'in',result:'shine'}),
      graphic('feBlend',{in:'SourceGraphic',in2:'shine',mode:'screen'}));
    return filter;
  }
  const finite=Number.isFinite;
  const number=new Intl.NumberFormat();
  const compact=new Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1});
  const format=value=>finite(value)?number.format(value):t('未回报');
  const shortDate=date=>date.slice(-5).replace('-','/');
  const control=node('div','jtrend-controls'), heading=node('div','jtrend-heading');
  const title=node('h2','jtrend-title'), range=node('p','jtrend-range'), note=node('p','jtrend-hint');
  const stage=node('div','jtrend-stage'), graph=node('div','jtrend-graph');
  const panel=node('div','jtrend-panel'), panelTitle=node('span'), panelDate=node('strong');
  const panelCaption=node('div','jtrend-panel-caption'), close=button('jtrend-close');
  const readings=node('ul','jtrend-values'), status=node('span','jtrend-status');
  status.setAttribute('role','status');
  heading.append(title,range);
  control.append(heading);
  panelCaption.append(panelTitle,panelDate,close);
  panel.append(panelCaption,readings);
  stage.append(graph,panel);
  root.classList.add('jtrend');
  root.replaceChildren(control,stage,note,status);

  let model={dates:[],account:[]};
  let dateIndex=-1,pinned=false,pointedSeries='';
  let wide=false,lastWidth=0,lastHeight=0,restorePopupFocus=false;
  let syncSpotlight=()=>{},clearDate=()=>{};
  close.onclick=()=>clearDate(true);
  function sample(row){
    const swatch=graphic('svg',{viewBox:'0 0 22 10',class:'jtrend-sample','aria-hidden':'true'});
    swatch.append(graphic('path',{d:'M1 5H21',stroke:color(row),'stroke-dasharray':dash(row),fill:'none'}));
    return swatch;
  }
  function render(){
    title.textContent=model.title||t('日阅读趋势');
    note.textContent=model.hint||'';
    const dates=model.dates;
    const period=dates.length?(dates[0]===dates.at(-1)?dates[0]:dates[0]+' — '+dates.at(-1)):t('近 7 天');
    range.textContent=period+' · '+t('单位：人');
    close.textContent=t('收起明细');
    pointedSeries='';
    draw();
  }

  function draw(){
    graph.replaceChildren();readings.replaceChildren();
    lastWidth=graph.clientWidth;
    lastHeight=graph.clientHeight;
    const dates=model.dates, records=model.account;
    const values=records.flatMap(row=>row.values.filter(finite));
    const height=Math.max(42,lastHeight), left=36, right=wide?12:17, top=9, bottom=height-18;
    const width=Math.max(130,lastWidth);
    const areaWidth=width-left-right;
    const maxValue=Math.max(...values,1);
    const rawStep=maxValue/3;
    const power=Math.pow(10,Math.floor(Math.log10(rawStep)));
    const unit=[1,2,2.5,5,10].find(step=>step*power>=rawStep)*power;
    const axisStep=maxValue<=3?1:unit;
    const max=axisStep*3;
    const x=index=>dates.length===1?left+areaWidth/2:left+index*areaWidth/(dates.length-1);
    const y=value=>bottom-(bottom-top)*value/max;
    const svg=graphic('svg',{viewBox:'0 0 '+width+' '+height,role:'img','aria-label':title.textContent});
    const lines=graphic('g',{}), highlights=graphic('g',{}), definitions=graphic('defs',{});
    const pins=new Map();
    const beadFills=new Map();
    const marks=new Map();
    const cursor=graphic('line',{y1:top,y2:bottom,class:'jtrend-crosshair',visibility:'hidden'});
    const hasPlot=Boolean(dates.length&&values.length);
    let targets=[];
    graph.toggleAttribute('data-empty',!hasPlot);
    if(hasPlot){
      definitions.append(surface(width,height));
      svg.append(definitions);
      for(let tick=0;tick<=3;tick++){
        const amount=axisStep*tick;
        if(tick!==1)svg.append(graphic('line',{x1:left,x2:width-right,y1:y(amount),y2:y(amount),class:tick?'jtrend-gridline':'jtrend-baseline'}));
        const label=graphic('text',{x:left-8,y:y(amount)+3,'text-anchor':'end',class:'jtrend-axis'});
        label.textContent=amount>=1000?compact.format(amount):number.format(amount);
        svg.append(label);
      }
      const showEvery=Math.max(1,Math.ceil(dates.length/(wide?10:7)));
      dates.forEach((day,index)=>{
        if(index%showEvery&&index!==dates.length-1)return;
        const label=graphic('text',{x:x(index),y:height-5,'text-anchor':'middle',class:'jtrend-axis','data-tick':index});
        label.textContent=shortDate(day);
        svg.append(label);
      });
      svg.append(cursor,lines,highlights);
      for(const [index,row] of records.entries()){
        const segments=[];
        let segment=[];
        row.values.forEach((value,index)=>{
          if(finite(value))segment.push([x(index),y(value)]);
          else if(segment.length){segments.push(segment);segment=[];}
        });
        if(segment.length)segments.push(segment);
        if(!segments.length)continue;
        const group=graphic('g',{'data-series':row.id,class:'jtrend-series'});
        const path={d:segments.map(curve).join(' '),fill:'none',stroke:color(row),'stroke-dasharray':dash(row)};
        group.style.setProperty('--tube-color',path.stroke);
        group.append(graphic('path',{...path,class:'jtrend-line'}),
          graphic('path',{...path,class:'jtrend-tube-face',filter:'url(#'+materialId+')','aria-hidden':'true'}));
        const id=materialId+'-cap-'+index;
        const cap=graphic('radialGradient',{id,cx:'37%',cy:'25%',r:'76%'});
        for(const [offset,paint] of [['0%','#fff'],['24%',path.stroke],['100%','color-mix(in srgb,'+path.stroke+' 82%,#182235)']]){
          cap.append(graphic('stop',{offset,'stop-color':paint}));
        }
        definitions.append(cap);
        beadFills.set(row.id,'url(#'+id+')');
        lines.append(group);
        marks.set(row.id,group);
        const active=graphic('g',{class:'jtrend-focus-marks'});
        highlights.append(active);pins.set(row.id,active);
      }
      graph.append(svg);
      const hitArea=node('div','jtrend-dates');
      hitArea.style.insetBlock='0 '+(height-bottom-1)+'px';
      targets=dates.map((date,index)=>{
        const hit=button('jtrend-date',date);
        const start=index===0?Math.max(0,left-12):(x(index-1)+x(index))/2;
        const end=index===dates.length-1?Math.min(width,x(index)+16):(x(index)+x(index+1))/2;
        hit.style.left=(start/width*100)+'%';hit.style.width=((end-start)/width*100)+'%';
        hit.setAttribute('aria-label',date+' '+t('查看同日指标'));
        hit.tabIndex=index===(dateIndex<0?dates.length-1:dateIndex)?0:-1;
        hit.onpointerenter=event=>{if(!pinned&&event.pointerType==='mouse')selectDate(index,false);};
        hit.onfocus=()=>{if(!restorePopupFocus)selectDate(index,pinned);};
        hit.onclick=()=>selectDate(index,true,true);
        hit.onkeydown=event=>{
          let next=index;
          const keys={ArrowLeft:index-1,ArrowRight:index+1,Home:0,End:dates.length-1};
          if(event.key==='Escape'){event.preventDefault();clearDate(false);return;}
          if(!(event.key in keys))return;
          event.preventDefault();
          next=Math.max(0,Math.min(dates.length-1,keys[event.key]));
          targets[next].focus({preventScroll:true});
        };
        hitArea.append(hit);return hit;
      });
      hitArea.onpointerleave=()=>{
        if(!pinned&&!targets.includes(document.activeElement))clearDate(false);
      };
      hitArea.onfocusout=event=>{
        if(!pinned&&!targets.includes(event.relatedTarget)&&!panel.contains(event.relatedTarget))clearDate(false);
      };
      graph.append(hitArea);
    }else{
      const message=t('暂无已回报的日序列。');
      const empty=node('div','jtrend-empty');
      empty.append(graphic('svg',{viewBox:'0 0 30 22',class:'jtrend-empty-icon','aria-hidden':'true'}));
      empty.firstChild.append(graphic('path',{d:'M2 2v18h26M6 14l5-5 5 2 5-6 6 1',fill:'none',stroke:'currentColor'}));
      empty.append(node('p','',message));graph.append(empty);
    }

    function selectDate(index,lock,announce=false){
      if(dateIndex===index&&pinned===lock&&!announce)return;
      dateIndex=index;pinned=lock;
      if(announce)status.textContent=dates[index]+' · '+records.map(row=>row.label+' '+format(row.values[index])).join(' · ');
      update();
    }
    clearDate=restore=>{
      if(dateIndex===-1&&!pinned)return;
      if(restore){
        restorePopupFocus=true;
        targets[dateIndex]?.focus({preventScroll:true});
        restorePopupFocus=false;
      }
      dateIndex=-1;pinned=false;status.textContent='';update();
    };
    syncSpotlight=()=>{
      const preferred=pointedSeries||model.selected;
      const active=records.some(row=>row.id===preferred)?preferred:'';
      for(const row of records){
        const dim=Boolean(active&&active!==row.id);
        marks.get(row.id)?.classList.toggle('is-muted',dim);
        pins.get(row.id)?.classList.toggle('is-muted',dim);
      }
      for(const label of readings.children){
        label.classList.toggle('is-muted',Boolean(active&&active!==label.dataset.series));
        label.firstChild.setAttribute('aria-pressed',String(model.selected===label.dataset.series));
      }
    };
    function marker(row,index,value,active){
      const point=graphic('circle',{cx:x(index),cy:y(value),r:active?4.7:3.9,
        fill:beadFills.get(row.id)||color(row),class:'jtrend-point'});
      point.dataset.date=dates[index];point.dataset.series=row.id;point.dataset.value=String(value);
      return point;
    }
    function update(){
      pointedSeries='';
      const selected=hasPlot&&dateIndex>=0&&dateIndex<dates.length;
      const day=selected?dateIndex:dates.length-1;
      const activeDate=dates[day];
      panel.hidden=!records.length;
      const labelGap=20,labelCenter=27,maxLabelOffset=height-labelCenter-11;
      panel.classList.toggle('has-align',wide&&hasPlot&&(records.length-1)*labelGap<=maxLabelOffset-2);
      panelTitle.textContent=selected?t('同日读数'):activeDate?t('期末读数'):t('日读数');
      panelDate.textContent=activeDate?shortDate(activeDate):'';
      close.hidden=!(selected&&pinned);
      const rowsForDay=records.map((row,order)=>({row,order,value:row.values[day]}));
      for(const group of pins.values())group.replaceChildren();
      const aligned=panel.classList.contains('has-align');
      if(aligned){
        rowsForDay.sort((a,b)=>(finite(b.value)?b.value:-Infinity)-(finite(a.value)?a.value:-Infinity)||a.order-b.order);
        const min=2,maxY=maxLabelOffset,gap=labelGap;
        const offsets=rowsForDay.map(({value})=>finite(value)?Math.max(min,y(value)-labelCenter):maxY);
        for(let i=1;i<offsets.length;i++)offsets[i]=Math.max(offsets[i],offsets[i-1]+gap);
        for(let i=offsets.length-1;i>=0;i--)offsets[i]=Math.min(offsets[i],i===offsets.length-1?maxY:offsets[i+1]-gap);
        readings.style.setProperty('--reading-height',(height-19)+'px');
        readings.replaceChildren(...rowsForDay.map(({row,value},i)=>reading(row,value,offsets[i])));
        if(!selected){
          for(const [i,{row,value}] of rowsForDay.entries()){
            if(!finite(value))continue;
            const labelY=offsets[i]+labelCenter;
            pins.get(row.id)?.append(graphic('path',{d:'M'+(x(day)+4)+' '+y(value)+'L'+width+' '+labelY,
              stroke:color(row),fill:'none',class:'jtrend-leader'}));
          }
        }
      }else{
        readings.replaceChildren(...rowsForDay.map(({row,value})=>reading(row,value,null)));
      }
      if(hasPlot){
        cursor.setAttribute('visibility',selected?'visible':'hidden');
        cursor.setAttribute('x1',x(day));cursor.setAttribute('x2',x(day));
        svg.querySelectorAll('[data-tick]').forEach(label=>label.classList.toggle('is-active',selected&&Number(label.dataset.tick)===day));
        targets.forEach((hit,index)=>{
          hit.tabIndex=index===day?0:-1;
          hit.setAttribute('aria-pressed',String(pinned&&index===day));
        });
        for(const row of records){
          const group=pins.get(row.id);
          if(!group)continue;
          row.values.forEach((value,index)=>{
            if(!finite(value))return;
            const isolated=!finite(row.values[index-1])&&!finite(row.values[index+1]);
            if(index===day||isolated)group.append(marker(row,index,value,selected&&index===day));
          });
        }
      }
      syncSpotlight();
    }
    function reading(row,value,offset){
      const item=node('li');
      item.dataset.series=row.id;
      if(offset!==null)item.style.top=offset+'px';
      const key=button('jtrend-reading');
      const name=node('span','jtrend-reading-name',row.label);
      const amount=node('strong',finite(value)?'':'jtrend-missing',format(value));
      const mark=node('span','jtrend-platform',row.mark||'');
      mark.dataset.platform=row.platform;
      mark.setAttribute('aria-hidden','true');
      const accessible=[row.platformLabel,row.label,format(value)].filter(Boolean).join(' · ');
      name.title=row.label;
      key.title=accessible;
      key.setAttribute('aria-label',accessible);
      key.append(sample(row),mark,name,amount);
      key.onpointerenter=event=>{if(event.pointerType==='mouse'){pointedSeries=row.id;syncSpotlight();}};
      key.onpointerleave=()=>{if(document.activeElement!==key){pointedSeries='';syncSpotlight();}};
      key.onfocus=()=>{pointedSeries=row.id;syncSpotlight();};
      key.onblur=()=>{pointedSeries='';syncSpotlight();};
      key.onclick=()=>model.select?.(row.id);
      item.append(key);return item;
    }
    update();
  }
  function curve(points){
    let path='M'+points[0].join(' ');
    for(let i=1;i<points.length;i++){
      const [start,low]=points[i-1],[end,high]=points[i];
      const control=(end-start)*.30;
      path+='C'+[start+control,low,end-control,high,end,high].join(' ');
    }
    return path;
  }
  const resize=new ResizeObserver(()=>{
    if(!root.clientWidth)return;
    wide=root.clientWidth>=670;
    root.toggleAttribute('data-wide',wide);
    if(graph.clientWidth!==lastWidth||graph.clientHeight!==lastHeight)draw();
  });
  resize.observe(root);resize.observe(graph);
  return {update(next){
    const sameDates=model.dates.join()===next.dates.join();
    model=next;
    appearance.clear();
    const ordered=[...(model.identities||model.account)].sort((a,b)=>(a.styleKey||a.id).localeCompare(b.styleKey||b.id,'en'));
    const counts=new Map();
    for(const row of ordered){
      const order=counts.get(row.platform)||0;
      appearance.set(row.styleKey||row.id,order);
      counts.set(row.platform,order+1);
    }
    if(!sameDates){dateIndex=-1;pinned=false;}
    render();
  }};
}
