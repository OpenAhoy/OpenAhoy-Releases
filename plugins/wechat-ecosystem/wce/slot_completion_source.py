"""Read an actual registered producer final completion; no caller done flag."""
from dataclasses import dataclass
from hashlib import sha256
import json,re
from .draft_revision_native_source import require,canonical,checked_guard
from .slot_native_evidence import completion_text
from .slot_producer_roles import ProducerRole

HEADER='WCE_SLOT_DELIVERY_V1\n'
_HASH=re.compile('[a-f0-9]{64}\\Z')
_SEAL=object()

@dataclass(frozen=True)
class CompletedDeclaration:
    value:dict
    fact:dict
    role:object
    text_sha256:str
    _revalidate:object
    _seal:object
    def __post_init__(self):require(self._seal is _SEAL,'SLOT_UNCHECKED_COMPLETION')
    def fence(self):self._revalidate();return True


def declaration(role,fact,guard):
    require(type(role)is ProducerRole,'SLOT_UNCHECKED_ROLE');role.fence()
    text=completion_text(role.lookup,fact,guard)
    require(text.count(HEADER)==1,'SLOT_COMPLETION_BLOCK_MISSING')
    prefix,raw=text.split(HEADER)
    # The completion is the final independently structured block. Surrounding
    # production prose is data and cannot change its closed fields.
    def pairs(items):
        out={}
        for key,value in items:require(key not in out,'SLOT_COMPLETION_JSON_INVALID');out[key]=value
        return out
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:require(False,'SLOT_COMPLETION_JSON_INVALID'))
    require(type(value)is dict and set(value)=={'schema','connection_id','day','slot','schedule_id','state','groups','production_qa'}
        and value['schema']==1 and value['state']=='COMPLETE'
        and value['connection_id']in role.value['connections'] and value['slot']in role.value['slots']
        and value['schedule_id']==role.value['schedule_id'] and type(value['day'])is str,
        'SLOT_COMPLETION_SCOPE_INVALID')
    from datetime import date
    require(date.fromisoformat(value['day']).isoformat()==value['day'],'SLOT_COMPLETION_SCOPE_INVALID')
    require(fact['terminal_ordinal']>=role.value['activation']['after_ordinal']
        and type(value['groups'])is list and value['groups'],'SLOT_COMPLETION_PRECEDES_ROLE')
    qa=value['production_qa'];require(type(qa)is dict and set(qa)=={'state','evidence_sha256'}
        and qa['state']=='PASS'and type(qa['evidence_sha256'])is str and _HASH.fullmatch(qa['evidence_sha256']),
        'SLOT_PRODUCTION_QA_MISSING')
    refs=set()
    for position,group in enumerate(value['groups']):
        require(type(group)is dict and set(group)=={'group_index','save_request_key','bundle_id','version','content_digest','articles'}
            and type(group['group_index'])is int and group['group_index']==position
            and all(type(group[k])is str and group[k] for k in ('save_request_key','bundle_id','version'))
            and type(group['content_digest'])is str and _HASH.fullmatch(group['content_digest'])
            and group['save_request_key']not in refs and type(group['articles'])is list and 1<=len(group['articles'])<=8,
            'SLOT_COMPLETION_GROUP_INVALID')
        refs.add(group['save_request_key']);articles=set()
        for member in group['articles']:
            require(type(member)is dict and set(member)=={'article_id','article_sha256','source_html_sha256'}
                and type(member['article_id'])is str and member['article_id']not in articles
                and type(member['article_sha256'])is str and _HASH.fullmatch(member['article_sha256'])
                and (member['source_html_sha256']is None or type(member['source_html_sha256'])is str
                    and _HASH.fullmatch(member['source_html_sha256'])),'SLOT_COMPLETION_MEMBER_INVALID')
            articles.add(member['article_id'])
    checksum=sha256(text.encode()).hexdigest()
    def check():
        role.fence();checked_guard(guard)
        require(completion_text(role.lookup,fact,guard)==text,'SLOT_COMPLETION_CHANGED')
    check();return CompletedDeclaration(value,fact,role,checksum,check,_SEAL)
