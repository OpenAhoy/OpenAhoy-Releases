"""Current platform marks. Presentation only; no platform or account I/O."""
import base64
from html import escape
import json

from .own_branding import _PACKAGE

_ASSETS = _PACKAGE / 'assets/platforms'
_PLATFORMS = {
    'wechat_official_account': ('公众号', 'official-account.svg', 'official-account.svg'),
    'x': ('X', 'x-black.png', 'x-white.svg'),
    'xiaohongshu': ('小红书', 'xiaohongshu.ico', 'xiaohongshu.ico'),
}


def catalog():
    def source(name):
        mime = 'image/svg+xml' if name.endswith('.svg') else ('image/x-icon' if name.endswith('.ico') else 'image/png')
        return 'data:' + mime + ';base64,' + base64.b64encode((_ASSETS / name).read_bytes()).decode('ascii')
    return {key: {'name': name, 'light': source(light), 'dark': source(dark)}
            for key, (name, light, dark) in _PLATFORMS.items()}


def label(platform_id, fallback):
    value = catalog().get(platform_id)
    if value is None:
        return escape(fallback)
    images = '<img class="oa-platform-logo" src="' + value['light'] + '" alt="">'
    if value['dark'] != value['light']:
        images = ('<img class="oa-platform-logo oa-platform-logo--light" src="' + value['light'] + '" alt="">'
                  '<img class="oa-platform-logo oa-platform-logo--dark" src="' + value['dark'] + '" alt="">')
    return ('<span class="oa-platform-mark" data-brand="' + platform_id + '" aria-hidden="true">' + images
            + '</span><span class="oa-platform-label">' + escape(value['name']) + '</span>')


def script():
    return 'const OAPlatformBranding=(()=>{const marks=' + json.dumps(catalog(), separators=(',', ':')) + r''';
 function decorate(button,id,fallback,ui){
  const value=Object.hasOwn(marks,id)?marks[id]:null;button.replaceChildren();
  if(value){const box=document.createElement('span');box.className='oa-platform-mark';box.dataset.brand=id;box.setAttribute('aria-hidden','true');
   const image=(src,variant='')=>{const img=document.createElement('img');img.className='oa-platform-logo'+(variant?' oa-platform-logo--'+variant:'');img.src=src;img.alt='';return img;};
   if(value.dark!==value.light)box.append(image(value.light,'light'),image(value.dark,'dark'));else box.append(image(value.light));
   button.append(box);
  }
  const text=document.createElement('span');text.className='oa-platform-label';if(ui&&(value||!fallback))ui.set(text,value?.name||'原平台当前不可用');else text.textContent=value?value.name:fallback;button.append(text);
 }
 return {decorate};
})();
'''
