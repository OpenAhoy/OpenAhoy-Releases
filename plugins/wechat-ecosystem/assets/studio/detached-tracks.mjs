import { clipEditing } from "./clip-editing.mjs";
import { trackColor } from "./track-colors.mjs";

const engine = () => globalThis.OAIMWVideo;
const time = ms => (ms / 1000).toFixed(3) + " 秒";
const keyOf = data => JSON.stringify([data.project,data.work]);
const laneKey = row => JSON.stringify([row.clip_id,row.delivery_id,row.sha256]);

export function mountDetachedTracks(studio) {
  const heads = studio.$("detached-heads"), lanes = studio.$("detached-lanes");
  const tracks = new Map(), clips = new Map();
  const events = new AbortController();
  let retained, renderedScope = "", lastSelected = "", editFocus = false, geometryStamp = "";
  const snapshot = () => engine()?.detachedAudio?.();
  function scope(data = snapshot()) {
    if (!data?.project || !data.work) return null;
    const {project,work} = data;
    if (studio.imw.enabled()) {
      const body = document.body.dataset;
      if (project === body.imwProject && work === body.imwWork)
        return {project,work,offset:Number(data.offsetSeconds) || 0};
    } else if (data.folded && Array.isArray(data.selection) && data.selection.length===3 &&
      data.selection[0]===project && project===studio.project?.id &&
      data.selection[1]===(studio.song?.id || "") && data.selection[2]===(studio.version?.id || "")) {
      return {project,work,offset:Number(data.offsetSeconds) || 0};
    } else if (retained && retained.project === project && retained.work === work &&
      studio.project?.id === project && (studio.song?.id || "") === retained.song &&
      (studio.version?.id || "") === retained.version) {
      return {project,work,offset:retained.offset};
    }
    return null;
  }
  function remember() {
    const current = scope();
    retained = current && {...current,song:studio.song?.id || "",version:studio.version?.id || ""};
  }
  function selectionChanged() {
    if (!studio.imw.enabled() && retained && (studio.project?.id !== retained.project ||
      (studio.song?.id || "") !== retained.song || (studio.version?.id || "") !== retained.version)) retained = null;
    refresh();
  }
  function controlsEnabled() {
    const data = snapshot();
    return !!scope(data) && keyOf(data) === renderedScope && !data.busy;
  }
  function edit(id, value) {
    if (!controlsEnabled()) return;
    editFocus = true;
    return engine().editDetached(id,value);
  }
  function cursorMs() {
    return studio.imw.enabled() ? Math.round(1000*(engine()?.state?.()?.seconds || 0)) :
      Math.round(1000*(studio.seconds + (scope()?.offset || 0)));
  }
  function split(id) { if(id)edit(id,{split_at_ms:cursorMs()}); }
  function extent() {
    const data = snapshot(), current = scope(data);
    if (!current || !data.rows?.length) return 0;
    const end = Math.max(data.pictureMs || 0,...data.rows.map(row => row.start_ms + row.out_ms - row.in_ms));
    return Math.max(0,end/1000-current.offset);
  }
  function displayLength() {
    return studio.imw.enabled() ? studio.imw.displayLength() : studio.rulerLength;
  }
  function place(node, start, duration, length = displayLength()) {
    if (!(length > 0)) return;
    const offset = studio.imw.enabled() ? 0 : scope()?.offset || 0;
    node.style.left = 100*(start-offset)/length+"%";
    node.style.width = 100*duration/length+"%";
  }
  function layout() {
    const length = displayLength(), current = scope();
    const stamp = JSON.stringify([renderedScope,length,studio.imw.enabled(),current?.offset]);
    if (stamp === geometryStamp) return;
    geometryStamp = stamp;
    for (const {group,row} of clips.values()) place(group,row.start_ms/1000,(row.out_ms-row.in_ms)/1000,length);
  }
  function createTrack(key,row,index) {
    const lane = document.createElement("div");
    lane.className = "track-row detached-row";
    lane.setAttribute("role","group");
    const name = row.title ? "原声 · "+row.title : "分离原声";
    lane.setAttribute("aria-label",name);
    const activeId = () => {
      const id=snapshot()?.selected;
      return clips.get(id)?.trackKey === key ? id : lane.firstElementChild?.dataset.detachedId;
    };
    const controls=studio.makeTrackHead({
      id:"detached-"+row.id,name,row:lane,expanded:false,expand:()=>{},select:()=>edit(activeId(),"select"),
      shortcuts:[["在播放头分割",()=>split(activeId())],["移除片段",()=>edit(activeId(),"remove")]],
    });
    const actions=controls.head.querySelector(".track-actions");
    const volume=document.createElement("input");
    volume.type="range";volume.min="0";volume.max="100";volume.step="1";
    const label=document.createElement("label");label.textContent="音量";
    volume.setAttribute("aria-label",name+"音量");label.append(volume);actions.append(label);
    volume.oninput=()=>volume.setAttribute("aria-valuetext",volume.value+"%");
    volume.onchange=()=>edit(activeId(),{volume:Number(volume.value)});
    lane.style.setProperty("--tone",trackColor(index+3));
    controls.head.classList.add("detached-head");
    controls.head.style.setProperty("--tone",trackColor(index+3));
    lanes.append(lane);heads.append(controls.head);
    return {lane,head:controls.head,label:controls.label,actions,volume,activeId};
  }
  function createClip(row,track,trackKey) {
    const group=document.createElement("div"),button=document.createElement("button"),wave=document.createElement("span");
    group.className="clip-group";group.dataset.detachedId=row.id;
    button.type="button";button.className="clip";wave.className="detached-wave";button.append(wave);group.append(button);
    const item={row,group,button,wave,trackKey,waveKey:"",dispose:[]};
    const owner=renderedScope;
    const enabled=()=>owner===renderedScope && clips.get(row.id)===item && controlsEnabled();
    const value=()=>{
      const r=item.row;
      return {start:r.start_ms/1000,sourceIn:r.in_ms/1000,duration:(r.out_ms-r.in_ms)/1000,
        head:r.in_ms/1000,tail:Math.max(0,r.source_ms-r.out_ms)/1000,silenceHead:0,silenceTail:0};
    };
    function bind(control,action) {
      item.dispose.push(clipEditing.bind(control,{
        action,enabled,read:value,playhead:studio.clipPlayhead(),
        geometry:()=>({width:lanes.getBoundingClientRect().width,length:displayLength()}),
        constraints:()=>({rate:1000,frames:item.row.source_ms,timelineLimit:Infinity}),
        select:()=>edit(row.id,"select"),
        preview:v=>place(group,v.start,v.duration),
        cancel:()=>{const v=value();place(group,v.start,v.duration);},
        commit:v=>{
          if (enabled()) edit(row.id,{start_ms:Math.round(v.start*1000),in_ms:Math.round(v.sourceIn*1000),out_ms:Math.round((v.sourceIn+v.duration)*1000)});
          refresh();
        },
      }));
    }
    button.onclick=()=>edit(row.id,"select");bind(button,"move");
    for (const [edge,label] of [["head","裁切入点"],["tail","裁切出点"]]) {
      const handle=document.createElement("button");
      handle.type="button";handle.className="trim-handle "+edge;
      handle.setAttribute("aria-label",label+" · "+(row.title || "分离原声"));
      group.append(handle);bind(handle,edge);
    }
    track.lane.append(group);
    return item;
  }
  function clearClip(id,item) {
    for (const unbind of item.dispose) unbind();
    item.group.remove();clips.delete(id);
  }
  function refresh() {
    const data=snapshot(),current=scope(data);
    const next=current ? keyOf(current) : "";
    if (next!==renderedScope) {
      renderedScope=next;lastSelected="";editFocus=false;
      for(const [id,item] of clips)clearClip(id,item);
      for(const {lane,head} of tracks.values()){lane.remove();head.remove();}
      tracks.clear();
    }
    const rows=current ? data.rows || [] : [];
    const ids=new Set(rows.map(row=>row.id)),keys=new Set(rows.map(laneKey));
    for(const [id,item] of clips) if(!ids.has(id))clearClip(id,item);
    for(const [key,t] of tracks)if(!keys.has(key)){t.lane.remove();t.head.remove();tracks.delete(key);}
    for(const row of rows) {
      const key=laneKey(row);
      if(!tracks.has(key))tracks.set(key,createTrack(key,row,tracks.size));
      const t=tracks.get(key);
      if(!clips.has(row.id))clips.set(row.id,createClip(row,t,key));
      const item=clips.get(row.id);
      item.row=row;
      const waveKey=JSON.stringify([row.delivery_id,row.sha256,row.in_ms,row.out_ms,row.volume]);
      if(item.waveKey!==waveKey) {
        item.waveKey=waveKey;
        const wave=document.createElement("span");
        wave.className="detached-wave";item.wave.replaceWith(wave);item.wave=wave;
        engine().detachedWave(wave,row.id);
      }
      const selected=data.selected===row.id;
      item.group.toggleAttribute("data-selected",selected);item.button.setAttribute("aria-pressed",String(selected));
      item.button.setAttribute("aria-label",(row.title || "分离原声")+" · "+time(row.start_ms)+" · 时长 "+time(row.out_ms-row.in_ms));
      item.button.title=item.button.getAttribute("aria-label");
    }
    for(const t of tracks.values()){
      const selected=clips.get(data?.selected)?.group.parentElement===t.lane;
      t.head.toggleAttribute("data-selected",selected);
      t.label.setAttribute("aria-pressed",String(selected));
      t.label.toggleAttribute("data-selected",selected);
      const row=clips.get(t.activeId())?.row;
      if(row && studio.shadowRoot.activeElement!==t.volume)t.volume.value=row.volume;
      t.volume.setAttribute("aria-valuetext",t.volume.value+"%");
      t.lane.toggleAttribute("data-monitor-muted",data.sourceAudible===false || row?.volume===0);
    }
    studio.toggleAttribute("data-detached-audio",!!rows.length);
    geometryStamp="";layout();
    if (data?.selected && data.selected!==lastSelected && clips.has(data.selected)) {
      const panel=studio.$("track-scroll-panel"), row=clips.get(data.selected).group.parentElement;
      requestAnimationFrame(()=>{
        if(!row.isConnected || !current || keyOf(current)!==renderedScope)return;
        const box=row.getBoundingClientRect(),viewport=panel.getBoundingClientRect();
        if(box.bottom>viewport.bottom)panel.scrollTop+=box.bottom-viewport.bottom;
        else if(box.top<viewport.top)panel.scrollTop+=box.top-viewport.top;
      });
    }
    lastSelected=data?.selected || "";
  }
  document.addEventListener("jiusera:detached-audio-change",()=>{
    if(!studio.isConnected)return;
    refresh();
    if(!studio.imw.enabled() && extent()>studio.length)studio.grid();
  },{signal:events.signal});
  document.addEventListener("jiusera:imw-binding",refresh,{signal:events.signal});
  // Removing the last selected clip moves focus to the document. Its work still owns undo.
  document.addEventListener("keydown",e=>{
    if(studio.imw.enabled() || !editFocus || !studio.isConnected || !studio.getClientRects().length ||
      !controlsEnabled() || e.defaultPrevented || e.isComposing || e.altKey || !(e.metaKey || e.ctrlKey))return;
    const target=e.composedPath()[0];
    if(target.closest?.('input,textarea,select,[contenteditable="true"],dialog'))return;
    const key=e.key.toLowerCase();
    if(key!=="z" && key!=="y")return;
    e.preventDefault();e.stopPropagation();
    edit(snapshot()?.selected,e.shiftKey || key==="y"?"redo":"undo");
  },{capture:true,signal:events.signal});
  studio.shadowRoot.addEventListener("pointerdown",e=>{
    editFocus=!!e.target.closest?.("#detached-heads,#detached-lanes");
  },true);
  studio.shadowRoot.addEventListener("keydown",e=>{
    if(e.isComposing || e.defaultPrevented || !controlsEnabled() ||
      e.target.closest?.('input, textarea, [contenteditable="true"]'))return;
    const id=e.target.closest?.("[data-detached-id]")?.dataset.detachedId || snapshot()?.selected;
    const command=e.ctrlKey||e.metaKey;
    const onClip=!!e.target.closest?.("#detached-lanes");
    if (onClip && ((command && !e.shiftKey && e.key.toLowerCase()==="b") || (!command && !e.altKey && e.key.toLowerCase()==="b"))) {
      e.preventDefault();e.stopPropagation();split(id);return;
    }
    if (!studio.imw.enabled() && (onClip || e.target.closest?.("#detached-heads")) && e.code==="Space" && !command && !e.altKey && !e.shiftKey) {
      e.preventDefault();e.stopPropagation();if(!e.repeat)void studio.toggle();return;
    }
    if (onClip && !command && !e.altKey) {
      if(e.key==="Delete" || e.key==="Backspace"){e.preventDefault();e.stopPropagation();edit(id,"remove");}

    }
  },true);
  return {scope,extent,refresh,layout,remember,selectionChanged,dispose:()=>events.abort()};
}
