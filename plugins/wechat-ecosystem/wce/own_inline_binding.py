"""App-only encrypted ADD. Original enrollment remains the authority/journal."""
from contextlib import ExitStack
from hashlib import sha256
import os
from pathlib import Path
import re
import secrets
import threading
import time

from .contracts import WCEError
from .tools import schema
from .own_bootstrap_security import path_check, CheckedTokenRejected
from .own_connection_policy import registry_path, locked
from .own_connection_registry import (APPID, OWNER, container, metadata, prepare_default_registry,
    write, digest, snapshot, check_snapshot)
from .own_connection_enrollment import exclusive
from .own_enrollment_checked import (propose_checked, enroll_checked, validate_record,
    resume_checked_publication, prepare_revalidation)

HANDLE={'type':'string','pattern':'^[a-f0-9]{64}$'}
ID={'type':'string','pattern':'^wx[a-fA-F0-9]{16}$'}
# Public protocol fixture only. This value is never an enrollment credential.
CHANNEL_APPID='wx0000000000000000'
CHANNEL_CANARY='OPENAHOY_PUBLIC_CHANNEL_CHECK_V1'
CHANNEL_TTL=120
BINDING_SPECS={
 'REBIND_BEGIN':schema({'view':HANDLE,'connection_id':{'type':'string','minLength':1},
                       'appid':ID,'binding_revision':HANDLE}),
 'REBIND_SUBMIT':schema({'view':HANDLE,'operation':HANDLE,'jwe':{'type':'string','minLength':1,'maxLength':16384}}),
 'REBIND_STATUS':schema({'view':HANDLE,'operation':HANDLE}),
 'REBIND_CANCEL':schema({'view':HANDLE,'operation':HANDLE}),
 'BINDING_CHECK':schema({'view':HANDLE},{'jwe':{'type':'string','minLength':1,'maxLength':16384}}),
 'BINDING_BEGIN':schema({'view':HANDLE,'appid':ID},{'label':{'type':'string','maxLength':64},
    'revalidate_unknown':{'type':'boolean'}}),
 'BINDING_SUBMIT':schema({'view':HANDLE,'operation':HANDLE,'jwe':{'type':'string','minLength':1,'maxLength':16384}}),
 'BINDING_STATUS':schema({'view':HANDLE,'operation':HANDLE}),
 'BINDING_CANCEL':schema({'view':HANDLE,'operation':HANDLE}),
 'BINDING_RESUME':schema({'view':HANDLE,'operation':HANDLE}),
}
from .own_binding_failure import JOURNAL_ERRORS as SAFE_ERRORS, failure_diagnostic, valid_failure, _error

def _hash(value):return sha256(value.encode()).hexdigest()


class InlineBinding:
    def __init__(self, registry=None, *, crypto_factory=None, enrollment=enroll_checked):
        self.default=registry is None
        self.registry=Path(registry) if registry is not None else registry_path()
        self.crypto_factory=crypto_factory
        self.enrollment=enrollment
        self.crypto=None;self.views={};self.challenges={};self.lock=threading.RLock();self.closed=False

    def open(self):
        with self.lock:
            if self.closed:raise WCEError('INLINE_BINDING_VIEW_CLOSED')
            view=secrets.token_hex(32)
            self.views[_hash(view)]={'registry':str(self.registry),'pin':None}
            pending=[];pending_unavailable=False
            directory=self.registry.parent/'inline-bindings'
            if os.path.lexists(directory):
                path_check(directory,True)
                for path in sorted(directory.glob('wx*.json')):
                    try:row=self._read(path)
                    except (WCEError,OSError,ValueError):pending_unavailable=True;continue
                    if row is None:continue
                    # Public metadata only. Don't adopt another view, reconnect,
                    # read credentials or prepare a new validation on open.
                    try:state=self._observe(path,row)
                    except (WCEError,OSError):pending_unavailable=True;continue
                    if state in {'READY','CANCELLED'}:
                        try:
                            _,record=self._pending(row)
                            if record is not None and record['attempts'][-1]['state']=='NOT_SENT':state='NOT_SENT'
                        except WCEError:pass
                    if state in {'UNKNOWN','NOT_SENT','STORED','STORAGE_UNKNOWN','IP_DENIED'}:
                        pending.append({'appid':row['appid'],'label':row['label'],'state':state})
            return {'state':'INLINE_BINDING_VIEW','view':view,'pending_bindings':pending,
                'pending_unavailable':pending_unavailable}

    def _view(self, view):
        if self.closed or type(view) is not str or re.fullmatch('[a-f0-9]{64}',view) is None or _hash(view) not in self.views:
            raise WCEError('INLINE_BINDING_VIEW_MISMATCH')
        value=self.views[_hash(view)]
        if value['registry']!=str(self.registry):raise WCEError('INLINE_BINDING_VIEW_MISMATCH')
        if value['pin'] is not None and list(path_check(self.registry.parent,True))!=value['pin']:
            raise WCEError('INLINE_BINDING_OWNER_CHANGED')
        return value

    def _directory(self, view):
        v=self._view(view)
        if self.default:prepare_default_registry()
        pin=list(path_check(self.registry.parent,True))
        if v['pin'] is None:v['pin']=pin
        if pin!=v['pin']:raise WCEError('INLINE_BINDING_OWNER_CHANGED')
        return container(self.registry.parent,'inline-bindings')

    def _crypto(self):
        if self.crypto is None or getattr(self.crypto,'closed',False):
            from .own_inline_crypto import NativeCrypto
            self.crypto=(self.crypto_factory or NativeCrypto)()
        return self.crypto

    @staticmethod
    def _close_probe(probe):
        timer=probe.pop('timer',None)
        if timer:timer.cancel()
        crypto=probe.get('crypto')
        probe['crypto']=None;probe['challenge']=None
        if crypto:crypto.close()

    def _expire_probe(self,key,probe):
        with self.lock:
            # A one-shot owner cleanup, not a connection or global health job.
            if self.views.get(key,{}).get('probe') is probe:
                self._close_probe(probe)

    def channel_check(self,view,jwe=None):
        """Same seal/pipe round trip, with fixed public data and no account IO.

        This is not a binding, capability grant or health gate for other tools.
        Only a mounted binding form calls it before accepting user input.
        """
        with self.lock:
            value=self._view(view)
            probe=value.get('probe')
            if jwe is not None and (type(jwe) is not str or not 0<len(jwe)<=16384):
                raise WCEError('INLINE_BINDING_INVALID_REQUEST')
            if jwe is None and probe is None:
                from .own_inline_crypto import NativeCrypto
                crypto=(self.crypto_factory or NativeCrypto)()
                try:challenge=crypto.begin(CHANNEL_APPID)
                except BaseException:
                    crypto.close();raise
                # Probe transport faults cannot destroy a real binding's key.
                probe={'crypto':crypto,'challenge':challenge,
                       'created':time.monotonic(),'envelope':None}
                value['probe']=probe
                timer=threading.Timer(CHANNEL_TTL,self._expire_probe,args=(_hash(view),probe))
                timer.daemon=True;probe['timer']=timer
                try:timer.start()
                except BaseException:
                    self._close_probe(probe);raise
            if probe is None:raise WCEError('INLINE_BINDING_KEY_EXPIRED')
            if probe['envelope'] is not None:
                if jwe is not None and probe['envelope']!=_hash(jwe):raise WCEError('INLINE_BINDING_ENVELOPE_REJECTED')
                return {'state':'BINDING_CHANNEL_VERIFIED','envelope_sha256':probe['envelope']}
            if probe['challenge'] is None or time.monotonic()-probe['created']>CHANNEL_TTL:
                self._close_probe(probe)
                raise WCEError('INLINE_BINDING_KEY_EXPIRED')
            if jwe is None:
                return {'state':'BINDING_CHANNEL_READY','challenge':dict(probe['challenge'])}
            envelope=_hash(jwe)
            secret=None
            try:
                appid,secret=probe['crypto'].decrypt(probe['challenge'],jwe)
                if appid!=CHANNEL_APPID or not secrets.compare_digest(secret.reveal_for_adapter(),CHANNEL_CANARY):
                    raise WCEError('INLINE_BINDING_ENVELOPE_REJECTED')
            finally:
                secret=None;self._close_probe(probe)
            probe['envelope']=envelope
            return {'state':'BINDING_CHANNEL_VERIFIED','envelope_sha256':envelope}

    def _read(self, path):
        value=metadata(path)
        if value is None:return None
        fields={'schema','operation','appid','label','view','parent','owner','transaction','root','state','cancelled','error','ip','revision'}
        if (type(value) is not dict or set(value)!=fields or value['schema']!=1
                or type(value['operation']) is not str or re.fullmatch('[a-f0-9]{64}',value['operation']) is None
                or type(value['appid']) is not str or APPID.fullmatch(value['appid']) is None
                or path.name!=value['appid']+'.json' or type(value['revision']) is not int
                or value['revision']<1 or type(value['cancelled']) is not bool
                or value['parent']!=list(path_check(path.parent,True))):
            raise WCEError('INLINE_BINDING_JOURNAL_HOLD')
        if (type(value['label']) is not str or not 1<=len(value['label'])<=64
                or type(value['view']) is not str or re.fullmatch('[a-f0-9]{64}',value['view']) is None
                or type(value['owner']) is not str or re.fullmatch('[a-f0-9]{64}',value['owner']) is None
                or type(value['transaction']) is not str or re.fullmatch('txn-[a-f0-9]{32}',value['transaction']) is None
                or type(value['state']) is not str or value['state'] not in {'READY','CANCELLED','ADMITTED'}
                or (value['error'] is not None and type(value['error']) is not str)
                or value['error'] not in SAFE_ERRORS|{None,'INLINE_BINDING_RESULT_UNDETERMINED'}
                or type(value['root']) is not str or Path(value['root']).parent!=self.registry.parent/'accounts'
                or re.fullmatch('[a-f0-9]{24}',Path(value['root']).name) is None
                or value['ip'] is not None and (type(value['ip']) is not str or len(value['ip'])>64)):
            raise WCEError('INLINE_BINDING_JOURNAL_HOLD')
        owner=metadata(self.registry.parent/OWNER)
        if owner is not None and value['owner']!=digest(owner):raise WCEError('INLINE_BINDING_OWNER_CHANGED')
        return value

    def _write(self,path,old,new):
        if self._read(path)!=old:raise WCEError('INLINE_BINDING_JOURNAL_CHANGED')
        if old is None:exclusive(path,new,list(path_check(path.parent,True)))
        else:write(path,new,list(path_check(path.parent,True)))
        if self._read(path)!=new:raise WCEError('INLINE_BINDING_JOURNAL_CHANGED')

    def _owned(self,view,operation):
        directory=self._directory(view)
        # Operation is opaque but never used as a caller-controlled path.
        if type(operation) is not str or re.fullmatch('[a-f0-9]{64}',operation) is None:
            raise WCEError('INLINE_BINDING_INVALID_REQUEST')
        for path in directory.glob('wx*.json'):
            row=self._read(path)
            if row and row['operation']==operation:
                if row['view']!=_hash(view):raise WCEError('INLINE_BINDING_VIEW_MISMATCH')
                return path,row
        raise WCEError('INLINE_BINDING_OPERATION_NOT_FOUND')

    def _pending(self,row):
        path=self.registry.parent/'connection-enrollments'/(row['appid']+'.json')
        value=metadata(path)
        if value is None:return path,None
        validate_record(value)
        current=value['attempts'][-1]['review']
        predecessor=(value['schema']==3 and len(value['attempts'])>1
            and value['attempts'][-1]['state']=='NOT_SENT'
            and current.get('continuation',{}).get('mode')=='NEW_VALIDATION'
            and value['attempts'][-2]['review']['transaction']==row['transaction'])
        if ((current['transaction']!=row['transaction'] and not predecessor) or current['base']['registry']!=str(self.registry)
                or value['identity']['appid']!=row['appid'] or value['identity']['private_directory']!=row['root']
                or digest(current['base']['owner'])!=row['owner']):
            raise WCEError('INLINE_BINDING_JOURNAL_CHANGED')
        return path,value

    def _observe(self,path,row):
        if row['state'] in {'READY','CANCELLED'}:return row['state']
        try:
            with locked(path.with_suffix('.run.lock'),nonblocking=True):pass
        except WCEError as error:
            if error.code=='CONNECTION_BUSY':return 'IN_PROGRESS'
            raise
        try:
            _,pending=self._pending(row)
            if pending is None:
                return 'UNKNOWN' if os.path.lexists(row['root']) else 'NOT_SENT'
            return {'NOT_SENT':'NOT_SENT','SPENT_RESULT_UNKNOWN':'UNKNOWN','REJECTED_IP':'IP_DENIED',
                    'VALIDATED':'STORAGE_UNKNOWN','STORED':'STORED','COMMITTED':'COMMITTED'}[pending['attempts'][-1]['state']]
        except Exception:return 'UNKNOWN'

    def _status(self,path,row):
        state=self._observe(path,row)
        result={'state':state,'operation':row['operation'],'appid':row['appid'],'cancel_requested':row['cancelled']}
        if row['error']:result['error']=row['error']
        try:
            _,original=self._pending(row)
            if original is not None:
                result['validation_attempts']=len(original['attempts'])
                result['credential_stored']=original['attempts'][-1]['credential']=='STORED'
                result['binding_committed']=original['attempts'][-1]['binding']=='COMMITTED'
                # An indication only; BEGIN rechecks full pins/current registry
                # while actually holding the run/setup locks before appending.
                result['can_revalidate']=(state=='UNKNOWN' and
                    original['attempts'][-1]['state']=='SPENT_RESULT_UNKNOWN')
        except Exception:pass
        # Separate diagnostic carrier leaves the authority journal and old
        # readers byte/schema compatible. Missing/invalid diagnostics never
        # change the original binding state or permit another token request.
        try:
            saved=metadata(path.parent/'diagnostics'/path.name)
            if (row['error'] is not None and state in {'UNKNOWN','STORAGE_UNKNOWN','IP_DENIED'}
                    and type(saved) is dict and set(saved)=={'schema','operation_sha256','transaction_sha256','failure'}
                    and saved['schema']==1 and saved['operation_sha256']==_hash(row['operation'])
                    and saved['transaction_sha256']==_hash(row['transaction'])
                    and valid_failure(saved['failure'])):
                result['diagnostic']=saved['failure']
        except Exception:pass
        if state=='IP_DENIED' and row['ip']:result['observed_ip']=row['ip']
        if state=='COMMITTED':
            _,record=self._pending(row);cid=record['identity']['connection_id']
            result.update(binding_result='COMMITTED', connection_id=cid)
            try:
                # This status path only reads membership and an existing broker;
                # it cannot start a broker, read Keychain or reconnect an account.
                from .own_connection_tools import status
                result['state']=status(cid,self.registry)['state']
            except (WCEError,OSError,EOFError):result['state']='ACTION_REQUIRED'
        return result

    def rebind_begin(self, view, connection_id, appid, binding_revision):
        from .own_connection_policy import resolve
        with self.lock:
            panel = self._view(view)
            previous = panel.get('rebind')
            if previous and previous['state'] in {'READY','IN_PROGRESS','UNKNOWN'}:
                raise WCEError('INLINE_BINDING_BUSY')
            policy = resolve(connection_id,self.registry,active=False)
            policy.check(readonly=True)
            if policy.data['appid'] != appid or policy.fingerprint != binding_revision:
                raise WCEError('CONNECTION_POLICY_CHANGED')
            challenge=self._crypto().begin(appid)
            operation=secrets.token_hex(32)
            panel['rebind']={'operation':operation,'policy':policy,'challenge':challenge,
                             'state':'READY','created':time.monotonic()}
            return {'operation':operation,'challenge':challenge,'state':'READY'}

    def _rebind(self, view, operation):
        item=self._view(view).get('rebind')
        if item is None or item['operation']!=operation:
            raise WCEError('INLINE_BINDING_OPERATION_NOT_FOUND')
        return item

    def rebind_status(self, view, operation):
        with self.lock:
            item=self._rebind(view,operation)
            return {'state':item['state'],'operation':operation,
                    'connection_id':item['policy'].data['connection_id']}

    def rebind_cancel(self, view, operation):
        with self.lock:
            item=self._rebind(view,operation)
            if item['state'] in {'READY','IN_PROGRESS'}:
                if item['state']=='READY':
                    try: self.crypto.cancel(item['challenge'])
                    except WCEError: pass
                item['state']='CANCELLED'
            return self.rebind_status(view,operation)

    def rebind_submit(self, view, operation, jwe):
        with self.lock:
            item=self._rebind(view,operation)
            if item['state']!='READY':
                return self.rebind_status(view,operation)
            if time.monotonic()-item['created']>120:
                self.rebind_cancel(view,operation)
                return self.rebind_status(view,operation)
            challenge=item.pop('challenge')
            item['state']='REJECTED'
            appid,secret=self.crypto.decrypt(challenge,jwe)
            if appid!=item['policy'].data['appid']:
                item['state']='REJECTED'
                raise WCEError('INLINE_BINDING_ENVELOPE_REJECTED')
            if not item['policy'].value['enabled']:
                raise WCEError('CONNECTION_DISCONNECTED')
            item['state']='IN_PROGRESS'
            threading.Thread(target=self._reauthorize,args=(item,secret),
                             daemon=True,name='openahoy-rebind').start()
            return self.rebind_status(view,operation)

    def _reauthorize(self,item,secret):
        from .own_bootstrap_security import acquire_checked
        from .own_keychain import KeychainCredential
        policy=item['policy']
        replacing=False
        try:
            with ExitStack() as locks:
                for path in (self.registry.parent/'connection-setup.lock',policy.root/'connection-start.lock',
                             policy.root/'connection.lock',policy.root/'connection-policy.lock'):
                    locks.enter_context(locked(path,nonblocking=True))
                policy.check(readonly=True)
                with self.lock:
                    if self.closed or item['state']!='IN_PROGRESS':
                        return
                acquire_checked(policy.data['appid'],secret.reveal_for_adapter())
                with self.lock:
                    if self.closed or item['state']!='IN_PROGRESS':
                        return
                    policy.check(readonly=True)
                    replacing=True
                    KeychainCredential(policy).replace(secret.reveal_for_adapter())
                    item['state']='BOUND_IDLE'
        except Exception:
            with self.lock:
                if item['state']=='IN_PROGRESS':
                    item['state']='UNKNOWN' if replacing else 'REJECTED'

    def begin(self,view,appid,label='',revalidate_unknown=False):
        with self.lock:
            if type(revalidate_unknown) is not bool:raise WCEError('INLINE_BINDING_INVALID_REQUEST')
            directory=self._directory(view)
            if type(appid) is not str or APPID.fullmatch(appid) is None:raise WCEError('CONNECTION_INVALID_APPID')
            appid=appid.lower()
            if type(label) is not str:raise WCEError('CONNECTION_INVALID_LABEL')
            label=label.strip() or '未命名公众号 · '+appid[-8:]
            current=snapshot(self.registry)
            for old_policy in current['policies'].values():
                identity=old_policy['value']['identity']
                if identity['appid'].lower()==appid:
                    return {'state':'ALREADY_BOUND','appid':appid,'connection_id':identity['connection_id']}
            path=directory/(appid+'.json')
            with locked(path.with_suffix('.lock'),nonblocking=True), ExitStack() as pending_locks:
                old=self._read(path)
                proposed=None
                if old:
                    state=self._observe(path,old)
                    # Only this explicit UI action may take ownership for read-only recovery.
                    if state=='IN_PROGRESS' and old['view']!=_hash(view):
                        raise WCEError('INLINE_BINDING_BUSY')
                    if revalidate_unknown:
                        if state!='UNKNOWN':raise WCEError('INLINE_BINDING_INVALID_REQUEST')
                        pending_locks.enter_context(locked(path.with_suffix('.run.lock'),nonblocking=True))
                        self._pending(old)
                        proposed=prepare_revalidation(appid,self.registry)
                        state='NOT_SENT'
                    row=old|{'view':_hash(view),'revision':old['revision']+1}
                    if state not in {'READY','CANCELLED','NOT_SENT','IP_DENIED'}:
                        self._write(path,old,row);return self._status(path,row)
                    if proposed is None and state in {'READY','CANCELLED','NOT_SENT'}:
                        _,record=self._pending(old)
                        if record is not None:
                            if record['attempts'][-1]['state']!='NOT_SENT':
                                raise WCEError('INLINE_BINDING_JOURNAL_HOLD')
                            proposed=record['attempts'][-1]['review']
                elif revalidate_unknown:raise WCEError('INLINE_BINDING_OPERATION_NOT_FOUND')
                if proposed is None:
                    proposed=propose_checked(appid,label,self.registry)
                proposed['preserve_existing']=True
                check_snapshot(proposed['base'])
                self._crypto()
                prior=self.challenges.pop(_hash(view),None)
                if prior:
                    try:self.crypto.cancel(prior['challenge'])
                    except WCEError:pass
                challenge=self.crypto.begin(appid)
                row={'schema':1,'operation':old['operation'] if old else secrets.token_hex(32),
                    'appid':appid,'label':proposed['label'],'view':_hash(view),
                    'parent':list(path_check(directory,True)),'owner':digest(proposed['base']['owner']),
                    'transaction':proposed['transaction'],'root':proposed['identity']['private_directory'],
                    'state':'READY','cancelled':False,'error':None,'ip':None,'revision':old['revision']+1 if old else 1}
                self._write(path,old,row)
                self.challenges[_hash(view)]={'challenge':challenge,'proposed':proposed,'operation':row['operation'],
                    'created':time.monotonic(),'path':path}
                return {'state':'READY','operation':row['operation'],'challenge':challenge}

    def submit(self,view,operation,jwe):
        with self.lock:
            path,row=self._owned(view,operation)
            with locked(path.with_suffix('.lock'),nonblocking=True):
                if row['state']!='READY':return self._status(path,row)
                item=self.challenges.get(_hash(view))
                if not item or item['operation']!=operation or time.monotonic()-item['created']>120:
                    raise WCEError('INLINE_BINDING_KEY_EXPIRED')
                if type(jwe) is not str or not 0<len(jwe)<=16384:raise WCEError('INLINE_BINDING_INVALID_REQUEST')
                appid,secret=self.crypto.decrypt(item['challenge'],jwe)
                if appid!=row['appid']:raise WCEError('INLINE_BINDING_ENVELOPE_REJECTED')
                self.challenges.pop(_hash(view),None)
                retained=ExitStack()
                try:
                    retained.enter_context(locked(path.with_suffix('.run.lock'),nonblocking=True))
                    updated=row|{'state':'ADMITTED','revision':row['revision']+1}
                    self._write(path,row,updated)
                    worker=threading.Thread(target=self._execute,args=(path,updated,item['proposed'],secret,retained),daemon=True,name='openahoy-bind')
                    worker.start()
                except BaseException:
                    retained.close();secret=None;raise
                return {'state':'IN_PROGRESS','operation':operation,'appid':appid}

    def _execute(self,path,row,proposed,secret,retained):
        error=None;ip=None;failure=None
        def guard():
            with self.lock:
                current=self._read(path)
                if self.closed or current['operation']!=row['operation'] or current['cancelled']:
                    raise WCEError('INLINE_BINDING_CANCELLED')
        try:
            pending=metadata(self.registry.parent/'connection-enrollments'/(row['appid']+'.json'))
            resume=bool(pending and pending.get('schema') in {2,3} and pending['attempts'][-1]['state']=='NOT_SENT')
            policy,cached,held,_=self.enrollment(proposed,secret.reveal_for_adapter,guard=guard,resume_not_sent=resume)
            try:policy.check()
            finally:cached=None;held.close()
        except Exception as exception:
            error=_error(exception)
            failure=failure_diagnostic(exception)
            if type(exception) is CheckedTokenRejected and exception.code=='BOOTSTRAP_TOKEN_IP_DENIED' and exception.proof is not None:
                ip=exception.observed_ip
        finally:
            secret=None
            if failure is not None:
                # The outer RPC already returned IN_PROGRESS. Feed this closed
                # worker event into the existing opt-in feedback snapshot too.
                try:
                    from .support_diagnostics import Diagnostics
                    Diagnostics(self.registry.parent/'diagnostics').emit('binding','VALIDATION','UNKNOWN',
                        tool='wce.ui.platform.action',code=failure['reason'],site=failure['site'])
                except Exception:pass
            try:
                with self.lock,locked(path.with_suffix('.lock'),nonblocking=True):
                    current=self._read(path)
                    self._write(path,current,current|{'error':error,'ip':ip,'revision':current['revision']+1})
                    if failure is not None:
                        directory=container(path.parent,'diagnostics')
                        write(directory/path.name,{'schema':1,'operation_sha256':_hash(row['operation']),
                            'transaction_sha256':_hash(row['transaction']),
                            'failure':failure},list(path_check(directory,True)))
            except Exception:pass # Original checked-enrollment journal remains authoritative.
            retained.close()

    def status(self,view,operation):
        with self.lock:
            path,row=self._owned(view,operation);return self._status(path,row)

    def cancel(self,view,operation):
        with self.lock:
            if operation==view:
                # A form without an enrollment intent cancels only its view.
                # In particular this cannot cancel or create an account task.
                value=self._view(view);probe=value.get('probe')
                if probe:self._close_probe(probe)
                # BEGIN may have created READY before its reply reaches the UI.
                # Retain this view for the subsequent correlated cancel/status.
                pending=self.challenges.get(_hash(view))
                if pending:return self.cancel(view,pending['operation'])
                self.views.pop(_hash(view),None)
                return {'state':'CANCELLED'}
            path,row=self._owned(view,operation)
            with locked(path.with_suffix('.lock'),nonblocking=True):
                current=row|{'cancelled':True,'revision':row['revision']+1}
                if row['state']=='READY':current['state']='CANCELLED'
                self._write(path,row,current)
                challenge=self.challenges.pop(_hash(view),None)
                if challenge and self.crypto:
                    try:self.crypto.cancel(challenge['challenge'])
                    except WCEError:pass
                return self._status(path,current)

    def resume(self,view,operation):
        with self.lock:
            path,row=self._owned(view,operation)
            if self._observe(path,row)!='STORED':return self._status(path,row)
            pending,record=self._pending(row)
            # Explicit completion of the original local metadata operation; no token request.
            result=resume_checked_publication(pending,record,self.registry)
            if result=='ROLLED_BACK':return {'state':'ROLLED_BACK','operation':operation,'appid':row['appid']}
            return self._status(path,self._read(path))

    def close(self):
        with self.lock:
            self.closed=True
            if self.crypto:self.crypto.close()
            for value in self.views.values():
                if value.get('probe'):self._close_probe(value['probe'])
            self.challenges.clear();self.views.clear()
