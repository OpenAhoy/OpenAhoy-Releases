"""Inline, scope-hashed UI. The MCP modal never contains credential inputs."""
import base64
from hashlib import sha256
from .own_presentation_ui import RENDER_JS, FILE_JS
from .own_production_rules_ui import HTML as RULES_HTML, JS as RULES_JS
from .own_article_status_ui import HTML as ARTICLES_HTML, JS as ARTICLES_JS
from .own_management_ui import STYLE as MANAGEMENT_STYLE, JS as MANAGEMENT_JS, page_body
from .official_account_routes import render_html as routes_html
from .html_technical_standard import render_html as technical_html

# Frozen historical descriptor artwork; retained only for exact authority projection.
# Kept inline so the trusted page needs no image endpoint or CSP exception.
LEGACY_LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1024" height="1024" fill="none" role="img" aria-labelledby="wce-title wce-description">
  <title id="wce-title">WCE logo — white background</title>
  <desc id="wce-description">Left WeChat face and both outer contours preserved from the supplied Streamline SVG; right eyes replaced by a black ChatGPT knot. WeChat source: Streamline. Knot reference: https://brandlogos.sgp1.digitaloceanspaces.com/svg/logos/openai.svg</desc>
  <rect width="24" height="24" fill="#fff" />
  <g id="wechat-left-original">
    <path stroke="#000000" stroke-linejoin="round" d="M16.5 9.5c0 -3.314 -3.358 -6 -7.5 -6 -4.142 0 -7.5 2.686 -7.5 6 0 1.891 1.094 3.578 2.803 4.678L4 17l3.302 -1.654a9.35 9.35 0 0 0 3.288 0.02" stroke-width="1" />
    <path stroke="#000000" stroke-linejoin="round" d="M6.5 8.5a0.5 0.5 0 0 1 0 -1" stroke-width="1" />
    <path stroke="#000000" stroke-linejoin="round" d="M6.5 8.5a0.5 0.5 0 0 0 0 -1" stroke-width="1" />
    <path stroke="#000000" stroke-linejoin="round" d="M11.5 8.5a0.5 0.5 0 0 1 0 -1" stroke-width="1" />
    <path stroke="#000000" stroke-linejoin="round" d="M11.5 8.5a0.5 0.5 0 0 0 0 -1" stroke-width="1" />
  </g>
  <g id="wechat-right-original-outline">
    <path stroke="#000000" stroke-linejoin="round" d="M10.5 14.5c0 2.761 2.686 5 6 5 0.34 0 0.675 -0.024 1 -0.07L21 21l-0.5 -2.773c1.227 -0.916 2 -2.246 2 -3.727 0 -2.761 -2.686 -5 -6 -5s-6 2.239 -6 5Z" stroke-width="1" />
  </g>
  <svg id="chatgpt-knot" x="12.75" y="10.75" width="7.5" height="7.5" viewBox="0 0 124.3 126" preserveAspectRatio="xMidYMid meet" fill="#000">
    <path d="M116.085 51.561a31.37 31.37 0 0 0-2.695-25.774a31.77 31.77 0 0 0-34.184-15.224A31.4 31.4 0 0 0 55.536.001a31.74 31.74 0 0 0-30.278 21.99A31.4 31.4 0 0 0 4.282 37.213a31.77 31.77 0 0 0 3.906 37.218a31.4 31.4 0 0 0 2.695 25.748a31.77 31.77 0 0 0 34.21 15.256a31.4 31.4 0 0 0 23.644 10.562a31.74 31.74 0 0 0 30.278-21.99a31.4 31.4 0 0 0 20.97-15.223a31.73 31.73 0 0 0-3.9-37.224m-47.348 66.22a23.52 23.52 0 0 1-15.108-5.478c.186-.104.548-.285.756-.422l25.09-14.484a4.07 4.07 0 0 0 2.06-3.567V58.453l10.6 6.119a.37.37 0 0 1 .208.296v29.28c0 13.041-10.564 23.618-23.606 23.633M18.015 96.12a23.56 23.56 0 0 1-2.82-15.821c.185.115.514.312.744.443l25.096 14.49a4.08 4.08 0 0 0 4.12 0L75.77 77.528v12.238a.37.37 0 0 1-.148.328L50.26 104.732c-11.292 6.502-25.716 2.637-32.245-8.64zm-6.573-54.782a23.5 23.5 0 0 1 12.287-10.354v29.823a4.08 4.08 0 0 0 2.06 3.567l30.623 17.683l-10.639 6.141a.37.37 0 0 1-.356.033L20.059 73.589c-11.282-6.527-15.148-20.957-8.64-32.25zm87.102 20.27L67.92 43.924l10.59-6.125a.38.38 0 0 1 .355-.033l25.359 14.643a23.61 23.61 0 0 1-3.649 42.598V65.191a4.08 4.08 0 0 0-2.049-3.583zM109.1 45.721a30 30 0 0 0-.745-.444L83.26 30.788a4.08 4.08 0 0 0-4.12 0L48.517 48.466V36.233a.4.4 0 0 1 .154-.328l25.358-14.638a23.61 23.61 0 0 1 35.06 24.46zM42.738 67.546l-10.605-6.119a.4.4 0 0 1-.203-.295V31.85a23.605 23.605 0 0 1 38.714-18.155c-.186.105-.52.285-.756.422l-25.09 14.484a4.08 4.08 0 0 0-2.06 3.567zm5.758-12.418l13.64-7.878l13.635 7.878v15.744l-13.64 7.877l-13.64-7.877z" />
  </svg>
</svg>"""

from .own_branding import HORIZONTAL as LOGO, header as brand_header

STYLE = """
:root{color-scheme:light dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
--bg:#f5f6f3;--surface:#fff;--soft:#f7f8f6;--ink:#202c28;--muted:#64736b;--line:#e1e7e1;
--accent:#226448;--tint:#edf5ee;--danger:#aa343b;--shadow:0 8px 32px #24392a05}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-size:14px;line-height:1.65}
button,input,select{font:inherit}
button{min-height:42px;padding:9px 16px;border:1px solid var(--line);border-radius:9px;white-space:nowrap;flex-shrink:0;
background:var(--surface);color:var(--ink);font-weight:600;cursor:pointer;transition:background .15s,border-color .15s}
button:hover:not(:disabled){background:var(--soft);border-color:#a7b6aa}
button:disabled{opacity:.45;cursor:default}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.primary:hover:not(:disabled){background:#174d36}
button.quiet{background:transparent}
button.danger{color:var(--danger)}
button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{
outline:3px solid #72af8e;outline-offset:3px}
input:not([type=checkbox]),select{display:block;width:100%;min-height:46px;padding:10px 12px;
border:1px solid var(--line);border-radius:9px;background:var(--surface);color:var(--ink)}
input::placeholder{color:#859188}input[type=checkbox]{accent-color:var(--accent);width:17px;height:17px;flex-shrink:0}
label{display:block;margin:0 0 18px;font-weight:600;font-size:13px}
label input,label select{margin-top:7px}
h1,h2,h3,p{margin:0}h1{font-size:32px;line-height:1.35;font-weight:650;letter-spacing:-.8px}
h2{font-size:18px;line-height:1.45;letter-spacing:-.3px}h3{font-size:14px}
.muted,.help{color:var(--muted)}.help{font-size:12px;line-height:1.7;font-weight:400;margin-top:7px}
.brandbar{height:76px;border-bottom:1px solid var(--line);background:var(--surface)}
.brandinner{max-width:1120px;height:100%;margin:auto;padding:0 32px;display:flex;align-items:center;justify-content:space-between;gap:20px}
.brand{white-space:normal;min-width:0;display:flex;align-items:center;gap:11px;font-weight:650;letter-spacing:-.2px}
.mark{display:block;flex-shrink:0;width:40px;height:40px;padding:3px;border:1px solid #e1e7e1;
border-radius:11px;background:#fff;overflow:hidden}.mark > svg{display:block;width:100%;height:100%}
.local-badge{display:inline-flex;align-items:center;gap:7px;color:var(--muted);font-size:12px}
.local-badge:before{content:"";width:6px;height:6px;border-radius:50%;background:var(--accent)}
.workspace{max-width:1120px;margin:auto;padding:44px 32px 26px}
.page-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:26px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:1.8px;color:var(--accent);margin-bottom:8px}
.subtitle{margin-top:10px;color:var(--muted);font-size:14px}
.notice{border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:9px;
padding:12px 16px;background:var(--surface);color:var(--muted);font-size:13px;margin-bottom:24px;overflow-wrap:anywhere}
.notice.error{border-left-color:var(--danger);color:var(--danger)}
.layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);align-items:start;gap:24px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:26px;box-shadow:var(--shadow);min-width:0}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:22px}
.card-head p{font-size:12px;color:var(--muted);margin-top:4px}
.count{font-size:12px;color:var(--muted);font-weight:500;padding:3px 8px;border-radius:6px;background:var(--soft);margin-left:6px}
.account{border:1px solid var(--line);border-radius:11px;padding:17px;margin-bottom:12px;display:flex;align-items:flex-start;gap:13px}
.avatar{display:grid;place-items:center;flex-shrink:0;width:52px;height:52px;border:1px solid var(--line);
border-radius:12px;background:var(--soft);color:var(--muted);font-size:10px;font-weight:500;overflow:hidden}
.avatar canvas{display:block;width:100%;height:100%}
.account-hint{font-size:11px;color:var(--muted);margin-top:5px}
.edit-profile{min-height:30px;padding:3px 9px;font-size:11px;margin-top:10px}
.profile-editor{padding:18px;background:var(--soft);border:1px solid var(--line);border-radius:11px;margin:18px 0}
.profile-editor h3{margin-bottom:16px}.profile-preview{margin-bottom:14px}
.profile-preview .avatar{width:72px;height:72px}
.account-body{min-width:0;flex:1}.account-top{display:flex;flex-wrap:wrap;align-items:center;gap:7px 12px}
.account-title{font-size:14px;font-weight:650;overflow-wrap:anywhere}
.account-id{display:block;margin-top:5px;font:11px/1.6 ui-monospace,SFMono-Regular,monospace;color:var(--muted);overflow-wrap:anywhere}
.status{display:inline-block;border-radius:5px;padding:2px 7px;background:var(--soft);color:var(--muted);font-size:11px;white-space:nowrap}
.status.good{background:var(--tint);color:var(--accent)}.status.attention{background:#fff2db;color:#865c1a}
.account-error{margin-top:7px;font:11px/1.6 ui-monospace,monospace;color:var(--danger);overflow-wrap:anywhere}
.account-tools{border-top:1px solid var(--line);padding-top:18px;margin-top:22px}
.account-tools>summary{color:var(--muted);font-size:13px}
.account-tools[open]>summary{margin-bottom:16px}
.actions{display:flex;gap:10px;flex-wrap:wrap}.actions button{flex-shrink:1;white-space:normal;max-width:100%}
.add-card .primary{width:100%}.add-card h2{margin-bottom:8px}
.add-intro{color:var(--muted);font-size:13px;margin-bottom:24px}
.security-note{border-top:1px solid var(--line);padding-top:16px;margin-top:20px;color:var(--muted);font-size:12px}
.empty{background:var(--soft);border:1px dashed var(--line);border-radius:11px;padding:28px 18px;text-align:center;color:var(--muted)}
.wide{grid-column:1/-1}.review-card{border-color:#8ab29a;scroll-margin-top:24px}
.review-summary{font:14px/1.9 -apple-system,BlinkMacSystemFont,sans-serif;margin:16px 0}
details{font-size:12px}summary{cursor:pointer;color:var(--muted);width:fit-content}
.technical{margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 ui-monospace,SFMono-Regular,monospace;
background:var(--soft);padding:16px;border-radius:9px;margin:12px 0 0}
#secretLabel{margin-top:20px;max-width:520px}
.consent{display:flex;align-items:flex-start;gap:9px;font-weight:400;font-size:13px;margin:22px 0}
.consent input{margin:3px 0 0}
.result-top{display:flex;justify-content:space-between;align-items:center;gap:20px}
.result-copy{margin-top:8px;color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.result-title{font-size:15px;font-weight:600;margin-top:14px}
.footer{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;color:var(--muted);font-size:11px;margin-top:24px}
.footer p{max-width:720px}.footer span{white-space:nowrap}
.modal-page{background:var(--surface);padding:24px;max-width:720px;margin:auto}
.modal-page h2{font-size:22px;margin:20px 0 14px}.modal-page .account{padding:14px;gap:12px}
.modal-page #status{color:var(--muted);font-size:13px;margin:18px 0}.modal-page #open{width:100%}
.modal-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}
.modal-heading button{min-height:34px;padding:5px 12px;font-size:12px}
.ip-value{font:15px/1.8 ui-monospace,monospace;overflow-wrap:anywhere;margin:8px 0}.setup-steps{padding-left:22px;color:var(--muted)}.setup-steps li{margin:12px 0}.setup-steps code{display:block;overflow-wrap:anywhere;color:var(--ink)}a{color:var(--accent);overflow-wrap:anywhere}
.body-recovery-case{margin:16px 0;padding:12px;border:1px solid var(--line);border-radius:9px}.body-recovery-case p{overflow-wrap:anywhere;font-size:12px;margin:8px 0}.body-recovery-case canvas{max-width:100%;height:auto}
[hidden]{display:none!important}
@media(max-width:760px){
.brandinner{padding:0 20px}.brandbar{height:64px}.workspace{padding:28px 20px 22px}
.page-heading{align-items:flex-start;flex-wrap:wrap}.page-heading button{font-size:12px;padding:8px 11px}
h1{font-size:27px}.layout{grid-template-columns:1fr;gap:18px}.card{padding:22px}
.result-top{align-items:flex-start;flex-direction:column;gap:14px}.footer{flex-direction:column;gap:6px}
}
@media(max-width:380px){.local-badge{display:none}.workspace{padding-left:14px;padding-right:14px}.card{padding:18px}}
@media(prefers-color-scheme:dark){
:root{--bg:#141c18;--surface:#1c2620;--soft:#232e27;--ink:#edf2ed;--muted:#a4b2a8;--line:#354239;
--accent:#77b990;--tint:#233e2d;--danger:#f4979d;--shadow:none}
button.primary{background:#387a52;border-color:#387a52}button.primary:hover:not(:disabled){background:#326d49}
.status.attention{background:#463b24;color:#e3bf7c}
}
@media(prefers-reduced-motion:reduce){button{transition:none}}
"""

STYLE += MANAGEMENT_STYLE

SCRIPT = RENDER_JS + FILE_JS + RULES_JS.replace('全局默认', '微信公众号默认规则').replace('全局版本', '微信默认版本') + MANAGEMENT_JS + r"""
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let bootstrap = location.hash.slice(1);
  history.replaceState(null, '', '/');
  let session = '', csrf = '', review = null, active = false, ended = false;
  let generation = 0, selectedId = '', finished = false;
  let rulesEditor = null;
  let publicationPending = true;
  let restoreAvailable = false;
  let navigationRevision = 0, navigationBusy = false, navigationSequence = null, navigationPolling = false;
  let navigationTimer = null;
  let targetSync = Promise.resolve(), targetPending = 0, targetError = false;
  const recoveryChoices = new Map();
  let rows=[], choices=new Map(), editing=null, avatarPNG=null, avatarPreview=null, imageGeneration=0, imageLoading=false;
  const recoveryIntent = 'RECOVER_BODY_BATCH_V1';
  const body5Intent = 'RECOVER_BODY5_ONCE_V1';
  const isRecovery = intent => [recoveryIntent,body5Intent].includes(intent);
  let riskPhrase = '';
  let riskTyped = false;
  function updateCommit() {
    const riskReady = !review || !isRecovery(review.intent) ||
      (riskTyped && $('riskAck').value === riskPhrase);
    $('commit').disabled = !$('consent').checked || !riskReady || active || ended || navigationBusy;
  }
  function clearBodyRecovery() {
    riskPhrase = '';
    riskTyped = false; $('riskAck').value = ''; $('riskLabel').hidden = true;
    $('bodyRecoveryPreview').replaceChildren();
  }
  function renderBodyRecovery(display) {
    throw new Error("LEGACY_CASE_NOT_DISTRIBUTED");
    clearBodyRecovery();
    if(!display || !Array.isArray(display.cases) || ![1,2,3].includes(display.cases.length) ||
       display.maximum_new_sends !== display.cases.length || display.per_case_new_sends !== 1)
      throw new Error('R1_PREVIEW_INVALID');
    if(display.cases.length===1 && (display.contract_sha!=='NOT_DISTRIBUTED' || display.cases[0].case_id!=='NOT_DISTRIBUTED')) throw new Error('R1_PREVIEW_INVALID');
    riskPhrase = display.cases.length === 1 ? '同意本图额外上传一次' : display.cases.length === 2 ? '同意两图各额外上传一次' : '同意三图各额外上传一次';
    $('riskHelp').textContent = riskPhrase;
    if(display.retained_unrelated_locks > 0) {
      const retained = document.createElement('p');
      retained.textContent = display.retained_unrelated_locks+'条经逐项关系校验的旧锁仍保留，仅不阻止本批固定图片恢复；不会处理、解锁或重新发送对应旧请求。';
      if(display.retained_unknown_adds === 2) retained.textContent += ' 其中两条为旧草稿保存结果未知；本次仅核验其历史，不定位、重建或重发这些草稿。';
      $('bodyRecoveryPreview').append(retained);
    }
    for(const item of display.cases) {
      const row = document.createElement('section'); row.className = 'body-recovery-case';
      const title = document.createElement('h3'); title.textContent = item.label+' · '+item.title;
      const info = document.createElement('p');
      info.textContent = '原位置：'+item.slot+'；原图片 SHA256：'+item.asset_sha256+
        (Number.isInteger(item.asset_bytes) ? '；'+item.asset_mime+'，'+item.asset_bytes+' 字节' : '')+
        (Number.isInteger(item.article_count) ? '；原组'+item.article_count+'篇；原准入次数'+item.original_admitted_attempts+'，结果未知；原attempt：'+item.original_attempt_id : '')+
        (item.source_counts && !Array.isArray(item.source_counts) ? '；已成功素材 '+item.source_counts.succeeded+' 项，其他未发 '+item.source_counts.unsent+' 项' : Array.isArray(item.source_counts) ? '；原源快照 成功/未知/未发：'+item.source_counts.join('/') : '');
      const image = item.preview;
      if(!image || !Number.isInteger(image.width) || !Number.isInteger(image.height) ||
          image.width < 1 || image.height < 1 || image.width > 640 || image.height > 640 ||
          typeof image.rgba !== 'string' || image.rgba.length > 2184536)
        throw new Error('R1_PREVIEW_INVALID');
      const binary = atob(image.rgba);
      if(binary.length !== image.width*image.height*4) throw new Error('R1_PREVIEW_INVALID');
      const data = Uint8ClampedArray.from(binary,c => c.charCodeAt(0));
      const canvas = document.createElement('canvas'); canvas.width=image.width;canvas.height=image.height;
      canvas.setAttribute('aria-label',item.title+'的原图片受控预览');
      canvas.getContext('2d').putImageData(new ImageData(data,image.width,image.height),0,0);
      row.append(title,info,canvas);$('bodyRecoveryPreview').append(row);
    }
    $('riskLabel').hidden = false;
  }
  $('riskAck').addEventListener('input',e => {riskTyped=!!e.isTrusted;updateCommit();});
  $('recoverBody5').addEventListener('click',e => {if(e.isTrusted)prepare(body5Intent);});
  $('recoverBody').addEventListener('click',e => {if(e.isTrusted)prepare(recoveryIntent);});

  const names = {CONNECTED:'已连接',BOUND_IDLE:'已绑定 · 空闲',DISCONNECTED:'已断开',
    ACTION_REQUIRED:'需要处理',UPGRADED:'版本升级完成',STOPPED:'未能确认完成',CLOSED:'已关闭',
    PUBLICATION_DISABLE_COMMITTED:'已确认关闭自动发表',PUBLICATION_ALREADY_OFF:'自动发表原本已关闭',
    READ_RECOVERY_GRANTED:'只读核对已授权',DRAFT_RESTORE_GRANTED:'草稿恢复已授权',TOKEN_CHECK_SUCCEEDED:'本次连接检查成功'};
  const auth = () => ({'Content-Type':'application/json','X-WCE-Session':session,'X-WCE-CSRF':csrf,
    'X-WCE-Navigation-Revision':String(navigationRevision)});
  async function call(path, value = {}, invalidationOnly = false) {
    const epoch = generation;
    if(ended) throw new Error('SETTINGS_EXPIRED');
    const response = await fetch(path,{method:'POST',headers:auth(),body:JSON.stringify(value),
      credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer'});
    const result = await response.json();
    if(ended) throw new Error('SETTINGS_EXPIRED');
    if(epoch !== generation && !invalidationOnly) throw new Error('STALE_RESPONSE');
    if (!response.ok) throw new Error(result.error || 'SETTINGS_RESULT_UNDETERMINED');
    return result;
  }
  function notice(text, error = false) {
    $('notice').textContent = text;
    $('notice').className = error ? 'notice error' : 'notice';
  }
  function stop() {
    ended = true; generation++; clearDiagnostic();
    if (navigationTimer !== null) clearInterval(navigationTimer);
    $('result').textContent = ''; $('resultTitle').textContent = ''; $('resultCopy').textContent = '';
    $('reviewDetails').textContent = ''; $('reviewSummary').textContent = ''; $('review').hidden = true;
    $('secret').value = ''; $('appid').value = ''; $('label').value = '';
    clearProfile();
    clearBodyRecovery();
    review = null; bootstrap = session = csrf = '';
    document.querySelectorAll('button,input,select,textarea').forEach(x => x.disabled = true);
    notice('管理页面已关闭或到期。已有绑定保留；已发送的请求仍可能完成。');
  }
  function error(e) {
    if(ended || e.message === 'STALE_RESPONSE') return;
    $('secret').value = '';
    const code = /^[A-Z][A-Z0-9_]{1,80}$/.test(e.message) ? e.message : 'SETTINGS_RESULT_UNDETERMINED';
    notice('操作未完成：' + code + '。页面不会自动重试。', true);
  }
  function renderAccounts(data) {
    rows=data.connections; choices=WCEPresentation.choices(rows);
    $('accounts').replaceChildren(); $('select').replaceChildren();
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = '请选择要管理的账号'; $('select').append(placeholder);
    $('accountCount').textContent = data.connections.length + ' 个';
    if (!data.connections.length) {
      const empty = document.createElement('div'); empty.className = 'empty';
      empty.textContent = '还没有公众号。从「添加公众号」开始绑定。'; $('accounts').append(empty);
    }
    for (const account of rows) {
      $('accounts').append(WCEPresentation.card(account,choices.get(account.connection_id),editProfile));
      const option = document.createElement('option'); option.value = account.connection_id;
      option.textContent = choices.get(account.connection_id);
      $('select').append(option);
    }
    if(data.connections.some(a => a.connection_id === selectedId)) $('select').value = selectedId;
    else $('select').value = '';
    OAManagement.accounts(rows,choices);
    if(rulesEditor)rulesEditor.accounts(rows,choices);
    selectedPreview();
  }
  function selectedPreview() {
    $('selectedAccount').replaceChildren();
    const row=rows.find(row=>row.connection_id===$('select').value);
    if(row)$('selectedAccount').append(WCEPresentation.card(row,choices.get(row.connection_id)));
    OAManagement.selected($('select').value);
    if(!document.body.classList.contains('oa-management')){void refreshPublication();void refreshRestore();}
  }
  function clearProfile() {
    imageGeneration++; imageLoading=false; editing=null; avatarPNG=avatarPreview=null;
    $('profileEditor').hidden=true; $('profileName').value=''; $('profileFile').value='';
    $('profilePreview').replaceChildren();
  }
  async function editProfile(row) {
    if(ended || active || review || targetPending || targetError || !['MISSING','SAVED'].includes(row.presentation?.state))return;
    generation++; clearDiagnostic(); clearProfile(); active=true; controls();
    try {
      const ack=await call('/select',{connection_id:row.connection_id});
      if(ack.state!=='READY' || ack.connection_id!==row.connection_id) throw new Error('SETTINGS_RESULT_UNDETERMINED');
      selectedId=row.connection_id; $('select').value=selectedId; finished=false;
      renderResult({state:'NOT_SUBMITTED'}); selectedPreview(); editing=row;
      $('profileName').value=row.presentation.display_name;
      avatarPreview=row.presentation.avatar;
      $('profilePreview').append(WCEPresentation.avatar(avatarPreview));
      $('profileEditor').hidden=false; $('profileName').focus();
    } catch(e) {error(e);} finally {active=false;controls();}
  }
  $('profileCancel').addEventListener('click',()=>{if(!active){clearProfile();controls();}});
  $('profileClear').addEventListener('click',e=>{
    if(!e.isTrusted || active || !editing)return;
    imageGeneration++;imageLoading=false;avatarPNG='';avatarPreview=null;
    $('profileFile').value='';$('profileSave').disabled=false;
    $('profilePreview').replaceChildren(WCEPresentation.avatar(null));
  });
  $('profileFile').addEventListener('change',async e=>{
    if(!e.isTrusted || ended || active || !editing)return;
    const generation=++imageGeneration, file=e.target.files[0];
    if(!file)return;
    imageLoading=true;$('profileSave').disabled=true;
    try {
      const result=await WCEThumbnail.load(file);
      if(generation!==imageGeneration || ended || !editing)return;
      avatarPNG=result.png;avatarPreview=result.avatar;
      $('profilePreview').replaceChildren(WCEPresentation.avatar(avatarPreview));
    } catch(_) {
      if(generation===imageGeneration)notice('头像未能读取。请选择不超过 2 MB、4096 像素边长与 400 万像素的 PNG 或 JPEG。',true);
    } finally {
      if(generation===imageGeneration){imageLoading=false;$('profileSave').disabled=false;}
    }
  });
  $('profileSave').addEventListener('click',async e=>{
    if(!e.isTrusted || ended || active || review || imageLoading || !editing)return;
    active=true;controls();$('profileSave').disabled=true;
    const value={connection_id:editing.connection_id,expected_revision:editing.presentation.revision,
      display_name:$('profileName').value.trim(),avatar_png:avatarPNG};
    try {
      await call('/presentation',value);
      clearProfile();await refresh();notice('公众号显示资料已保存到本机。回到插件弹窗后点击刷新即可看到。');
    } catch(e) {
      clearProfile();error(e);
      if(e.message==='PRESENTATION_WRITE_UNKNOWN')notice('本次保存结果未确认。请刷新查看当前资料，页面不会自动重试。',true);
    } finally {active=false;controls();}
  });
  function renderResult(result) {
    OAManagement.result(result);
    $('result').textContent = JSON.stringify(result,null,2);
    const state = result.error ? 'STOPPED' : result.state;
    const descriptions = {
      NOT_SUBMITTED:'完成账号信息核对后，本次操作结果会显示在这里。',
      IN_PROGRESS:'操作正在处理中。可以查询结果，请勿重复提交。',
      TOKEN_CHECK_SUCCEEDED:'本次已向微信发送一次连接验证并成功。素材、草稿等业务接口的权限仍需各自验证。',
      BOUND_IDLE:'账号已绑定，当前处于空闲状态。你可以在使用插件时明确选择该账号。',
      UPGRADED:'账号授权版本已更新。已有绑定及各账号的启用状态已保留。',
      READ_RECOVERY_GRANTED:'原封面的这一次只读核对已授权。程序将按原请求查找图片，不重复上传封面；本页没有执行素材读取。',
      DISCONNECTED:'该账号已断开。已经发出的请求仍可能完成。',
      PUBLICATION_DISABLE_COMMITTED:'这次关闭已记录。已经发出的请求可能无法撤回。',
      PUBLICATION_ALREADY_OFF:'该账号原本已经关闭自动发表，本次没有新增修改。',
      DRAFT_RESTORE_GRANTED:'本次恢复范围已授权，尚未在此页面发送或保存草稿。后续保存和独立读回的结果需分别核验。',
      STOPPED:'本次执行未能确认正常完成，已经发出的请求仍可能完成。请查看详细回执，勿重复提交。'
    };
    $('resultTitle').textContent = names[state] || ({NOT_SUBMITTED:'等待操作',IN_PROGRESS:'正在处理'})[state] || '操作回执';
    $('resultCopy').textContent = descriptions[state] || '已收到本次操作的状态，完整信息可在详细回执中查看。';
    if (result.error) {
      const messages = {
        BOOTSTRAP_TOKEN_IP_DENIED:['IP 白名单需要配置','微信拒绝了本次来源 IP。请按下方引导核对所选公众号的白名单。'],
        BOOTSTRAP_TOKEN_ADMIN_PENDING:['等待管理员确认','请由公众号管理员完成微信侧确认。本页不会循环请求。'],
        BOOTSTRAP_TOKEN_ADMIN_DENIED:['管理员已拒绝','请联系公众号管理员处理，勿通过更换网络绕过拒绝。'],
        BOOTSTRAP_TOKEN_QUOTA_DENIED:['请求额度受限','请在微信开发平台检查频率和额度，暂勿反复检查。'],
        BOOTSTRAP_TOKEN_CREDENTIAL_REJECTED:['凭据需要本人处理','请本人核对 AppID 与 AppSecret，勿把密钥发到聊天。'],
        CONNECTION_UPGRADE_REVIEW_REQUIRED:['需要升级授权版本','请返回管理后核对并升级当前插件版本。'],
        CONNECTION_CHECK_BUDGET_SPENT:['历史专项检查已消耗','这份历史专项中的原请求不会重发。正常添加与连接检查不使用这份专项预算。'],
        CONNECTION_CHECK_COOLDOWN:['历史专项执行条件未满足','尚未发送本次历史专项请求；正常连接检查没有本机等待额度。'],
        CONNECTION_CHECK_TIME_INVALID:['本机时间不可用','未能核验本次检查时间，尚未发送请求。'],
        CONNECTION_ENROLLMENT_REQUIRES_RECONCILIATION:['原尝试需要核对','原尝试结果未知，不能再次提交同一账号。其他已绑定账号仍可单独管理。']
      };
      const message = messages[result.error];
      if(message) { $('resultTitle').textContent = message[0]; $('resultCopy').textContent = message[1]; }
      $('resultCopy').textContent += ' 错误码：' + result.error;
      if(result.retry_available) $('resultCopy').textContent += ' 本次明确拒绝已保留；修复后可返回管理，为同一 AppID 重新核对并提交一次新检查。本页不会自动重试。';
    }
    if(result.checked_at) $('resultCopy').textContent += ' 检查时间：'+new Date(result.checked_at*1000).toLocaleString();
  }
  async function refresh() { renderAccounts(await call('/overview')); }
  async function refreshPublication() {
    const target = selectedId;
    publicationPending = true; controls();
    if(!target) { $('publicationState').textContent='自动发表默认关闭。选择账号后查看该账号状态。'; return; }
    $('publicationState').textContent='正在读取所选账号的自动发表状态。';
    try {
      const result = await call('/publication-status',{connection_id:target});
      if(target !== selectedId) return;
      if(result.connection_id !== target || !['ON','OFF','UNKNOWN'].includes(result.state) ||
          (result.state === 'UNKNOWN' ? result.enabled !== null :
           typeof result.enabled !== 'boolean' || result.enabled !== (result.state === 'ON')))
        throw new Error('PUBLICATION_STATE_UNVERIFIED');
      publicationPending = result.state === 'UNKNOWN' || result.pending_disable !== null;
      $('publicationState').textContent='所选账号：自动发表'+(result.state==='UNKNOWN'?'状态未能确认':result.enabled?'已启用':'已关闭')+
        (publicationPending ? '。此前关闭结果尚未确认，请查询原操作结果，不能重复提交。' : '')+
        (!publicationPending && result.last_disable?.state === 'OFF_CONFIRMED' ? '。此前关闭操作已按原记录确认。' : '')+
        (!publicationPending && result.last_disable?.state === 'NO_CHANGE' ? '。此前操作确认账号原本已关闭。' : '')+
        '。独立审核运行环境尚不可用，生产目录与完整基线的接入尚未完成，当前无法开启。';
      controls();
    } catch(e) {
      if(e.message === 'STALE_RESPONSE' || target !== selectedId || ended) return;
      $('publicationState').textContent='当前账号的自动发表状态未能确认。独立审核运行环境尚不可用，当前无法开启。';
    }
  }
  async function refreshRestore() {
    const target = selectedId;
    restoreAvailable = false; controls();
    if(!target) { $('restoreState').textContent='选择账号后查看本批草稿恢复准备。'; return; }
    $('restoreState').textContent='正在检查本批草稿恢复准备。';
    try {
      const result = await call('/restore-status',{connection_id:target});
      if(target !== selectedId) return;
      if(result.connection_id !== target || !['AVAILABLE','NO_PROPOSAL','HOLD'].includes(result.state) ||
          !Number.isSafeInteger(result.candidate_count) || result.candidate_count < 0 || result.candidate_count > 100 ||
          typeof result.message !== 'string' || result.message.length > 1024 ||
          (result.state === 'AVAILABLE' && result.candidate_count < 1))
        throw new Error('DRAFT_RESTORE_STATUS_INVALID');
      restoreAvailable = result.state === 'AVAILABLE';
      $('restoreState').textContent = (restoreAvailable ? '可核对 '+result.candidate_count+' 份恢复对象。' :
        result.state === 'NO_PROPOSAL' ? '目前没有可核对的恢复对象。' : '恢复准备尚未满足条件。') + ' ' + result.message;
      controls();
    } catch(e) {
      if(e.message === 'STALE_RESPONSE' || target !== selectedId || ended) return;
      $('restoreState').textContent='本批恢复准备无法确认，请稍后刷新查看。';
    }
  }
  function restoreSummary(display) {
    const bounded = (v,n) => typeof v === 'string' && v.length > 0 && v.length <= n;
    if(!display || !Array.isArray(display.candidates) || display.candidates.length < 1 || display.candidates.length > 100 ||
        !Array.isArray(display.published_exclusions) || display.published_exclusions.length > 128 ||
        display.max_saves_per_object !== 1 || display.max_reads_per_object !== 5 || display.new_uploads !== 0 ||
        !display.published_exclusions.every(x => x && typeof x === 'object' &&
          ['connection_id','parent_step_id','version','lineage','title'].every(k => bounded(x[k],512))))
      throw new Error('DRAFT_RESTORE_REVIEW_INVALID');
    const window = display.clear_window;
    if(!window || typeof window !== 'object' || !Number.isFinite(window.not_before) || !Number.isFinite(window.not_after) ||
        window.not_before < 0 || window.not_before > window.not_after || window.not_after > 8640000000000)
      throw new Error('DRAFT_RESTORE_REVIEW_INVALID');
    const lines = ['本人清空时间范围（UTC）：'+new Date(window.not_before*1000).toISOString()+' 至 '+new Date(window.not_after*1000).toISOString()];
    for (const item of display.candidates) {
      if(!item || !Array.isArray(item.titles) || item.titles.length < 1 || item.titles.length > 8 ||
          !item.titles.every(x => bounded(x,256)) || !bounded(item.old_reference,512) || !bounded(item.clear_source,2000) ||
          !bounded(item.account_label,256) || !bounded(item.account_id,128) || !bounded(item.version,512) ||
          !Number.isSafeInteger(item.prior_restoration_count) || item.prior_restoration_count < 0 ||
          !item.clear_window || item.clear_window.not_before !== window.not_before || item.clear_window.not_after !== window.not_after)
        throw new Error('DRAFT_RESTORE_REVIEW_INVALID');
      const hex = x => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
      if(!hex(item.original_payload_sha) || !hex(item.restore_payload_sha) || !hex(item.comment_policy_sha) ||
          !item.comment_policy || item.comment_policy.id !== 'RESTORE_COMMENT_DEFAULTS_1_0_V1' ||
          item.comment_policy.schema !== 1 || !item.comment_policy.values ||
          item.comment_policy.values.need_open_comment !== 1 || item.comment_policy.values.only_fans_can_comment !== 0 ||
          !Array.isArray(item.comments_by_article) || item.comments_by_article.length !== item.titles.length)
        throw new Error('DRAFT_RESTORE_REVIEW_INVALID');
      for (const [i, c] of item.comments_by_article.entries()) {
        if(!c || c.index !== i || !c.original || !c.restore ||
            c.restore.need_open_comment !== 1 || c.restore.only_fans_can_comment !== 0 ||
            !['need_open_comment','only_fans_can_comment'].every(k => c.original[k] &&
              typeof c.original[k].present === 'boolean' &&
              (c.original[k].present || c.original[k].value === null)))
          throw new Error('DRAFT_RESTORE_REVIEW_INVALID');
        const previous = k => c.original[k].present ? JSON.stringify(c.original[k].value) : '未提供';
        lines.push('第 '+(i+1)+' 篇留言：原设置 '+previous('need_open_comment')+' / '+previous('only_fans_can_comment')+
          '；恢复设置：开启留言，所有人可留言（1 / 0）。');
      }
      lines.push('原内容摘要：'+item.original_payload_sha+'；恢复内容摘要：'+item.restore_payload_sha+
        '；留言策略摘要：'+item.comment_policy_sha);
      lines.push('恢复账号：'+item.account_label+' · '+item.account_id, '原稿顺序：'+item.titles.join(' → '),
        '旧成功草稿引用：'+item.old_reference+'；版本：'+item.version, '本人清空来源：'+item.clear_source,
        '此前已记录恢复次数：'+item.prior_restoration_count);
    }
    if(display.published_exclusions.length) {
      lines.push('已发表排除对象：');
      for(const item of display.published_exclusions) lines.push('标题：'+item.title+'；账号：'+item.connection_id+
        '；原步骤：'+item.parent_step_id+'；版本：'+item.version+'；文章脉络：'+item.lineage);
    } else lines.push('本批未列已发表排除条目，不代表全部历史已核验。');
    lines.push('请本人核对：本批原成功稿均在上述清空时段之前保存，确已删除、尚未发表；已发表内容已按上述明细排除。',
      '候选质量依据为程序化检查，未验证视觉质量；来源标识用于定位，不证明质量。',
      '每个对象最多新保存一次、独立读取五次；不上传新图片，不公开发布。确认只建立恢复授权，实际保存与读回另行核验。');
    return lines;
  }
  function clearDiagnostic() {
    $('ipValue').textContent = ''; $('ipPanel').hidden = true; $('copyIP').disabled = true;
  }
  function controls() {
    const unavailable = ended || !session || active || targetPending > 0 || targetError || navigationBusy;
    for(const id of ['add','upgrade','enable','disconnect','checkConnection','loadRecovery','recover','recoverBody','recoverBody5'])
      $(id).disabled = unavailable || !!review || finished || !!editing;
    $('publicationEnable').disabled = true;
    $('publicationDisable').disabled = unavailable || !!review || finished || !!editing || !selectedId || publicationPending;
    $('restoreDrafts').disabled = unavailable || !!review || finished || !!editing || !selectedId || $('select').value !== selectedId || !restoreAvailable;
    $('select').disabled = unavailable || !!review || !!editing;
    $('appid').disabled = $('label').disabled = ended || !session || active || !!review || !!editing;
    $('appid').readOnly = $('label').readOnly = $('secret').readOnly = navigationBusy;
    $('riskAck').readOnly = navigationBusy;
    $('consent').disabled = $('cancel').disabled = navigationBusy;
    updateCommit();
    OAManagement.busy(unavailable || !!review || !!editing);
    $('continue').disabled = ended || !session || active || targetPending > 0 || !!editing || navigationBusy;
    $('refresh').disabled = unavailable || !!review;
    $('readResult').disabled = unavailable || !!editing;
    for(const id of ['profileName','profileFile','profileClear','profileCancel']) $(id).disabled = unavailable;
    $('profileSave').disabled = unavailable || imageLoading || !editing;
    document.querySelectorAll('.edit-profile').forEach(button => button.disabled = unavailable || !!review || button.dataset.editable !== 'true');
    document.querySelectorAll('#recoveryTargets input[type=checkbox]').forEach(box => {
      box.disabled = unavailable || !!review || finished || !!editing;
    });
  }
  async function diagnostic() {
    const result = await call('/diagnostic');
    if(ended || editing || result.state !== 'IP_DENIED' || result.connection_id !== selectedId || !finished) return;
    $('ipPanel').hidden = false;
    $('ipValue').textContent = result.observed_ip || '微信未提供可识别的来源 IP';
    $('copyIP').disabled = !result.observed_ip;
  }
  $('copyIP').addEventListener('click',async e => {
    if(!e.isTrusted || ended || active || editing || targetPending || targetError || $('copyIP').disabled) return;
    const epoch = generation;
    try { await navigator.clipboard.writeText($('ipValue').textContent); if(!ended && epoch === generation) notice('已复制本次微信返回的来源 IP。'); }
    catch(_) { if(!ended) notice('浏览器未允许复制，请手动选中当前来源 IP。'); }
  });
  for(const id of ['appid','label']) $(id).addEventListener('input',e => {
    if(!e.isTrusted || ended || active || review || !session) return;
    generation++; clearDiagnostic();
    selectedId = ''; $('select').value = ''; finished = false; selectedPreview();
    renderResult({state:'NOT_SUBMITTED'});
    if(targetPending) return;
    targetPending = 1; controls();
    // One request in flight; changes during it are coalesced into one further
    // invalidation. An old ACK cannot re-enable actions for a newer target.
    targetSync = (async () => {
      while(!ended) {
        const epoch = generation;
        const ack = await call('/select',{connection_id:null},true);
        if(ack.state !== 'READY' || ack.connection_id !== null || !Number.isSafeInteger(ack.generation))
          throw new Error('SETTINGS_RESULT_UNDETERMINED');
        if(epoch === generation) { targetError = false; break; }
      }
    })().catch(e => { targetError = true; error(e); })
      .finally(() => { targetPending = 0; controls(); });
  });
  async function chooseAccount(next,e) {
    if(!e.isTrusted || active || ended || review || targetPending || targetError || editing) return;
    generation++; clearDiagnostic(); active = true; controls();
    try {
      await call('/select',{connection_id:next || null});
      selectedId = next; $('select').value = next; finished = false; selectedPreview();
      renderResult({state:'NOT_SUBMITTED'}); notice('已选择账号，尚未发起连接检查。');
    } catch(e) { error(e); } finally { active = false; controls(); }
  }
  $('select').addEventListener('change',e=>{const next=e.target.value;e.target.value=selectedId;chooseAccount(next,e);});
  $('continue').addEventListener('click',async e => {
    if(!e.isTrusted || active || ended || targetPending) return;
    generation++; clearDiagnostic(); clearReview(); active = true; controls();
    try {
      await call('/continue'); targetError = false; finished = false; renderResult({state:'NOT_SUBMITTED'});
      await refresh(); notice('可以继续管理账号。每次检查都需重新核对，不会自动发送请求。');
      $('appid').focus();
    } catch(e) { error(e); } finally { active = false; controls(); }
  });
  function clearReview() {
    clearBodyRecovery();
    review = null; $('review').hidden = true; $('secret').value = '';
    $('consent').checked = false; $('commit').disabled = true;
  }

  function addPageClean() {
    return !ended && !active && !review && !editing && !targetPending && !targetError &&
      !$('appid').value && !$('label').value && !$('secret').value && !$('riskAck').value &&
      !$('profileName').value && !$('profileFile').value && !$('consent').checked &&
      !document.querySelector('#recoveryTargets input:checked') && !imageLoading;
  }
  function addPageFocused() {
    const field = $('appid'), rect = field.getBoundingClientRect();
    return document.visibilityState === 'visible' && document.hasFocus() &&
      document.activeElement === field && rect.width > 0 && rect.height > 0 &&
      rect.top < innerHeight && rect.bottom > 0 && rect.left < innerWidth && rect.right > 0;
  }
  async function finishNavigation(sequence) {
    if (!addPageClean() || !addPageFocused()) return false;
    const result = await call('/navigation/complete',{sequence,visible:true,focused:true},true);
    if (result.state !== 'COMPLETE' || result.sequence !== sequence || result.revision !== navigationRevision)
      throw new Error('SETTINGS_NAVIGATION_UNKNOWN');
    navigationBusy = false; navigationSequence = null; controls();
    notice('已打开添加公众号。请填写账号信息，下一步再核对。');
    return true;
  }
  async function navigationPoll() {
    if (ended || !session || navigationPolling) return;
    navigationPolling = true;
    try {
      if (navigationBusy && navigationSequence !== null) {
        const status = await call('/navigation/status',{sequence:navigationSequence},true);
        if (status.state === 'APPLIED' || status.state === 'UNKNOWN') {
          navigationRevision = status.revision;
          selectedId = ''; $('select').value = ''; selectedPreview(); finished = false;
          renderResult({state:'NOT_SUBMITTED'});
          if (document.visibilityState === 'visible' && document.hasFocus()) {
            OAManagement.adding();
            $('appid').scrollIntoView({block:'center'}); $('appid').focus({preventScroll:true});
            await finishNavigation(navigationSequence);
          }
        } else if (status.state === 'CANCELLED') {
          navigationRevision = status.revision; navigationBusy = false; navigationSequence = null; controls();
        } else if (status.state === 'COMPLETE') {
          navigationRevision = status.revision; navigationBusy = false; navigationSequence = null; controls();
        }
        return;
      }
      const navigation = await call('/navigation/poll',{},true);
      if (navigation.state !== 'READY') {
        if (navigation.state === 'NONE' && Number.isSafeInteger(navigation.revision))
          navigationRevision = navigation.revision;
        return;
      }
      if (!Number.isSafeInteger(navigation.sequence) || navigation.sequence < 1)
        throw new Error('SETTINGS_NAVIGATION_STALE');
      if (!addPageClean()) { notice('请先完成或取消当前页面中的输入，再添加公众号。'); return; }
      // Freeze synchronously before any await; old target changes cannot race
      // an ACK. readOnly keeps the target field focusable without data loss.
      navigationBusy = true; navigationSequence = navigation.sequence; controls();
      if (!addPageClean() || document.visibilityState !== 'visible' || !document.hasFocus()) {
        navigationBusy = false; navigationSequence = null; controls(); return;
      }
      OAManagement.adding();
      $('appid').scrollIntoView({block:'center'}); $('appid').focus({preventScroll:true});
      if (!addPageClean() || !addPageFocused()) { navigationBusy = false; navigationSequence = null; controls(); return; }
      const ack = await call('/navigation/ack',{sequence:navigation.sequence,visible:true,focused:true},true);
      if (ack.state !== 'APPLIED' || ack.sequence !== navigation.sequence || !Number.isSafeInteger(ack.revision))
        throw new Error('SETTINGS_NAVIGATION_UNKNOWN');
      navigationRevision = ack.revision;
      selectedId = ''; $('select').value = ''; selectedPreview(); finished = false;
      renderResult({state:'NOT_SUBMITTED'});
      await finishNavigation(navigation.sequence);
    } catch (e) {
      // Never replay ACK: while its result is unknown remain frozen and query
      // the exact same in-memory navigation sequence on the next poll.
      if (!ended && navigationBusy) notice('添加页面状态正在核对；请勿重复操作。',true);
      else error(e);
    } finally {
      navigationPolling = false;
    }
  }
  async function prepare(intent) {
    if (active || ended || navigationBusy || targetPending || targetError || finished) return;
    if (editing) { notice('请先保存或取消资料编辑，再操作账号授权。'); return; }
    if (review) { notice('请先确认或取消当前核对，再选择另一项操作。'); return; }
    generation++; clearDiagnostic(); clearReview(); active = true; controls();
    try {
      let value = {intent};
      if (intent === 'ADD') Object.assign(value,{appid:$('appid').value.trim(),label:$('label').value.trim()});
      if (['ENABLE','DISCONNECT','CHECK_CONNECTION','PUBLICATION_DISABLE','RESTORE_DRAFTS'].includes(intent)) value.connection_id = $('select').value;
      if (intent === 'RECOVER_COVERS') {
        value.targets = [...recoveryChoices].filter(([box]) => box.checked).map(([,target]) => target);
        if (!value.targets.length || value.targets.length > 2) throw new Error('SETTINGS_INVALID_REQUEST');
      }
      const response = await call('/review',value);
      if(isRecovery(intent)) {
        const d=response.review?.body_recovery;
        if(response.review?.intent!==intent || !d ||
            ((intent===body5Intent)!==(d.contract_sha==='NOT_DISTRIBUTED')) ||
            (intent===body5Intent && (d.maximum_new_sends!==1 || d.cases?.length!==1 || d.cases[0].case_id!=='NOT_DISTRIBUTED'))) {
          await call('/cancel'); throw new Error('R1_REVIEW_CHANGED');
        }
      }
      let restoreLines = null;
      if(intent === 'RESTORE_DRAFTS') {
        try {
          if(response.review.intent !== 'RESTORE_DRAFTS' || response.review.connection_id !== selectedId)
            throw new Error('DRAFT_RESTORE_REVIEW_INVALID');
          restoreLines = restoreSummary(response.review.restore_drafts);
        }
        catch(e) { await call('/cancel'); throw e; }
      }
      selectedId = response.review.new_account?.connection_id || response.review.selected_connection || selectedId;
      review = {id:response.review_id,approval:response.approval,intent};
      $('review').hidden = false;
      $('secretLabel').hidden = intent !== 'ADD';
      const r = response.review;
      $('reviewTitle').textContent = ({ADD:'确认添加公众号',UPGRADE_ONLY:'确认版本升级',
        ENABLE:'确认重新启用',DISCONNECT:'确认断开',CHECK_CONNECTION:'检查所选账号连接',RECOVER_COVERS:'确认原封面只读核对',RECOVER_BODY_BATCH_V1:'确认固定正文各额外上传一次',RECOVER_BODY5_ONCE_V1:'确认最后一张正文图额外上传一次',PUBLICATION_DISABLE:'确认关闭自动发表',RESTORE_DRAFTS:'确认恢复已清空草稿'})[intent];
      const summary = [];
      if(intent === 'RESTORE_DRAFTS') {
        const account=rows.find(a=>a.connection_id===selectedId);
        summary.push('本页选择的账号：'+(account ? choices.get(account.connection_id) : selectedId)+'；本批实际恢复范围以以下逐项账号为准。', ...restoreLines);
      } else if(intent === 'PUBLICATION_DISABLE') {
        const account=rows.find(a=>a.connection_id===r.connection_id);
        summary.push('所选账号：'+(account ? choices.get(account.connection_id) : r.connection_id),
          '关闭自动发表；已经发出的请求可能无法撤回。不会重发未知请求，不影响其他账号。');
      } else if(isRecovery(intent)) {
        renderBodyRecovery(r.body_recovery);
        summary.push('以下'+r.body_recovery.cases.length+'项原正文结果均未知，原图片可能已经在微信保存；本次每项最多额外上传一次，总计最多'+r.body_recovery.maximum_new_sends+'次，可能产生重复图片。',
          '原成功素材、原 UNKNOWN、原未发余额保持；不自动重试，不由此保存草稿或公开发布。',
          '插件版本与原五项权限已自动承接；这里仅批准独立风险额度，不需要输入 AppSecret 或再次升级。',
          '按下列固定顺序执行，任何错误、超时、关闭或撤销均停止全批；不会自动接续或再次补传。',
          r.body_recovery.cases.length === 1 ? '本次只包括此篇最后一张正文图；前五项已成功素材不再上传，原稿内容与配图顺序不变。' : r.body_recovery.cases.length === 2 ? '未列出的晨间正文不在本批，不会因本次批准获得新发送权限，也不因此声明其已发表。' : '本批只包括下列三项，每项额外一次；未列出的请求不获得发送权限。',
          '请核对图片及其原位置，并输入：'+riskPhrase);
      } else {
      if (r.new_account) summary.push('新账号：'+r.new_account.label+' · '+r.new_account.appid);
      if(intent === 'CHECK_CONNECTION') {
        const a = r.existing_accounts.find(a => a.connection_id === r.selected_connection);
        summary.push('本次账号：'+a.label+' · '+a.appid);
      }
      if(r.retry_sequence) summary.push('同一账号的第 '+r.retry_sequence+' 次尝试；原记录保留，不是新账号。');
      for (const a of r.existing_accounts) if (a.will_change) summary.push(
        '现有账号：'+a.label+' · '+a.appid+'；'+(a.enabled_before?'已启用':'已断开')+
        ' → '+(a.enabled_after?'已启用':'已断开'));
      summary.push(intent === 'ADD'
        ? '仅验证新账号一次，成功后将密钥保存到该号系统钥匙串。结果未知时不自动重试。完成后账号处于空闲状态。'
        : intent === 'CHECK_CONNECTION' ? '本次从该账号系统钥匙串读取密钥，向微信发送一次普通连接检查。不会使用缓存结果，不上传图片、不读写草稿，不自动重试。'
        : '本次不读取已有密钥，不发起连接验证。已发出的请求无法撤回。');
      summary.push('持续委托只包含你明确请求的图片、草稿保存和读取；不包含公开发布、群发或重发未知请求。');
      if (r.cover_recovery) {
        for (const item of r.cover_recovery.targets) {
          const target = item.proposal.target;
          const account = r.existing_accounts.find(a => a.connection_id === item.connection_id);
          summary.push('只读核对：'+(account?.label || item.connection_id)+' · '+target.title+
            '\n原请求：'+target.request_key+'；此前已启动核对 '+item.proposal.prior_read_attempts+' 次。');
        }
        summary.push('每号只允许本次核对：最多 1000 次素材列表读取和 5 次图片读取，零业务写入；确认后 15 分钟内启动，执行最多 5 分钟。中断或结果未知也消耗这一次，不会自动重跑。',
          '两遍完整列表一致，且只有一张图片的尺寸、全部像素和透明度精确匹配才恢复原记录。允许指定 PNG 元数据差异，不验证 C2PA；不缩放、不近似匹配，不重发封面。');
      }
      }
      OAManagement.reviewing(intent);
      $('reviewSummary').textContent = summary.join('\n');
      const technical = isRecovery(intent) ? {...r,body_recovery:{...r.body_recovery,
        cases:r.body_recovery.cases.map(item => ({...item,preview:{width:item.preview.width,height:item.preview.height,rgba:'[仅在原图画布显示]'}}))}} : r;
      $('reviewDetails').textContent = JSON.stringify(technical,null,2);
      notice('请核对本次操作。确认有效期为两分钟。');
      $('review').scrollIntoView({block:'start'});
      $('reviewTitle').focus({preventScroll:true});
    } catch(e) { error(e); } finally { active = false; controls(); }
  }
  $('consent').addEventListener('change',updateCommit);
  $('checkConnection').addEventListener('click',e => { if(e.isTrusted) prepare('CHECK_CONNECTION'); });
  $('add').addEventListener('click',e => { if(e.isTrusted) prepare('ADD'); });
  $('upgrade').addEventListener('click',e => { if(e.isTrusted) prepare('UPGRADE_ONLY'); });
  $('enable').addEventListener('click',e => { if(e.isTrusted) prepare('ENABLE'); });
  $('disconnect').addEventListener('click',e => { if(e.isTrusted) prepare('DISCONNECT'); });
  $('publicationDisable').addEventListener('click',e => { if(e.isTrusted) prepare('PUBLICATION_DISABLE'); });
  $('restoreDrafts').addEventListener('click',e => { if(e.isTrusted && restoreAvailable) prepare('RESTORE_DRAFTS'); });
  $('loadRecovery').addEventListener('click',async e => {
    if(!e.isTrusted || active || ended || review) return;
    active = true;
    try {
      const result = await call('/cover-recoveries');
      recoveryChoices.clear(); $('recoveryTargets').replaceChildren();
      for(const target of result.targets) {
        const label = document.createElement('label'); label.className = 'consent';
        const box = document.createElement('input'); box.type = 'checkbox';
        const text = document.createElement('span');
        text.textContent = target.label+' · '+target.title+'（此前核对 '+target.prior_read_attempts+' 次）';
        recoveryChoices.set(box,{connection_id:target.connection_id,request_key:target.request_key});
        label.append(box,text); $('recoveryTargets').append(label);
      }
      $('recover').hidden = !result.targets.length;
      notice(result.targets.length ? '选择需要核对的原封面，最多两个账号，然后查看本次授权。'
        : '没有可核对的未完成封面。');
    } catch(e) { error(e); } finally { active = false; controls(); }
  });
  $('recover').addEventListener('click',e => { if(e.isTrusted) prepare('RECOVER_COVERS'); });
  $('refresh').addEventListener('click',() => refresh().catch(error));
  $('cancel').addEventListener('click',async () => {
    if(active) return;
    generation++; clearDiagnostic();
    try { await call('/cancel'); clearReview(); $('appid').value=$('label').value='';OAManagement.cancelled();controls(); notice('已取消本次操作。'); } catch(e) { error(e); }
  });
  $('commit').addEventListener('click',async e => {
    if (!e.isTrusted || ended || active || !review || !$('consent').checked ||
        (isRecovery(review.intent) && (!riskTyped || $('riskAck').value !== riskPhrase))) return;
    active = true; controls(); $('commit').disabled = true;
    let value = {review_id:review.id,approval:review.approval};
    if(review.intent === 'ADD') value.secret = $('secret').value;
    if(isRecovery(review.intent)) value.risk_ack = $('riskAck').value;
    $('secret').value = ''; clearBodyRecovery(); review = null;
    $('review').hidden = true;
    for(const id of ['add','upgrade','enable','disconnect','checkConnection','loadRecovery','recover','recoverBody','recoverBody5']) $(id).disabled = true;
    notice('正在执行一次提交。请稍候；关闭页面无法撤回已经发出的请求。');
    try {
      const promise = call('/commit',value);
      value = null;
      const result = await promise;
      finished = true; renderResult(result);
      await diagnostic();
      notice((result.error ? names.STOPPED : names[result.state] || result.state)+'。本次提交不会重复发送。', !!result.error);
      $('review').hidden = true;
      await refresh();
    } catch(e) { error(e); } finally { value = null; active = false; finished = true; controls(); }
  });
  $('readResult').addEventListener('click',async () => {
    if(ended || active || editing || targetPending || targetError) return;
    try { renderResult(await call('/result')); await diagnostic(); } catch(e) { error(e); }
  });
  $('close').addEventListener('click',async () => {
    const closing = call('/close'); stop(); try { await closing; } catch(_) {}
  });
  addEventListener('pagehide',() => {
    if(session) fetch('/close',{method:'POST',headers:auth(),body:'{}',keepalive:true,
      credentials:'omit',cache:'no-store',redirect:'error'}).catch(()=>{});
    stop();
  });
  rulesEditor = WCEProductionRules.mount(async (name,args)=>{
    const routes={'own.production.rules.read':'/rules/read','wce.settings.production.save':'/rules/save','wce.settings.production.restore':'/rules/restore'};
    if(!Object.hasOwn(routes,name))throw new Error('RULES_INVALID_REQUEST');
    return {structuredContent:await call(routes[name],args)};
  });
  OAManagement.bind({choose:chooseAccount,profile:editProfile,rules:cid=>rulesEditor.selectScope(cid),
    add:async e=>{if(!e.isTrusted||ended||active||review||editing||targetPending)return;
      active=true;generation++;controls();try{await call('/select',{connection_id:null});
        selectedId='';$('select').value='';finished=false;clearReview();$('appid').value=$('label').value='';
        selectedPreview();OAManagement.adding();notice('填写新公众号信息，下一步核对账号。');
      }catch(e){error(e);}finally{active=false;controls();}},
    cancel:async e=>{if(!e.isTrusted||ended||active||targetPending)return;
      active=true;generation++;controls();try{await call('/cancel');clearReview();
        $('appid').value=$('label').value='';OAManagement.cancelled();notice('已取消添加，未绑定新账号。');
      }catch(e){error(e);}finally{active=false;controls();}}
  });
  async function init() {
    controls();
    if(!bootstrap) { stop(); return; }
    let value = {bootstrap}; bootstrap = '';
    const result = await call('/bootstrap',value); value = null;
    session = result.session; csrf = result.csrf;
    navigationRevision = result.navigation_revision;
    setTimeout(stop,result.expires_in_seconds*1000);
    await refresh();
    rulesEditor.setReady(true);
    controls();
    notice('本机安全管理页。查看列表不会读取已有密钥或重新连接。关闭后绑定仍保留。');
    navigationTimer = setInterval(navigationPoll,500);
    addEventListener('focus',navigationPoll);
    document.addEventListener('visibilitychange',navigationPoll);
  }
  init().catch(e => { error(e); document.querySelectorAll('button,input,select').forEach(x => x.disabled=true); });
})();
"""

PAGE = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>OpenAhoy · 公众号管理</title><style>' + STYLE + '</style>'
        + page_body(LOGO, RULES_HTML, technical_html(), routes_html())
        + '<script>' + SCRIPT + '</script></body></html>')


def csp_hash(value):
    return "'sha256-" + base64.b64encode(sha256(value.encode()).digest()).decode() + "'"


CSP = ("default-src 'none'; script-src " + csp_hash(SCRIPT) + "; style-src " + csp_hash(STYLE)
       + "; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

MODAL_SCRIPT = RENDER_JS + RULES_JS + ARTICLES_JS + r"""
(() => {
  'use strict';
  let next = 1, ready = false, refreshing = false, opening = false, openUnknown = false, disposed = false;
  const pending = new Map(), status = document.getElementById('status');
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const has = (value,key) => Object.prototype.hasOwnProperty.call(value,key);
  const toolResult = value => record(value) && Array.isArray(value.content) &&
    (!has(value,'isError') || typeof value.isError === 'boolean');
  function send(method,params) {
    if(disposed)return Promise.reject(new Error('VIEW_CLOSED'));
    const id = next++;
    return new Promise((resolve,reject) => {
      const timer=setTimeout(()=>{pending.delete(id);reject(new Error('HOST_TIMEOUT'));},15000);
      pending.set(id,{resolve,reject,timer});
      parent.postMessage({jsonrpc:'2.0',id,method,params},'*');
    });
  }
  document.getElementById('productionRules').hidden=true;
  const rules = WCEProductionRules.mount((name,arguments_) => send('tools/call',{name,arguments:arguments_}));
  const articles = WCEArticleStatus.mount((name,arguments_) => send('tools/call',{name,arguments:arguments_}),
    () => parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/size-changed',params:{height:document.documentElement.scrollHeight}},'*'));
  function dispose() {
    if(disposed)return;
    disposed=true;ready=false;
    document.getElementById('open').disabled=true;
    document.getElementById('refresh').disabled=true;
    rules.setReady(false);articles.setReady(false);
    for(const item of pending.values()){clearTimeout(item.timer);item.reject(new Error('VIEW_CLOSED'));}
    pending.clear();
  }
  addEventListener('pagehide',event=>{if(!event.persisted)dispose();});
  for(const name of ['accounts','articles','data','rules'])document.getElementById('tab-'+name).addEventListener('click',()=>{
    for(const id of ['accounts','articles','data','rules']){document.getElementById('tab-'+id).setAttribute('aria-selected',String(id===name));
      document.getElementById({accounts:'accountPanel',articles:'articlePanel',data:'dataPanel',rules:'productionRules'}[id]).hidden=id!==name;}
    if(name==='articles')articles.articles();if(name==='data')articles.data();
  });
  function render(result) {
    if(disposed)return;
    const accounts = result?.structuredContent?.connections;
    if(!toolResult(result) || result.isError || !Array.isArray(accounts) ||
       Array.from(accounts).some(item => !record(item) || typeof item.connection_id !== 'string' ||
         typeof item.state !== 'string' ||
         ['label','account_id','error'].some(key => has(item,key) && typeof item[key] !== 'string'))) {
      if(!openUnknown) status.textContent='账号列表未能确认读取。';
      return;
    }
    const box=document.getElementById('accounts'); box.replaceChildren();
    const choices=WCEPresentation.choices(accounts);
    rules.accounts(accounts,choices);
    articles.accounts(accounts,choices);
    if(!accounts.length) {
      const empty=document.createElement('p');empty.className='empty';
      empty.textContent='还没有公众号。打开管理页添加你的账号。';box.append(empty);
    }
    for(const item of accounts) box.append(WCEPresentation.card(item,choices.get(item.connection_id)));
    parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/size-changed',
      params:{height:document.documentElement.scrollHeight}},'*');
  }
  async function refresh() {
    if(!ready || refreshing)return;
    refreshing=true;document.getElementById('refresh').disabled=true;
    try {render(await send('tools/call',{name:'wce.settings.manage',arguments:{}}));}
    catch(_) {if(!openUnknown) status.textContent='账号列表未能确认读取，请稍后刷新。';}
    finally {refreshing=false;document.getElementById('refresh').disabled=!ready;}
  }
  addEventListener('message',event => {
    if(event.source !== parent || !record(event.data) || event.data.jsonrpc !== '2.0') return;
    const data=event.data;
    if(data.method==='ui/resource-teardown' && has(data,'id') &&
       !has(data,'result') && !has(data,'error')) {
      if(!['string','number'].includes(typeof data.id) || !record(data.params) || Object.keys(data.params).length) {
        parent.postMessage({jsonrpc:'2.0',id:data.id,error:{code:-32602,message:'Invalid params'}},'*');
        return;
      }
      dispose();
      parent.postMessage({jsonrpc:'2.0',id:data.id,result:{}},'*');
      return;
    }
    if(pending.has(data.id)) {
      const p=pending.get(data.id);clearTimeout(p.timer);pending.delete(data.id);
      if(has(data,'method') || has(data,'result') === has(data,'error') || has(data,'error'))
        p.reject(new Error('HOST_ERROR'));
      else p.resolve(data.result);
    } else if(!has(data,'id') && !has(data,'result') && !has(data,'error') &&
              data.method==='ui/notifications/tool-result') {
      const result=data.params, value=result?.structuredContent;
      // A render-entry acknowledgement is not an account snapshot.
      if(toolResult(result) && result.isError !== true && record(value) &&
         Object.keys(value).length===1 && value.state==='MANAGEMENT_VIEW_READY') return;
      render(result);
    }
  });
  document.getElementById('open').addEventListener('click',async e => {
    if(!ready || opening || !e.isTrusted) return;
    openUnknown=false;
    opening=true;document.getElementById('open').disabled=true;
    status.textContent='正在请求打开安全页面，请稍候。';
    const unknown = () => {
      openUnknown=true;
      status.textContent='打开结果尚未确认。可以重新打开安全页面；已有账号操作不会重试。';
    };
    try {
      const result=await send('tools/call',{name:'wce.settings.open',arguments:{}});
      const state=result?.structuredContent?.state;
      if(!toolResult(result)) unknown();
      else if(result.isError) {
        const code=result?.structuredContent?.error || result.content?.[0]?.text;
        if(code==='SETTINGS_LAUNCH_UNKNOWN' || code==='SETTINGS_NAVIGATION_UNKNOWN') unknown();
        else if(code==='SETTINGS_BUSY') status.textContent='安全页面有操作正在进行，请先完成已有页面的操作。';
        else if(code==='SETTINGS_FOCUS_UNAVAILABLE') status.textContent='未能确认已切换到 Safari，请检查已有安全页面。';
        else if(code==='SETTINGS_OPEN_FAILED' || code==='SETTINGS_EXPIRED')
          status.textContent='安全页面未能打开，请检查已有页面和当前状态。';
        else unknown();
      } else if(state==='SETTINGS_ALREADY_OPEN')
        status.textContent='已有安全页面，已请求切换到 Safari。请查看已有页面，确认所需标签已显示。';
      else if(state==='SETTINGS_OPENED')
        status.textContent='已请求在 Safari 打开本机安全页面，请查看页面是否显示。';
      else unknown();
    } catch(_) {unknown();}
    finally {opening=false;document.getElementById('open').disabled=!ready;}
  });
  document.getElementById('refresh').addEventListener('click',refresh);
  addEventListener('focus',refresh);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  send('ui/initialize',{appInfo:{name:'wechat-ecosystem-settings',version:'0.4.96'},
    appCapabilities:{availableDisplayModes:['inline','fullscreen']},protocolVersion:'2026-01-26'})
  .then(async host => {
    if(disposed)return;
    if(host.protocolVersion !== '2026-01-26' ||
       !host.hostInfo || typeof host.hostInfo.name !== 'string' || typeof host.hostInfo.version !== 'string' ||
       !host.hostContext || typeof host.hostContext !== 'object' || Array.isArray(host.hostContext))
      throw new Error('INVALID_HOST');
    parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*');
    if(!host.hostCapabilities || !host.hostCapabilities.serverTools ||
       typeof host.hostCapabilities.serverTools !== 'object' || Array.isArray(host.hostCapabilities.serverTools))
      throw new Error('NO_SERVER_TOOLS');
    ready=true;document.getElementById('open').disabled=false;rules.setReady(true);articles.setReady(true);
    await refresh();
  }).catch(()=>{if(!disposed)status.textContent='当前宿主未提供设置工具桥。';});
})();
"""
MODAL = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{STYLE}</style><body class="modal-page"><div class="brand">{brand_header()}</div>
<nav class="actions" role="tablist" aria-label="公众号管理中心" style="margin-top:20px"><button id="tab-accounts" role="tab" aria-selected="true">公众号</button><button id="tab-articles" role="tab" aria-selected="false">文章</button><button id="tab-data" role="tab" aria-selected="false">数据</button><button id="tab-rules" role="tab" aria-selected="false">生产规则</button></nav>
<section id="accountPanel"><div class="modal-heading"><h2>你的公众号</h2><button id="refresh" class="quiet" disabled>刷新</button></div>
<div id="accounts"></div>
<p id="status">正在连接设置工具；账号信息将在独立的本机安全页面填写。</p>
<button id="open" class="primary" disabled>添加或管理公众号 · 打开安全页面</button>
</section>{ARTICLES_HTML}{RULES_HTML}<script>{MODAL_SCRIPT}</script></body></html>"""
