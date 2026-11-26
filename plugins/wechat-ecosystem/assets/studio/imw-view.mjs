import { trackColor } from "./track-colors.mjs";
// Keep the original editor nodes and listeners alive as the workstation switches views.
export function mountVideoView(studio) {
  const $ = studio.$;
  const original = new Map();
  let showOriginal = false, activeTrack = "";
  let boundKey = "", lastScale = "", selectedLane = "";
  let audioViewport=0, viewportGain=0;
  const audioScale=()=>audioViewport*(studio.draft?.zoom || 1)/studio.fitLength;
  const laneHeaders = new Map();
  const originalTrack = "@video-original";
  let observer, sourceObserver, projectObserver, resize, frame = 0, sourceFrame = 0;
  let videoProject = "", videoSong = null, archivedInert = false;
  function syncProject() {
    if (!enabled()) return;
    const source=document.getElementById("directorProject");
    const project=videoProject || source?.value || "";
    const option=source && [...source.options].find(o=>o.value===project);
    const name=option?.text || studio.projects?.find(p=>p.id===project)?.name;
    const button=$("imw-project");
    button.textContent=name || (project ? "视频项目" : "选择视频项目");
    button.dataset.project=project;
    button.title=name ? "切换视频项目 · "+name : "切换视频项目";
    const s=selection();
    const matches=videoSong && s && videoSong.project===project && s.project===project &&
      videoSong.song===s.song && videoSong.version===s.version;
    studio.toggleAttribute("data-imw-song",!!matches);
    if (!matches && $("songs").classList.contains("open")) studio.drawer(false);
  }
  function setProject(project,song) {
    videoProject=project || ""; videoSong=song || null;
    syncProject();
    if (enabled()) updateRows();
  }
  function createLaneHeaders() {
    if (laneHeaders.size) return;
    const seek = () => engine()?.seek?.(0);
    const definitions = [
      ["video","视频","dmCutStrip",null,[
        ["定位起点",seek],
      ]],
      ["original","镜头原声","imw-original-track","source",[
        ["定位起点",seek],["收起此轨",()=>{showOriginal=false;updateRows();}],
      ]],
    ];
    for (const [id,name,rowID,bus,shortcuts] of definitions) {
      const row=$(rowID)||document.getElementById(rowID)||$("imw-folded-video");
      const controls=studio.makeTrackHead({
        id:"imw-"+id,name,row,shortcuts,expanded:false,
        monitor:bus ? action=>engine()?.toggleMonitor?.(bus,action) : null,
        expand:value=>{
          if(id!=="original") studio.style.setProperty("--imw-"+id+"-row-height",
            value ? "calc(var(--track-height) + var(--track-action-height))" : "var(--track-height)");
          scheduleMeasure();
        },
        select:()=>selectLane(id),
      });
      controls.head.id=id==="video"?"imw-video-label":"imw-"+id+"-head";
      controls.bus=bus;
      laneHeaders.set(id,controls);
      if(id==="video") {
        controls.label.onclick=()=>videoToggle?.click();
        controls.label.setAttribute("aria-controls","imw-screen");
        controls.label.setAttribute("aria-expanded","false");
        controls.head.querySelector(".track-actions").hidden=true;
        $("imw-video-header").append(controls.head);
      } else $("imw-lane-labels").append(controls.head);
    }
    for (const [name,slot] of [["video",4],["source",5]])
      studio.style.setProperty("--imw-"+name+"-tone",trackColor(slot));
  }
  function paintSelection() {
    for (const [id,{label}] of laneHeaders) {
      label.toggleAttribute("data-selected",id===selectedLane);
      label.setAttribute("aria-pressed",String(id===selectedLane));
    }
    if (selectedLane) for (const label of studio.trackHeads?.values() || []) {
      label.removeAttribute("data-selected");label.setAttribute("aria-pressed","false");
    }
  }
  function selectLane(id) { selectedLane=id;paintSelection(); }
  function monitorHeaders() {
    if (!enabled()) return;
    for(const {bus,solo,mute,...parts} of laneHeaders.values()) {
      if(!bus) continue;
      const state=engine()?.monitorState?.(bus);
      const audio=!!document.querySelector("#dmCutStrip .dc-source-wave");
      solo.disabled=mute.disabled=!audio || !state;
      studio.paintTrackMonitor({...parts,solo,mute},state || {audible:true,mute:false,solo:false});
    }
  }
  function sourceRow() {
    sourceFrame=0;
    if (!enabled()) return;
    const clips = [...document.querySelectorAll("#dmCutStrip button[data-clip]")];
    const available = clips.some(clip => clip.querySelector(".dc-source-wave"));
    const show = available && showOriginal;
    laneHeaders.get("original").head.hidden = $("imw-original-track").hidden = !show;
    const row = $("imw-original-track"); row.replaceChildren();
    if (show) {
      let start=0;
      for (const clip of clips) {
        const width=parseFloat(clip.closest(".clip-group")?.style.width || clip.style.width) || 0;
        const group=document.createElement("div");
        group.className="clip-group";group.style.left=start+"%";group.style.width=width+"%";
        group.style.setProperty("--tone","var(--imw-source-tone)");start+=width;
        const wave=clip.querySelector(".dc-source-wave");
        const item=document.createElement("button");
        item.className="clip";item.type="button";item.ariaLabel=clip.title || "定位镜头";
        item.onclick=()=>{clip.click();selectLane("original");};
        if (wave) {
          const shape=wave.querySelector("svg")?.cloneNode(true);
          if (shape)item.append(shape);else item.textContent=wave.textContent;
          item.title=wave.title;
        }
        group.append(item);row.append(group);
      }
    }
    const choice=$("imw-add-track");
    choice.hidden=!available||show;
    if (!choice.options.length) choice.add(new Option("＋ 显示镜头原声",""));
    if (choice.options.length===1) choice.add(new Option("镜头原声",originalTrack));
    choice.value="";
    monitorHeaders();
  }
  const enabled = () => studio.hasAttribute("data-imw-video");
  const engine = () => globalThis.OAIMWVideo;
  const selection = () => studio.project && {
    project: studio.project.id, song: studio.song?.id, version: studio.version?.id,
  };
  function trackSelection() {
    const current=selection();
    return enabled() && videoSong && current?.project===videoProject &&
      videoSong.project===current.project && videoSong.song===current.song &&
      videoSong.version===current.version ? current : null;
  }
  function scoreWindow(clock) {
    const music=clock?.music;
    const source=engine()?.audioBinding?.();
    const take=trackSelection();
    return music && document.body.dataset.imwMusicSha===music.sha256 &&
      source && take && source.project===take.project &&
      source.song===take.song && source.version===take.version ? music : null;
  }
  const offset = clock => {
    const window=scoreWindow(clock);
    return window ? (window.start_ms-window.in_ms)/1000 : 0;
  };
  function measures() {
    if (!enabled()) return;
    const cut=document.getElementById("dmCut");
    const monitorHeight=$("imw-screen").clientHeight;
    const extraHeight=$("imw-original-track").getBoundingClientRect().height;
    if (monitorHeight>0) studio.style.setProperty("--imw-frame-fit",
      (100*monitorHeight/(monitorHeight+extraHeight)).toFixed(3)+"cqw");
    studio.toggleAttribute("data-imw-empty-video",cut.hidden||document.getElementById("dmCutTracks").hidden);
  }
  function selectStem(track) {
    if (!track) return;
    activeTrack=track.id;
    selectLane("");
    for (const [id,label] of studio.trackHeads || [])
      label.parentElement.toggleAttribute("data-imw-current",id===activeTrack);
  }
  function currentKey() {
    return JSON.stringify([document.body.dataset.imwWork,trackSelection()]);
  }
  function updateRows() {
    if (!enabled()) return;
    const key=currentKey(), changed=boundKey!==key;
    if (changed) {showOriginal=false;boundKey=key;selectedLane="";activeTrack="";}
    const tracks=trackSelection() ? studio.version?.tracks || [] : [];
    const ids=new Set(tracks.map(track=>track.id));
    if (!ids.has(activeTrack)) activeTrack=tracks[0]?.id || "";
    for (const el of studio.shadowRoot.querySelectorAll("[data-track-row]")) {
      const id=el.dataset.trackRow;
      el.toggleAttribute("data-imw-track",ids.has(id));
      if (el.classList.contains("track-head")) el.toggleAttribute("data-imw-current",id===activeTrack);
    }
    studio.toggleAttribute("data-imw-stems",!!tracks.length);
    studio.toggleAttribute("data-imw-compact",tracks.length>1);
    studio.toggleAttribute("data-imw-dense",tracks.length>=12);
    $("regions").style.setProperty("--imw-parts",String(tracks.length||1));
    $("imw-empty-tracks").hidden=!!tracks.length;
    if (tracks.length && (!studio.selected || studio.selected.id!==activeTrack)) {
      studio.selected=tracks.find(track=>track.id===activeTrack);
      studio.selectedPart=0;
      studio.updateSelection();
    }
    sourceRow();paintSelection();syncClock(engine()?.state?.());scheduleMeasure();
  }
  function scheduleMeasure() {
    if (!frame) frame = requestAnimationFrame(()=>{
      frame=0;
      measureAxis();syncClock(engine()?.state?.());measures();
      // Track loading rebuilds hidden canvases before the selected lanes become visible again.
      if (enabled()) studio.paint();
    });
  }
  function measureAxis() {
    if (!enabled()) return;
    const reference=$("imw-audio-fit");
    const nativeWidth=reference.lastElementChild.getBoundingClientRect().width;
    const labelWidth=reference.firstElementChild.getBoundingClientRect().width;
    if (!(nativeWidth>0 && labelWidth>0)) return;
    const value=labelWidth+"px";
    if (studio.style.getPropertyValue("--imw-label-width")!==value)
      studio.style.setProperty("--imw-label-width",value);
    audioViewport=nativeWidth;
    viewportGain=Math.max(0,$("scroll").getBoundingClientRect().width-nativeWidth);
  }
  // Extend only the display axis. The extra visible width must not stretch clips or change playback length.
  function extendDisplayLength(base) {
    return audioViewport>0 && trackSelection() ? base+viewportGain/audioScale() : base;
  }
  function displayLength(clock=engine()?.state?.()) {
    const film=Number(clock?.displayLength || clock?.length) || 0;
    const source=studio.rulerLength+Math.max(0,offset(clock));
    return trackSelection() ? Math.max(film,extendDisplayLength(Math.max(source,Number(clock?.length)||0))) : film;
  }
  function syncClock(clock) {
    if (!enabled() || !clock) return;
    if (boundKey !== currentKey()) return updateRows();
    const length=displayLength(clock);
    const start = offset(clock);
    const scale=[length,start,studio.rulerLength,audioScale()].join(":");
    if (lastScale !== scale) {
      lastScale=scale;
      if (trackSelection() && audioViewport>0) $("lane").style.width=length*audioScale()+"px";
      else $("lane").style.width="100%";
      studio.drawRuler();
      if (length > 0) {
        $("regions").style.width = 100 * studio.rulerLength / length + "%";
        $("regions").style.left = 100 * start / length + "%";
      }
      engine()?.syncGeometry?.();
      studio.detachedTracks?.layout();
    }
    if(length>0) {
      $("playhead").style.left=100*clock.seconds/length+"%";
      $("seek").max=clock.length;$("seek").value=clock.seconds;
      $("seek").setAttribute("aria-valuetext",clock.seconds.toFixed(2)+" 秒");
    }
    studio.frameRuler?.sync(clock);
  }
  function togglePanel(tab) {
    const node = document.querySelector('[data-dt-tab="' + tab + '"]');
    if (!node) return;
    if (node.getAttribute("aria-pressed") !== "true") node.click();
    studio.setAttribute("data-imw-inspector","");
    $("imw-inspect").setAttribute("aria-expanded","true");
  }
  $("imw-project").onclick=()=>{
    const work=document.getElementById("daWork"), select=document.getElementById("directorProject");
    if (!work || !select) return;
    studio.setAttribute("data-imw-inspector","");
    $("imw-inspect").setAttribute("aria-expanded","true");
    work.open=true;select.focus();
  };
  const videoToggle=document.getElementById("imw-video-toggle");
  if (videoToggle) videoToggle.onclick=()=>document.dispatchEvent(new CustomEvent("jiusera:imw-video-toggle",{
    detail:{enabled:studio.disclosure.reversing()||(!enabled()&&!studio.hasAttribute("data-imw-opening")),selection:selection()},
  }));
  $("imw-folded-video").onclick=()=>{
    if(enabled()) togglePanel("media");
    else videoToggle?.click();
  };
  createLaneHeaders();
  const audioTab=document.querySelector('#directorMonitor [data-dt-tab="audio"]');
  function openTrackSettings(event) {
    if (!enabled()) return;
    event?.preventDefault();
    event?.stopImmediatePropagation();
    const label=trackSelection() && studio.trackHeads?.get(activeTrack);
    if (!label) { $("imw-empty-tracks").focus({preventScroll:true});return; }
    if (label.getAttribute("aria-expanded")!=="true") label.click();
    label.focus({preventScroll:true});
  }
  $("imw-score-settings").onclick = openTrackSettings;
  $("imw-captions").onclick = () => { studio.drawer(false); togglePanel("captions"); };
  $("imw-inspect").onclick = () => $("imw-inspect").setAttribute("aria-expanded",
    String(studio.toggleAttribute("data-imw-inspector")));
  document.addEventListener("jiusera:imw-monitor", monitorHeaders);
  studio.addEventListener("click",e=>{
    if(!enabled())return;
    const el=e.composedPath()[0];
    if(el.closest?.("#dmCutStrip"))selectLane("video");
    if(el.matches?.(".track-row[data-imw-track]")) {
      const track=studio.version.tracks.find(t=>t.id===el.dataset.trackRow);
      if(track)studio.selectClip(track);
    }
  });
  studio.shadowRoot.addEventListener("focusin",event=>{
    if(!enabled())return;
    const group=event.target.closest?.("#regions .clip-group");
    const track=group && studio.version?.tracks.find(t=>t.id===group.dataset.track);
    if(track && (studio.selected!==track || studio.selectedPart!==Number(group.dataset.part))) {
      studio.selectClip(track, Number(group.dataset.part));
    }
  });
  $("imw-add-track").onchange = e => {
    if (e.target.value===originalTrack) showOriginal=true;
    updateRows();
  };
  document.addEventListener("jiusera:imw-clock", e=>syncClock(e.detail));
  document.addEventListener("jiusera:imw-binding", () => {
    if (enabled()) {syncProject();updateRows();engine()?.refreshMix?.();}
  });
  // The timeline consumes playback hotkeys at capture. A focusable, empty or loading
  // projection still owns Space so the browser never scrolls the workstation underneath.
  studio.shadowRoot.addEventListener("keydown", event => {
    if (!enabled() || event.defaultPrevented || event.isComposing || event.key !== " " ||
        event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const target=event.composedPath()[0];
    if (target?.isContentEditable || target?.closest?.("textarea,[role=textbox],dialog[open],input:not([type=range]):not([type=button])")) return;
    event.preventDefault();
    if (!event.repeat && engine()?.state?.()?.ready) engine().toggle(event);
  });
  function move(id,name) {
    const el=typeof id==="string"?document.getElementById(id):id, mark=document.createComment(name);
    el.before(mark); original.set(el,mark); el.slot=name; studio.append(el);
  }
  function setMode(on) {
    if (on === enabled()) return;
    if (on && (!document.getElementById("directorMonitor") || !document.getElementById("dmCut"))) return;
    const clock = engine()?.state?.();
    const previousHeight=studio.disclosure.takeHeight();
    const scrollLeft=studio.frameRuler.audioScroll();
    if (on) {
      studio.stopAndRemember(); studio.$("master-aac-player").pause();
      studio.trackEditor.closeMenu(); studio.trackEditor.foldForVideo(true);
      move("directorMonitor","imw-video"); move("dmCut","imw-timeline");move("dmCutMusicLane","imw-archived-score");
      const fields=document.querySelector("#dmCutSettings > .dc-music");
      if(fields)move(fields,"imw-archived-score-settings");
      if(audioTab?.getAttribute("aria-pressed")==="true")audioTab.click();
      audioTab?.addEventListener("click",openTrackSettings,true);
      const archived=document.getElementById("dmCutMusicLane");
      archivedInert=archived.inert;archived.inert=true;
      studio.setAttribute("data-imw-video","");
      measureAxis();
      laneHeaders.get("video").label.setAttribute("aria-expanded","true");
      $("imw-folded-video").setAttribute("aria-expanded","true");
      $("imw-folded-video").setAttribute("aria-label","添加视频素材");
      $("imw-folded-video").firstElementChild.textContent="添加视频素材";
      studio.transport.activateVideo();
      syncProject();
      const projects=document.getElementById("directorProject");
      if (projects) {
        projectObserver=new MutationObserver(syncProject);
        projectObserver.observe(projects,{childList:true,subtree:true,attributes:true,attributeFilter:["title"]});
      }
      observer=new MutationObserver(updateRows);
      observer.observe($("regions"),{childList:true});
      resize=new ResizeObserver(scheduleMeasure);
      resize.observe($("imw-audio-fit"));resize.observe($("scroll"));
      resize.observe($("regions"));
      resize.observe($("imw-screen"));
      for (const id of ["dmCut","dmCutStrip"])
        resize.observe(document.getElementById(id));
      sourceObserver=new MutationObserver(()=>{
        if(!sourceFrame)sourceFrame=requestAnimationFrame(sourceRow);
      });
      sourceObserver.observe(document.getElementById("dmCutStrip"),{childList:true,subtree:true});
      updateRows();
    } else {
      studio.detachedTracks.remember();
      engine()?.pause?.();
      const musicBound=!!trackSelection();
      observer?.disconnect();resize?.disconnect();sourceObserver?.disconnect();
      projectObserver?.disconnect();videoProject="";videoSong=null;studio.removeAttribute("data-imw-song");
      cancelAnimationFrame(sourceFrame);sourceFrame=0;
      cancelAnimationFrame(frame);frame=0;
      studio.removeAttribute("data-imw-video");studio.removeAttribute("data-imw-inspector");
      $("imw-inspect").setAttribute("aria-expanded","false");
      audioTab?.removeEventListener("click",openTrackSettings,true);
      document.getElementById("dmCutMusicLane").inert=archivedInert;
      // The timeline placeholder is inside the monitor; restoring the monitor first also restores its holder.
      for (const [el,mark] of original) { el.removeAttribute("slot"); mark.replaceWith(el); }
      audioViewport=0;viewportGain=0;studio.style.removeProperty("--imw-label-width");
      original.clear();showOriginal=false;activeTrack="";boundKey="";lastScale="";selectedLane="";
      paintSelection();
      studio.removeAttribute("data-imw-dense");studio.removeAttribute("data-imw-compact");$("regions").style.removeProperty("--imw-parts");
      $("imw-empty-tracks").hidden=true;
      studio.removeAttribute("data-imw-stems");studio.removeAttribute("data-imw-empty-video");
      laneHeaders.get("video").label.setAttribute("aria-expanded","false");
      $("imw-folded-video").setAttribute("aria-expanded","false");
      $("imw-folded-video").setAttribute("aria-label","展开视频");
      $("imw-folded-video").firstElementChild.textContent="展开视频";
      studio.frameRuler?.reset();studio.setLaneExtent(studio.rulerLength);studio.drawRuler();$("seek").max=studio.length;
      $("regions").style.removeProperty("width");$("regions").style.removeProperty("left");$("regions").style.removeProperty("clip-path");
      studio.trackEditor.foldForVideo(false);
      studio.transport.activate();
      if (musicBound && Number.isFinite(clock?.seconds)) studio.seek(clock.seconds-offset(clock));
      studio.position(); studio.transport.sync(); studio.paint();
    }
    studio.detachedTracks.refresh();
    if (!on && studio.detachedTracks.extent()>studio.length) studio.grid();
    $("scroll").scrollLeft=scrollLeft;
    if (on) document.body.dataset.imwAspect=studio.dataset.imwAspect || "landscape";
    else delete document.body.dataset.imwAspect;
    if (videoToggle) {
      videoToggle.setAttribute("aria-expanded",String(on));
      videoToggle.setAttribute("aria-label",on?"收起视频":"展开视频");
      videoToggle.title=on?"收起视频":"展开视频";
    }
    studio.$("imw-settings")?.hidePopover();
    if(on)void studio.disclosure.reveal(previousHeight);
  }
  function selectionChanged() {
    if (enabled()) {
      updateRows();
      document.dispatchEvent(new CustomEvent("jiusera:imw-selection-changed",{detail:selection()}));
    }
  }
  return {setMode,setProject,syncProject,enabled,displayLength,extendDisplayLength,selectionChanged,updateRows,paintSelection,trackSelection,selectStem,
    loopStem(start,end) {
      const clock=engine()?.state?.();
      if (!clock?.length || !trackSelection()) return;
      const window=scoreWindow(clock),shift=offset(clock);
      const inMs=Math.max(0,Math.round(1000*(Math.max(start,(window?.in_ms||0)/1000)+shift)));
      const outMs=Math.min(Math.round(clock.length*1000),Math.round(1000*(Math.min(end,(window?.out_ms??Infinity)/1000)+shift)));
      if (outMs-inMs<250) return studio.status("可循环的片段至少需要 0.25 秒。");
      const send=detail=>document.dispatchEvent(new CustomEvent("jiusera:imw-transport-command",{detail}));
      let state;
      const receive=event=>{state=event.detail;};
      document.addEventListener("jiusera:imw-transport-state",receive,{once:true});
      send({action:"loop-range",inMs,outMs});
      document.removeEventListener("jiusera:imw-transport-state",receive);
      if (state?.ready && !state.loop) send({action:"loop"});
    },
    seek(sourceTime){engine()?.seek?.(sourceTime+offset(engine()?.state?.()));},
    dragWidth(){return $("regions").getBoundingClientRect().width;},
    fit(){lastScale="";syncClock(engine()?.state?.());},
  };
}
