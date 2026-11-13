"""Read existing account journals only. Never remote inventory or API authority."""
import math
import os
from pathlib import Path
import re
import sqlite3
import time

from .contracts import WCEError
from .own_connection_policy import resolve,registry_path
from .draft_revision_guard import historical_identity_guard,policy_binding
from .draft_group_history_context import readonly_history_snapshot
from .own_store import OwnStore
from .own_workflow import stored
from .service import canonical,digest

PROFILE='LOCAL_ARTICLE_JOURNAL_V1'
PAGE_ITEMS=20  # A response transport page, never a total article allowance.
VIEWS={'summary','drafts','publications'}
CURSOR=re.compile(r'article-page-([a-f0-9]{64})-([0-9]+)\Z')


def _need(value):
    if value is not True:raise WCEError('ARTICLE_STATUS_INVALID_REQUEST')


def validate(value):
    _need(type(value)is dict and set(value) in ({'connection_id','view'},{'connection_id','view','before'}))
    _need(type(value.get('connection_id'))is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value['connection_id'])is not None)
    _need(type(value.get('view'))is str and value['view'] in VIEWS)
    if 'before' in value:
        _need(value['view']!='summary' and type(value['before'])is str and CURSOR.fullmatch(value['before'])is not None)


def _code(error):
    value=getattr(error,'code',None)
    if type(value)is str and re.fullmatch(r'(?:OWN|CONNECTION|CURRENT|PUBLICATION|GROUP|DRAFT|ARTICLE)_[A-Z0-9_]{1,96}',value):return value
    return 'ARTICLE_STATUS_JOURNAL_UNAVAILABLE'


def _reason(value):
    return value if type(value)is str and value!='PARSED_SUCCESS' and re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}',value) else None


def _time(value):
    return float(value) if type(value)in(int,float) and math.isfinite(value) and value>0 else None


def _titles(value):
    rows=value.get('articles') if type(value)is dict else None
    if rows is None:rows=[value.get('article',value)] if type(value)is dict else []
    if type(rows)is not list or not rows or any(type(row)is not dict or type(row.get('title'))is not str for row in rows):
        raise WCEError('ARTICLE_STATUS_JOURNAL_UNAVAILABLE')
    return [row['title'] for row in rows]


def _draft_rows(db,policy):
    binding=policy_binding(policy,'OPERATOR_ATTESTED')
    result=[]
    for row in db.execute("SELECT * FROM own_steps WHERE operation='add' AND tenant=? AND principal=? AND connection=? AND resource=? ORDER BY rowid DESC",
            (binding['tenant'],binding['principal'],binding['connection'],binding['resource'])):
        intent=stored(row['intent'],row['intent_digest'])
        if intent['binding']!=binding:raise WCEError('ARTICLE_STATUS_BINDING_CHANGED')
        from .own_diagnostics import read as diagnostic_read
        diagnostic=diagnostic_read(db,row)
        projection=intent['projection']
        titles=([item['title'] for item in projection['articles']] if 'articles' in projection else [projection['title']])
        result.append({'id':'draft-'+digest(row['id']),'kind':'DRAFT_SAVE_JOURNAL','state':row['state'],
            'articles':[{'index':i+1,'title':title,'url':None} for i,title in enumerate(titles)],
            'readback_state':row['readback'],'created_at':_time(row['created']),
            'last_recorded_at':_time(row['completed']) or _time(row['created']),
            'published_at':None,'source_order':None,'error_code':diagnostic.get('wechat_code'),
            'error_reason':diagnostic['reason'] if diagnostic['reason']!='PARSED_SUCCESS' else None,'provenance':'OWN_ADD_JOURNAL',
            'remote_inventory_state':'NOT_QUERIED'})
    return result


def _current_rows(policy,registry,guard):
    from .current_publication_store import Store,public_target
    store=Store(policy,registry,guard=guard)
    paths=(store.directory,store.path,store.pin,store.enrollment)
    present=[os.path.lexists(path) for path in paths]
    if not any(present):return {'source':'CURRENT_PUBLICATION_JOURNAL','state':'NOT_ACQUIRED'},[]
    if not all(present):raise WCEError('CURRENT_PUBLICATION_HISTORY_MISSING')
    value=store.read();rows=[]
    for handle,row in value['targets'].items():
        # Older validated READY rows may not include article metadata. Keep
        # their real operation state without inventing titles or a zero count.
        if 'titles' in row and 'article_count' in row:public=public_target(row)
        else:public={'state':row['state'],'titles':[],'article_urls':[],
            'error_code':(row.get('reply') or {}).get('error_code')}
        urls=dict(public['article_urls']) if public['state'] in {'PUBLISHED','PUBLISHED_URLS_INCOMPLETE'} else {}
        rows.append({'id':'publication-'+digest(handle),'kind':'PUBLICATION_JOURNAL','state':public['state'],
            'articles':[{'index':i+1,'title':title,'url':urls.get(i+1)} for i,title in enumerate(public['titles'])],
            'readback_state':None,'created_at':None,'last_recorded_at':None,'published_at':None,
            'source_order':row['page']*20+row['page_index']+1 if type(row.get('page'))is int and type(row.get('page_index'))is int else None,
            'error_code':public['error_code'],
            'error_reason':_reason(public.get('reason') or (public.get('last_query') or {}).get('reason') or (row.get('reply') or {}).get('reason')),
            'provenance':'CURRENT_FREEPUBLISH_JOURNAL',
            'remote_inventory_state':'NOT_QUERIED'})
    guard()
    return {'source':'CURRENT_PUBLICATION_JOURNAL','state':'AVAILABLE'},rows


def _legacy_rows(db,policy,registry,history):
    from .publication_store import PublicationStore
    store=PublicationStore(policy,registry)
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if version<7:return {'source':'PUBLICATION_JOURNAL','state':'NOT_ACQUIRED'},[]
    count=db.execute('SELECT COUNT(*) FROM publication_intents WHERE account_key=?',(store.key,)).fetchone()[0]
    if not os.path.lexists(store.head_path):
        if count:raise WCEError('PUBLICATION_RECOVERY_HOLD')
        return {'source':'PUBLICATION_JOURNAL','state':'NOT_ACQUIRED'},[]
    store._verify(db,history_locators=history)
    output=[]
    query='''SELECT i.*,a.manifest,a.digest AS manifest_sha FROM publication_intents i
        JOIN publication_candidates c ON c.account_key=i.account_key AND c.artifact_id=i.artifact_id
        JOIN own_articles a ON a.version=c.version WHERE i.account_key=?'''
    for row in db.execute(query,(store.key,)):
        titles=_titles(stored(row['manifest'],row['manifest_sha']))
        urls={}
        if row['state']=='PUBLISHED':
            for article in db.execute('SELECT article_index,official_url FROM publication_articles WHERE account_key=? AND intent_id=?',
                    (store.key,row['intent_id'])):
                urls[article['article_index']]=article['official_url']
        times=[]
        for event in db.execute('SELECT event_json FROM publication_events WHERE account_key=? AND intent_id=?',(store.key,row['intent_id'])):
            from .publication_contract import strict_json
            value=strict_json(event['event_json'].encode());stamp=_time(value.get('created_ms'))
            if stamp is not None:times.append(stamp/1000)
        output.append({'id':'publication-'+digest(row['intent_id']),'kind':'PUBLICATION_JOURNAL','state':row['state'],
            'articles':[{'index':i+1,'title':title,'url':urls.get(i+1)} for i,title in enumerate(titles)],
            'readback_state':None,'created_at':_time(row['submit_ms']/1000) if row['submit_ms'] is not None else None,
            'last_recorded_at':max(times) if times else None,'published_at':None,'source_order':None,'error_code':None,
            'error_reason':'PLATFORM_STATUS_'+row['platform_status'] if row['state']=='PLATFORM_FAILED' and row['platform_status']in{'2','3','4'} else None,
            'provenance':'LEGACY_PUBLICATION_JOURNAL','remote_inventory_state':'NOT_QUERIED'})
    return {'source':'PUBLICATION_JOURNAL','state':'AVAILABLE'},output


def _snapshot(policy,registry,guard):
    with readonly_history_snapshot(policy,policy.root/'state.sqlite3') as (db,history):
        from .publication_schema import classify_read_only
        source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
        if source is None or source[0]!='OPERATOR_ATTESTED':raise WCEError('OWN_STATE_UNVERIFIED')
        classify_read_only(db,source[0],policy,history_locators=history)
        # Borrow the exact original history validators without constructor,
        # migration, writer transaction, token broker or sender.
        owner=object.__new__(OwnStore);owner.path=policy.root/'state.sqlite3';owner.history_policy=policy
        owner._check_legacy_history(db,source[0],history=history)
        drafts=_draft_rows(db,policy)
        legacy_source,legacy=_legacy_rows(db,policy,registry,history)
        guard()
    current_source,current=_current_rows(policy,registry,guard)
    guard()
    publications=legacy+current
    publications.sort(key=lambda row:(row['last_recorded_at'] is None,-(row['last_recorded_at'] or 0),
        row['provenance'],row['source_order'] if row['source_order'] is not None else 2**63,row['id']))
    return drafts,publications,[{'source':'OWN_ADD_JOURNAL','state':'AVAILABLE'},legacy_source,current_source]


def _metrics(drafts,publications,sources):
    publication_available=any(source['state']=='AVAILABLE' for source in sources[1:])
    return {'local_saved_groups':sum(row['state']=='SUCCEEDED' for row in drafts),
        'local_unknown_saves':sum(row['state']=='RESULT_UNKNOWN' for row in drafts),
        'local_readback_matched':sum(row['readback_state']=='MATCHED' for row in drafts),
        'local_published_groups':sum(row['state']in{'PUBLISHED','PUBLISHED_URLS_INCOMPLETE'} for row in publications) if publication_available else None,
        'official_followers':None,'official_reads':None,'official_shares':None,
        'official_metrics_state':'NOT_ACQUIRED'}


def read(value,registry=None,*,wall=time.time):
    validate(value)
    registry=Path(registry) if registry is not None else registry_path()
    stamp=_time(wall())
    if stamp is None:raise WCEError('ARTICLE_STATUS_TIME_UNAVAILABLE')
    base={'profile':PROFILE,'connection_id':value['connection_id'],'view':value['view'],
        'observed_at':stamp,'provenance':'LOCAL_VALIDATED_JOURNAL','remote_inventory_state':'NOT_QUERIED',
        'published_date_state':'NOT_ACQUIRED','official_metrics_state':'NOT_ACQUIRED'}
    try:
        policy=resolve(value['connection_id'],registry,active=False)
        guard=historical_identity_guard(policy)
        drafts,publications,sources=_snapshot(policy,registry,guard)
        observed=_time(wall())
        if observed is None:raise WCEError('ARTICLE_STATUS_TIME_UNAVAILABLE')
        base['observed_at']=observed
        rows=drafts if value['view']=='drafts' else publications
        if value['view']=='summary':
            return base|{'state':'AVAILABLE','sources':sources,'metrics':_metrics(drafts,publications,sources),
                'last_recorded_at':max((row['last_recorded_at'] for row in drafts+publications if row['last_recorded_at'] is not None),default=None)}
        relevant=sources[:1] if value['view']=='drafts' else sources[1:]
        acquired=any(source['state']=='AVAILABLE' for source in relevant)
        snapshot=digest({'connection_id':value['connection_id'],'view':value['view'],'rows':rows,'sources':relevant})
        offset=0
        if 'before' in value:
            match=CURSOR.fullmatch(value['before'])
            if match[1]!=snapshot:raise WCEError('ARTICLE_STATUS_CURSOR_CHANGED')
            offset=int(match[2]);_need(0<offset<=len(rows) and offset%PAGE_ITEMS==0)
        page=rows[offset:offset+PAGE_ITEMS];end=offset+len(page)
        guard()
        return base|{'state':'AVAILABLE' if acquired else 'NOT_ACQUIRED','sources':relevant,'items':page,
            'total_local_groups':len(rows) if acquired else None,
            'next_before':'article-page-'+snapshot+'-'+str(end) if end<len(rows) else None}
    except (WCEError,OSError,sqlite3.Error,ValueError,TypeError,KeyError) as error:
        if isinstance(error,WCEError) and error.code in {'ARTICLE_STATUS_INVALID_REQUEST','ARTICLE_STATUS_CURSOR_CHANGED'}:raise
        return base|{'state':'UNAVAILABLE','error_code':_code(error),'sources':[],
            'items':[],'total_local_groups':None,'next_before':None,
            'metrics':{'local_saved_groups':None,'local_unknown_saves':None,'local_readback_matched':None,
                'local_published_groups':None,'official_followers':None,'official_reads':None,'official_shares':None,
                'official_metrics_state':'NOT_ACQUIRED'}}
