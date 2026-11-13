"""Deterministic human control restrictions, never platform authorization.

Private Context is supplied from the standing owner/verified artifact provider.
Parsing it cannot create a seed, ordinary-publication grant or audience grant.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from .draft_revision_native_source import canonical, require

RULE = 'SLOT_HUMAN_CONTROL_V1'
SHA = re.compile(r'[a-f0-9]{64}')


def checksum(value): return sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Account:
    connection_id: str
    aliases: tuple


@dataclass(frozen=True)
class Target:
    connection_id: str
    date: str
    slot_id: str
    group_id: str
    article_id: str
    version_id: str
    aliases: tuple
    references: tuple  # Verified artifact refs/hashes, not permission.


@dataclass(frozen=True)
class Context:
    owner_sha256: str
    standing_sha256: str
    accounts: tuple
    targets: tuple
    evidence_sha256: str

    def validate(self):
        require(all(type(x) is str and SHA.fullmatch(x) for x in
            (self.owner_sha256,self.standing_sha256,self.evidence_sha256)), 'SLOT_CONTROL_CONTEXT_INVALID')
        require(type(self.accounts) is tuple and self.accounts and type(self.targets) is tuple,
            'SLOT_CONTROL_CONTEXT_INVALID')
        ids = set(); aliases = set()
        for account in self.accounts:
            require(type(account) is Account and type(account.connection_id) is str
                and account.connection_id and account.connection_id not in ids
                and type(account.aliases) is tuple and account.aliases
                and all(type(s) is str and s for s in account.aliases), 'SLOT_CONTROL_CONTEXT_INVALID')
            require(not (set(account.aliases) & aliases), 'SLOT_CONTROL_ALIAS_CONFLICT')
            aliases.update(account.aliases); ids.add(account.connection_id)
        target_ids = set(); aliases = set()
        for target in self.targets:
            require(type(target) is Target and target.connection_id in ids
                and target.article_id not in target_ids and type(target.aliases) is tuple
                and all(type(s) is str and s for s in target.aliases)
                and type(target.references) is tuple and target.references
                and all(type(s) is str and SHA.fullmatch(s) for s in target.references),
                'SLOT_CONTROL_CONTEXT_INVALID')
            require(all(type(getattr(target,k)) is str and getattr(target,k)
                for k in ('slot_id','group_id','article_id','version_id')), 'SLOT_CONTROL_CONTEXT_INVALID')
            datetime.strptime(target.date,'%Y-%m-%d'); target_ids.add(target.article_id)
        return self

    @property
    def sha256(self): return checksum(asdict(self.validate()))


def command_text(text):
    """Discard data-bearing blocks without inspecting URLs, attachments or paths."""
    require(type(text) is str, 'SLOT_CONTROL_TEXT_INVALID')
    text = re.sub(r'```[\s\S]*?(?:```|$)', '', text)
    text = re.sub(r'<(?:appshot|in-app-browser-context|send_user_message_question_reply|image|document|attachment)\b[^>]*>[\s\S]*?</(?:appshot|in-app-browser-context|send_user_message_question_reply|image|document|attachment)>', '', text, flags=re.I)
    text = re.sub(r'^\s*>.*$', '', text, flags=re.M)
    # Quoted imperatives are data; quoted account/title names remain selectors.
    text = re.sub(r'[“「『\"]([^”」』\"\n]*)[”」』\"]',
        lambda m: '' if re.search(r'不要发|别发|暂停|停止发布|继续发表|恢复发表|群发',m[1]) else m[1],text)
    return text.strip()


def _date(word, created):
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',word):
        try: datetime.strptime(word,'%Y-%m-%d'); return word
        except ValueError: return None
    if created is None: return None
    try:
        if type(created) in (int,float): current = datetime.fromtimestamp(created,timezone(timedelta(hours=8)))
        else:
            parsed=datetime.fromisoformat(created.replace('Z','+00:00'))
            if parsed.tzinfo is None: return None
            current=parsed.astimezone(timezone(timedelta(hours=8)))
        return (current.date()+timedelta(days={'今天':0,'明天':1,'昨天':-1}[word])).isoformat()
    except (ValueError,OverflowError,OSError): return None


def _scope(accounts, targets, dates=()):
    return {'connection_ids':sorted(set(accounts)), 'dates':sorted(set(dates)),
        'group_ids':sorted({t.group_id for t in targets}),
        'article_ids':sorted({t.article_id for t in targets}),
        'version_ids':sorted({t.version_id for t in targets}),
        'target_keys':[list(key) for key in sorted({(t.connection_id,t.date,t.group_id) for t in targets})]}


def _progress(clause):
    return bool(re.search(r'(怎么样|进展|查到哪|修到哪|好了[吗么]|能发[吗么]|能不能发|为什么|怎么还没|是不是|是否|[?？])',clause))


def interpret(text, fact, context, previous=()):
    """Interpret only after a real codec USER pair; output remains non-authority.

    Unknown ordinary topics are consumed NON_CONTROL. Ambiguity is reserved
    for an actual publication command with an unresolved, bounded target.
    """
    context.validate()
    require(fact.get('authority') is False and fact.get('text_sha256') == sha256(text.encode()).hexdigest(),
        'SLOT_CONTROL_PAIR_MISMATCH')
    cleaned = command_text(text)
    clauses = [s.strip() for s in re.split(r'[，,。；;！!\n]|但是|不过|而是',cleaned) if s.strip()]
    effects=[]; publication_topic=False
    all_ids=[a.connection_id for a in context.accounts]
    for clause in clauses:
        ids=[a.connection_id for a in context.accounts if any(alias in clause for alias in a.aliases)]
        named=[t for t in context.targets if any(alias in clause for alias in t.aliases)]
        selected=named or ([t for t in context.targets if not ids or t.connection_id in ids]
                           if re.search(r'这篇|那篇|这组|那组|这个稿|那个稿',clause) else [])
        deictic=bool(re.search(r'这篇|那篇|这组|那组|这个稿|那个稿',clause))
        words=re.findall(r'\d{4}-\d{2}-\d{2}|今天|明天|昨天',clause)
        dates=[_date(word,fact.get('created')) for word in words]
        date_unknown=any(d is None for d in dates)
        dates=[d for d in dates if d is not None]
        pause=bool(re.search(r'(?:先|暂时|现在)?(?:不要|别|不|先不)(?:再)?(?:普通|公开)?(?:发文|发表|发布|发)(?:了|吧|送)?|暂停(?:一下)?(?:普通|公开)?(?:发表|发布|发文)|停止(?:普通)?(?:发表|发布|发文)|暂缓(?:发表|发布)|(?:留|存|保存)(?:在|为)?草稿|只做草稿|等我(?:看完|确认).*再发|(?:改完|修改完|改好).*再发|先修改再(?:发表|发)',clause))
        resume=bool(re.search(r'(?:继续|恢复|照常|正常)(?:普通)?(?:发表|发布|发文)|(?:不要|别)暂停.*(?:发表|发布|发文)|只(?:做)?普通发表',clause))
        selector_words=[alias for a in context.accounts for alias in a.aliases]+[alias for t in context.targets for alias in t.aliases]
        selected_clause=clause
        for word in sorted(selector_words,key=len,reverse=True): selected_clause=selected_clause.replace(word,'')
        if re.search(r'(?:继续|恢复|照常|正常)(?:的|今天|明天|昨天|普通|公开|\s)*(?:发表|发布|发文)',selected_clause): resume=True
        if publication_topic and ids and re.search(r'(?:正常|照常)$',clause): resume=True
        audience=bool(re.search(r'群发|发给(?:所有)?粉丝|改(?:变)?受众',clause))
        if re.search(r'不群发|不要群发|别群发',clause): audience=False
        if re.search(r'不要暂停|别暂停|不是让你(?:停止|暂停)',clause): pause=False
        if re.search(r'(?:不是|没(?:有)?说|并非|不要以为|不代表|不等于).*?(?:继续|恢复|正常|照常)',clause): resume=False
        if re.search(r'(?:不要|别|不)(?:再)?(?:继续|恢复|正常|照常).*?(?:发表|发布|发文)',clause):
            resume=False; pause=True
        content=bool(re.search(r'修改|改一下|改完|改好|换图|排版|重写|调整',clause))
        generic=bool(re.fullmatch(r'(?:那就)?继续(?:吧|呀|啊)?',clause))
        if generic:
            # A new composer task or merely newer timestamp is never resume.
            last=None
            for candidate in reversed(previous):
                if candidate['thread_id'] != fact['thread_id']: continue
                if candidate['turn_id'] != fact['turn_id']: break
                if all(e['kind']=='NON_CONTROL' and e['reason']=='PROGRESS_ONLY' for e in candidate['effects']): continue
                last=candidate; break
            if last and last['turn_id']==fact['turn_id'] and last['context_sha256']==context.sha256:
                prior=[x for x in last['effects'] if x['kind'] in ('RESTRICT','AMBIGUOUS','AUDIENCE_CHANGE','RESUME')]
                if len(prior)==1 and prior[0]['kind']!='AMBIGUOUS':
                    effects.append({'kind':'RESUME','reason':'SAME_TASK_CONTROL_CONTINUATION','scope':prior[0]['scope']})
            continue
        if _progress(clause) and (not pause or re.search(r'是不是|是否|为什么|怎么|能不能',clause)): continue
        if re.match(r'^(?:(?:新闻|报道|文章(?:里|中)|材料(?:里|中)).*(?:说|提到|表示|宣布)|(?:他|她|他们|对方|别人|同事|模型)说|引用|转述)',clause): continue
        if not (pause or resume or audience):
            if content:
                effects.append({'kind':'CONTENT_CHANGE','reason':'CONTENT_ONLY','scope':_scope(ids or {t.connection_id for t in selected},selected,dates)})
            continue
        publication_topic=True
        explicit_all=bool(re.search(r'全部|所有|都',clause))
        inherited_scope=None
        if not ids and not selected and not explicit_all:
            prior_control=[x for x in effects if x['kind'] in ('RESTRICT','RESUME','AMBIGUOUS','AUDIENCE_CHANGE')]
            if prior_control:
                inherited_scope=prior_control[-1]['scope']
            else:
                # Unnamed command uses the actual current candidate domain,
                # never every standing account merely because it is registered.
                selected=[t for t in context.targets if not dates or t.date in dates]
        accounts=ids or sorted({t.connection_id for t in selected}) or (all_ids if explicit_all else [])
        if ids: selected=[t for t in selected if t.connection_id in ids]
        if selected:
            dates=dates or sorted({t.date for t in selected})
        scope=inherited_scope or _scope(accounts,selected,dates)
        unresolved=not scope['connection_ids']
        unnamed_multiple=not ids and not explicit_all and inherited_scope is None and len({t.group_id for t in selected})>1
        ambiguous=unresolved or unnamed_multiple or ((deictic or bool(named)) and len({t.group_id for t in selected})!=1) or date_unknown
        if date_unknown:
            scope['dates']=sorted({t.date for t in context.targets if t.connection_id in accounts})
        if ambiguous:
            kind='AMBIGUOUS'; reason='SCOPE_UNRESOLVED' if unresolved else 'DATE_UNVERIFIED' if date_unknown else 'TARGET_AMBIGUOUS'
        elif audience: kind='AUDIENCE_CHANGE'; reason='AUDIENCE_IS_NOT_ORDINARY'
        elif pause and resume: kind='AMBIGUOUS'; reason='CONTRADICTORY_CONTROL'
        elif pause: kind='RESTRICT'; reason='CONTENT_REQUIRED' if content else 'EXPLICIT_PAUSE'
        else: kind='RESUME'; reason='EXPLICIT_ORDINARY_CONTINUATION'
        effects.append({'kind':kind,'reason':reason,'scope':scope})
    if not effects: effects=[{'kind':'NON_CONTROL','reason':'PROGRESS_ONLY' if cleaned and _progress(cleaned) else 'NO_PUBLICATION_CONTROL','scope':_scope([],[])}]
    result = {'schema':1,'rule_version':RULE,'authority':False,
        'owner_sha256':context.owner_sha256,'standing_sha256':context.standing_sha256,
        'context_sha256':context.sha256,'thread_id':fact['thread_id'],'turn_id':fact['turn_id'],
        'item_id':fact['item_id'],'text_sha256':fact['text_sha256'],
        'raw_ordinal':fact['raw_ordinal'],'typed_ordinal':fact['typed_ordinal'], 'effects':effects}
    if 'opaque_images' in fact:
        from .slot_control_text_profile import validate_descriptor
        result['opaque_images'] = dict(validate_descriptor(fact['opaque_images']))
    return result


def matches(scope,target):
    return (target['connection_id'] in scope['connection_ids']
        and (not scope['dates'] or target['date'] in scope['dates'])
        and (not scope['group_ids'] or target['group_id'] in scope['group_ids']))


def restrictions(events,target,*,operation='submit'):
    """Restrictions only: even UNRESTRICTED is not permission to publish.

    Per-source causal order wins only within that source. Other sources' pauses
    remain unless an actual causal bridge is separately proved by the provider.
    Old-task reads never invoke a new-submit control gate.
    """
    require(operation in ('submit','task_read'), 'SLOT_CONTROL_OPERATION_INVALID')
    if operation=='task_read': return {'authority':False,'state':'TASK_READ_UNAFFECTED','reasons':[]}
    current={}
    for event in events:
        require(event.get('authority') is False and event.get('rule_version')==RULE,
            'SLOT_CONTROL_EVENT_INVALID')
        key=event['thread_id']
        for effect in event['effects']:
            if not matches(effect['scope'],target): continue
            if effect['kind']=='RESUME': current[key]=None
            elif effect['kind'] in ('RESTRICT','AMBIGUOUS','AUDIENCE_CHANGE'): current[key]=effect['reason']
    reasons=sorted({value for value in current.values() if value})
    return {'authority':False,'state':'RESTRICTED' if reasons else 'UNRESTRICTED_FACTS_ONLY','reasons':reasons}
