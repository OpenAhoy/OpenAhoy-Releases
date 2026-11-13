"""Private deterministic per-key journal deltas; no authority or I/O."""
from copy import deepcopy

from .contracts import WCEError


def _hold():
    raise WCEError('CONTINUATION_HISTORY_HOLD')


def changes(before, after):
    """Keep changed map members only; never serialize an entire growing map."""
    if type(before) is not dict or type(after) is not dict or not set(before) <= set(after):
        _hold()
    if any(type(field) is not str for field in after):
        _hold()
    result = []
    for field in sorted(after):
        if field == 'targets':
            continue
        if field not in before:
            result.append({'field':field, 'key':None, 'old_present':False,
                           'old':None, 'new':deepcopy(after[field])})
            continue
        old, new = before[field], after[field]
        if old == new:
            continue
        if type(old) is dict and type(new) is dict:
            if any(type(key) is not str for key in new) or not set(old) <= set(new):
                _hold()
            for key in sorted(new):
                if type(key) is not str:
                    _hold()
                if key not in old or old[key] != new[key]:
                    result.append({'field':field, 'key':key,
                                   'old_present':key in old,
                                   'old':deepcopy(old.get(key)),
                                   'new':deepcopy(new[key])})
        else:
            result.append({'field':field, 'key':None, 'old_present':True,
                           'old':deepcopy(old), 'new':deepcopy(new)})
    return result


def apply(before, delta):
    if type(before) is not dict or type(delta) is not list:
        _hold()
    value = deepcopy(before)
    seen = set()
    for entry in delta:
        if type(entry) is not dict or set(entry) != {'field','key','old_present','old','new'}:
            _hold()
        field, key = entry['field'], entry['key']
        if type(field) is not str or field == 'targets' or type(entry['old_present']) is not bool:
            _hold()
        if key is not None and type(key) is not str:
            _hold()
        if (field, key) in seen:
            _hold()
        seen.add((field, key))
        if key is None:
            if ((field in value) != entry['old_present']
                    or value.get(field) != entry['old']):
                _hold()
            value[field] = deepcopy(entry['new'])
        else:
            if type(key) is not str or type(value[field]) is not dict:
                _hold()
            if (key in value[field]) != entry['old_present'] or value[field].get(key) != entry['old']:
                _hold()
            value[field][key] = deepcopy(entry['new'])
    return value
