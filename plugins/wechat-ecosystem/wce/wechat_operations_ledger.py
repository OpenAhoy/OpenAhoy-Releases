"""Local WeChat work, editorial, rights and accounting records per account."""
import csv
from datetime import date, datetime, timedelta
import io
from secrets import token_hex
import time

from .contracts import WCEError
from .own_connection_policy import atomic_write, read_optional
from .tools import schema
from .wechat_engagement import CST, _date

MAX_BYTES = 1024 * 1024
MAX_ROWS = 600
DATA_FILE = 'wechat-operations.json'
FIELDS = {
    'work': ('title', 'project_ref', 'work_ref', 'version_ref', 'source_ref', 'draft_ref', 'article_url'),
    'idea': ('title', 'work_ref', 'article_url', 'comment_ref', 'notes'),
    'schedule': ('title', 'work_ref', 'date', 'channel', 'audience', 'notes'),
    'rights': ('title', 'work_ref', 'version_ref', 'rights_basis', 'license_scope', 'expires_on', 'offer_url'),
    'deal': ('title', 'work_ref', 'stage', 'date', 'external_ref', 'amount_cents', 'notes'),
    'money': ('title', 'work_ref', 'date', 'entry', 'source', 'external_ref', 'amount_cents', 'notes'),
}
ENTRY_TYPES = ('revenue', 'settlement', 'received', 'refund', 'cost')
SOURCES = ('advertising', 'praise', 'affiliate', 'paid_content', 'brand', 'licensing', 'production', 'other')
STAGES = ('inquiry', 'quoted', 'delivery', 'invoice', 'paid', 'closed')
REQUIRED = {
    'work': {'title','project_ref','work_ref','version_ref'},
    'idea': {'title','article_url','comment_ref'},
    'schedule': {'title','date','channel'},
    'rights': {'title','work_ref','version_ref','rights_basis','license_scope'},
    'deal': {'title','stage','date'},
    'money': {'title','date','entry','source','external_ref','amount_cents'},
}


def actions(action, key):
    text = {'type':'string','minLength':1,'maxLength':280}
    string = {**text, 'maxLength':1024}
    ids = {'type':'string','pattern':'^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,119}$'}
    iso = {'type':'string','pattern':r'^\d{4}-\d{2}-\d{2}$'}
    kind = {'type':'string','enum':list(FIELDS)}
    columns = {field:text for fields in FIELDS.values() for field in fields}
    columns.update(title={**text,'maxLength':120}, date=iso, expires_on=iso, notes=string,
                   article_url=string, offer_url=string, work_ref=ids, version_ref=ids,
                   project_ref=ids, stage={'type':'string','enum':list(STAGES)},
                   entry={'type':'string','enum':list(ENTRY_TYPES)}, source={'type':'string','enum':list(SOURCES)},
                   amount_cents={'type':'integer','minimum':0,'maximum':10**12})
    fields = {'oneOf':[schema({'kind':{'type':'string','const':group},
                      **{name:columns[name] for name in FIELDS[group] if name in REQUIRED[group]}},
                      {name:columns[name] for name in FIELDS[group] if name not in REQUIRED[group]})
                       for group in FIELDS]}
    revision={'type':'integer','minimum':0}
    return {
        'ops_list':action('ops_list',{}, {'kind':kind,'work_ref':ids,'offset':{'type':'integer','minimum':0,'maximum':MAX_ROWS}}),
        'ops_import_money':action('ops_import_money',{'expected_revision':revision,
            'statement_csv':{'type':'string','minLength':1,'maxLength':120000}}),
        'ops_put':action('ops_put',{'expected_revision':revision,'record':fields},
                         {'record_id':key}),
    }


def _read(policy):
    value=read_optional(policy.root/DATA_FILE,MAX_BYTES)
    if value is None:
        return {'schema':1,'appid':policy.data['appid'],'revision':0,'items':[]}
    if (type(value) is not dict or value.get('schema')!=1 or value.get('appid')!=policy.data['appid']
            or type(value.get('revision')) is not int or not isinstance(value.get('items'),list)
            or len(value['items'])>MAX_ROWS):
        raise WCEError('WECHAT_LEDGER_UNVERIFIED')
    return value


def _values(values):
    from urllib.parse import urlsplit
    from .publication_wire import article_url_supported
    normalized = {}
    for key,value in values.items():
        if isinstance(value,str):
            value=value.strip()
            if not value:
                raise WCEError('WECHAT_LEDGER_REQUIRED')
        if key in ('date','expires_on'):
            _date(value)
        if key=='article_url' and not article_url_supported(value):
            raise WCEError('WECHAT_LEDGER_ARTICLE_URL_INVALID')
        if key=='offer_url':
            url=urlsplit(value)
            if url.scheme!='https' or not url.hostname or url.username or url.password:
                raise WCEError('WECHAT_LEDGER_OFFER_URL_INVALID')
        normalized[key]=value
    return normalized


def _accounting(rows):
    as_of=datetime.now(CST).date()
    totals={}
    for days in (7,30,90):
        start=as_of-timedelta(days=days-1)
        amounts={kind:0 for kind in ENTRY_TYPES}
        by_source={}
        unassigned=0
        count=0
        for row in rows:
            if row['kind']!='money' or not start<=date.fromisoformat(row['date'])<=as_of:
                continue
            count+=1
            amount=row['amount_cents']
            amounts[row['entry']]+=amount
            flows=by_source.setdefault(row['source'],{kind:0 for kind in ENTRY_TYPES})
            flows[row['entry']]+=amount
            if row['entry']=='revenue' and not row.get('work_ref'):
                unassigned+=amount
        totals[str(days)]={'record_count':count,'entries_cents':amounts if count else None,
            'sources_cents':by_source,'unassigned_revenue_cents':unassigned if count else None,
            'contribution_cents':amounts['revenue']-amounts['refund']-amounts['cost'] if count else None}
    return totals


STATEMENT_FIELDS = ('date','entry','source','external_ref','title','amount_cents','work_ref','notes')


def _money_key(row):
    return row['entry'],row['source'],row['external_ref']


def _statement(text):
    rows=csv.DictReader(io.StringIO(text.removeprefix('\ufeff')),strict=True)
    if rows.fieldnames!=list(STATEMENT_FIELDS):
        raise WCEError('WECHAT_LEDGER_STATEMENT_HEADER')
    result=[]
    try:
        for index,row in enumerate(rows):
            if index>=100 or not all(isinstance(value,str) for value in row.values()) or None in row:
                raise WCEError('WECHAT_LEDGER_STATEMENT_INVALID')
            row={key:value.strip() for key,value in row.items()}
            if (row['entry'] not in ENTRY_TYPES or row['source'] not in SOURCES
                    or not 1<=len(row['title'])<=120 or not 1<=len(row['external_ref'])<=280
                    or not row['amount_cents'].isascii() or not row['amount_cents'].isdigit()
                    or len(row['amount_cents'])>13 or int(row['amount_cents'])>10**12
                    or len(row['notes'])>1024 or len(row['work_ref'])>120):
                raise WCEError('WECHAT_LEDGER_STATEMENT_INVALID')
            result.append({'kind':'money',**_values({k:v for k,v in row.items() if v})})
            result[-1]['amount_cents']=int(row['amount_cents'])
    except csv.Error:
        raise WCEError('WECHAT_LEDGER_STATEMENT_INVALID') from None
    if not result:
        raise WCEError('WECHAT_LEDGER_STATEMENT_INVALID')
    return result


def _import(saved,args):
    original={_money_key(row):row for row in saved['items'] if row['kind']=='money'}
    added=[]
    repeated=0
    for row in _statement(args['statement_csv']):
        key=_money_key(row)
        before=original.get(key)
        if before is not None:
            if row!={k:v for k,v in before.items() if k not in {'id','updated_at'}}:
                raise WCEError('WECHAT_LEDGER_STATEMENT_CONFLICT')
            repeated+=1
            continue
        original[key]=row
        added.append({**row,'id':'wxops-'+token_hex(12),'updated_at':int(time.time())})
    if len(saved['items'])+len(added)>MAX_ROWS:
        raise WCEError('WECHAT_LEDGER_LIMIT')
    version=saved['revision']+int(bool(added))
    return {'state':'SAVED','revision':version,'added':len(added),'repeated':repeated}, saved['items']+added



def execute(client,args,action):
    from .own_connection_policy import locked
    policy=client.policy
    if action=='ops_list':
        saved=_read(policy)
        rows=[row for row in saved['items'] if args.get('work_ref',row.get('work_ref'))==row.get('work_ref')]
        selected=[row for row in rows if args.get('kind',row['kind'])==row['kind']]
        selected.sort(key=lambda r:(r.get('date',''),r['updated_at'],r['id']),reverse=True)
        offset=args.get('offset',0)
        return {'state':'OBSERVED','revision':saved['revision'],'items':selected[offset:offset+25],
                'next_offset':offset+25 if offset+25<len(selected) else None,'record_count':len(selected),
                'accounting':_accounting(rows),'accounting_source':'ENTERED_DOCUMENTS'}
    planned=_values(args['record']) if action=='ops_put' else None
    client.guard('draft_read')
    with locked(policy.root/'wechat-operations.lock'):
        saved=_read(policy)
        if saved['revision']!=args['expected_revision']:
            raise WCEError('WECHAT_LEDGER_CHANGED')
        if action=='ops_import_money':
            result,rows=_import(saved,args)
            if result['added']:
                client.guard('draft_read')
                atomic_write(policy.root/DATA_FILE,{**saved,'revision':result['revision'],'items':rows},maximum=MAX_BYTES)
            return result
        rows=saved['items']
        existing=next((r for r in rows if r['id']==args.get('record_id')),None)
        if args.get('record_id') and (existing is None or existing['kind']!=planned['kind']):
            raise WCEError('WECHAT_LEDGER_RECORD_UNAVAILABLE')
        if len(rows)>=MAX_ROWS and existing is None:
            raise WCEError('WECHAT_LEDGER_LIMIT')
        if planned['kind']=='money' and any(r['kind']=='money' and r['id']!=args.get('record_id')
                and all(r[k]==planned[k] for k in ('entry','source','external_ref')) for r in rows):
            raise WCEError('WECHAT_LEDGER_DUPLICATE_STATEMENT_ENTRY')
        item={**planned,'id':existing['id'] if existing else 'wxops-'+token_hex(12),'updated_at':int(time.time())}
        result={'state':'SAVED','revision':saved['revision']+1,'item':item}
        client.guard('draft_read')
        atomic_write(policy.root/DATA_FILE,{**saved,'revision':result['revision'],
            'items':[r for r in rows if r['id']!=item['id']]+[item]},maximum=MAX_BYTES)
        return result
