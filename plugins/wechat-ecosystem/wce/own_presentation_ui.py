"""Shared local account cards and a metadata-free browser thumbnail encoder."""

RENDER_JS = r"""
const WCEPresentation = (() => {
  'use strict';
  const states = {CONNECTED:'已连接',BOUND_IDLE:'已绑定 · 空闲',DISCONNECTED:'已断开',
    ACTION_REQUIRED:'需要处理'};
  function name(row) {
    const value = row.presentation?.display_name;
    return typeof value === 'string' && value.trim() ? value : '资料待完善';
  }
  function choices(rows) {
    const sorted = [...rows].sort((a,b) => a.connection_id < b.connection_id ? -1 : a.connection_id > b.connection_id ? 1 : 0);
    return new Map(sorted.map((row,index) => [row.connection_id,
      name(row) + (rows.filter(other => name(other) === name(row)).length > 1 ? ' · 账号 '+(index+1) : '')]));
  }
  function avatar(value) {
    const box = document.createElement('span'); box.className = 'avatar';
    box.setAttribute('role','img');
    box.setAttribute('aria-label',value ? '本人提供的公众号头像' : '未设置头像');
    if(!value) { box.textContent='暂无头像'; return box; }
    try {
      if(value.width !== 96 || value.height !== 96 || typeof value.rgba !== 'string' ||
         !/^[A-Za-z0-9+/]{49152}$/.test(value.rgba)) throw new Error('INVALID_AVATAR');
      const binary = atob(value.rgba);
      if(binary.length !== 36864) throw new Error('INVALID_AVATAR');
      const pixels = Uint8ClampedArray.from(binary, ch => ch.charCodeAt(0));
      const canvas = document.createElement('canvas'); canvas.width=canvas.height=96;
      canvas.setAttribute('aria-hidden','true');
      canvas.getContext('2d').putImageData(new ImageData(pixels,96,96),0,0);
      box.append(canvas);
    } catch(_) {
      box.textContent='显示失败'; box.setAttribute('aria-label','头像未能显示');
    }
    return box;
  }
  function card(row, title, onEdit) {
    const item=document.createElement('div'); item.className='account';
    const body=document.createElement('div'); body.className='account-body';
    const top=document.createElement('div'); top.className='account-top';
    const heading=document.createElement('strong'); heading.className='account-title';
    heading.textContent=title || name(row);
    const status=document.createElement('span');
    status.className='status'+(['CONNECTED','BOUND_IDLE'].includes(row.state) ? ' good' :
      row.state==='ACTION_REQUIRED' ? ' attention' : '');
    status.textContent=states[row.state] || '状态待确认';
    top.append(heading,status); body.append(top);
    const hint=document.createElement('p'); hint.className='account-hint';
    hint.textContent=row.presentation?.state==='UNAVAILABLE' ? '账号资料暂时无法安全读取。' :
      row.presentation?.state==='INVALID' ? '本机显示资料损坏，请保留资料并检查。' :
      !row.presentation?.avatar ? '补齐公众号头像，更容易辨认账号。' : '本机保存的公众号资料';
    body.append(hint);
    if(row.error) {
      const message=document.createElement('p'); message.className='account-hint';
      message.textContent=row.error==='CONNECTION_UPGRADE_REVIEW_REQUIRED' ? '请在管理页核对授权版本。' : '账号需要检查，请打开管理页。';
      body.append(message);
    }
    if(onEdit) {
      const edit=document.createElement('button'); edit.className='edit-profile quiet';
      edit.textContent='编辑资料';
      edit.dataset.editable=String(['MISSING','SAVED'].includes(row.presentation?.state));
      edit.disabled=edit.dataset.editable!=='true';
      edit.addEventListener('click',e => {if(e.isTrusted) onEdit(row);});
      body.append(edit);
    }
    item.append(avatar(row.presentation?.avatar),body);
    return item;
  }
  return {name,choices,avatar,card};
})();
"""

FILE_JS = r"""
const WCEThumbnail = (() => {
  'use strict';
  const join = (...parts) => {
    const out=new Uint8Array(parts.reduce((n,p)=>n+p.length,0));
    let offset=0; for(const part of parts) {out.set(part,offset);offset+=part.length;} return out;
  };
  const u32 = n => new Uint8Array([(n>>>24)&255,(n>>>16)&255,(n>>>8)&255,n&255]);
  function crc(bytes) {
    let value=0xffffffff;
    for(const byte of bytes) {value^=byte;for(let i=0;i<8;i++)value=(value>>>1)^((value&1)?0xedb88320:0);}
    return (value^0xffffffff)>>>0;
  }
  function chunk(type, bytes) {
    const body=join(Uint8Array.from(type,ch=>ch.charCodeAt(0)),bytes);
    return join(u32(bytes.length),body,u32(crc(body)));
  }
  function png(pixels) {
    if(pixels.length!==36864) throw new Error('PRESENTATION_INVALID_IMAGE');
    const filtered=new Uint8Array(36960);
    for(let y=0;y<96;y++)filtered.set(pixels.subarray(y*384,(y+1)*384),y*385+1);
    let a=1,b=0;for(const byte of filtered){a=(a+byte)%65521;b=(b+a)%65521;}
    const n=filtered.length, inv=(~n)&65535;
    const zlib=join(new Uint8Array([120,1,1,n&255,n>>>8,inv&255,inv>>>8]),filtered,u32((b*65536+a)>>>0));
    return join(new Uint8Array([137,80,78,71,13,10,26,10]),
      chunk('IHDR',join(u32(96),u32(96),new Uint8Array([8,6,0,0,0]))),
      chunk('IDAT',zlib),chunk('IEND',new Uint8Array()));
  }
  const base64 = bytes => {
    let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);return btoa(binary);
  };
  function dimensions(bytes,mime) {
    const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    if(mime==='image/png' && bytes.length>=33 &&
      [137,80,78,71,13,10,26,10].every((b,i)=>bytes[i]===b) &&
      view.getUint32(8)===13 && String.fromCharCode(...bytes.subarray(12,16))==='IHDR')
      return [view.getUint32(16),view.getUint32(20)];
    if(mime==='image/jpeg' && bytes[0]===255 && bytes[1]===216) {
      let i=2;
      while(i+4<=bytes.length) {
        if(bytes[i++]!==255)break;
        while(i<bytes.length && bytes[i]===255)i++;
        const marker=bytes[i++];if(marker===218 || marker===217)break;
        if(marker===1 || (marker>=208 && marker<=215))continue;
        if(i+2>bytes.length)break;
        const length=view.getUint16(i);
        if(length<2 || i+length>bytes.length)break;
        if([192,193,194].includes(marker) && length>=8 && bytes[i+2]===8)
          return [view.getUint16(i+5),view.getUint16(i+3)];
        i+=length;
      }
    }
    throw new Error('PRESENTATION_INVALID_IMAGE');
  }
  async function load(file) {
    if(!file || !['image/png','image/jpeg'].includes(file.type) || file.size<1 || file.size>2097152)
      throw new Error('PRESENTATION_INVALID_IMAGE');
    const bytes=new Uint8Array(await file.arrayBuffer()), [w,h]=dimensions(bytes,file.type);
    if(w<1 || h<1 || w>4096 || h>4096 || w*h>4194304)
      throw new Error('PRESENTATION_INVALID_IMAGE');
    const bitmap=await createImageBitmap(file);
    try {
      if(bitmap.width<1 || bitmap.height<1 || bitmap.width>4096 || bitmap.height>4096 ||
         bitmap.width*bitmap.height>4194304)throw new Error('PRESENTATION_INVALID_IMAGE');
      const canvas=document.createElement('canvas');canvas.width=canvas.height=96;
      const ctx=canvas.getContext('2d'), scale=Math.min(96/bitmap.width,96/bitmap.height);
      const width=bitmap.width*scale,height=bitmap.height*scale;
      ctx.drawImage(bitmap,(96-width)/2,(96-height)/2,width,height);
      const pixels=ctx.getImageData(0,0,96,96).data;
      return {png:base64(png(pixels)),avatar:{width:96,height:96,rgba:base64(pixels)}};
    } finally {bitmap.close();}
  }
  return {load};
})();
"""
