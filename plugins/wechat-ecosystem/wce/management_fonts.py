"""Offline, OFL-licensed type for the native workspace chrome."""
import base64
from functools import lru_cache

from .own_branding import _PACKAGE


@lru_cache(maxsize=1)
def style():
    folder = _PACKAGE / 'assets/management/fonts'
    faces = []
    for file, family, weights in (
        ('openahoy-rounded-sc.woff2', 'OpenAhoy Rounded SC', '500'),
        ('openahoy-rounded-latin.woff2', 'OpenAhoy Rounded Latin', '400 800'),
    ):
        data = base64.b64encode((folder / file).read_bytes()).decode('ascii')
        faces.append(
            f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{data}) '
            f'format("woff2");font-weight:{weights};font-display:swap}}'
        )
    return ''.join(faces) + """
body.oa-management.oa-native{
 --oa-ui-font:"OpenAhoy Rounded Latin","OpenAhoy Rounded SC",-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
 font-family:var(--oa-ui-font);font-weight:500
}
.oa-management.oa-native :is(button,input:not([type=password]),textarea,select){font-family:var(--oa-ui-font)}
.oa-management.oa-native :is(h1,h2,.oa-platform-label,.oa-starter-options strong){font-weight:700}
.oa-native .oa-starter-options{gap:6px;grid-template-columns:repeat(auto-fit,minmax(min(100%,145px),1fr));margin:7px 0}
.oa-native .oa-starter-options button{padding:7px 9px;gap:3px;line-height:1.35}
.oa-native .oa-starter-options button span{font-size:11px}
.oa-native .oa-starter-options button span:last-child{display:none}
"""
