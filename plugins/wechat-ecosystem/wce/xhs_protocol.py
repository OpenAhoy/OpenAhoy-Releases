"""Outer Xiaohongshu extension; original WeChat/X authority is unchanged."""
from copy import deepcopy
import re

from .contracts import WCEError
from .tools import schema
from .xhs_platform import PLATFORM, XHSPlatform

STRING={'type':'string'}
CID={'type':'string','pattern':'^xhs-[0-9a-f]{24}$'}
NOTE={'type':'string','pattern':'^[0-9a-f]{24}$'}
ID={'type':'string','pattern':'^[A-Za-z0-9_-]{1,128}$'}
IMAGE=schema({'absolute_path':{'type':'string','minLength':1},
    'expected_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'}})
UI='xhs.ui.action'
SPECS={
 'xhs.connections.list':schema({}),
 'xhs.profile.read':schema({'connection_id':CID}),
 'xhs.notes.list':schema({'connection_id':CID}),
 'xhs.notes.read':schema({'connection_id':CID,'note_id':NOTE}),
 'xhs.notes.publish':schema({'connection_id':CID,'attempt_id':ID,
    'title':{'type':'string','minLength':1},'body':{'type':'string','minLength':1},
    'images':{'type':'array','minItems':1,'items':IMAGE}},
    {'topics':{'type':'array','items':{'type':'string','minLength':1}},'recovery_id':ID}),
 'xhs.attempt.status':schema({'connection_id':CID,'attempt_id':ID}),
 'xhs.notes.readback':schema({'connection_id':CID,'attempt_id':ID}),
 UI:schema({'operation':{'type':'string','enum':['READ','BEGIN','POLL','CANCEL']}},{'connection_id':CID,'binding_id':{'type':'string','pattern':'^[0-9a-f]{32}$'}}),
}


def validate(value,spec):
    """Closed input types without inventing note length/image-count quotas."""
    def check(ok):
        if not ok:raise WCEError('XHS_INVALID_REQUEST')
    kind=spec['type']
    if kind=='object':
        check(type(value) is dict and not set(value)-set(spec['properties']) and not set(spec['required'])-set(value))
        for key,item in value.items():validate(item,spec['properties'][key])
    elif kind=='array':
        check(type(value) is list and len(value)>=spec.get('minItems',0))
        for item in value:validate(item,spec['items'])
    elif kind=='string':
        check(type(value) is str and len(value)>=spec.get('minLength',0))
        try:value.encode('utf-8')
        except UnicodeError:raise WCEError('XHS_INVALID_REQUEST') from None
        check(not any(ord(c)<32 and c not in '\n\r\t' for c in value))
        if 'pattern' in spec:check(re.fullmatch(spec['pattern'],value) is not None)
        if 'enum' in spec:check(value in spec['enum'])
    else:raise WCEError('XHS_INVALID_REQUEST')


def descriptors():
    notes={
      'xhs.connections.list':'Read local Xiaohongshu account association only. This is not proof of a current login.',
      'xhs.profile.read':'Read this bound account through its isolated normal browser session. Human QR/risk challenges stay in the official page.',
      'xhs.notes.list':'Read visible own-note cards only, with ownership and completeness labels. No feed, likes, comments or recommendation polling.',
      'xhs.notes.read':'Read an exact note visible on this account own profile. Return canonical ID/URL; anonymous public readability is not implied.',
      'xhs.notes.publish':'Publish one currently authorized native image-text note via normal creator UI. Use real title/body, ordered image files and original attempt_id. No HTML, automatic retry or account switch. UNKNOWN: original status/readback only. Only a fresh explicit human authorization accepting duplicate risk permits recovery_id, which resumes the same attempt exactly once; never infer or automatically generate that permission.',
      'xhs.attempt.status':'Read the original local note attempt without another upload or submission.',
      'xhs.notes.readback':'Independently read the original observed note ID from own pages and verify identity/content. UNKNOWN without an observed ID remains unresolved; never repost.',
      UI:'App-only standard browser login start/poll/cancel. Human scans the official QR. No cookie, QR or token is returned to the model.'}
    rows=[]
    for name,spec in SPECS.items():
        write=name in {UI,'xhs.notes.publish'}
        row={'name':name,'description':notes[name],'inputSchema':deepcopy(spec),
            'annotations':{'readOnlyHint':not write,'destructiveHint':False,'idempotentHint':not write,
                'openWorldHint':name not in {'xhs.connections.list','xhs.attempt.status'}}}
        if name==UI:row['_meta']={'ui':{'visibility':['app']}}
        rows.append(row)
    return rows


class XHSRouter:
    def __init__(self,inner,platform=None):
        self.inner=inner;self.xhs=platform or XHSPlatform();self._xhs_call=False
    def __getattr__(self,name):return getattr(self.inner,name)
    @property
    def _inline_probe_meta(self):return self.inner._inline_probe_meta
    @_inline_probe_meta.setter
    def _inline_probe_meta(self,value):self.inner._inline_probe_meta=value
    def list_tools(self):return self.inner.list_tools()+descriptors()
    def evidence(self):
        return {'platform_id':'xiaohongshu','runtime':'standard_browser_adapter'} if self._xhs_call else self.inner.evidence()
    def call(self,name,args):
        self._xhs_call=name in SPECS
        if name not in SPECS:
            result=self.inner.call(name,args)
            if name=='wce.ui.management.overview':
                from .own_settings_protocol import read_platform_overview
                result=deepcopy(result)
                result['platforms'].append(deepcopy(PLATFORM))
                rows,status=read_platform_overview(self.xhs.overview)
                result.setdefault('platform_reads', {})['xiaohongshu']=status
                result['connections'].extend(rows or [])
            return result
        validate(args,SPECS[name])
        if name==UI:return self.xhs.ui(args['operation'],args.get('connection_id'),args.get('binding_id'))
        if name=='xhs.connections.list':return {'connections':self.xhs.overview()}
        a=dict(args);cid=a.pop('connection_id')
        if name=='xhs.profile.read':return self.xhs.read(cid,'profile')
        if name=='xhs.notes.list':return self.xhs.read(cid,'notes')
        if name=='xhs.notes.read':return self.xhs.read(cid,'note',a['note_id'])
        if name=='xhs.notes.publish':return self.xhs.publish(cid,**a)
        return self.xhs.status(cid,**a,readback=name=='xhs.notes.readback')
