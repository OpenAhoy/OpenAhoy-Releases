"""One closed native visible-text projection; never HTML normalization.

Only the exact host memory-citation suffix is recognized. No path is opened,
no citation text is retained, and no marker inside metadata becomes a delivery.
"""
from hashlib import sha256
import re
from .contracts import WCEError

PROFILE='NATIVE_VISIBLE_TRAILING_MEMORY_CITATION_V1'
FIELDS=frozenset({'projection_profile','text_bytes','raw_text_sha256','raw_text_bytes',
    'metadata_suffix_sha256','metadata_suffix_bytes','terminal_variant',
    'terminal_text_sha256','terminal_text_bytes'})
_HASH=re.compile(r'[a-f0-9]{64}\Z')
_UUID=re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\Z')
_ENTRY=re.compile(r'(?P<path>[A-Za-z0-9_./-]+\.md):(?P<start>[1-9][0-9]{0,9})-'
    r'(?P<end>[1-9][0-9]{0,9})\|note=\[(?P<note>[^\[\]<>\&\r\n]+)\]\Z')
_OPEN='<oai-mem-citation>\n<citation_entries>\n'
_MIDDLE='\n</citation_entries>\n<rollout_ids>\n'
_CLOSE='</rollout_ids>\n</oai-mem-citation>'


def need(value):
    if value is not True:raise WCEError('SLOT_NATIVE_PAIR_INVALID')


def fingerprint(raw):return {'sha256':sha256(raw).hexdigest(),'bytes':len(raw)}


def validate(value,visible,raw):
    need(type(value)is dict and set(value)==FIELDS and value['projection_profile']==PROFILE
        and value['terminal_variant']=='VISIBLE_EXACT')
    for key in ('text_bytes','raw_text_bytes','metadata_suffix_bytes','terminal_text_bytes'):
        need(type(value[key])is int and value[key]>=0)
    for key in ('raw_text_sha256','metadata_suffix_sha256','terminal_text_sha256'):
        need(type(value[key])is str and _HASH.fullmatch(value[key])is not None)
    need(value['text_bytes']==visible['bytes'] and value['terminal_text_bytes']==visible['bytes']
        and value['terminal_text_sha256']==visible['sha256']
        and value['raw_text_sha256']==raw['sha256'] and value['raw_text_bytes']==raw['bytes']
        and value['metadata_suffix_bytes']>0
        and value['raw_text_bytes']==value['text_bytes']+value['metadata_suffix_bytes'])


def project(raw_text,visible):
    need(type(raw_text)is str and type(visible)is dict and set(visible)=={'sha256','bytes'}
        and type(visible['bytes'])is int and visible['bytes']>=0
        and type(visible['sha256'])is str and _HASH.fullmatch(visible['sha256'])is not None)
    try:raw=raw_text.encode('utf8',errors='strict');prefix=raw[:visible['bytes']];text=prefix.decode('utf8',errors='strict')
    except UnicodeError:raise WCEError('SLOT_NATIVE_PAIR_INVALID')from None
    need(fingerprint(prefix)==visible and len(raw)>len(prefix)
        and not any(tag in text for tag in ('<oai-mem-citation','</oai-mem-citation',
            '<citation_entries','</citation_entries','<rollout_ids','</rollout_ids')))
    suffix=raw[len(prefix):]
    try:block=suffix.decode('utf8',errors='strict')
    except UnicodeError:raise WCEError('SLOT_NATIVE_PAIR_INVALID')from None
    need(block.startswith(_OPEN) and block.endswith(_CLOSE)
        and block.count(_OPEN)==1 and block.count(_MIDDLE)==1
        and '&'not in block and 'WCE_SLOT_DELIVERY_V1'not in block)
    interior=block[len(_OPEN):-len(_CLOSE)]
    entries,rollouts=interior.split(_MIDDLE)
    entry_lines=entries.split('\n');need(bool(entries)and len(set(entry_lines))==len(entry_lines))
    for line in entry_lines:
        match=_ENTRY.fullmatch(line);need(match is not None and line.isprintable())
        path=match['path'];parts=path.split('/')
        need(not path.startswith('/') and all(part and part not in {'.','..'}for part in parts)
            and (path=='MEMORY.md' or parts[0]in {'rollout_summaries','skills'})
            and int(match['start'])<=int(match['end']))
    # The newline directly before </rollout_ids> belongs to each UUID line.
    need(rollouts=='' or rollouts.endswith('\n'))
    ids=[] if rollouts=='' else rollouts[:-1].split('\n')
    need(len(ids)==len(set(ids)) and all(_UUID.fullmatch(line)is not None for line in ids))
    value={'projection_profile':PROFILE,'text_bytes':visible['bytes'],
        'raw_text_sha256':sha256(raw).hexdigest(),'raw_text_bytes':len(raw),
        'metadata_suffix_sha256':sha256(suffix).hexdigest(),'metadata_suffix_bytes':len(suffix),
        'terminal_variant':'VISIBLE_EXACT','terminal_text_sha256':visible['sha256'],
        'terminal_text_bytes':visible['bytes']}
    validate(value,visible,fingerprint(raw));return value


def identity(fact):
    base=(fact['schema'],fact['root_turn_id'],fact['text_sha256'])
    if fact['schema']==1:return base
    need(fact['schema']==2)
    return base+tuple(fact[key]for key in sorted(FIELDS))
