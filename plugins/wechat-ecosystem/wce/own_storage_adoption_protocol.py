"""App-only storage recovery. Approval and account selection stay in local code."""
from pathlib import Path
import os
import threading

from .contracts import WCEError
from .own_connection_policy import registry_path
from .own_inline_crypto import NativeCrypto
from .own_storage_adoption import apply_reviewed, review, verify_adopted
from .own_volume_identity import ADOPTION_FILE
from .prepared_contracts import strict_validate
from .service import digest
from .tools import schema

NAME = 'wce.ui.wechat.storage_recovery'
SPEC = schema({'action': {'type': 'string', 'enum': ['inspect', 'confirm', 'status']}})


def confirm_native(checksum, appids):
    helper = NativeCrypto(storage=True)
    try:
        reply = helper.call({'operation':'storage_confirm','context':checksum,'appids':appids}, timeout=82)
    finally:
        helper.close()
    if not reply['ok']:
        raise WCEError('CONNECTION_' + reply['error'])
    if reply != {'ok': True, 'context': checksum}:
        raise WCEError('CONNECTION_RELOCATION_CONFIRMATION_INVALID')


def native_available():
    helper = NativeCrypto(storage=True)
    try:
        return helper.call({'operation':'storage_capability'}) == {'ok':True}
    finally:
        helper.close()


class AdoptionRouter:
    def __init__(self, inner, registry):
        self.inner = inner
        self.registry = Path(registry) if registry is not None else registry_path()
        self.lock = threading.Lock()
        self.result = None

    def __getattr__(self,name):
        return getattr(self.inner,name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self,value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        return [*self.inner.list_tools(), {'name':NAME, 'title':'恢复原公众号绑定',
            'description':'App-only storage recovery with macOS device-owner confirmation.',
            'inputSchema':SPEC,'outputSchema':{'type':'object'},'_meta':{'ui':{'visibility':['app']}},
            'annotations':{'readOnlyHint':False,'destructiveHint':False,'openWorldHint':False,
                           'idempotentHint':True}}]

    def call(self,name,args):
        if name != NAME:
            return self.inner.call(name,args)
        strict_validate(args,SPEC)
        action=args['action']
        with self.lock:
            if self.result is not None and (action=='status' or self.result['state']=='PENDING'):
                return dict(self.result)
            if action=='confirm':
                self.result={'state':'PENDING'}
                threading.Thread(target=self._run,daemon=True).start()
                return dict(self.result)
        return self.inspect()

    def inspect(self):
        existing = os.path.lexists(self.registry.parent / ADOPTION_FILE)
        try:
            if existing:
                verify_adopted(self.registry)
                return {'state':'COMMITTED'}
            _, _, _, appids=review(self.registry)
            if not native_available():
                return {'state':'BLOCKED','code':'CONNECTION_RECOVERY_WITNESS_UNAVAILABLE'}
            return {'state':'READY_FOR_CONFIRMATION','appids':appids}
        except (WCEError,OSError,ValueError,TypeError,KeyError) as error:
            code = getattr(error,'code','CONNECTION_RELOCATION_SOURCE_UNVERIFIED')
            if existing and code in {'CONNECTION_VOLUME_WITNESS_UNVERIFIED','INLINE_BINDING_CRYPTO_UNAVAILABLE'}:
                return {'state':'VERIFY_REQUIRED','code':code}
            return {'state':'BLOCKED','code':code}

    def _run(self):
        try:
            if not os.path.lexists(self.registry.parent / ADOPTION_FILE):
                proposed=review(self.registry)
                if not native_available():
                    raise WCEError('CONNECTION_RECOVERY_WITNESS_UNAVAILABLE')
                confirm_native(digest(proposed[0]),proposed[3])
                apply_reviewed(self.registry,proposed)
            verify_adopted(self.registry)
            outcome={'state':'COMMITTED'}
        except (WCEError,OSError,ValueError,TypeError,KeyError) as error:
            state='RESULT_UNKNOWN' if os.path.lexists(self.registry.parent/ADOPTION_FILE) else 'BLOCKED'
            code=getattr(error,'code','CONNECTION_RELOCATION_SOURCE_UNVERIFIED')
            if state=='RESULT_UNKNOWN' and code in {'CONNECTION_VOLUME_WITNESS_UNVERIFIED','INLINE_BINDING_CRYPTO_UNAVAILABLE'}:
                state='VERIFY_REQUIRED'
            outcome={'state':state,'code':code}
        finally:
            with self.lock:
                self.result=outcome if 'outcome' in locals() else {'state':'RESULT_UNKNOWN'}
