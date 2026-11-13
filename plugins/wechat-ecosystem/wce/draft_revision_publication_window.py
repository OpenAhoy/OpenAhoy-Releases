"""Bind the exact observed publication USER window; this grants nothing."""
from .contracts import WCEError
from .draft_revision_native_source import registration_digest

def hold():raise WCEError('CURRENT_REVISION_PUBLICATION_SOURCE_HOLD')

def _pin(pin):
    return (pin.thread_id,pin.turn_id,pin.message_id,pin.text_sha256,pin.purpose)

def require_authorization_window(adapter,authority):
    from .draft_revision_input import RevisionInputAdapter
    from .draft_revision_source_observer import SourceWindow,HumanPin
    from .current_publication_source import Authorization,_SEAL
    from .publication_contract import binding
    if type(adapter) is not RevisionInputAdapter or type(authority) is not Authorization:hold()
    if (getattr(authority,'_seal',None) is not _SEAL or authority.policy is not adapter.service.policy
            or authority.policy_binding!=binding(authority.policy.data)
            or authority.connection_id!=authority.policy.data['connection_id']
            or type(authority.window) is not SourceWindow):hold()
    target=authority.window
    if (type(target.pins) is not tuple or not 1<=len(target.pins)<=4
            or any(type(p) is not HumanPin or p.purpose!='current_inventory_publication' for p in target.pins)):
        hold()
    authority.fence()
    expected=sorted(_pin(pin) for pin in target.pins)
    if len(set(expected))!=len(expected):hold()
    from .draft_revision_source_views import validate_direct_windows,RELATION
    relation=validate_direct_windows(adapter.windows)
    if relation==RELATION:
        window=adapter.windows[1]
    else:
        candidates=[]
        for candidate in adapter.windows:
            publication=[pin for pin in candidate.pins if pin.purpose=='current_inventory_publication']
            if publication:candidates.append(candidate)
        if len(candidates)!=1:hold()
        window=candidates[0]
    actual=tuple(_pin(pin) for pin in window.pins)
    target_pins=tuple(_pin(pin) for pin in target.pins)
    if (registration_digest(window.source)!=registration_digest(target.source)
            or (actual!=target_pins if relation==RELATION else sorted(actual)!=sorted(target_pins))):
        hold()
    authority.fence()
    return True
