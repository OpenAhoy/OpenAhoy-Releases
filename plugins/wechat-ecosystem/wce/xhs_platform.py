"""Explicit Xiaohongshu accounts via normal pages and isolated browser profiles.

No official posting API is claimed. Account association is separate from an
observed login or a publicly readable note. No cookie, token or QR crosses MCP.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import secrets
import shutil
import time

from .contracts import WCEError
from .own_account_metadata import read_metadata
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, registry_path
from .own_connection_registry import container
from .xhs_browser import Browser

PLATFORM={'id':'xiaohongshu','name':'小红书','account_noun':'小红书账号','account_id_label':'用户 ID',
    'settings_help':'本人扫码、本人笔记读取、原生图文发布及原链接读回；标准浏览器接入，不是官方发布 API。',
    'settings_supported':False,'binding_supported':True}
USER=re.compile('[0-9a-f]{24}')
ATTEMPT=re.compile('[A-Za-z0-9_-]{1,128}')


def require(ok,code='XHS_INVALID_REQUEST'):
    if not ok:raise WCEError(code)


def profile(value):
    require(type(value) is dict and set(value)=={'id','name'},'XHS_IDENTITY_UNVERIFIED')
    require(type(value['id']) is str and USER.fullmatch(value['id']) is not None
        and type(value['name']) is str and bool(value['name'].strip()),'XHS_IDENTITY_UNVERIFIED')
    return dict(value)


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


class XHSPlatform:
    def __init__(self,*,root=None,browser=None,browser_factory=None):
        self.root=Path(root) if root is not None else registry_path().parent/'xhs-platform'
        self.browser_factory=browser_factory or (lambda path: browser if browser is not None else Browser(path))
        self.browsers={}

    def _prepare(self):
        path_check(self.root.parent,True)
        container(self.root.parent,self.root.name)
        container(self.root,'accounts');container(self.root,'sessions')

    def _connections(self):
        if not os.path.lexists(self.root):return {}
        path_check(self.root,True);rows={}
        accounts=self.root/'accounts'
        if accounts.exists():
            path_check(accounts,True)
            for d in sorted(accounts.iterdir()):
                require(re.fullmatch('xhs-[0-9a-f]{24}',d.name) is not None,'XHS_CONNECTION_INVALID')
                path_check(d,True);row=read_metadata(d/'connection.json')
                if row is None:continue
                require(set(row)=={'schema','profile','session'} and row['schema']==2
                    and type(row['session']) is str and re.fullmatch('[0-9a-f]{32}',row['session']), 'XHS_CONNECTION_INVALID')
                value=profile(row['profile']);require(d.name=='xhs-'+value['id'],'XHS_CONNECTION_INVALID')
                rows[d.name]=row
        # A staged v1 association stays addressable without rewriting it or
        # copying its credentials. New bindings never replace its browser profile.
        old=read_metadata(self.root/'connection.json')
        if old is not None:
            require(set(old)=={'schema','profile'} and old['schema']==1,'XHS_CONNECTION_INVALID')
            value=profile(old['profile']);rows.setdefault('xhs-'+value['id'],old|{'session':'legacy'})
        return rows

    def _removed(self, cid, row):
        marker = read_metadata(self.root/'accounts'/cid/'disconnected.json')
        if marker is None:
            return False
        require(type(marker) is dict and set(marker)=={'schema','session'}
                and marker['schema']==1 and type(marker['session']) is str, 'XHS_CONNECTION_INVALID')
        return marker['session'] == row['session']

    @staticmethod
    def _binding_revision(cid, row):
        return fingerprint([cid,row['session']])

    def disconnect(self, cid, account_id, binding_revision):
        self._prepare()
        with locked(self.root/'binding.lock',nonblocking=True):
            row = self._account(cid, allow_removed=True)
            require(row['profile']['id'] == account_id, 'XHS_ACCOUNT_MISMATCH')
            require(self._binding_revision(cid,row)==binding_revision,'XHS_ACCOUNT_MISMATCH')
            directory = self.root if row['session']=='legacy' else self.root/'accounts'/cid
            with locked(directory/'account.lock',nonblocking=True):
                pending = self._pending()
                if pending and pending['state'] in {'LOGIN_PENDING','HUMAN_ACTION_REQUIRED'}:
                    require(pending['connection_id'] not in (None,cid), 'XHS_BINDING_IN_PROGRESS')
                target = container(self.root/'accounts',cid)/'disconnected.json'
                if not self._removed(cid,row):
                    atomic_write(target,{'schema':1,'session':row['session']},maximum=None)
                browser = self.browsers.pop(row['session'],None)
                if browser:
                    browser.close()
        return {'connection_id':cid,'state':'DISCONNECTED','remote_revocation':'NOT_REQUESTED'}

    def _account(self,cid,*,allow_removed=False):
        require(type(cid) is str and re.fullmatch('xhs-[0-9a-f]{24}',cid) is not None)
        row=self._connections().get(cid);require(row is not None,'XHS_ACCOUNT_MISMATCH')
        if not allow_removed:
            require(not self._removed(cid,row),'XHS_CONNECTION_DISCONNECTED')
        return row

    def _directory(self,cid):
        row=self._account(cid)
        return self.root if row['session']=='legacy' else self.root/'accounts'/cid

    def _browser(self,session):
        if session not in self.browsers:
            directory=self.root if session=='legacy' else self.root/'sessions'/session
            if session!='legacy':container(self.root/'sessions',session)
            self.browsers[session]=self.browser_factory(directory)
        return self.browsers[session]

    def overview(self):
        return [{'platform_id':'xiaohongshu','connection_id':cid,'account_id':row['profile']['id'],
            'binding_revision':self._binding_revision(cid,row),
            'state':'DISCONNECTED' if self._removed(cid,row) else 'BOUND_IDLE','presentation':{'display_name':row['profile']['name'],'avatar':None}}
            for cid,row in self._connections().items()]

    def _pending(self):
        value=read_metadata(self.root/'binding.json')
        if value is not None:
            if set(value)=={'session','connection_id','state'}:value=value|{'binding_id':value['session']}
            require(set(value)=={'session','connection_id','state','binding_id'} and re.fullmatch('[0-9a-f]{32}',value['binding_id']) and re.fullmatch('[0-9a-f]{32}',value['session'])
                and value['state'] in {'LOGIN_PENDING','HUMAN_ACTION_REQUIRED','BOUND_IDLE','CANCELLED'},'XHS_CONNECTION_INVALID')
            if value['connection_id'] is not None:self._account(value['connection_id'],allow_removed=True)
        return value

    def begin_login(self,connection_id=None):
        self._prepare()
        with locked(self.root/'binding.lock',nonblocking=True):
            pending=self._pending()
            if pending and pending['state'] in {'LOGIN_PENDING','HUMAN_ACTION_REQUIRED'}:
                require(pending['connection_id']==connection_id,'XHS_BINDING_IN_PROGRESS')
            else:
                if connection_id:
                    self._account(connection_id)
                # Keep the old browser login until the staged QR confirms the same identity.
                sid=secrets.token_hex(16)
                pending={'session':sid,'connection_id':connection_id,'state':'LOGIN_PENDING','binding_id':secrets.token_hex(16)}
                atomic_write(self.root/'binding.json',pending,maximum=None)
            result=self._browser(pending['session']).call('BEGIN')
            return {'state':result['state'],'binding_id':pending['binding_id'],'instruction':'请在已打开的独立 Chrome 官方页面扫码；验证码或风控由本人处理。'}

    def poll_login(self,binding_id):
        self._prepare()
        with locked(self.root/'binding.lock',nonblocking=True):
            pending=self._pending();require(pending is not None,'XHS_NO_PENDING_LOGIN')
            require(binding_id==pending['binding_id'],'XHS_BINDING_MISMATCH')
            if pending['state']=='BOUND_IDLE':return {'state':'BOUND_IDLE','connections':self.overview()}
            require(pending['state'] in {'LOGIN_PENDING','HUMAN_ACTION_REQUIRED'},'XHS_NO_PENDING_LOGIN')
            browser=self._browser(pending['session'])
            try:value=profile(browser.call('POLL'))
            except WCEError as error:
                if error.code in {'XHS_LOGIN_REQUIRED','XHS_HUMAN_ACTION_REQUIRED'}:
                    pending['state']='HUMAN_ACTION_REQUIRED' if error.code=='XHS_HUMAN_ACTION_REQUIRED' else 'LOGIN_PENDING'
                    atomic_write(self.root/'binding.json',pending,maximum=None)
                    return {'state':'HUMAN_ACTION_REQUIRED' if pending['state']=='HUMAN_ACTION_REQUIRED' else 'AWAITING_HUMAN_LOGIN'}
                raise
            cid='xhs-'+value['id'];target=pending['connection_id']
            require(target is None or target==cid,'XHS_ACCOUNT_MISMATCH')
            directory=container(self.root/'accounts',cid)
            with locked(directory/'account.lock',nonblocking=True):
                existing=self._connections().get(cid)
                if existing is None or self._removed(cid,existing) or target==cid:
                    atomic_write(directory/'connection.json',{'schema':2,'profile':value,'session':pending['session']},maximum=None)
                # A duplicate login must not silently overwrite an existing session.
                pending['state']='BOUND_IDLE';atomic_write(self.root/'binding.json',pending,maximum=None)
            browser.close()
            return {'state':'BOUND_IDLE','connection_id':cid,'connections':self.overview()}

    def ui(self,operation,connection_id=None,binding_id=None):
        if operation=='READ':
            pending=self._pending() if self.root.exists() else None
            from .xhs_browser import runtime
            try:runtime();available=True
            except WCEError:available=False
            return {'state':pending['state'] if pending and pending['state'] in {'LOGIN_PENDING','HUMAN_ACTION_REQUIRED'} else 'READY','binding_id':pending['binding_id'] if pending else None,'connections':self.overview(),
                'runtime_available':available,'method':'STANDARD_BROWSER_HUMAN_LOGIN','official_posting_api':False}
        if operation=='BEGIN':return self.begin_login(connection_id)
        if operation=='POLL':return self.poll_login(binding_id)
        require(operation=='CANCEL');self._prepare()
        with locked(self.root/'binding.lock',nonblocking=True):
            pending=self._pending()
            if pending:
                require(binding_id==pending['binding_id'],'XHS_BINDING_MISMATCH')
                self._browser(pending['session']).close();pending['state']='CANCELLED'
                atomic_write(self.root/'binding.json',pending,maximum=None)
            return {'state':'CANCELLED'}

    @contextmanager
    def _session(self,cid):
        row=self._account(cid);directory=self._directory(cid)
        with locked(directory/'account.lock',nonblocking=True):
            require(self._account(cid)['session']==row['session'],'XHS_ACCOUNT_MISMATCH')
            browser=self._browser(row['session'])
            try:yield row['profile'],browser,directory
            except WCEError as error:
                # Keep a real human challenge visible for its owner; don't
                # close it in finally before they can complete it.
                if error.code not in {'XHS_HUMAN_ACTION_REQUIRED','XHS_LOGIN_REQUIRED'} and not getattr(browser,'retain',False):browser.close()
                raise
            else:
                if not getattr(browser,'retain',False):browser.close()

    def read(self,cid,kind,note_id=None):
        with self._session(cid) as (account,browser,directory):
            if kind=='profile':return {'profile':profile(browser.call('PROFILE',user_id=account['id']))}
            if kind=='notes':return browser.call('NOTES',user_id=account['id'])
            require(kind=='note' and type(note_id) is str and USER.fullmatch(note_id) is not None)
            value=browser.call('NOTE',user_id=account['id'],note_id=note_id)
            require(value.get('id')==note_id and value.get('owner_id')==account['id'],'XHS_NOTE_OWNERSHIP_UNVERIFIED')
            return value

    def _path(self,cid,attempt_id):
        require(type(attempt_id) is str and ATTEMPT.fullmatch(attempt_id) is not None)
        row = self._account(cid,allow_removed=True)
        current = self.root/'accounts'/cid/'attempts'/(attempt_id+'.json')
        if row['session']=='legacy':
            return self.root/'attempts'/(attempt_id+'.json')
        if not current.exists():
            old = self.root/'attempts'/(attempt_id+'.json')
            receipt = read_metadata(old)
            if receipt is not None and receipt.get('connection_id')==cid:
                return old
        return current

    def _receipt(self,row):
        return {k:row[k] for k in ('attempt_id','connection_id','state','phase','note_id','note','error','resolution','resolution_details','media_readback') if k in row}

    def _image(self,item,directory,index):
        require(type(item) is dict and set(item)=={'absolute_path','expected_sha256'})
        p=Path(item['absolute_path'])
        require(p.is_absolute() and '..' not in p.parts and p.resolve(strict=True)==p,'XHS_SOURCE_UNSAFE')
        require(type(item['expected_sha256']) is str and re.fullmatch('[a-f0-9]{64}',item['expected_sha256']) is not None)
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            before=os.fstat(fd);require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid(),'XHS_SOURCE_UNSAFE')
            with os.fdopen(os.dup(fd),'rb') as source:header=source.read(12)
            if header.startswith(b'\x89PNG\r\n\x1a\n'):mime,ext='image/png','png'
            elif header[:3]==b'\xff\xd8\xff':mime,ext='image/jpeg','jpg'
            elif header[:4]==b'RIFF' and header[8:12]==b'WEBP':mime,ext='image/webp','webp'
            else:raise WCEError('XHS_MEDIA_FORMAT_UNSUPPORTED')
            target=directory/(str(index)+'.'+ext);hasher=sha256();os.lseek(fd,0,os.SEEK_SET)
            out=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                with os.fdopen(out,'wb',closefd=False) as sink:
                    while True:
                        block=os.read(fd,65536)
                        if not block:break
                        hasher.update(block);sink.write(block)
                    sink.flush();os.fsync(out)
            finally:os.close(out)
            after=os.fstat(fd)
            require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
                and hasher.hexdigest()==item['expected_sha256'],'XHS_SOURCE_CHANGED')
            return {'path':str(target),'mime':mime,'extension':ext,'sha256':hasher.hexdigest()}
        finally:os.close(fd)

    def publish(self,cid,attempt_id,title,body,images,topics=None,recovery_id=None):
        require(type(title) is str and bool(title.strip()) and type(body) is str and bool(body.strip()))
        require(type(images) is list and bool(images) and type(topics or []) is list)
        topics=[] if topics is None else topics
        require(all(type(t) is str and bool(t.strip()) and '\n' not in t for t in topics))
        intent={'title':title,'body':body,'images':images,'topics':topics};sig=fingerprint(intent)
        with self._session(cid) as (account,browser,directory):
            container(directory,'attempts');path=self._path(cid,attempt_id);old=read_metadata(path)
            if old is not None:
                require(old.get('signature')==sig and old.get('connection_id')==cid,'XHS_ATTEMPT_CONFLICT')
                if recovery_id is not None:
                    require(type(recovery_id) is str and ATTEMPT.fullmatch(recovery_id) is not None)
                    history=old.get('submission_recoveries',[])
                    if not any(v['recovery_id']==recovery_id for v in history):
                        # Only a new, explicitly authorized duplicate-risk
                        # recovery may reopen an UNKNOWN original submission.
                        # This ID is consumed before any side effect; repeated
                        # calls with it cannot submit a third time.
                        require(old['phase']=='SUBMIT_STARTED' and old['state'] in {'UNKNOWN','SUBMITTED_UNVERIFIED'}
                            and not old.get('note_id'),'XHS_ORIGINAL_RESULT_NOT_RETRYABLE')
                        prior={k:old[k] for k in ('phase','state','error','observation') if k in old}
                        history=history+[{'recovery_id':recovery_id,'previous':prior,'authorized_at':time.time()}]
                        old=old|{'submission_recoveries':history,'phase':'PREPARED','state':'NOT_SENT'}
                        old.pop('error',None);old.pop('observation',None)
                        atomic_write(path,old,maximum=None)
                # A timeout/unknown upload or any attempted submit is never
                # replayed. Deterministic form validation failures, however,
                # prove no submit happened: resume this same original intent.
                if old['phase']=='UPLOAD_STARTED' and old.get('error') in {
                    'XHS_FORM_CONTENT_MISMATCH','XHS_FORM_TITLE_MISMATCH','XHS_FORM_BODY_MISMATCH',
                    'XHS_PUBLIC_VISIBILITY_UNVERIFIED','XHS_PUBLISH_DISABLED','XHS_TITLE_FORM_LIMIT'}:
                    old.setdefault('preparation_history',[]).append({'phase':old['phase'],'state':old['state'],
                        'error':old['error'],'result':'CONFIRMED_NOT_SUBMITTED'})
                    old=old|{'phase':'PREPARED','state':'NOT_SENT'};old.pop('error',None)
                    atomic_write(path,old,maximum=None)
                if old['phase'] not in {'PREPARED','STAGED'}:return self._receipt(old)
                row=old
            else:
                assets=container(directory,'assets');stage=container(assets,'.stage-'+secrets.token_hex(16))
                try:
                    staged=[self._image(item,stage,i) for i,item in enumerate(images)]
                except BaseException:
                    # Only our newly allocated stage may be cleaned. Retain
                    # any old original-attempt target and all caller originals.
                    shutil.rmtree(stage);raise
                row={'schema':1,'attempt_id':attempt_id,'connection_id':cid,'signature':sig,
                    'input':intent,'images':staged,'stage':stage.name,'phase':'STAGED','state':'NOT_SENT'}
                # Persist the original stage before its rename. A crash after
                # rename can then recover this exact stage without re-upload.
                atomic_write(path,row,maximum=None)
            if row['phase']=='STAGED':
                assets=directory/'assets';stage=assets/row['stage'];target=assets/attempt_id
                require(re.fullmatch('.stage-[0-9a-f]{32}',row['stage']) is not None,'XHS_STAGED_ASSETS_INVALID')
                require(stage.exists()!=target.exists(),'XHS_STAGED_ASSETS_INVALID')
                chosen=stage if stage.exists() else target;path_check(chosen,True)
                for item in row['images']:
                    source=chosen/Path(item['path']).name;path_check(source)
                    require(sha256(source.read_bytes()).hexdigest()==item['sha256'],'XHS_SOURCE_CHANGED')
                if chosen==stage:os.rename(stage,target)
                row=row|{'images':[item|{'path':str(target/Path(item['path']).name)} for item in row['images']],
                    'phase':'PREPARED'}
                atomic_write(path,row,maximum=None)
            def event(phase,data=None):
                nonlocal row
                require((row['phase'],phase) in {('PREPARED','UPLOAD_STARTED'),('UPLOAD_STARTED','SUBMIT_STARTED')},'XHS_ATTEMPT_CONFLICT')
                row=row|{'phase':phase,'state':'UNKNOWN'}
                if phase=='SUBMIT_STARTED':browser.retain=True
                if data is not None:
                    require(type(data) is dict and set(data) in ({'before_ids','submitted_at','visibility'},{'before_ids','submitted_at','visibility','target_method'}) and data['visibility']=='PUBLIC'
                        and type(data['before_ids']) is list and all(type(v) is str and USER.fullmatch(v) for v in data['before_ids'])
                        and type(data['submitted_at']) is int,'XHS_BROWSER_PROTOCOL_INVALID')
                    if 'target_method' in data:require(data['target_method'] in {'DOM_BUTTON_NAME','BROWSER_ACCESSIBLE_BUTTON_NAME'},'XHS_BROWSER_PROTOCOL_INVALID')
                    row['observation']=data
                atomic_write(path,row,maximum=None)
            try:
                result=browser.call('PUBLISH',user_id=account['id'],title=title,body=body,topics=topics,
                    images=row['images'],on_event=event)
                row=row|{'state':result.get('state','SUBMITTED_UNVERIFIED')}
                if result.get('note_id'):browser.retain=False
                if type(result.get('observation')) is dict:row['observation']=result['observation']
                if type(result.get('note_id')) is str and USER.fullmatch(result['note_id']):row['note_id']=result['note_id']
                atomic_write(path,row,maximum=None)
            except WCEError as error:
                # Fixed error codes only; browser never supplies raw exceptions.
                row=row|{'error':error.code};atomic_write(path,row,maximum=None)
                if error.code in {'XHS_HUMAN_ACTION_REQUIRED','XHS_LOGIN_REQUIRED'}:raise
            return self._receipt(row)

    def status(self,cid,attempt_id,*,readback=False):
        if not readback:
            row = read_metadata(self._path(cid,attempt_id))
            if row is None:
                return {'state':'NOT_FOUND','attempt_id':attempt_id}
            require(row.get('connection_id')==cid,'XHS_ACCOUNT_MISMATCH')
            return self._receipt(row)
        with self._session(cid) as (account,browser,directory):
            row=read_metadata(self._path(cid,attempt_id))
            if row is None:return {'state':'NOT_FOUND','attempt_id':attempt_id}
            require(row.get('connection_id')==cid,'XHS_ACCOUNT_MISMATCH')
            if readback and not row.get('note_id') and row['phase']=='SUBMIT_STARTED':
                observed=browser.call('RESOLVE',user_id=account['id'],title=row['input']['title'],
                    body=row['input']['body'],topics=row['input']['topics'],image_count=len(row['images']),observation=row.get('observation',{}))
                if observed.get('note_id'):row['note_id']=observed['note_id']
                row['resolution']=observed.get('state','UNKNOWN')
                row['resolution_details']={k:observed[k] for k in ('candidate_count','candidate_note_ids','query_errors','mismatch_fields') if k in observed}
            if readback and row.get('note_id'):
                value=browser.call('NOTE',user_id=account['id'],note_id=row['note_id'],verify_public=True)
                expected=row['input']['body']+('\n'+' '.join('#'+t.lstrip('#') for t in row['input']['topics']) if row['input']['topics'] else '')
                require(value.get('id')==row['note_id'] and value.get('owner_id')==account['id']
                    and value.get('title')==row['input']['title'] and ' '.join(value.get('body','').replace('\u200b','').replace('\ufeff','').split())==' '.join(expected.replace('\u200b','').replace('\ufeff','').split())
                    and len(value.get('images',[]))==len(row['images']),'XHS_READBACK_MISMATCH')
                row=row|{'state':value.get('state','OWNER_READABLE'),'note':value,'media_readback':{'expected_count':len(row['images']),'observed_count':len(value['images']),'order':'DETAIL_CAROUSEL_DOM_ORDER','source_order':'ORIGINAL_FILE_INPUT_ARRAY','original_bytes_equal_claimed':False}}
                row.pop('error',None);browser.retain=False
            if readback:atomic_write(self._path(cid,attempt_id),row,maximum=None)
            return self._receipt(row)
