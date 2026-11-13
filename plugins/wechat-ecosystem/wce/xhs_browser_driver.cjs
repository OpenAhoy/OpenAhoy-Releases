/* OpenAhoy standard-browser adapter. No private HTTP API or page-state extraction.
 * DOM workflow research: xpzouying/xiaohongshu-mcp bb6fa2e (Apache-2.0).
 * Independently implemented using Playwright locators; no upstream code copied.
 */
'use strict';
const readline = require('node:readline');
const USER = /^[0-9a-f]{24}$/i;
const ROOT = 'https://www.xiaohongshu.com';
const CREATOR = 'https://creator.xiaohongshu.com';
function fail(code) { throw Object.assign(new Error(code), {code}); }
function idFrom(raw, kind) {
  try {
    const u = new URL(raw, ROOT);
    if (u.origin !== ROOT) return null;
    const m = u.pathname.match(kind === 'user' ? /^\/user\/profile\/([0-9a-f]{24})$/i : /^\/(?:(?:explore|discovery\/item)\/|user\/profile\/[0-9a-f]{24}\/)([0-9a-f]{24})$/i);
    return m ? m[1].toLowerCase() : null;
  } catch (_) { return null; }
}
class Adapter {
  constructor(context) { this.context = context; this.page = null; }
  async tab() { if (!this.page || this.page.isClosed()) this.page = await this.context.newPage(); return this.page; }
  async go(url) { const p = await this.tab(); await p.goto(url, {waitUntil:'domcontentloaded'}); await this.challenge(); return p; }
  async challenge() {
    const p = await this.tab();
    // A challenge stays in the real browser for its human owner. Never dismiss it.
    for (const selector of ['.captcha-container', '#captcha', '.verify-container', '[data-testid="captcha"]'])
      if (await p.locator(selector).first().isVisible()) fail('XHS_HUMAN_ACTION_REQUIRED');
    if (/\/(?:login|verify)(?:[/?#]|$)/.test(new URL(p.url()).pathname)) fail('XHS_LOGIN_REQUIRED');
  }
  async firstVisible(selector, root = this.page) {
    const all = root.locator(selector);
    for (let i=0;i<await all.count();i++) if (await all.nth(i).isVisible()) return all.nth(i);
    return null;
  }
  async text(selector, root = this.page) { const el = await this.firstVisible(selector, root); return el ? (await el.innerText()).trim() : ''; }
  async begin() {
    const p=await this.go(ROOT+'/explore');
    const selector='.qrcode-img, .main-container .user a[href*="/user/profile/"], .main-container .user .link-wrapper .channel';
    try {await p.locator(selector).first().waitFor({state:'visible',timeout:30000});}
    catch (_) {await this.challenge();fail('XHS_LOGIN_ENTRY_UNAVAILABLE');}
    await this.challenge();
    if(await p.locator('.qrcode-img').isVisible())return {state:'AWAITING_HUMAN_LOGIN',qr_visible:true};
    return {state:'LOGIN_PRESENT',qr_visible:false};
  }
  async identity() {
    await this.challenge();
    const p = await this.tab();
    const own = await this.firstVisible('.main-container .user a[href*="/user/profile/"]');
    let id = own && idFrom(await own.getAttribute('href'), 'user');
    if(!id) {
      const channel=await this.firstVisible('.main-container .user .link-wrapper .channel');
      if(!channel)fail('XHS_LOGIN_REQUIRED');
      await channel.click();
      try{await p.waitForURL(u=>!!idFrom(u.href,'user'),{timeout:15000});}catch(_){fail('XHS_IDENTITY_UNVERIFIED');}
      id=idFrom(p.url(),'user');
    } else await p.goto(ROOT+'/user/profile/'+id, {waitUntil:'domcontentloaded'});
    await this.challenge();
    try{await p.locator('.user-name, .user-info .nickname, .user-info .name').first().waitFor({state:'visible'});}catch(_){fail('XHS_IDENTITY_UNVERIFIED');}
    const name = await this.text('.user-name, .user-info .nickname, .user-info .name');
    if (!name) fail('XHS_IDENTITY_UNVERIFIED');
    return {id, name};
  }
  async profile(expected) {
    await this.go(ROOT+'/explore'); const v = await this.identity();
    if (expected && v.id !== expected) fail('XHS_ACCOUNT_MISMATCH');
    return v;
  }
  async notes(expected) {
    const profile = await this.profile(expected), p = await this.tab();
    const tab = p.getByText('笔记', {exact:true});
    if (await tab.count() === 1 && await tab.isVisible()) await tab.click();
    // Only DOM cards on the bound user's own profile, never the home feed.
    const cards = p.locator('.note-item'); const notes = [];
    for(let i=0;i<await cards.count();i++) {
      const card=cards.nth(i), author=card.locator('a.author[href*="/user/profile/"]').first();
      const owner=await author.count() ? idFrom(await author.getAttribute('href'),'user') : null;
      const link=card.locator('a[href*="/explore/"],a[href*="/discovery/item/"]').first();
      const id=await link.count() ? idFrom(await link.getAttribute('href'),'note') : null;
      if (!id || owner !== profile.id) fail('XHS_NOTE_OWNERSHIP_UNVERIFIED');
      notes.push({id, owner_id:owner, title:await this.text('.title',card), url:ROOT+'/explore/'+id});
    }
    const empty = await this.text('.empty-container, .empty-box');
    if(!notes.length && !empty) fail('XHS_NOTES_UNVERIFIED');
    return {profile, notes, completeness:'VISIBLE_PAGE_ONLY', has_more:'UNKNOWN', public_url_verified:false};
  }
  async note(expected, id, verifyPublic=false) {
    if(!USER.test(id)) fail('XHS_INVALID_NOTE_ID');
    // Recover the official link from the same-account profile DOM. Its query is
    // used only inside this browser and is never returned, persisted or logged.
    await this.profile(expected); const p=await this.tab();
    try{await p.locator('a[href*="/'+id+'"]').first().waitFor({state:'attached',timeout:10000});}catch(_){/* The exact creator result may still be awaiting profile visibility. */}
    const links=p.locator('a[href]'); let href=null;
    for(let i=0;i<await links.count();i++) {
      const el=links.nth(i), raw=await el.getAttribute('href');
      if(idFrom(raw,'note')===id){const candidate=new URL(raw,ROOT);href=candidate.href;if(candidate.searchParams.has('xsec_token'))break;}
    }
    await this.go(href||ROOT+'/explore/'+id);
    try{await p.locator('#detail-title, .note-detail .title').first().waitFor({state:'visible'});}catch(_){await this.challenge();fail('XHS_NOTE_NOT_VISIBLE');}
    const author=await this.firstVisible('.author-container a[href*="/user/profile/"], .note-detail-mask .author a[href*="/user/profile/"]');
    if(!author || idFrom(await author.getAttribute('href'),'user')!==expected) fail('XHS_NOTE_OWNERSHIP_UNVERIFIED');
    const title=await this.text('#detail-title, .note-detail .title');
    const body=await this.text('#detail-desc, .note-detail .desc');
    if(!title || !body) fail('XHS_NOTE_DETAIL_UNVERIFIED');
    // Detail text and the image carousel hydrate separately. Wait for the
    // actual note media, not avatars/feed images or an empty slider shell.
    try{await p.waitForFunction(()=>[...document.querySelectorAll('.note-slider .swiper-slide img')].some(e=>e.complete&&e.naturalWidth>0&&(e.currentSrc||e.src).startsWith('https:')),{},{timeout:15000});}
    catch(_){fail('XHS_NOTE_MEDIA_NOT_READY');}
    const images=await p.locator('.note-slider .swiper-slide').evaluateAll(xs=>{
      const positions=new Map();xs.forEach((e,i)=>{const index=Number(e.getAttribute('data-swiper-slide-index')??i);const img=e.querySelector('img');if(img&&(!positions.has(index)||!e.classList.contains('swiper-slide-duplicate')))positions.set(index,img.currentSrc||img.src);});
      return [...positions].sort((a,b)=>a[0]-b[0]).map(v=>v[1]);
    });
    const unique=images.filter(raw=>{try{return new URL(raw).protocol==='https:';}catch(_){return false;}});
    const canonical=ROOT+'/explore/'+id;
    let publiclyReadable=false;
    if(verifyPublic) {
      const isolated=await this.context.browser().newContext();
      try {
        const check=await isolated.newPage();await check.goto(canonical,{waitUntil:'domcontentloaded'});
        await check.locator('#detail-title, .note-detail .title').first().waitFor({state:'visible',timeout:10000});
        const owner=await check.locator('.author-container a[href*="/user/profile/"]').first().getAttribute('href');
        const actualTitle=(await check.locator('#detail-title, .note-detail .title').first().innerText()).trim();
        const actualBody=(await check.locator('#detail-desc, .note-detail .desc').first().innerText()).trim();
        publiclyReadable=!(await check.locator('.qrcode-img').isVisible())&&idFrom(owner,'user')===expected&&actualTitle===title&&actualBody===body;
      }catch(_){/* Public readability is not implied by owner access. */}
      finally{await isolated.close();}
    }
    return {id, owner_id:expected, title, body, url:canonical, images:unique,
      image_order:'DETAIL_CAROUSEL_DOM_ORDER',state:publiclyReadable?'PUBLIC_READABLE':'OWNER_READABLE',public_url_verified:publiclyReadable};
  }
  cardId(card) {
    return card.getAttribute('data-impression').then(raw=>{
      try {const id=JSON.parse(raw)?.noteTarget?.value?.noteId;return USER.test(id||'')?id.toLowerCase():null;}catch(_){return null;}
    });
  }
  async creatorNotes(expected) {
    const own=await this.notes(expected);this.ownNoteIds=new Set(own.notes.map(v=>v.id));
    const p=await this.go(CREATOR+'/new/note-manager');
    try{await p.locator('.note-card, .empty-container, .empty').first().waitFor({state:'visible'});}catch(_){await this.challenge();fail('XHS_CREATOR_LIST_UNVERIFIED');}
    await this.creatorIdentity(expected);
    const cards=p.locator('.note-card');const ids=[];
    for(let i=0;i<await cards.count();i++) {const id=await this.cardId(cards.nth(i));if(id&&!ids.includes(id))ids.push(id);}
    return ids;
  }
  creatorNoteId(raw) {
    const ordinary=idFrom(raw,'note');if(ordinary)return ordinary;
    try {const u=new URL(raw,CREATOR);if(u.origin!==CREATOR)return null;
      if(!/^\/(?:publish|new\/note-manager|note)/.test(u.pathname))return null;
      const id=u.searchParams.get('note_id')||u.searchParams.get('id');return USER.test(id||'')?id.toLowerCase():null;
    }catch(_){return null;}
  }
  async creatorIdentity(expected) {
    const p=await this.tab(),links=p.locator('a[href*="xiaohongshu.com/user/profile/"]');let ids=[];
    for(let i=0;i<await links.count();i++)if(await links.nth(i).isVisible()) {
      const id=idFrom(await links.nth(i).getAttribute('href'),'user');if(id&&!ids.includes(id))ids.push(id);
    }
    if(ids.length){if(ids.length===1&&ids[0]===expected)return;fail('XHS_ACCOUNT_MISMATCH');}
    // Current creator UI has no profile anchor. Its rendered own-note card ID
    // must intersect a note just observed on this exact authenticated profile.
    // Read a DOM data attribute, never window state, cookies or a hidden API.
    const cards=p.locator('.note-card');
    for(let i=0;i<await cards.count();i++)if(this.ownNoteIds?.has(await this.cardId(cards.nth(i)))) {
      this.creatorOwner=expected;return;
    }
    if(this.creatorOwner===expected&&new URL(p.url()).origin===CREATOR)return;
    fail('XHS_CREATOR_IDENTITY_UNVERIFIED');
  }
  async resolve(a) {
    // No upload/click/publish happens here. Revisit only this original attempt.
    if(a.observation&&new URL((await this.tab()).url()).pathname==='/publish/publish')this.page=await this.context.newPage();
    const known=new Set(a.observation?.before_ids||[]),p=await this.tab();
    let ids=[];const current=this.creatorNoteId(p.url());if(current)ids.push(current);
    const links=p.locator('a[href]');
    for(let i=0;i<await links.count();i++) {
      const link=links.nth(i),id=this.creatorNoteId(await link.getAttribute('href'));
      if(id&&!known.has(id)&&!ids.includes(id))ids.push(id);
    }
    if(!ids.length) {
      await this.creatorNotes(a.user_id);
      const candidates=(await this.tab()).locator('.note-card');
      for(let i=0;i<await candidates.count();i++) {
        const link=candidates.nth(i),id=await this.cardId(link);
        if(!id||known.has(id)||ids.includes(id))continue;
        // Limit to the current rendered list, exact requested title. Ambiguity
        // stays UNKNOWN; never broaden into a full-history scan or repost.
        const title=await this.text('.note-card__title',link);
        const date=(await link.innerText()).match(/(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);
        const time=date?new Date(date[1]+'T'+date[2]+':00').getTime():NaN;
        if(title===a.title&&Number.isFinite(time)&&time>=Math.floor((a.observation?.submitted_at||Date.now())/60000)*60000)ids.push(id);
      }
    }
    const matches=[],queryErrors=[],mismatchFields=[];
    for(const id of ids) {
      try {const v=await this.note(a.user_id,id);
        const body=a.body+(a.topics?.length?'\n'+a.topics.map(t=>'#'+t.replace(/^#/,'')).join(' '):'');
        const normalize=v=>v.replace(/[\u200b\ufeff]/g,'').replace(/\s+/g,' ').trim();
        const mismatch=[];if(v.images.length!==(a.image_count??a.images?.length))mismatch.push('image_count');if(v.title!==a.title)mismatch.push('title');if(normalize(v.body)!==normalize(body))mismatch.push('body');
        if(!mismatch.length)matches.push(v);else mismatchFields.push(...mismatch);
      }catch(e){if(['XHS_HUMAN_ACTION_REQUIRED','XHS_LOGIN_REQUIRED','XHS_ACCOUNT_MISMATCH'].includes(e.code))throw e;queryErrors.push(/^XHS_[A-Z_]+$/.test(e.code||'')?e.code:'XHS_NOTE_QUERY_UNAVAILABLE');}
    }
    return matches.length===1?{state:'NOTE_OBSERVED',note_id:matches[0].id}:
      {state:matches.length>1?'AMBIGUOUS':'SUBMITTED_UNVERIFIED',candidate_count:ids.length,candidate_note_ids:ids,query_errors:queryErrors,mismatch_fields:[...new Set(mismatchFields)]};
  }
  async imageTab() {
    const p=await this.tab(),tabs=p.getByText('上传图文',{exact:true});
    try{await tabs.first().waitFor({state:'attached'});}catch(_){await this.challenge();fail('XHS_FORM_TAB_UNAVAILABLE');}
    for(let i=0;i<await tabs.count();i++) {
      const tab=tabs.nth(i);
      const actionable=await tab.evaluate(e=>{const r=e.getBoundingClientRect();
        if(r.width<=0||r.height<=0||r.x<0||r.y<0||r.x+r.width>innerWidth||r.y+r.height>innerHeight)return false;
        const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit&&(e.contains(hit)||hit.contains(e));});
      if(actionable){await tab.click();return;}
    }
    fail('XHS_FORM_CHANGED');
  }
  async inspectResult(expectedTitle) {
    const p=await this.tab(),u=new URL(p.url());await this.challenge();
    if(u.origin!==CREATOR||!/^\/publish\/(?:publish|success)$/.test(u.pathname))fail('XHS_RESULT_VIEW_UNAVAILABLE');
    const input=await this.firstVisible('div.d-input input, input[placeholder*="标题"]');
    if(u.pathname==='/publish/publish'&&(!input||await input.inputValue()!==expectedTitle))fail('XHS_RESULT_VIEW_UNAVAILABLE');
    if(u.pathname==='/publish/success'&&await p.getByText(expectedTitle,{exact:true}).count()!==1)fail('XHS_RESULT_VIEW_UNAVAILABLE');
    if(await p.locator('input[type=password],.qrcode-img').count())fail('XHS_RESULT_VIEW_UNAVAILABLE');
    const alerts=await p.locator('[role=alert],.el-message,.d-message,.error-tip,.field-error,.d-form-item__message').allTextContents();
    const dialogs=await p.locator('[role=dialog],.d-modal,.el-dialog,.feature-guide').allTextContents();
    return {state:'ORIGINAL_VISIBLE_RESULT',path:u.pathname,alerts,dialogs,
      visible_text:await p.locator('body').innerText(),screenshot_png_base64:(await p.screenshot()).toString('base64')};
  }
  async publicationControl() {
    const p=await this.tab(),buttons=p.getByRole('button',{name:'发布',exact:true});
    if(await buttons.count()===1&&await buttons.isVisible()) {
      return {enabled:await buttons.isEnabled(),method:'DOM_BUTTON_NAME',click:()=>buttons.click()};
    }
    // The current official footer is a closed web component containing both
    // Save and Publish. Clicking its host centre hits the gap, not a button.
    // Read standard browser accessibility names + public element geometry;
    // never open/replace the shadow root, read application state or call APIs.
    const host=p.locator('xhs-publish-btn');if(await host.count()!==1)fail('XHS_FORM_CHANGED');
    const hostBox=await host.boundingBox();if(!hostBox)fail('XHS_PUBLISH_DISABLED');
    const session=await this.context.newCDPSession(p);
    try {
      const tree=await session.send('Accessibility.getFullAXTree');const found=[];
      for(const node of tree.nodes) {
        if(node.role?.value!=='button'||node.name?.value!=='发布'||!node.backendDOMNodeId)continue;
        const box=(await session.send('DOM.getBoxModel',{backendNodeId:node.backendDOMNodeId})).model.border;
        const x=(box[0]+box[4])/2,y=(box[1]+box[5])/2;
        if(x<hostBox.x||x>hostBox.x+hostBox.width||y<hostBox.y||y>hostBox.y+hostBox.height)continue;
        const clear=await host.evaluate((e,{x,y})=>{const hit=document.elementFromPoint(x,y);return hit===e||e.contains(hit);},{x,y});
        if(clear)found.push({x,y,enabled:!node.properties?.some(v=>v.name==='disabled'&&v.value.value===true)});
      }
      if(found.length!==1)fail('XHS_PUBLISH_TARGET_UNVERIFIED');
      const target=found[0];return {enabled:target.enabled,method:'BROWSER_ACCESSIBLE_BUTTON_NAME',click:()=>p.mouse.click(target.x,target.y)};
    }finally{await session.detach();}
  }
  async form(expected) {
    await this.creatorNotes(expected);
    const p=await this.go(CREATOR+'/publish/publish?source=official');await this.creatorIdentity(expected);
    await this.imageTab();
    const files=p.locator('input[type=file][accept*="image"], input.upload-input[type=file]');
    return {state:'FORM_OBSERVED',file_inputs:await files.count(),accept:await files.count()===1?await files.getAttribute('accept'):null};
  }
  async publish(a, event) {
    await this.profile(a.user_id);
    const before=await this.creatorNotes(a.user_id);
    const p=await this.go(CREATOR+'/publish/publish?source=official');
    // Creator and consumer login can differ. Require an actual profile link,
    // not merely a matching nickname, before touching the publication form.
    const profileLinks=p.locator('a[href*="xiaohongshu.com/user/profile/"]'); let creatorId=null;
    for(let i=0;i<await profileLinks.count();i++) if(await profileLinks.nth(i).isVisible()) {
      const id=idFrom(await profileLinks.nth(i).getAttribute('href'),'user');
      if(id) { if(creatorId && creatorId!==id) fail('XHS_CREATOR_IDENTITY_UNVERIFIED'); creatorId=id; }
    }
    if(creatorId!==a.user_id)await this.creatorIdentity(a.user_id);
    await this.imageTab();
    // File inputs are normally visually hidden; Playwright supports the real
    // input without changing DOM, dismissing overlays or forcing button clicks.
    const files=p.locator('input[type=file][accept*="image"], input.upload-input[type=file]');
    if(await files.count()!==1) fail('XHS_FORM_CHANGED');
    const accept=await files.getAttribute('accept');
    if(accept && !a.images.every(v=>accept.split(',').map(x=>x.trim().toLowerCase()).some(x=>x==='image/*'||x===v.mime||x==='.'+v.extension))) fail('XHS_MEDIA_FORMAT_REJECTED');
    // No image/title/body truncation or private business quota. Actual form
    // constraints and upload completion are inspected on the current page.
    await event('UPLOAD_STARTED');
    await files.setInputFiles(a.images.map(v=>v.path));
    await p.locator('.img-preview-area .pr').nth(a.images.length-1).waitFor({state:'visible'});
    if(await p.locator('.img-preview-area .pr').count()!==a.images.length) fail('XHS_UPLOAD_UNVERIFIED');
    return this.submitForm(a,event,before,false);
  }
  async resumeDraft(a,event) {
    const before=await this.creatorNotes(a.user_id),p=await this.go(CREATOR+'/publish/publish?source=official');
    await this.creatorIdentity(a.user_id);
    const box=p.getByText(/^草稿箱\(\d+\)$/);await box.waitFor({state:'visible'});await box.click();
    const imageTab=p.getByText(/^图文笔记\(\d+\)$/);await imageTab.waitFor({state:'visible'});await imageTab.click();
    const title=p.getByText(a.title,{exact:true});await title.waitFor({state:'visible'});
    // Locate only the original matching draft. Never create a new draft or
    // upload again on this explicitly authorized recovery path.
    let parent=title,edit=null;
    for(let i=0;i<8;i++) {
      parent=parent.locator('xpath=..');const buttons=parent.getByText('编辑',{exact:true});
      if(await buttons.count()===1){edit=buttons;break;}
    }
    if(!edit)fail('XHS_ORIGINAL_DRAFT_AMBIGUOUS');await edit.click();
    await p.locator('div.d-input input, input[placeholder*="标题"]').first().waitFor({state:'visible'});
    if(await p.locator('.img-preview-area .pr').count()!==a.images.length)fail('XHS_ORIGINAL_DRAFT_MEDIA_MISMATCH');
    return this.submitForm(a,event,before,true);
  }
  async submitForm(a,event,before,reuse) {
    const p=await this.tab();
    const title=await this.firstVisible('div.d-input input, input[placeholder*="标题"]');
    const body=await this.firstVisible('div[role="textbox"][contenteditable="true"],div.tiptap[contenteditable="true"],div.ql-editor[contenteditable="true"]');
    if(!title||!body) fail('XHS_FORM_CHANGED');
    const maxlength=await title.getAttribute('maxlength');
    if(maxlength && [...a.title].length>Number(maxlength)) fail('XHS_TITLE_FORM_LIMIT');
    await this.challenge();if(!reuse)await title.fill(a.title);
    const text=a.body+(a.topics.length?'\n'+a.topics.map(t=>'#'+t.replace(/^#/, '')).join(' '):'');
    if(!reuse)await body.fill(text);
    if(await title.inputValue()!==a.title)fail('XHS_FORM_TITLE_MISMATCH');
    const normalized=v=>v.replace(/[\u200b\ufeff]/g,'').replace(/\s+/g,' ').trim();
    if(normalized(await body.innerText())!==normalized(text))fail('XHS_FORM_BODY_MISMATCH');
    // Dismiss only this normal editing feature guide; never login, permission
    // or risk challenges. The latter remain in challenge() for their owner.
    const guide=await this.firstVisible('.feature-guide__btn');
    if(guide&&(await guide.innerText()).trim()==='我知道了')await guide.click();
    const button=await this.publicationControl();
    if(!button.enabled)fail('XHS_PUBLISH_DISABLED');
    // This operation is authorized for a public post. Inspect the visible
    // audience control, never inherit a private-only setting silently.
    const publicControl=await this.firstVisible('text=公开可见');
    if(!publicControl)fail('XHS_PUBLIC_VISIBILITY_UNVERIFIED');
    // Parent durably ACKs before we click; a broken pipe cannot cause an
    // unrecorded submission. After this point absence of a note is UNKNOWN.
    const observation={before_ids:before,submitted_at:Date.now(),visibility:'PUBLIC',target_method:button.method};
    await event('SUBMIT_STARTED',observation); await button.click();
    // A successful click does not mean the asynchronous submission finished.
    // Keep the original page alive until its normal result is observed;
    // immediately navigating elsewhere can abort the platform's request.
    try {await Promise.any([
      p.waitForURL(u=>u.origin===CREATOR&&/^\/publish\/success(?:\/|$)/.test(u.pathname),{timeout:20000}),
      p.getByText('发布成功',{exact:true}).first().waitFor({state:'visible',timeout:20000})
    ]);}catch(_){await this.challenge();return {state:'UNKNOWN',observation};}
    await this.challenge();
    const result=await this.resolve({...a,observation});
    return {...result,observation};
  }
}
module.exports={Adapter,idFrom};
if(require.main===module) void (async()=>{
  process.umask(0o077);
  const [entry,browser,profile]=process.argv.slice(2);
  let context=null,adapter=null;
  const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  let activeRequestId=null;
  const emit=v=>process.stdout.write(JSON.stringify({...v,request_id:activeRequestId})+'\n');
  let ack=null;
  const event=(phase,data)=>new Promise(resolve=>{ack=resolve;emit(data?{event:phase,data}:{event:phase});});
  async function close(){try{await context?.close();}catch(_){}context=null;}
  process.on('SIGTERM',()=>void close().finally(()=>process.exit(0)));
  process.on('disconnect',()=>void close());
  let serial=Promise.resolve();
  rl.on('line',line=>{
    let a;try{a=JSON.parse(line);}catch(_){emit({error:'XHS_INVALID_REQUEST'});return;}
    if(a.ack===true&&ack&&a.request_id===activeRequestId){const f=ack;ack=null;f();return;}
    serial=serial.then(async()=>{
      activeRequestId=a.request_id;
      try{
        if(a.op==='CLOSE'){await close();emit({result:{state:'CLOSED'}});return;}
        if(!context){const {chromium}=require(entry);context=await chromium.launchPersistentContext(profile,{executablePath:browser,headless:false});context.setDefaultTimeout(15000);adapter=new Adapter(context);}
        let result;
        if(a.op==='BEGIN')result=await adapter.begin();
        else if(a.op==='POLL')result=await adapter.identity();
        else if(a.op==='PROFILE')result=await adapter.profile(a.user_id);
        else if(a.op==='NOTES')result=await adapter.notes(a.user_id);
        else if(a.op==='NOTE')result=await adapter.note(a.user_id,a.note_id,a.verify_public===true);
        else if(a.op==='FORM')result=await adapter.form(a.user_id);
        else if(a.op==='PUBLISH')result=await adapter.publish(a,event);
        else if(a.op==='RESUME_DRAFT')result=await adapter.resumeDraft(a,event);
        else if(a.op==='RESULT')result=await adapter.inspectResult(a.expected_title);
        else if(a.op==='RESOLVE')result=await adapter.resolve(a);
        else fail('XHS_INVALID_REQUEST');
        emit({result});
      }catch(e){emit({error:/^XHS_[A-Z_]+$/.test(e.code||'')?e.code:'XHS_BROWSER_UNAVAILABLE'});}
    });
  });
  rl.on('close',()=>void close().finally(()=>process.exit(0)));
})().catch(()=>{process.stdout.write('{"error":"XHS_RUNTIME_UNAVAILABLE"}\n');process.exitCode=1;});
