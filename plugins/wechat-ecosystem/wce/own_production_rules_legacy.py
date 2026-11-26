"""Read-only compatibility for real same-account editorial preferences.

A legacy per-account value is an account override, above new global defaults.
No preferences file/lock is created and no account or document is modified.
"""
import os
from pathlib import Path
from .own_connection_policy import locked, read_registry, load_policy
from .own_connection_registry import check_member
from .own_editor_preferences import FILENAME, value
from .service import canonical, digest
from .contracts import WCEError

PREFIX='legacy-editor-'


def snapshot(connection_id, registry):
    if not connection_id:return None
    registry=Path(registry)
    with locked(registry.parent/'connections.lock',nonblocking=True,shared=True,existing=True,readonly=True):
        registered=read_registry(registry)
        path=registered['connections'].get(connection_id)
        if path is None:
            from .wechat_component_binding import configuration_account
            if configuration_account(registry,connection_id):return None
            raise WCEError('RULES_ACCOUNT_UNAVAILABLE')
        policy=load_policy(path,active=False)
        check_member(policy,revocation=False,readonly=True)
        binding=digest({'registry':str(registry),'identity':policy.data,'owner_digest':policy.value.get('owner_digest')})
        if not os.path.lexists(policy.root/FILENAME):return None
        with locked(policy.root/'editor-preferences.lock',nonblocking=True,shared=True,existing=True,readonly=True):
            result=value(policy,binding)
            if result['revision']==0:return None
            # Originality/summary choices are not converted into new QA or
            # publication gates. Preserve them untouched in their original file.
            preferences=result['preferences']
            fields={'author':preferences['author'],
                    'visual_layout':canonical({key:preferences[key] for key in ('layout_profile','cover_alignment')})}
            token=PREFIX+digest({'binding':binding,'revision':result['revision'],'preferences':preferences})
            if value(policy,binding)!=result:raise WCEError('RULES_LEGACY_CHANGED')
            return {'version_id':token,'revision':result['revision'],'fields':fields}
