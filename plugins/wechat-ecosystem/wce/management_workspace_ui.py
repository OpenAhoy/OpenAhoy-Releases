"""Shared presentation only: summary navigation around the original editors.

No transport, storage, credentials or duplicate configuration state. Each adapter
keeps its fields, operation IDs and lock handling in its existing controller.
"""
from html import escape

from .account_starter_ui import SCRIPT as STARTER_SCRIPT, STYLE as STARTER_STYLE


def workspace(prefix, description, fields, actions, tools='', context=''):
    p = escape(prefix, quote=True)
    return f'''<div id="{p}Workspace" class="oa-task-workspace">
<section class="oa-task-summary"><header class="oa-task-heading"><h1>内容配置</h1>
<p class="help">{escape(description)}</p><div class="oa-task-tools">{tools}</div></header>
<nav id="{p}Summary" class="oa-task-rows" aria-label="内容配置分类"></nav>
<div class="oa-task-summary-bottom">{context}</div></section>
<aside id="{p}Sheet" class="oa-task-sheet" aria-label="配置编辑">
<header class="oa-task-sheet-head"><h2 id="{p}SheetTitle">内容配置</h2><button id="{p}SheetClose" type="button" aria-label="关闭编辑面板">×</button></header>
<div class="oa-task-fields">{fields}</div><footer class="oa-task-actions">{actions}</footer>
</aside></div>'''


SCRIPT = STARTER_SCRIPT + r'''
globalThis.OATaskWorkspace={mount(prefix,groups){
 const $=s=>document.getElementById(prefix+s),root=$('Workspace');
 if(!root?.classList)return null;
 const ui=globalThis.OAUI||globalThis.OAPlainUI;
 let index=0,open=true;
 const buttons=[];
 function show(i,focus=false){index=i;open=true;root.classList.remove('oa-sheet-closed');
  ui.set($('SheetTitle'),groups[i].title);
  groups.forEach((g,j)=>{g.show?.(i===j);buttons[j].setAttribute('aria-expanded',String(i===j));buttons[j].classList.toggle('is-selected',i===j);});
  if(focus){$('SheetTitle').tabIndex=-1;$('SheetTitle').focus();}
 }
 const shapes=["data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iY3VycmVudENvbG9yIiB2aWV3Qm94PSIwIDAgMjU2IDI1NiIgYXJpYS1oaWRkZW49InRydWUiPjxwYXRoIGQ9Ik0yMjAuMDYsODRhMTAyLjA2LDEwMi4wNiwwLDEsMS0yNC4zMS0zMi4yN2wyNC0yNGE2LDYsMCwwLDEsOC40OCw4LjQ5bC05Niw5NmE2LDYsMCwxLDEtOC40OC04LjQ5bDI5LjM5LTI5LjRhNDIsNDIsMCwxLDAsMTYuNzgsMzEuMjQsNiw2LDAsMSwxLDEyLS42OEE1NCw1NCwwLDEsMSwxNjEuNyw4NS44M2wyNS41NC0yNS41NWE4OS45MSw4OS45MSwwLDEsMCwyMiwyOC45M0E2LDYsMCwxLDEsMjIwLjA2LDg0WiI+PC9wYXRoPjwvc3ZnPg==", "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iY3VycmVudENvbG9yIiB2aWV3Qm94PSIwIDAgMjU2IDI1NiIgYXJpYS1oaWRkZW49InRydWUiPjxwYXRoIGQ9Ik0yMjUuOSw3NC43OCwxODEuMjEsMzAuMDlhMTQsMTQsMCwwLDAtMTkuOCwwTDM4LjEsMTUzLjQxYTEzLjk0LDEzLjk0LDAsMCwwLTQuMSw5LjlWMjA4YTE0LDE0LDAsMCwwLDE0LDE0SDkyLjY5YTEzLjk0LDEzLjk0LDAsMCwwLDkuOS00LjFMMjI1LjksOTQuNThhMTQsMTQsMCwwLDAsMC0xOS44Wk05NC4xLDIwOS40MWEyLDIsMCwwLDEtMS40MS41OUg0OGEyLDIsMCwwLDEtMi0yVjE2My4zMWEyLDIsMCwwLDEsLjU5LTEuNDFMMTM2LDcyLjQ4LDE4My41MSwxMjBaTTIxNy40MSw4Ni4xLDE5MiwxMTEuNTEsMTQ0LjQ5LDY0LDE2OS45LDM4LjU4YTIsMiwwLDAsMSwyLjgzLDBsNDQuNjgsNDQuNjlhMiwyLDAsMCwxLDAsMi44M1oiPjwvcGF0aD48L3N2Zz4=", "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iY3VycmVudENvbG9yIiB2aWV3Qm94PSIwIDAgMjU2IDI1NiIgYXJpYS1oaWRkZW49InRydWUiPjxwYXRoIGQ9Ik0yMjkuMTgsMTczYTYsNiwwLDAsMS0yLjE2LDguMmwtOTYsNTZhNiw2LDAsMCwxLTYsMGwtOTYtNTZhNiw2LDAsMCwxLDYtMTAuMzZsOTMsNTQuMjMsOTMtNTQuMjNBNiw2LDAsMCwxLDIyOS4xOCwxNzNaTTIyMSwxMjIuODJsLTkzLDU0LjIzTDM1LDEyMi44MmE2LDYsMCwwLDAtNiwxMC4zNmw5Niw1NmE2LDYsMCwwLDAsNiwwbDk2LTU2YTYsNiwwLDAsMC02LTEwLjM2Wk0yNiw4MGE2LDYsMCwwLDEsMy01LjE4bDk2LTU2YTYsNiwwLDAsMSw2LDBsOTYsNTZhNiw2LDAsMCwxLDAsMTAuMzZsLTk2LDU2YTYsNiwwLDAsMS02LDBsLTk2LTU2QTYsNiwwLDAsMSwyNiw4MFptMTcuOTEsMEwxMjgsMTI5LjA1LDIxMi4wOSw4MCwxMjgsMzFaIj48L3BhdGg+PC9zdmc+", "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iY3VycmVudENvbG9yIiB2aWV3Qm94PSIwIDAgMjU2IDI1NiIgYXJpYS1oaWRkZW49InRydWUiPjxwYXRoIGQ9Ik0yMDgsMzRINDhBMTQsMTQsMCwwLDAsMzQsNDhWMjA4YTE0LDE0LDAsMCwwLDE0LDE0SDIwOGExNCwxNCwwLDAsMCwxNC0xNFY0OEExNCwxNCwwLDAsMCwyMDgsMzRaTTQ2LDIwOFY0OGEyLDIsMCwwLDEsMi0ySDIwOGEyLDIsMCwwLDEsMiwydjgyLjJsLTI4LjEtMjguMWExNCwxNCwwLDAsMC0xOS44LDBMNTQuMiwyMTBINDhBMiwyLDAsMCwxLDQ2LDIwOFptMTYyLDJINzEuMTdsOTkuNDEtOTkuNDFhMiwyLDAsMCwxLDIuODMsMEwyMTAsMTQ3LjE3VjIwOEEyLDIsMCwwLDEsMjA4LDIxMFpNOTYsMTE4QTIyLDIyLDAsMSwwLDc0LDk2LDIyLDIyLDAsMCwwLDk2LDExOFptMC0zMkExMCwxMCwwLDEsMSw4Niw5NiwxMCwxMCwwLDAsMSw5Niw4NloiPjwvcGF0aD48L3N2Zz4=", "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgZmlsbD0iY3VycmVudENvbG9yIiB2aWV3Qm94PSIwIDAgMjU2IDI1NiIgYXJpYS1oaWRkZW49InRydWUiPjxwYXRoIGQ9Ik0yMjIuNzIsNjcuOWwtODgtNDguMTdhMTMuOSwxMy45LDAsMCwwLTEzLjQ0LDBsLTg4LDQ4LjE4QTE0LDE0LDAsMCwwLDI2LDgwLjE4djk1LjY0YTE0LDE0LDAsMCwwLDcuMjgsMTIuMjdsODgsNDguMThhMTMuOTIsMTMuOTIsMCwwLDAsMTMuNDQsMGw4OC00OC4xOEExNCwxNCwwLDAsMCwyMzAsMTc1LjgyVjgwLjE4QTE0LDE0LDAsMCwwLDIyMi43Miw2Ny45Wk0xMjcsMzAuMjVhMiwyLDAsMCwxLDEuOTIsMEwyMTIuNTEsNzYsMTI4LDEyMi4yNCw0My40OSw3NlpNMzksMTc3LjU3YTIsMiwwLDAsMS0xLTEuNzVWODYuNjZsODQsNDZWMjIzWm0xNzcuOTIsMEwxMzQsMjIzVjEzMi42NGw4NC00NnY4OS4xNkEyLDIsMCwwLDEsMjE3LDE3Ny41N1oiPjwvcGF0aD48L3N2Zz4="];
 groups.forEach((g,i)=>{const button=document.createElement('button');button.type='button';button.className='oa-task-row';
  const icon=document.createElement('span');icon.className='oa-task-row-icon';const image=document.createElement('img');image.src=shapes[i%shapes.length];image.alt='';icon.append(image);icon.setAttribute('aria-hidden','true');
  const copy=document.createElement('span'),title=document.createElement('strong'),text=document.createElement('small'),edit=document.createElement('span');
  copy.className='oa-task-row-copy';ui.set(title,g.title);copy.append(title,text);edit.className='oa-task-row-edit';ui.set(edit,'编辑 ›');button.append(icon,copy,edit);
  button.onclick=()=>{show(i);if(root.closest?.('.oa-native')&&matchMedia('(max-width:799px), (max-height:599px)').matches)$('Sheet').scrollIntoView({block:'start'});};buttons.push(button);g.preview=text;$('Summary').append(button);
 });
 function refresh(){groups.forEach(g=>{const value=g.summary?.();if(typeof value==='string'&&value){ui.raw(g.preview,value);}else{ui.set(g.preview,...(value||['未设置']));}});}
 $('SheetClose').onclick=()=>{open=false;root.classList.add('oa-sheet-closed');buttons.forEach(b=>{b.classList.remove('is-selected');b.setAttribute('aria-expanded','false');});buttons[index].focus();};
 root.addEventListener('input',refresh);root.addEventListener('change',refresh);
 show(0);refresh();
 return {refresh,show,restore(){if(open)show(index);refresh();}};
}};
'''


STYLE = r'''
.oa-x-tools-back{display:none!important}body.oa-x-tools .oa-x-tools-back{display:inline-flex!important;margin:0 0 12px}.oa-capability-details{margin:0 0 8px!important;font-size:12px}
/* Accepted MD-C compact workspace. Shared by native and local safety views. */
body.oa-management{color-scheme:light;--bg:#fff;--surface:#fff;--soft:#f5f5f5;--ink:#222;--muted:#686868;--line:#e7e7e7;--accent:#353535;--tint:#f5f5f5;--control-edge-hover:#c7c7c7;--raised:0 2px 3px #15151505,0 8px 24px #1515150b;--control-shadow:inset 0 1px 0 #fff,0 1px 2px #1515150a,0 3px 7px #15151510;--control-hover:inset 0 1px 0 #fff,0 2px 4px #1515150c,0 6px 13px #1515151c;--control-pressed:inset 0 2px 4px #15151520,0 1px 0 #fff;--primary-shadow:inset 0 1px 0 #fff,0 2px 3px #15151512,0 5px 11px #15151520;--field-shadow:inset 0 1px 3px #15151510,0 1px 0 #fff;--glyph-filter:none;--x-tile:#fff;--platform-light:block;--platform-dark:none;--error:#b62b3b;--inset:var(--field-shadow);background:var(--bg)}
.oa-management .oa-shell{grid-template-columns:210px minmax(0,1fr)}
.oa-management .oa-sidebar{padding:24px 14px 18px;gap:22px;background:var(--bg)}.oa-management .oa-brand-logo{width:168px;margin:4px 7px 0}
.oa-management .oa-nav button{min-height:42px;padding:8px 16px;gap:15px;font-size:14px;border-radius:10px}.oa-management .oa-platform-mark{width:23px;height:23px;flex-basis:23px;padding:3px;background:none}.oa-management .oa-platform-logo{width:17px;height:17px;object-fit:contain}.oa-management .oa-platform-mark[data-brand=wechat_official_account]{background:#07c160;border-radius:6px}.oa-management .oa-platform-logo--light{display:block}.oa-management .oa-platform-logo--dark{display:none}
.oa-management .oa-content{max-width:none;padding:18px 18px 24px 28px}.oa-management button.primary:hover:not(:disabled){background:var(--surface)}.oa-management button{border-radius:8px;min-height:34px;padding:7px 12px}.oa-management .primary{min-height:40px;padding:9px 20px;font-size:14px;background:var(--surface)}
.oa-management .oa-software-update{border:1px solid var(--line);border-radius:13px;padding:13px;gap:8px;background:var(--surface)}.oa-management .oa-update-version{font-size:13px}.oa-management .oa-update-actions{align-items:flex-start}.oa-management .oa-update-actions button{width:auto;min-height:29px;padding:5px 10px}
.oa-management .oa-task-workspace{display:grid;grid-template-columns:minmax(270px,1fr) minmax(330px,390px);gap:26px;grid-template-rows:minmax(0,1fr);min-width:0;min-height:0;height:100%}
.oa-management .oa-task-summary{min-width:0;display:flex;flex-direction:column;padding-top:24px}.oa-management .oa-task-heading{min-height:104px;position:relative;padding-right:0}.oa-management .oa-task-heading h1{margin:0 0 12px;font-size:26px;line-height:1.35;font-weight:650;letter-spacing:-.6px}.oa-management .oa-task-heading>.help{font-size:13px;margin:0 0 14px}.oa-management .oa-task-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px}.oa-management .oa-task-tools button,.oa-management .oa-task-tools summary{font-size:12px}
.oa-management .oa-task-rows{border-top:1px solid var(--line)}.oa-management .oa-task-row{width:100%;min-height:88px;display:flex;justify-content:flex-start;gap:18px;border:0;border-bottom:1px solid var(--line);border-radius:0;padding:14px 12px;background:none;white-space:normal;text-align:left}.oa-management .oa-task-row.is-selected{background:var(--tint);border-radius:13px;border-bottom-color:transparent}.oa-task-row-icon img{display:block;width:24px;height:24px;fill:currentColor}.oa-task-row-icon{font-size:26px;line-height:1;width:26px;flex:none;font-weight:300;color:#35423f}.oa-task-row-copy{min-width:0;flex:1}.oa-task-row-copy strong{display:block;font-size:18px;line-height:1.3;font-weight:600;margin-bottom:5px}.oa-task-row-copy small{display:block;color:var(--muted);font-size:13px;line-height:1.55;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.oa-task-row-edit{font-size:12px;color:var(--muted);white-space:nowrap}.is-selected .oa-task-row-edit{color:var(--accent)}
.oa-task-summary-bottom{margin-top:auto;padding-top:24px;display:flex;flex-wrap:wrap;align-items:center;gap:8px}.oa-task-summary-bottom>details{width:100%}.oa-task-summary-bottom>p{width:100%}
.oa-management .oa-task-sheet{display:flex;flex-direction:column;min-height:0;min-width:0;border:1px solid var(--line);border-radius:17px;padding:25px 22px 22px;background:var(--surface);box-shadow:var(--raised);overflow:hidden}.oa-task-sheet-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:24px;flex:none}.oa-management .oa-task-sheet-head h2{font-size:22px;line-height:1.35;letter-spacing:-.3px;margin:0}.oa-management .oa-task-sheet-head button{border:0;background:none;padding:0;min-height:28px;min-width:28px;font-size:25px;font-weight:300;color:var(--muted)}
.oa-management .oa-task-fields{min-height:0;overflow:auto;flex:1;padding:1px 1px 16px;scrollbar-width:thin}.oa-management .oa-task-actions{flex:none;display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap;padding-top:18px;background:var(--surface)}.oa-task-actions .notice{width:100%;margin:0;max-height:72px;overflow:auto}.oa-task-actions .primary{order:10}.oa-task-actions button:not(.primary){font-size:12px}
.oa-management .oa-task-fields label{font-size:14px;margin:0 0 23px}.oa-management .oa-task-fields :is(input:not([type=checkbox]),textarea,select){font-size:14px;line-height:1.55;padding:10px 13px;border-radius:10px;margin-top:9px}.oa-management .oa-task-fields textarea{min-height:64px}.oa-management .oa-task-fields :is(input:not([type=checkbox]),select){min-height:40px}.oa-management .oa-task-fields .help{font-size:12px}.oa-management .oa-task-fields .rule-source{font-size:11px;color:var(--muted)}
.oa-management .oa-sheet-closed{grid-template-columns:minmax(0,1fr)}.oa-sheet-closed>.oa-task-sheet{display:none!important}.oa-sheet-closed .oa-task-summary{max-width:960px}
.oa-management #rulesEditing{display:block;height:100%;min-height:0}.oa-management #rulesFields{display:block;margin:0}.oa-management .rule-editor{padding:0;margin:0 0 24px;border:0;box-shadow:none;background:none}.oa-management .rule-editor>summary{display:none}.oa-management .rule-editor label{margin:0}.oa-management .rule-editor label>span:first-child{font-weight:550}.oa-management .rule-editor .rule-input{margin:9px 0 0}.oa-management .rule-editor .rule-summary{display:none}.oa-management .rules-body{overflow:visible;padding:0;flex:none}.oa-management .rules-context{margin:0 0 16px}.oa-management #rulesScope{max-width:100%;width:100%;min-width:0}.oa-management #rulesEditing .rules-body>h2,.oa-management #rulesEditing .rules-body>.help{display:none}.oa-management .rules-context #rulesStatus{font-size:11px}
.oa-management #productionRules,.oa-management #xSettings{padding:0!important;border:0;background:transparent;box-shadow:none;margin:0!important;min-height:0}.oa-management #xOperatingPanel{padding:0;border:0;margin:0;height:100%}.oa-management #xOperatingPanel>summary{display:none}.oa-management #xConfigSections{min-height:0}.oa-management .x-config-fields{max-height:none;padding:0;overflow:visible}.oa-management .x-config-grid{grid-template-columns:1fr;gap:0}.oa-management .x-config-methods{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 24px}.oa-management .x-config-methods label{position:relative;display:flex;align-items:center;justify-content:center;gap:5px;min-height:36px;padding:7px;border:1px solid var(--line);border-radius:8px;font-size:12px;line-height:1.4;margin:0!important;background:var(--surface)}.oa-management .x-config-methods label:has(:checked){background:var(--tint);color:var(--ink);border-color:var(--accent)}.oa-management .x-config-methods input{width:12px;height:12px}.oa-management .oa-x-config h4{font-size:14px;font-weight:550;margin:0 0 11px}.oa-management .x-config-column{margin:0 0 18px;padding:0 0 12px}.oa-management .oa-task-fields details{margin-top:12px}
.oa-management .oa-account-header{display:flex;align-items:center;justify-content:space-between;gap:18px;min-height:64px;margin-bottom:0;flex:none}.oa-management #accountPanel.oa-account-picker{position:relative;padding:0;border:0;box-shadow:none;max-height:none;overflow:visible;margin:0;background:none;z-index:45}.oa-account-picker>summary{list-style:none;display:flex;align-items:center;gap:12px;padding:8px 12px;min-height:54px;border:1px solid var(--line);border-radius:13px;background:var(--surface);box-shadow:var(--raised);cursor:pointer;margin:0;color:var(--ink)}.oa-account-picker>summary::-webkit-details-marker{display:none}.oa-account-picker .oa-current-card{display:flex;align-items:center;gap:10px;min-width:0}.oa-account-picker .oa-current-card strong{font-size:14px}.oa-account-picker .oa-current-card small{display:block;font-size:11px;color:var(--muted)}.oa-account-picker .avatar{width:36px;height:36px;flex-basis:36px;border-radius:50%}.oa-account-popover{position:absolute;top:calc(100% + 8px);left:0;width:330px;max-width:calc(100vw - 40px);max-height:min(70vh,600px);overflow:auto;padding:10px;border:1px solid var(--line);border-radius:13px;background:var(--surface);box-shadow:var(--raised)}.oa-management .oa-account-options{display:flex;flex-wrap:wrap;gap:3px}.oa-management .oa-account-tools{display:flex;flex-wrap:wrap}.oa-management .oa-account-tools>.actions{justify-content:flex-start;display:flex;gap:6px;margin-top:10px}.oa-management #nativeWorkspace>.oa-heading{display:none}.oa-management #nativeWorkspace>#notice:not(.error){position:absolute;clip-path:inset(50%);width:1px;height:1px;overflow:hidden}.oa-management #nativeWorkspace>#notice.error{margin:8px 0}
.oa-management .oa-platform-settings{margin:0!important;padding:0!important;border:0;min-height:0;flex:1}.oa-management .oa-context-tabs{margin:0 0 10px;gap:6px}.oa-management .oa-context-tabs button,.oa-management #wechatSettings>.oa-tabs button{font-size:12px;min-height:29px;padding:5px 9px}.oa-management #wechatSettings>.oa-tabs{border:0;margin:0;padding:0 0 8px}.oa-management .oa-context-tabs{justify-content:flex-end}.oa-management #wechatSettings,#xSettings{min-height:0}.oa-management #wechatSettings>#productionRules{flex:1}.oa-management #xSettings:not([hidden]){display:flex;flex-direction:column;flex:1;overflow:visible!important}.oa-management #xSettings>.oa-x-production,.oa-management #xSettings>#xSchedulePanel,.oa-management #xSettings>details:not(#xOperatingPanel){display:none}.oa-management.oa-x-tools #xSettings{overflow:auto!important}.oa-management.oa-x-tools #xSettings>.oa-x-production,.oa-management.oa-x-tools #xSettings>#xSchedulePanel,.oa-management.oa-x-tools #xSettings>details:not(#xOperatingPanel){display:block}.oa-management.oa-x-tools #xOperatingPanel{display:none}.oa-management #xCapabilities{display:none!important}.oa-management .oa-capability-details #xCapabilities{display:block!important}.oa-management .oa-capability-details .oa-x-features{grid-template-columns:1fr 1fr}
@media(min-width:800px) and (min-height:600px){.oa-management .oa-shell{height:100dvh;min-height:0;overflow:hidden}.oa-management .oa-content{height:100%;overflow:hidden}.oa-management #nativeWorkspace{display:flex;height:100%;min-height:0;flex-direction:column}.oa-management #settingsPanel{flex:1;min-height:0;display:flex;flex-direction:column}.oa-management #wechatSettings{display:flex;min-height:0;flex:1;flex-direction:column}.oa-management #productionRules{overflow:hidden}.oa-management #rulesWorkspace{height:100%}.oa-management #xConfigWorkspace{height:100%}}
@media(max-width:1199px){.oa-management .oa-shell{grid-template-columns:180px minmax(0,1fr)}.oa-management .oa-brand-logo{width:148px;margin-inline:1px}.oa-management .oa-content{padding-inline:20px}.oa-management .oa-task-workspace{grid-template-columns:minmax(240px,1fr) minmax(310px,365px);gap:20px}.oa-task-row-copy strong{font-size:17px}.oa-task-row-edit{display:none}}
@media(max-width:999px){.oa-management .oa-shell{grid-template-columns:158px minmax(0,1fr)}.oa-management .oa-brand-logo{width:132px}.oa-management .oa-task-workspace{grid-template-columns:minmax(0,1fr)}.oa-management .oa-task-sheet{position:fixed;z-index:35;right:16px;top:156px;bottom:16px;width:min(390px,calc(100vw - 192px));box-shadow:-15px 10px 60px #263e2e18}.oa-management .oa-task-workspace:not(.oa-sheet-closed)>.oa-task-summary{opacity:.42;pointer-events:none}.oa-management .oa-sheet-closed>.oa-task-summary{opacity:1;pointer-events:auto}}
@media(max-width:799px),(max-height:599px){.oa-management .oa-shell{display:block;height:auto;min-height:100dvh;overflow:visible}.oa-management .oa-sidebar{display:grid;grid-template-columns:132px minmax(0,1fr);padding:12px 16px;gap:12px;align-items:center}.oa-management .oa-sidebar>div:last-child{grid-column:2;grid-row:1}.oa-management .oa-sidebar #softwareUpdateSlot{grid-column:1/-1;grid-row:2}.oa-management .oa-nav{justify-content:flex-end;gap:4px}.oa-management .oa-nav button{width:auto;min-height:35px;font-size:13px;padding:5px 7px;gap:6px}.oa-management .oa-brand-logo{width:132px;margin:0}.oa-management .oa-platform-mark{width:20px;height:20px;flex-basis:20px}.oa-management .oa-platform-logo{width:20px;height:20px}.oa-management .oa-software-update{flex-direction:row;align-items:center;justify-content:space-between;padding:6px 9px}.oa-management .oa-update-copy{flex-direction:row;gap:10px;align-items:center;flex-wrap:wrap}.oa-management .oa-update-version{font-size:11px}.oa-management .oa-update-status{font-size:10px}.oa-management .oa-update-actions{flex-direction:row}.oa-management .oa-content{padding:10px 16px 20px}.oa-management .oa-account-header{min-height:55px;gap:8px}.oa-management .oa-account-header>.actions{gap:5px}.oa-management .oa-account-header>.actions button{padding:6px 9px;font-size:12px;min-height:32px}.oa-account-picker>summary{padding:7px 9px;gap:8px;min-height:49px}.oa-account-picker .avatar{width:31px;height:31px;flex-basis:31px}.oa-account-picker .oa-current-card strong{font-size:13px}.oa-management .oa-task-heading h1{font-size:24px}.oa-management .oa-task-summary{padding-top:14px}.oa-management .oa-task-row{min-height:78px;padding:12px 8px;gap:14px}.oa-task-row-copy strong{font-size:16px}.oa-task-row-copy small{font-size:12px}.oa-management .oa-task-sheet{inset:236px 12px 12px;width:auto;padding:21px 19px 18px;border-radius:16px}.oa-management .oa-task-sheet-head h2{font-size:21px}.oa-management .oa-task-fields :is(input:not([type=checkbox]),textarea,select){font-size:14px;padding:9px 12px}.oa-management .oa-task-summary-bottom{padding-top:22px}.oa-management .oa-context-tabs{justify-content:flex-start;margin-top:8px}.oa-management #accountPanel.oa-account-picker{max-width:calc(100% - 122px)}.oa-account-picker .oa-current-card{overflow:hidden}.oa-account-picker .oa-current-card strong{display:block;max-width:115px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.oa-management .oa-task-actions{padding-top:13px}.oa-management .oa-task-actions .primary{padding:8px 16px;min-height:39px}}
@media(prefers-reduced-motion:reduce){.oa-management *{transition:none!important}}
'''

STYLE += "\n@media(min-width:1000px) and (min-height:600px){.oa-management #xSettings{overflow:hidden!important}.oa-management #xOperatingPanel{flex:1;min-height:0;overflow:hidden;height:calc(100% - 30px)}.oa-management #xConfigWorkspace{height:100%}.oa-management .oa-task-sheet{height:100%}}"

STYLE += "\n.oa-management #xSettings>.oa-capability-details{display:block}.oa-management.oa-x-tools #xOperatingPanel{display:none}.oa-management .oa-task-menu>summary{display:inline-flex;align-items:center;min-height:33px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink)}.oa-management .oa-task-menu[open]>.actions{padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--surface);box-shadow:var(--raised);margin-top:8px}"

STYLE += "\n.oa-management:not(.oa-native) [data-workspace-project]{display:none}.oa-management .oa-task-menu{position:relative}.oa-management .oa-task-menu[open]>.actions{position:absolute;left:0;top:100%;z-index:50;min-width:230px;display:grid!important;gap:6px}.oa-management .oa-task-menu[open]>.actions button{justify-content:flex-start;white-space:normal;text-align:left}"
STYLE += """
.oa-x-recovery{display:grid;grid-template-columns:minmax(66px,auto) minmax(0,1fr) auto;gap:6px;margin-top:7px}
.oa-x-recovery input,.oa-x-recovery select{width:100%;min-width:0}
.oa-x-recovery output{grid-column:1/-1;overflow-wrap:anywhere}
"""

STYLE += "\n.oa-management #safeAccountPicker{position:relative;display:inline-block;margin:0 0 12px;z-index:45}.oa-management #safeAccountPicker>summary{padding:8px 12px;min-height:49px;min-width:170px}.oa-management #safeAccountCurrent{font-size:14px;font-weight:600}.oa-management:not(.oa-native) #productionRules{height:calc(100dvh - 220px);min-height:520px}.oa-management:not(.oa-native) #rulesCreator{height:100%}@media(max-width:799px){.oa-management:not(.oa-native) #productionRules{min-height:500px}}"

# Account choice is always visible, never a dropdown/popover, on both surfaces.
STYLE += """
.oa-management .oa-account-header{flex-wrap:wrap;align-items:flex-start;gap:8px}
.oa-management .oa-account-header>.actions{order:0;margin-left:auto}
.oa-management #accountPanel.oa-account-cards{order:1;flex:0 0 100%;width:100%;max-width:none;max-height:none;padding:0;background:none;overflow:visible}
.oa-management .oa-account-cards-body{position:static;width:100%;max-width:none;max-height:none;box-shadow:none;border:0;background:none;padding:0}
.oa-management .oa-account-options{display:flex;flex-wrap:wrap;gap:10px}
.oa-management .oa-account-options>.account{min-width:0;cursor:pointer;position:relative;flex:0 1 auto;width:max-content;max-width:min(100%,270px);min-height:57px;padding:10px 14px;border:1px solid var(--line);border-radius:13px;background:var(--surface);box-shadow:var(--control-shadow);transition:box-shadow .16s,border-color .16s}
.oa-management .oa-account-options>.account.is-selected{border-color:var(--accent);background:var(--surface);box-shadow:inset 3px 0 0 var(--accent),var(--primary-shadow)}
.oa-management .oa-account-options>.account:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.oa-management #safeAccountPicker{display:block;width:100%;margin:0 0 12px}
.oa-management .oa-account-tools{margin-top:8px}
.oa-management #accountPanel [hidden]{display:none!important}
"""

STYLE += "\n.oa-scope-tabs{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.oa-scope-tabs button{min-height:30px;padding:5px 10px;font-size:12px}.oa-scope-tabs button[aria-pressed=true]{background:var(--tint);border-color:var(--accent);color:var(--accent)}.oa-scope-tabs select[hidden]{display:none!important}"


# Shared presentation layer: raised controls, quiet canvas, compact account cards.
# System color preference is the fallback; data-color-scheme supports host styling
# and the isolated preview without changing account or bridge state.
DARK_TOKENS = """color-scheme:dark;--bg:#171717;--surface:#252525;--soft:#1e1e1e;--ink:#f2f2f2;--muted:#b4b4b4;--line:#414141;--accent:#dedede;--tint:#303030;--control-edge-hover:#727272;--raised:inset 0 1px 0 #ffffff0b,0 3px 6px #0004,0 12px 25px #0005;--control-shadow:inset 0 1px 0 #ffffff16,0 1px 2px #0006,0 4px 8px #0006;--control-hover:inset 0 1px 0 #ffffff22,0 2px 5px #0008,0 7px 15px #0008;--control-pressed:inset 0 2px 5px #0009,0 1px 0 #ffffff0c;--primary-shadow:inset 0 1px 0 #ffffff28,0 2px 4px #0007,0 5px 12px #0008;--field-shadow:inset 0 2px 4px #0005,0 1px 0 #ffffff08;--glyph-filter:invert(1);--x-tile:#000;--platform-light:none;--platform-dark:block;--error:#ffb0ba;"""
STYLE += r''' 
.oa-management .oa-brand-logo{color:var(--ink)}.oa-management .oa-brand-logo svg :is([fill="#026364"],[fill="#0B1C2F"]){fill:currentColor}
.oa-management .oa-nav button[aria-current=page]{background:var(--surface);color:var(--ink);border-color:var(--line);box-shadow:inset 3px 0 0 var(--accent),var(--control-shadow);font-weight:650}
.oa-management .oa-account-options>.account:hover{box-shadow:var(--control-hover);border-color:var(--control-edge-hover)}
.oa-management .oa-account-options>.account:active{box-shadow:var(--control-pressed)}
.oa-management .oa-account-options>.account>div:last-child{min-width:0}.oa-management .oa-account-options .account-select{display:block;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.oa-management .oa-account-options .avatar{width:32px;height:32px;flex-basis:32px;border-radius:9px}.oa-management .oa-account-options .status{font-size:11px;line-height:1.5}
.oa-management .oa-account-tools{display:flex;align-items:center;justify-content:flex-start;gap:10px;margin:12px 0 6px}.oa-management .oa-account-tools details{margin:0}
.oa-more-settings{position:relative}.oa-management .oa-more-settings>summary{display:flex;align-items:center;min-height:34px;padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);box-shadow:var(--control-shadow);list-style:none}.oa-more-settings>summary::-webkit-details-marker{display:none}
.oa-more-settings>summary::after{content:"⌄";margin-left:8px}.oa-more-settings[open]>summary{box-shadow:var(--control-pressed)}
.oa-management .oa-more-popover{position:absolute;left:0;top:calc(100% + 7px);z-index:60;display:grid;gap:8px;width:260px;max-width:calc(100vw - 32px);padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--surface);box-shadow:var(--raised)}.oa-more-popover button{width:100%;justify-content:flex-start}.oa-more-popover .help{font-size:11px;margin:0}
.oa-management .oa-task-heading h1{font-size:23px}.oa-management .oa-task-heading{min-height:76px}.oa-management .oa-task-summary{padding-top:16px}.oa-management .oa-task-rows{display:grid;gap:10px;border:0}.oa-management .oa-task-row{min-height:72px;padding:12px 14px;gap:14px;border:1px solid var(--line);border-radius:13px;background:var(--surface);box-shadow:var(--control-shadow)}.oa-management .oa-task-row-icon img{filter:var(--glyph-filter)}.oa-task-row-copy strong{font-size:16px}.oa-management .oa-task-row.is-selected{background:var(--surface);border:1px solid var(--accent);box-shadow:inset 3px 0 0 var(--accent),var(--primary-shadow)}
.oa-management .oa-task-sheet{padding:22px 20px 18px;border-radius:16px;box-shadow:var(--raised)}.oa-management .oa-task-sheet-head{margin-bottom:20px}.oa-management .oa-task-sheet-head h2{font-size:20px}.oa-management .oa-task-sheet-head button{box-shadow:none}
.oa-management :is(input:not([type=checkbox]):not([type=file]),textarea,select){background:var(--surface);border-color:var(--line);box-shadow:var(--field-shadow)}.oa-management :is(input,textarea,select):disabled{background:var(--soft);color:var(--muted);box-shadow:none}
.oa-management .oa-task-actions{border-top:1px solid var(--line);padding-top:13px}.oa-management .oa-task-actions .primary{min-width:114px}.oa-management .oa-software-update{box-shadow:var(--raised);background:var(--surface)}
.oa-management .oa-task-menu>summary{box-shadow:var(--control-shadow)}.oa-management .oa-tabs button[aria-selected=true],.oa-management .oa-context-tabs button[aria-selected=true],.oa-management .oa-scope-tabs button[aria-pressed=true]{background:var(--surface);color:var(--ink);border-color:var(--line);box-shadow:var(--control-shadow)}
.oa-management .oa-task-menu[open]>.actions,.oa-management .review-card,.oa-management .profile-editor{background:var(--surface)}
.oa-management:has(#xSettings:not([hidden])) .oa-account-tools,.oa-management:has(#xhsSettings:not([hidden])) .oa-account-tools{display:none}.oa-management .notice.error{color:#b62b3b}.oa-management .status.good{color:var(--muted)}
.oa-management :is(button,input,select,textarea,a,summary,[role=option]):focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@media(max-width:799px){.oa-management .oa-nav{display:flex;flex-wrap:wrap}.oa-management .oa-sidebar .oa-nav{justify-content:flex-start}.oa-management .oa-sidebar>div:last-child{grid-column:1/-1;grid-row:3}.oa-management .oa-task-sheet{top:290px}.oa-management .oa-account-options>.account{max-width:100%}.oa-management .oa-account-tools{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){.oa-management *{transition:none!important;animation:none!important}}
'''
STYLE += '@media(prefers-color-scheme:dark){body.oa-management:not([data-color-scheme=light]){'+DARK_TOKENS+'}}body.oa-management[data-color-scheme=dark]{'+DARK_TOKENS+'}'
STYLE += '.oa-management .notice.error{color:var(--error)}.oa-management .oa-platform-logo--light{display:var(--platform-light)}.oa-management .oa-platform-logo--dark{display:var(--platform-dark)}'



STYLE += """
.oa-management .oa-account-header{align-items:center;gap:14px;margin-bottom:14px;min-height:64px}
.oa-management #accountPanel.oa-account-cards{order:0;flex:1 1 300px;width:auto}
.oa-management .oa-account-cards-body{display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.oa-management .oa-account-cards-body>.oa-list-head{display:none}
.oa-management .oa-account-options{flex:0 1 auto;max-width:100%;max-height:min(28vh,220px);overflow:auto;padding:3px 4px 6px}
.oa-management .oa-account-tools{margin:0}
.oa-management .oa-account-header>.actions{flex:none;margin:0}
.oa-management .oa-task-summary-bottom>[data-workspace-project]{display:none}
@media(max-width:799px){.oa-management .oa-account-header{align-items:center;gap:10px}.oa-management #accountPanel.oa-account-cards{flex:1 1 100%}.oa-management .oa-account-header>.actions{margin-left:auto}.oa-management .oa-task-summary-bottom{padding-top:14px}}
"""


# Category controls are navigation; the editor owns the remaining workspace.
STYLE += """
@media(min-width:1000px){
.oa-management .oa-task-workspace{grid-template-columns:240px minmax(0,1fr);gap:22px}
.oa-management .oa-task-sheet{width:100%;max-width:none}
.oa-management .oa-task-summary{padding-top:8px}
.oa-management .oa-task-heading{min-height:0;margin-bottom:12px}
.oa-management .oa-task-heading h1{font-size:20px;margin-bottom:8px}
.oa-management .oa-task-heading>.help{font-size:12px;line-height:1.6;margin-bottom:8px}
.oa-management .oa-task-tools{margin-bottom:12px}
.oa-management .oa-task-rows{gap:9px}
.oa-management .oa-task-row{min-height:58px;padding:10px 12px;gap:10px}
.oa-management .oa-task-row-copy strong{font-size:14px;margin:0}
.oa-management .oa-task-row-copy small{font-size:12px;max-width:165px;line-height:1.5}
.oa-management .oa-task-row-icon,.oa-management .oa-task-row-icon img{width:20px;height:20px}
.oa-management .oa-task-row-edit{display:none}
.oa-management .oa-task-sheet-head{margin-bottom:16px}
.oa-management .oa-task-fields .rule-input{min-height:clamp(160px,32vh,360px)}
.oa-management .oa-sheet-closed{grid-template-columns:240px}
}
"""

STYLE += STARTER_STYLE

STYLE += """
.oa-management .oa-platform-mark[data-brand=x]{background:var(--x-tile);border:1px solid var(--line)}
"""


# Native workspace surfaces. The local safety form retains its own styling.
STYLE += """
body.oa-management.oa-native{
 --oa-canvas:#f8f8fa;--oa-rail:#f0f0f3;--oa-fill:#efeff2;--oa-hover:#e6e6eb;
 --oa-selection:#dfe7f4;--oa-selected-ink:#203a5e;--oa-action:#25262b;--oa-action-hover:#41434b;
 --oa-action-ink:#fff;--oa-focus:#426fae;
 --oa-blue-fill:#e4edff;--oa-blue-ink:#254a89;
 --oa-violet-fill:#eee8fb;--oa-violet-ink:#5b3d88;
 --oa-teal-fill:#def2ec;--oa-teal-ink:#235f51;
 --oa-amber-fill:#f8edd8;--oa-amber-ink:#75501b;
 --oa-slate-fill:#e9edf2;--oa-slate-ink:#40536a;
 --oa-save:#255ab3;--oa-save-hover:#19488e;--oa-save-ink:#fff;
 --oa-connected:#297450;
 --oa-panel-shadow:0 2px 5px #24253508,0 10px 35px #2425350e;
 --oa-popover-shadow:0 4px 12px #24253514,0 16px 40px #24253520;
 background:var(--oa-canvas);
}
body.oa-management.oa-native[data-color-scheme=dark]{
 --oa-canvas:#19191c;--oa-rail:#212125;--oa-fill:#2f2f35;--oa-hover:#3b3b43;
 --oa-selection:#384964;--oa-selected-ink:#edf4ff;--oa-action:#e7e9f0;--oa-action-hover:#fff;
 --oa-action-ink:#222630;--oa-focus:#a2c1fd;
 --oa-blue-fill:#293c5c;--oa-blue-ink:#c4d8ff;
 --oa-violet-fill:#403452;--oa-violet-ink:#e5d3ff;
 --oa-teal-fill:#243f39;--oa-teal-ink:#b4e5d4;
 --oa-amber-fill:#453824;--oa-amber-ink:#f3d59b;
 --oa-slate-fill:#333d49;--oa-slate-ink:#d2e0ef;
 --oa-save:#a9c6fb;--oa-save-hover:#c3d7fd;--oa-save-ink:#122746;
 --oa-connected:#80c6a1;
 --oa-panel-shadow:0 5px 20px #0003;--oa-popover-shadow:0 10px 28px #0007;
}
@media(prefers-color-scheme:dark){
 body.oa-management.oa-native:not([data-color-scheme=light]){
  --oa-canvas:#19191c;--oa-rail:#212125;--oa-fill:#2f2f35;--oa-hover:#3b3b43;
  --oa-selection:#384964;--oa-selected-ink:#edf4ff;--oa-action:#e7e9f0;--oa-action-hover:#fff;
  --oa-action-ink:#222630;--oa-focus:#a2c1fd;
  --oa-blue-fill:#293c5c;--oa-blue-ink:#c4d8ff;
  --oa-violet-fill:#403452;--oa-violet-ink:#e5d3ff;
  --oa-teal-fill:#243f39;--oa-teal-ink:#b4e5d4;
  --oa-amber-fill:#453824;--oa-amber-ink:#f3d59b;
  --oa-slate-fill:#333d49;--oa-slate-ink:#d2e0ef;
  --oa-save:#a9c6fb;--oa-save-hover:#c3d7fd;--oa-save-ink:#122746;
  --oa-connected:#80c6a1;
  --oa-panel-shadow:0 5px 20px #0003;--oa-popover-shadow:0 10px 28px #0007;
 }
}
.oa-management.oa-native .oa-sidebar{border:0;background:var(--oa-rail)}
.oa-management.oa-native .oa-sidebar .oa-nav{grid-template-columns:minmax(0,1fr)}
.oa-management.oa-native .oa-sidebar .oa-nav button{min-width:0;max-width:100%}
.oa-management.oa-native .oa-platform-label{white-space:normal;overflow-wrap:anywhere}
.oa-management.oa-native :is(.oa-footer,.oa-tabs,.oa-platform-settings,.oa-task-actions,.oa-starter,.oa-schedule,.project-save,.route-row,.x-config-column){border:0}
.oa-management.oa-native :is(button,.oa-task-menu>summary,.oa-more-settings>summary){
 border:0;background:var(--oa-fill);box-shadow:none;
}
.oa-management.oa-native :is(button:not(:disabled):hover,.oa-task-menu>summary:hover,.oa-more-settings>summary:hover){
 background:var(--oa-hover);box-shadow:none;
}
.oa-management.oa-native :is(.oa-nav button,.oa-task-row,.oa-tabs button,.oa-context-tabs button,.oa-task-sheet-head button){
 background:transparent;box-shadow:none;
}
.oa-management.oa-native :is(
 .oa-nav button[aria-current=page],.oa-task-row.is-selected,.oa-tabs button[aria-selected=true],
 .oa-context-tabs button[aria-selected=true],.oa-scope-tabs button[aria-pressed=true],
 .oa-starter-options button[aria-pressed=true],.oa-choice-picks button[aria-pressed=true],
 .oa-account-options>.account.is-selected
){
 border:0;background:var(--oa-selection);color:var(--oa-selected-ink);box-shadow:none;
}
.oa-management.oa-native button.primary{
 border:0;background:var(--oa-action);color:var(--oa-action-ink);box-shadow:none;
}
.oa-management.oa-native button.primary:not(:disabled):hover{background:var(--oa-action-hover)}
.oa-management.oa-native :is(#rulesSave,#xConfigSave,#creatorSave):not(:disabled){
 background:var(--oa-save);color:var(--oa-save-ink);
}
.oa-management.oa-native :is(#rulesSave,#xConfigSave,#creatorSave):not(:disabled):hover{background:var(--oa-save-hover)}
.oa-management.oa-native .status.good::before{background:var(--oa-connected)}
.oa-management.oa-native :is(.oa-task-row,[data-choice-tone]){
 --oa-kind-fill:var(--oa-blue-fill);--oa-kind-ink:var(--oa-blue-ink);
}
.oa-management.oa-native :is(#rulesSummary,#xConfigSummary)>.oa-task-row:nth-child(2),
.oa-management.oa-native [data-choice-tone=violet]{
 --oa-kind-fill:var(--oa-violet-fill);--oa-kind-ink:var(--oa-violet-ink);
}
.oa-management.oa-native :is(#rulesSummary>.oa-task-row:nth-child(3),#xConfigSummary>.oa-task-row:nth-child(4),[data-choice-tone=teal]){
 --oa-kind-fill:var(--oa-teal-fill);--oa-kind-ink:var(--oa-teal-ink);
}
.oa-management.oa-native :is(#rulesSummary>.oa-task-row:nth-child(4),#xConfigSummary>.oa-task-row:nth-child(3),[data-choice-tone=amber]){
 --oa-kind-fill:var(--oa-amber-fill);--oa-kind-ink:var(--oa-amber-ink);
}
.oa-management.oa-native :is(#rulesSummary,#xConfigSummary)>.oa-task-row:nth-child(5){
 --oa-kind-fill:var(--oa-slate-fill);--oa-kind-ink:var(--oa-slate-ink);
}
.oa-management.oa-native .oa-task-row-icon{
 display:grid;place-items:center;width:28px;height:28px;border-radius:8px;
 background:var(--oa-kind-fill);
}
.oa-management.oa-native .oa-task-row-icon img{width:16px;height:16px}
.oa-management.oa-native :is(.oa-task-row.is-selected,[data-choice-tone] .oa-choice-picks button[aria-pressed=true]){
 background:var(--oa-kind-fill);color:var(--oa-kind-ink);
}
.oa-management.oa-native .oa-task-row.is-selected .oa-task-row-icon{background:var(--surface)}
.oa-management.oa-native .oa-choice-editor [data-choice-tone]{--oa-chip-fill:#245cce;--oa-chip-ink:#fff}
.oa-management.oa-native .oa-choice-editor [data-choice-tone=violet]{--oa-chip-fill:#7639bd}
.oa-management.oa-native .oa-choice-editor [data-choice-tone=teal]{--oa-chip-fill:#087861}
.oa-management.oa-native .oa-choice-editor [data-choice-tone=amber]{--oa-chip-fill:#ffbf49;--oa-chip-ink:#29200d}
.oa-management.oa-native .oa-choice-editor .oa-choice-picks button[aria-pressed=true]{
 background:var(--oa-chip-fill);color:var(--oa-chip-ink);font-weight:650;
}
.oa-management.oa-native #xSettings :is(.oa-task-row,[data-choice-tone]){
 --oa-x-choice-fill:#245cce;--oa-x-choice-ink:#fff;
}
.oa-management.oa-native #xSettings :is(#xConfigSummary>.oa-task-row:nth-child(2),[data-choice-tone=violet],.x-config-methods){
 --oa-x-choice-fill:#7639bd;
}
.oa-management.oa-native #xSettings :is(#xConfigSummary>.oa-task-row:nth-child(3),[data-choice-tone=amber]){
 --oa-x-choice-fill:#ffbf49;--oa-x-choice-ink:#29200d;
}
.oa-management.oa-native #xSettings :is(#xConfigSummary>.oa-task-row:nth-child(4),[data-choice-tone=teal]){
 --oa-x-choice-fill:#087861;
}
.oa-management.oa-native #xSettings #xConfigSummary>.oa-task-row:nth-child(5){
 --oa-x-choice-fill:#435c83;
}
.oa-management.oa-native #xSettings #xConfigSummary>.oa-task-row:not(.is-selected){
 background:var(--oa-fill);color:var(--ink);
}
.oa-management.oa-native #xSettings #xConfigSummary>.oa-task-row:not(.is-selected):hover{
 background:var(--oa-hover);
}
.oa-management.oa-native #xSettings :is(
 #xConfigSummary>.oa-task-row.is-selected,
 .x-config-methods label:has(:checked)
){
 background:var(--oa-x-choice-fill);color:var(--oa-x-choice-ink);
}
.oa-management.oa-native #xSettings #xConfigSummary>.oa-task-row.is-selected .oa-task-row-copy small{
 color:inherit;
}
.oa-management.oa-native .oa-task-rows{grid-template-columns:minmax(0,1fr);gap:4px}
.oa-management.oa-native .oa-task-row-copy strong{overflow-wrap:anywhere}
.oa-management.oa-native .oa-task-row-copy small{max-width:100%}
.oa-management.oa-native .oa-task-tools{align-items:flex-start}
.oa-management.oa-native .oa-task-tools>.oa-task-menu{margin:0;min-width:0;max-width:100%}
.oa-management.oa-native .oa-task-tools>button,
.oa-management.oa-native .oa-task-tools>.oa-task-menu>summary{
 display:inline-flex;align-items:center;min-height:34px;margin:0;padding:6px 10px;line-height:1.3;
}
.oa-management.oa-native .oa-starter-options>button{
 position:relative;align-content:start;padding-inline-end:30px;overflow-wrap:anywhere;
}
.oa-management.oa-native .oa-starter-options>button:nth-child(1){--oa-preset-fill:#245cce}
.oa-management.oa-native .oa-starter-options>button:nth-child(2){--oa-preset-fill:#7639bd}
.oa-management.oa-native .oa-starter-options>button:nth-child(3){--oa-preset-fill:#a13921}
.oa-management.oa-native .oa-starter-options>button:nth-child(4){--oa-preset-fill:#ad2d74}
.oa-management.oa-native .oa-starter-options>button:nth-child(5){--oa-preset-fill:#087861}
.oa-management.oa-native .oa-starter-options>button:nth-child(6){--oa-preset-fill:#ffbf49;--oa-preset-ink:#29200d}
.oa-management.oa-native .oa-starter-options>button:nth-child(7){--oa-preset-fill:#07536c}
.oa-management.oa-native .oa-starter-options>button:is(:hover,[aria-pressed]){
 background:var(--oa-preset-fill);color:var(--oa-preset-ink,#fff);
}
.oa-management.oa-native .oa-starter-options>button span{color:inherit}
.oa-management.oa-native .oa-starter-options>button[aria-pressed=true]{
 outline:2px solid var(--oa-focus);outline-offset:2px;
}
.oa-management.oa-native .oa-starter-options>button[aria-pressed=true]::after{
 content:"✓";position:absolute;inset-block-start:8px;inset-inline-end:8px;
 width:16px;height:16px;display:grid;place-items:center;border:1px solid currentColor;
 border-radius:50%;font-size:11px;font-weight:700;
}
.oa-management.oa-native .oa-account-header{
 display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 12px;min-height:0;margin-bottom:10px;
}
.oa-management.oa-native .oa-account-header>.oa-heading{grid-area:1/1;margin:0}
.oa-management.oa-native .oa-account-header>.oa-heading h1{overflow-wrap:anywhere}
.oa-management.oa-native .oa-account-header>.actions{grid-area:1/2;justify-content:flex-end}
.oa-management.oa-native .oa-account-header>.actions>button{
 min-height:36px;padding:6px 10px;line-height:1.3;
}
.oa-management.oa-native #accountPanel.oa-account-cards{grid-column:1/-1;min-width:0;width:100%}
.oa-management.oa-native .oa-account-options>.empty{margin:0;padding:8px 0}
.oa-management.oa-native .oa-account-options{min-width:0}
.oa-management.oa-native .oa-account-options>.account{
 flex:0 0 auto;width:280px;max-width:100%;height:94px;margin:0;
 border:0;background:var(--oa-fill);box-shadow:none;
}
.oa-management.oa-native .oa-account-options>.account>div:last-child{
 flex:1;min-width:0;
}
.oa-management.oa-native .oa-account-options .account-select{
 width:100%;max-width:none;
}
.oa-management.oa-native .oa-account-options>.account :is(.help,.status){
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.oa-management.oa-native .oa-account-options>.account:not(.is-selected):hover{
 background:var(--oa-hover);box-shadow:none;
}
.oa-management.oa-native :is(.avatar,.oa-platform-mark[data-brand=x]){border:0;box-shadow:none}
.oa-management.oa-native :is(.panel,.oa-x-config,.oa-x-capabilities,.review-card,.profile-editor,.oa-software-update,.template-card){
 border:0;box-shadow:none;
}
.oa-management.oa-native :is(.oa-x-capabilities,.oa-software-update){background:var(--oa-fill)}
.oa-management.oa-native .oa-task-sheet{
 border:0;background:var(--surface);box-shadow:var(--oa-panel-shadow);
}
.oa-management.oa-native :is(.oa-more-popover,.oa-task-menu[open]>.actions){
 border:0;background:var(--surface);box-shadow:var(--oa-popover-shadow);
}
.oa-management.oa-native :is(input:not([type=checkbox]):not([type=file]),textarea,select){
 border:0;background:var(--oa-fill);box-shadow:none;
}
.oa-management.oa-native :is(input,textarea,select):disabled{background:var(--oa-canvas)}
.oa-management.oa-native :is(button,input,select,textarea,a,summary,[role=option]):focus-visible{
 outline:2px solid var(--oa-focus);outline-offset:2px;
}
@media(min-width:800px) and (max-width:999px) and (min-height:600px){
 .oa-management.oa-native .oa-sidebar .oa-nav button{font-size:12px;padding-inline:6px;gap:6px}
 .oa-management.oa-native .oa-sidebar .oa-platform-label{overflow-wrap:normal}
 .oa-management.oa-native .oa-task-workspace{grid-template-columns:170px minmax(0,1fr);gap:14px}
 .oa-management.oa-native .oa-task-workspace.oa-sheet-closed{grid-template-columns:170px}
 .oa-management.oa-native .oa-task-summary{overflow:auto;scrollbar-width:thin}
 .oa-management.oa-native .oa-task-heading{flex:none;min-height:0}
 .oa-management.oa-native .oa-task-row{min-height:56px;padding:8px;gap:8px}
 .oa-management.oa-native .oa-task-row-copy strong{font-size:14px}
 .oa-management.oa-native #xSettings{overflow:hidden!important}
 .oa-management.oa-native #xOperatingPanel{flex:1;min-height:0;overflow:hidden;height:auto}
 .oa-management.oa-native.oa-x-tools #xSettings{overflow:auto!important}
}
@media(max-width:999px){
 .oa-management.oa-native .oa-task-sheet{position:static;width:100%}
 .oa-management.oa-native .oa-task-workspace:not(.oa-sheet-closed)>.oa-task-summary{opacity:1;pointer-events:auto}
 .oa-management.oa-native .oa-task-tools>.oa-task-menu[open]>.actions{
  position:static;min-width:0;max-width:100%;margin-top:4px;contain:inline-size;
 }
 .oa-management.oa-native .oa-task-menu[open]>.actions>button{white-space:normal;overflow-wrap:anywhere}
}
@media(max-width:799px),(max-height:599px){
 .oa-management.oa-native .oa-task-workspace{display:flex;flex-direction:column;gap:12px;height:auto}
 .oa-management.oa-native .oa-task-summary{padding-top:0}
 .oa-management.oa-native .oa-task-heading{min-height:0}
 .oa-management.oa-native .oa-task-rows{display:flex;flex-wrap:wrap;gap:5px}
 .oa-management.oa-native .oa-task-row{width:auto;min-height:36px;padding:6px 8px;gap:5px}
 .oa-management.oa-native .oa-task-row-icon{width:22px;height:22px}
 .oa-management.oa-native .oa-task-row-copy :is(strong,small){margin:0}
 .oa-management.oa-native .oa-task-row :is(small,.oa-task-row-edit){display:none}
 .oa-management.oa-native .oa-task-sheet{position:static;width:100%}
}
"""


# Native-only finish. Keep the trusted local safety page on its existing styling.
NATIVE_FINISH_STYLE = """
body.oa-management.oa-native:is([data-color-scheme], :not([data-color-scheme])) {
  --oa-canvas: light-dark(#fff, #1d1d20);
  --oa-rail: light-dark(#fff, #242427);
  --bg: var(--oa-canvas);
  --surface: light-dark(#fff, #29292d);
  --soft: light-dark(#f7f7f8, #303034);
  --ink: light-dark(#222123, #f3f2f5);
  --muted: light-dark(#5d5b61, #c3c1c8);
  --line: light-dark(#e8e7ea, #44434a);
  --oa-fill: light-dark(#f3f2f4, #35353a);
  --oa-hover: light-dark(#eae9ec, #404047);
  --oa-selection: light-dark(#f4e6f7, #48394d);
  --oa-selected-ink: light-dark(#482b54, #fae9fa);
  --oa-action: light-dark(#262426, #f0edf1);
  --oa-action-hover: light-dark(#383538, #fff);
  --oa-action-ink: light-dark(#fff, #242226);
  --oa-focus: light-dark(#764589, #e9a9ef);
  --oa-save: var(--oa-action);
  --oa-save-hover: var(--oa-action-hover);
  --oa-save-ink: var(--oa-action-ink);
  --oa-key-edge: light-dark(#24212b26, #101013bc);
  --oa-main-shadow: light-dark(#211c3240, #0008);
  --oa-key-shadow: light-dark(#24212b15, #0005);
  --oa-panel-shadow: 0 7px 26px light-dark(#25213012, #0004);
  --oa-popover-shadow: 0 8px 24px light-dark(#25213022, #0008);
}
body.oa-management.oa-native :is(.oa-heading h1,.oa-task-heading h1,.oa-task-sheet-head h2) {
  font-weight: 800;
}
.oa-management.oa-native .oa-starter-options > button {
  border-radius: 9px;
}
body.oa-management.oa-native .oa-starter-options strong {
  font-weight: 750;
  letter-spacing: -.01em;
}
.oa-management.oa-native .oa-account-options > .account.is-selected {
  background: var(--oa-selection);
  color: var(--oa-selected-ink);
  box-shadow: none;
}
.oa-management.oa-native :is(.oa-account-header > .actions > button, .oa-task-tools > button,
 .oa-task-tools > .oa-task-menu > summary, #rulesSave, #xConfigSave, #creatorSave):not(:disabled) {
  box-shadow: 0 2px 3px var(--oa-key-shadow);
}
.oa-management.oa-native :is(.oa-account-header > .actions > .primary, #rulesSave, #xConfigSave, #creatorSave) {
  border-radius: 11px;
  font-weight: 650;
  letter-spacing: -.01em;
  padding-inline: 12px;
}
.oa-management.oa-native :is(.oa-account-header > .actions > .primary, #rulesSave, #xConfigSave, #creatorSave):not(:disabled) {
  box-shadow: 0 5px 12px -4px var(--oa-main-shadow);
}
.oa-management.oa-native :is(.oa-account-header > .actions > button, .oa-task-tools > button,
 .oa-task-tools > .oa-task-menu > summary, .oa-starter-options > button,
 #rulesSave, #xConfigSave, #creatorSave):active:not(:disabled) {
  box-shadow: inset 0 2px 3px var(--oa-key-edge);
}
@media (prefers-reduced-motion:no-preference) {
  .oa-management.oa-native :is(.oa-account-header > .actions > button, .oa-task-tools > button,
   .oa-task-tools > .oa-task-menu > summary, .oa-starter-options > button,
   #rulesSave, #xConfigSave, #creatorSave):not(:disabled) { transition: box-shadow 90ms ease; }
}

/* Preview surfaces use fill and diffuse elevation without decorative strokes. */
body.oa-management.oa-native :is(.oa-sidebar, .oa-account-options > .account, .oa-task-sheet,
 .panel, .oa-x-config, .oa-x-capabilities, .oa-support-links, .oa-support-dialog,
 .oa-support-header, .oa-support-footer, .oa-more-popover, .oa-task-menu[open] > .actions,
 .review-card, .profile-editor, .template-card, .oa-software-update, .oa-starter,
 .oa-choice-picks > button, button, input, textarea, select, summary) {
  border-color: transparent;
}
body.oa-management.oa-native .oa-starter-options > button[aria-pressed=true]:not(:focus-visible) {
  outline: none;
}
body.oa-management.oa-native .oa-starter-options > button[aria-pressed=true]::after {
  border: 0;
  background: var(--oa-preset-ink, #fff);
  color: var(--oa-preset-fill);
}
"""

NATIVE_FINISH_STYLE += """
.oa-management.oa-native #accountPanel.oa-account-cards{container-type:inline-size}
.oa-management.oa-native #accountPanel .oa-account-cards-body{justify-content:flex-start;align-items:center}
.oa-management.oa-native #accounts{display:flex;flex-wrap:wrap;width:max-content;max-width:100%;max-height:none;overflow:visible}
.oa-native #accounts>.account{flex:0 0 auto;width:clamp(200px,calc((100cqw - 20px)/2),270px);max-width:100%}
.oa-management.oa-native #accountPanel .oa-account-tools{flex:0 0 auto;flex-direction:row;margin:0}
@container(max-width:439px){
 .oa-native #accounts>.account{width:min(100%,270px)}
}
.oa-native #accounts .oa-account-copy{flex:1;min-width:0}
.oa-native #accounts .account-select{max-width:100%}
.oa-native .oa-account-menu{position:relative;align-self:flex-start;flex:0 0 auto;margin-left:auto}
.oa-native #accounts>.account>.oa-account-recovery{align-self:center;min-height:28px;padding:3px 6px;font-size:11px;margin-inline-start:auto}
.oa-native .oa-account-menu summary{display:grid;place-items:center;width:30px;height:30px;list-style:none;cursor:pointer;border-radius:7px;color:var(--muted);font-size:18px}
.oa-native .oa-account-menu summary::-webkit-details-marker{display:none}
.oa-native .oa-account-menu summary:hover{background:var(--soft);color:var(--ink)}
.oa-native .oa-account-menu>div{position:absolute;right:0;top:100%;z-index:45;display:grid;gap:3px;white-space:nowrap;background:var(--surface);padding:4px;border-radius:8px;box-shadow:var(--raised)}
.oa-native .oa-account-menu:not([open])>div{display:none}
.oa-native .oa-account-menu>div>.oa-account-remove{color:var(--danger)}
.oa-native #accounts>.account:has(.oa-account-menu[open]){z-index:46}
.oa-native .oa-account-remove-dialog{width:min(420px,calc(100% - 32px));padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--surface);color:var(--ink)}
.oa-native .oa-account-remove-dialog::backdrop{background:#0006}
.oa-native .oa-account-remove-dialog p{margin:8px 0;overflow-wrap:anywhere}
.oa-native .oa-account-remove-dialog .actions{justify-content:flex-end;margin-top:14px}
"""

PLATFORM_ACCOUNT_NAV_STYLE = """
.oa-platform-group{min-width:0}
.oa-platform-group .oa-platform-trigger{display:flex;align-items:center}
.oa-platform-chevron{
 width:6px;height:6px;flex:none;margin-inline-start:auto;margin-inline-end:2px;
 border-inline-end:1.5px solid currentColor;border-bottom:1.5px solid currentColor;
 transform:rotate(-45deg);color:var(--muted)
}
.oa-platform-trigger[aria-expanded=true] .oa-platform-chevron{transform:rotate(45deg)}
.oa-management.oa-native.oa-platform-view #accountPanel{
 min-width:0;min-height:0;max-height:none;overflow:visible;
 margin:2px 0 4px 9px;padding:2px 0 0 6px;border-inline-start:1px solid var(--line)
}
.oa-platform-accounts .oa-list-head{
 display:flex;justify-content:space-between;align-items:center;gap:4px;padding:3px 6px;
 font-size:11px;line-height:1.35;color:var(--muted)
}
.oa-management.oa-native.oa-platform-view #accounts{
 display:flex;flex-flow:column nowrap;gap:2px;min-width:0;width:100%;padding:2px;
 max-height:min(42dvh,450px);overflow:auto;overscroll-behavior:contain;scrollbar-width:thin
}
.oa-management.oa-native.oa-platform-view #accounts > .account{
 display:flex;align-items:center;flex:none;min-width:0;width:100%;height:auto;min-height:40px;
 padding:0;margin:0;gap:0;border:0;border-radius:8px;background:transparent
}
.oa-management.oa-native.oa-platform-view #accounts > .account.is-selected{
 background:var(--oa-selection);color:var(--oa-selected-ink)
}
.oa-management.oa-native.oa-platform-view #accounts .account-select{
 display:flex;align-items:center;gap:6px;flex:1;min-width:0;max-width:100%;min-height:40px;
 border:0;border-radius:8px;background:transparent;padding:3px 4px 3px 5px
}
.oa-management.oa-native.oa-platform-view #accounts .account-select:hover{background:var(--oa-hover)}
.oa-management.oa-native.oa-platform-view #accounts .account-select:focus-visible{outline-offset:-2px}
.oa-management.oa-native.oa-platform-view #accounts .avatar{width:24px;height:24px;flex-basis:24px;font-size:12px;border-radius:6px}
.oa-management.oa-native.oa-platform-view #accounts .oa-account-copy{
 display:grid;gap:1px;min-width:0;font-size:12px;line-height:1.2
}
.oa-management.oa-native.oa-platform-view #accounts .oa-account-copy>strong{
 min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:650
}
.oa-management.oa-native.oa-platform-view #accounts .status{
 display:block;font-size:10px;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis
}
.oa-management.oa-native.oa-platform-view #accounts .oa-account-menu{align-self:center;margin:0 2px 0 0}
.oa-management.oa-native.oa-platform-view #accounts .oa-account-menu summary{width:24px;height:29px}
.oa-management.oa-native.oa-platform-view #accounts>.empty{padding:6px;font-size:12px}
.oa-management.oa-native.oa-platform-view .oa-account-header{min-width:0}
.oa-management.oa-native.oa-platform-view .oa-account-header > .oa-heading{display:block;min-width:0}
.oa-native #accountCurrent{width:100%;min-width:0}
.oa-management.oa-native.oa-platform-view #pageTitle{
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap
}
.oa-native #accountCaption{
 display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 color:var(--muted);font-size:11px;line-height:1.3;margin-top:2px
}
.oa-management.oa-native.oa-platform-view #accountTools{margin:0;align-self:center}
.oa-native #accountTools .oa-more-settings > summary{min-height:31px;padding:4px 8px;white-space:nowrap}
.oa-management.oa-native:is(.oa-platform-view,.oa-video-open) .oa-workspace-popover:popover-open{
 position:fixed;inset:auto;margin:0;overflow:auto;overscroll-behavior:contain;
 color:var(--ink);background:var(--surface);white-space:normal;
 box-shadow:var(--oa-popover-shadow);border:1px solid var(--line);border-radius:9px
}
.oa-native:is(.oa-platform-view,.oa-video-open) .oa-workspace-popover button{white-space:normal;overflow-wrap:anywhere}
.oa-native.oa-platform-view .oa-workspace-popover .oa-account-menu{position:relative}
.oa-native.oa-platform-view .oa-account-menu > div.oa-workspace-popover button{
 width:100%;max-width:none;padding:6px 8px;justify-content:flex-start
}
.oa-native:is(.oa-platform-view,.oa-video-open) #softwareUpdateSlot[popover]:not(:popover-open){display:none}
.oa-native:is(.oa-platform-view,.oa-video-open) #softwareUpdateSlot:popover-open .oa-software-update{margin:0}
.oa-native:is(.oa-platform-view,.oa-video-open) #softwareUpdateSlot:popover-open .oa-support-links{
 grid-template-columns:repeat(2,minmax(0,1fr));gap:3px;margin:4px 0 0;padding:3px
}
.oa-native:is(.oa-platform-view,.oa-video-open) #wechatCompactUpdates{
 min-height:28px;padding:4px 7px;white-space:nowrap;font-size:12px;align-self:start
}
@media(min-width:561px) and (max-width:799px),(min-width:561px) and (max-height:599px){
 body.oa-management.oa-native.oa-platform-view:not(.oa-x-developer-open) .oa-shell{
  grid-template-columns:122px minmax(0,1fr)
 }
 body.oa-management.oa-native.oa-platform-view:not(.oa-x-developer-open) .oa-sidebar{
  display:flex;flex-direction:column;align-items:stretch;padding:10px 7px;gap:8px
 }
 .oa-native.oa-platform-view .oa-sidebar .oa-brand-logo{width:104px}
 .oa-management.oa-native.oa-platform-view .oa-sidebar .oa-nav button{padding:4px 6px;gap:5px;min-height:32px}
 .oa-management.oa-native.oa-platform-view #accountPanel{margin-inline-start:5px;padding-inline-start:3px}
 .oa-management.oa-native.oa-platform-view #accounts .avatar{width:17px;height:17px;flex-basis:17px;font-size:10px}
 .oa-management.oa-native.oa-platform-view .oa-sidebar #accounts .account-select{padding-inline:3px;gap:3px}
 .oa-management.oa-native.oa-platform-view #accounts .oa-account-menu summary{width:18px}
}
@media(min-width:561px){
 body.oa-management.oa-native.oa-platform-view:not(.oa-x-developer-open) .oa-shell{
  display:grid;height:100dvh;min-height:0;grid-template-rows:minmax(0,1fr);overflow:hidden
 }
 body.oa-management.oa-native.oa-platform-view:not(.oa-x-developer-open) .oa-sidebar{
  min-height:0;min-width:0;overflow:auto;overscroll-behavior:contain
 }
 body.oa-management.oa-native.oa-platform-view:not(.oa-wechat-view,.oa-x-developer-open) .oa-content{
  height:100%;min-height:0;min-width:0;overflow:auto
 }
 .oa-management.oa-native.oa-platform-view .oa-sidebar > div:has(#platformNavigation){
  display:flex;flex:1 1 auto;flex-direction:column;min-height:0
 }
 .oa-management.oa-native.oa-platform-view #platformNavigation{
  display:flex;flex-direction:column;min-height:0
 }
 .oa-native.oa-platform-view .oa-platform-group{
  display:flex;flex:0 0 auto;flex-direction:column;min-height:0
 }
 .oa-native.oa-platform-view .oa-platform-group:has([aria-current=page]){flex:0 1 auto}
 .oa-native.oa-platform-view .oa-platform-trigger,.oa-native.oa-platform-view .oa-list-head{flex:none}
 .oa-management.oa-native.oa-platform-view #accountPanel:not([hidden]){
  display:flex;flex:1 1 auto;flex-direction:column;min-height:58px
 }
 .oa-management.oa-native.oa-platform-view #accounts{min-height:0}
 .oa-native.oa-platform-view .oa-sidebar :is(#softwareUpdateSlot,#wechatCompactUpdates){order:1}
 .oa-native.oa-platform-view .oa-sidebar > .oa-support-links{order:2}
 .oa-native.oa-platform-view .oa-sidebar > :is(.oa-brand,#softwareUpdateSlot,#wechatCompactUpdates,.oa-support-links){
  flex:none
 }
}
@media(max-width:560px){
 .oa-management.oa-native.oa-platform-view .oa-sidebar{
  display:grid;grid-template-columns:minmax(0,1fr) auto;align-content:start;padding:4px 9px;gap:2px 5px
 }
 .oa-native.oa-platform-view .oa-sidebar .oa-brand{display:flex;align-items:center;gap:6px;min-width:0}
 .oa-native.oa-platform-view .oa-sidebar .oa-brand-logo{width:100px}
 .oa-native.oa-platform-view .oa-sidebar #wechatCompactUpdates{grid-area:1/2}
 .oa-management.oa-native.oa-platform-view .oa-sidebar > div:has(#platformNavigation){
  display:flex;align-items:center;gap:4px;grid-area:2/1/3/-1;min-width:0;overflow:auto;scrollbar-width:thin
 }
 .oa-native.oa-platform-view .oa-sidebar > div:has(#platformNavigation) > .help{display:none}
 .oa-management.oa-native.oa-platform-view .oa-sidebar .oa-nav{
  display:flex;flex:none;flex-wrap:nowrap;gap:3px;margin:0
 }
 .oa-management.oa-native.oa-platform-view .oa-sidebar .oa-nav button{
  min-height:29px;padding:3px 6px;gap:4px;white-space:nowrap
 }
 .oa-management.oa-native.oa-platform-view #accountPanel:popover-open{
  padding:5px;margin:0;overflow:auto
 }
 .oa-management.oa-native.oa-platform-view #accountPanel:popover-open #accounts{max-height:none;overflow:visible}
 .oa-management.oa-native.oa-platform-view #accountPanel:popover-open .oa-list-head{
  position:sticky;top:-5px;z-index:1;background:var(--surface);padding-block:5px
 }
}
@media(max-width:420px){
 .oa-native.oa-platform-view .oa-sidebar #openMediaStudio > span{display:none}
 .oa-management.oa-native.oa-platform-view .oa-account-header{column-gap:5px}
 .oa-management.oa-native.oa-platform-view .oa-account-header>.actions{gap:3px}
 .oa-management.oa-native.oa-platform-view .oa-account-header>.actions>button,
 .oa-native.oa-platform-view #accountTools .oa-more-settings>summary{
  padding-inline:5px;font-size:11px
 }
}
"""

STYLE += r'''
.oa-management .oa-content-heading{font-size:14px;line-height:1.35;margin:10px 0 6px}
.oa-management :is(#xBilling,#xProductionResume,.oa-capability-details) button{white-space:normal;overflow-wrap:anywhere}
.oa-management .oa-x-setup-help{margin-block:6px 10px}
.oa-management .oa-x-recovery>output{overflow-wrap:anywhere}
.oa-native:not(.oa-x-tools) #xSettings > :is(.oa-capability-details,.oa-x-production,#xSchedulePanel),
.oa-native.oa-x-billing-view #xSettings > :not(#xWorkspaceBack,#xBilling){display:none!important}
.oa-native.oa-x-tools #xSettings{overflow:auto!important}
'''
