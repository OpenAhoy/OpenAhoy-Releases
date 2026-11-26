"""Workspace-local derived gallery data. Original and playback reads keep their own checks."""
from base64 import b64decode, b64encode
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache, partial
from multiprocessing import get_context
from contextlib import closing, contextmanager
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import sqlite3
from threading import Lock
from time import monotonic, time_ns

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .project_context import PLATFORMS
from .media_library import LIBRARY_ID
from . import article_work, asset_image_library, character_library, media_monitor

GROUPS = ('characters', 'images', 'articles', 'media')
ACTIONS = ('gallery_index', 'gallery_group', 'gallery_preview')
MAX_BYTES = 64 * 1024 * 1024
SCOPE = {'connection_id': {'type':'string','maxLength':128}, 'platform':{'enum':list(PLATFORMS),'type':'string'}}


def specs(action, project, digest, attempt):
    return [
        action('gallery_index', {}, SCOPE | {'project_id':project}),
        action('gallery_group', {'project_id':project,'group':{'type':'string','enum':list(GROUPS)}},
               SCOPE | {'ticket':{'type':'string','maxLength':64},'offset':{'type':'integer','minimum':0}}),
        action('gallery_preview', {'project_id':project,'kind':{'type':'string','enum':['characters','images','gif','video']},
                                  'sha256':digest}, SCOPE | {'version_id':character_library.ID, 'attempt_id':attempt,
                                                          'ticket':{'type':'string','maxLength':64},'family':{'type':'string','enum':['audio','video','gif']}}),
    ]


class Cache:
    def __init__(self, store):
        self.dir = store.root/'gallery-preview-v1'
        self.owner = store.owner()
        self.fallback=OrderedDict()
        self.fallback_bytes=0

    def open(self):
        self.dir.mkdir(mode=0o700,exist_ok=True)
        path_check(self.dir,True)
        path=self.dir/'derived.sqlite'
        fd=os.open(path,os.O_CREAT|os.O_NOFOLLOW|os.O_RDWR,0o600)
        os.close(fd)
        path_check(path,False)
        db=sqlite3.connect(path,timeout=3)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, data BLOB NOT NULL, used INTEGER NOT NULL, kind TEXT NOT NULL)')
        except sqlite3.Error:
            db.close()
            raise
        return db

    def key(self,project,*parts):
        return sha256(json.dumps([self.owner,project['id'],project['root'],*parts]).encode()).hexdigest()

    @contextmanager
    def reader(self):
        db=None
        try:
            if self.dir.exists():db=self.open()
        except (WCEError,OSError,sqlite3.Error):
            pass
        try:yield db
        finally:
            if db is not None:db.close()

    def get(self,k,db=None):
        if k in self.fallback:return self.fallback[k]
        try:
            if db is None:
                with self.reader() as db:
                    if db is None:return None
                    row=db.execute('SELECT data FROM cache WHERE k=?',(k,)).fetchone()
            else:row=db.execute('SELECT data FROM cache WHERE k=?',(k,)).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def put(self,k,data,kind):
        previous=self.fallback.pop(k,None)
        if previous is not None:self.fallback_bytes-=len(previous)
        try:
            self._write(k,data,kind)
        except (WCEError,OSError,sqlite3.Error):
            if len(data)>MAX_BYTES:return
            self.fallback[k]=data
            self.fallback_bytes+=len(data)
            while self.fallback_bytes>MAX_BYTES:
                self.fallback_bytes-=len(self.fallback.popitem(last=False)[1])

    def _write(self,k,data,kind):
        if len(data)>MAX_BYTES:return
        with closing(self.open()) as db, db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?,?)',(k,data,time_ns(),kind))
            # Separate quotas prevent thumbnail churn from evicting the last good catalog.
            total=db.execute('SELECT sum(length(data)) FROM cache WHERE kind=?',(kind,)).fetchone()[0]
            if total>MAX_BYTES:
                for old,size in db.execute('SELECT k,length(data) FROM cache WHERE kind=? ORDER BY used',(kind,)).fetchall():
                    db.execute('DELETE FROM cache WHERE k=?',(old,))
                    total-=size
                    if total<=MAX_BYTES:break


def empty(project,group):
    p={'id':project['id'],'name':project['name']}
    if group in ('characters','images'):
        return {'projects':[p|{'assets' if group=='characters' else 'images':[]}]}
    return {'articles':[],'projects':[p]} if group=='articles' else {'rows':[],'unavailable':[]}


def bad(row,reason='ASSET_UNREADABLE'):
    return row|{'gallery_state':'UNAVAILABLE','gallery_reason':reason}


def rows_of(data,group):
    if group in ('characters','images'):
        return data['projects'][0]['assets' if group=='characters' else 'images']
    return data['articles' if group=='articles' else 'rows']


def key_for(row,group):
    if group=='images':return row['sha256']
    if group=='characters':return row['id']
    if group=='articles':return row['work_id']
    return (row['family'],row['attempt'])


def encoded(value):
    return json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()


def page_of(data,group,offset,limit,budget):
    rows=rows_of(data,group)
    total=len(rows)
    end=min(total,offset+limit)
    page=[]
    size=0
    if group=='characters':data['projects'][0].pop('browse_guides',None)
    for row in rows[offset:end]:
        row.pop('_source_pin',None)
        if group=='images' and len(row['uses'])>64:row['uses']=row['uses'][:64]
        amount=len(encoded(row))
        if page and size+amount>budget:break
        page.append(row)
        size+=amount
    rows[:]=page
    end=offset+len(page)
    return data,end if end<total else None


@lru_cache(maxsize=1)
def source_reader(registry):
    from types import SimpleNamespace
    from .video_director import Director
    from .video_protocol import VideoRouter
    media=VideoRouter(None,registry)
    director=Director(media.video_jobs.projects)
    return SimpleNamespace(director=director,characters=character_library.CharacterLibrary(director),
                           jobs=media.video_jobs,gif_jobs=media.gif_jobs,audio_jobs=media.audio_jobs)


def preview_worker_ready():
    # Spawn and import the gallery module while the first native catalogs load.
    return None


def read_worker(registry,project,command,options,source):
    # The existing history reader proves the SQLite FD against this process's
    # open files. Isolate all source I/O from simultaneous work and the MCP host.
    api=source_reader(registry)
    store=api.director.projects
    def check():
        known=(api.audio_jobs.media.project() if project['id']==LIBRARY_ID else
               next((p for p in store.view()['projects'] if p['id']==project['id']),None))
        if not known or known['root']!=project['root']:raise WCEError('PROJECT_NOT_REGISTERED')
    check()
    value=(load_group(api,project,options,source) if command=='scan' else render_preview(api,project,options,source))
    check()
    return value


def check_sources(root,specs,prior,row):
    from .bounded_file import FileSource
    for spec in specs:
        try:
            pin=character_library.file_pin(root,spec)
            if prior and (prior.get('_source_pin')!=list(pin) or prior.get('gallery_reason')):
                digest=sha256()
                for chunk in FileSource(root).iter_html(spec['path'],expected_state=pin):digest.update(chunk)
                if digest.hexdigest()!=spec['sha256']:continue
            row['_source_pin']=list(pin)
            return True
        except (WCEError,OSError):
            continue
    row.update(bad(row))
    return False


def load_group(api,p,g,old):
    director=api.director;pid=p['id']
    base=empty(p,g);partial=False
    try:
        if pid==LIBRARY_ID and g!='media':return base,'READY',None
        try:
            Path(p['root']).lstat()
        except FileNotFoundError:
            return old or base,'UNAVAILABLE','PROJECT_OFFLINE'
        if pid!=LIBRARY_ID:root,pin=director.project(pid)
        prior={key_for(r,g):r for r in rows_of(old,g)} if old else {}
        if g=='images':
            state=director.load(pid,director.storage(root,pin));failures=[]
            items=asset_image_library.images_in(pid,state,api.director.projects.registry,failures)
            for row,sources in items.values():
                paths=[spec for spec in sources.values() if 'path' in spec]
                if paths and len(paths)==len(sources):
                    if not check_sources(root,paths,prior.get(row['sha256']),row):partial=True
                base['projects'][0]['images'].append(row|{'project_label':p['name']})
            if failures:
                known={r['sha256'] for r in rows_of(base,g)}
                for row in rows_of(old,g) if old else []:
                    if row['sha256'] not in known and any(use.get('work_id') in failures for use in row['uses']):
                        rows_of(base,g).append(bad(row))
                partial=True
        elif g=='characters':
            base=api.characters.list([{'id':pid,'name':p['name']}],readonly=True)
            if base['projects'][0].get('unavailable'):raise WCEError('PROJECT_UNREADABLE')
            for row in rows_of(base,g):
                if not check_sources(root,[row['file']],prior.get(row['id']),row):partial=True
        elif g=='articles':
            base=article_work.catalog(director,api.director.projects.registry,pid,excerpt=True)
            if not base['projects'] or base['projects'][0].get('unavailable'):raise WCEError('PROJECT_UNREADABLE')
            prior={row['work_id']:row for row in rows_of(old,g)} if old else {}
            for i,row in enumerate(rows_of(base,g)):
                if row.get('error'):
                    partial=True
                    if row['work_id'] in prior:rows_of(base,g)[i]=bad(prior[row['work_id']])
        else:
            base=media_monitor.collect(api.jobs,api.gif_jobs,api.audio_jobs,include_scope=True,selected=pid)
            if base['unavailable'] or any(r['state']=='UNAVAILABLE' for r in base['rows']):
                partial=True;missing={r['family'] for r in base['unavailable']}
                prior={key_for(r,g):r for r in rows_of(old,g)} if old else {}
                for i,row in enumerate(base['rows']):
                    prev=prior.pop(key_for(row,g),None)
                    if row['state']=='UNAVAILABLE' and prev:base['rows'][i]=bad(prev)
                base['rows'].extend(bad(r) for r in prior.values() if r['family'] in missing)
            for row in base['rows']:
                for unused in ('versions','used_in','soundtrack'):row.pop(unused,None)
        if pid!=LIBRARY_ID and director.project(pid)!=(root,pin):raise WCEError('PROJECT_UNREADABLE')
    except (WCEError,OSError,sqlite3.Error,ValueError):
        return old or empty(p,g),'UNAVAILABLE','PROJECT_UNREADABLE'
    return base,('PARTIAL' if partial else 'READY'),('SOURCE_PARTIAL' if partial else None)


def render_preview(api,p,args,row):
    k=args['kind'];digest=args['sha256']
    pid=p['id'];a={'project_id':pid,'sha256':digest}
    if k=='characters':
        result=api.characters.media(a|{'action':'character_thumbnail','version_id':row['id']})
        raw=b64decode(result['data'],validate=True)
    elif k=='images':
        # Restrict original lookup to a visible usage, including unscoped
        # reads where some account references have since been revoked.
        if args.get('connection_id'):a['connection_id']=args['connection_id']
        result=asset_image_library.original(api.director,a,thumbnail=True,allowed_uses=row['uses'])
        raw=b64decode(result['data'],validate=True)
    elif k=='video':
        job=row['attempt']
        if row['family']=='audio':result=api.audio_jobs.preview_video(job,pid,0,digest)
        else:
            _,asset,pin=api.jobs._playable(job,pid)
            if asset['sha256']!=digest:raise WCEError('ASSET_UNREADABLE')
            result=api.jobs.preview_frames(0,job,pid)
            if api.jobs._playable(job,pid)[2]!=pin:raise WCEError('ASSET_UNREADABLE')
        raw=b64decode(result['frames'][0],validate=True)
    else:
        receipt,artifact,pin=api.gif_jobs.available(row['attempt'],pid)
        if receipt['asset']['sha256']!=digest or receipt['asset']['bytes']>12*1024*1024:
            raise WCEError('ASSET_UNREADABLE')
        from .bounded_file import FileSource
        gif=b''.join(FileSource(api.gif_jobs.root).iter_html(artifact.name,expected_state=pin))
        if sha256(gif).hexdigest()!=digest:raise WCEError('ASSET_UNREADABLE')
        from .video_director_media import preview_image_bytes
        raw=b64decode(preview_image_bytes(gif,digest,True)['data'],validate=True)
    if not raw.startswith(b'\xff\xd8\xff') or len(raw)>2*1024*1024:raise WCEError('ASSET_UNREADABLE')
    return raw

class Gallery:
    def __init__(self,router):
        self.api=router
        self.store=router.director.projects
        self.cache=None
        self.pool=ProcessPoolExecutor(max_workers=3,mp_context=get_context('spawn'))
        self.preview_pool=ProcessPoolExecutor(max_workers=2,mp_context=get_context('spawn'))
        self.preview_started=False
        self.jobs={}
        self.latest={}
        self.lock=Lock()

    def registry(self):
        projects=self.store.view()['projects']
        media=self.api.audio_jobs.media.project()
        return {p['id']:p for p in projects+([media] if media else [])}

    def account(self,platform,cid):
        if platform=='wechat_official_account':
            from .wechat_component_binding import configuration_account
            if configuration_account(self.store.registry,cid):return True
            from .own_connection_registry import check_member
            from .own_connection_policy import resolve
            try:
                policy=resolve(cid,self.store.registry,active=False,readonly=True)
                if policy.value['schema']==2:check_member(policy,readonly=True)
                return bool(policy.value['enabled'])
            except WCEError as exc:
                if exc.code in ('CONNECTION_NOT_BOUND','CONNECTION_DISCONNECTED','CONNECTION_NOT_COMMITTED',
                                'CONNECTION_COMMITTED_IDENTITY_CHANGED'):return False
                raise WCEError('ACCOUNT_ACCESS_UNAVAILABLE') from None
            except (ValueError,OSError):raise WCEError('ACCOUNT_ACCESS_UNAVAILABLE') from None
        tools={'x':'x.connections.list','xiaohongshu':'xhs.connections.list'}
        return any(row['connection_id']==cid and row.get('state') not in ('REVOKED','REMOVED','DISCONNECTED')
                   for row in self.api.inner.call(tools[platform],{})['connections'])

    def scoped(self,data,group,args):
        data=deepcopy(data)
        account=args.get('connection_id')
        platform=args.get('platform','wechat_official_account')
        from functools import lru_cache
        allowed=lru_cache(maxsize=64)(self.account)
        if account and not allowed(platform,account):raise WCEError('ACCOUNT_ACCESS_REVOKED')
        rows=rows_of(data,group)
        if group=='characters' and account:
            pid=self.store.settings(platform,account)['settings']['project_id']
            if data['projects'][0]['id']!=pid:rows.clear()
        if group=='articles':
            rows[:]=[r for r in rows if r.get('connection_id') and (not account or (platform=='wechat_official_account' and account==r['connection_id']))
                     and allowed('wechat_official_account',r['connection_id'])]
        if group=='images':
            for row in rows:
                uses=[u for u in row['uses'] if (not account or (platform=='wechat_official_account' and u.get('connection_id')==account))
                      and (not u.get('connection_id') or allowed('wechat_official_account',u['connection_id']))]
                if uses and len(uses)!=len(row['uses']):row['title']=uses[0].get('title') or uses[0].get('work') or 'Image'
                row['uses']=uses
            rows[:]=[r for r in rows if r['uses']]
        if group=='media' and any(row.get('account_key') for row in rows):
            keys=set()
            for plat,tool in [('wechat_official_account','own.connections.list'),('x','x.connections.list'),('xiaohongshu','xhs.connections.list')]:
                if account and platform!=plat:continue
                try:
                    ids=[account] if account else [r['connection_id'] for r in self.api.inner.call(tool,{})['connections']]
                    if not account and plat=='wechat_official_account':
                        from .wechat_component_binding import ComponentBinding
                        ids.extend(r['connection_id'] for r in ComponentBinding(self.store.registry).overview())
                    keys.update(sha256((plat+'\0'+cid).encode()).hexdigest() for cid in ids if allowed(plat,cid))
                except (ValueError, WCEError, OSError):continue
            rows[:]=[r for r in rows if (not account and not r.get('account_key')) or r.get('account_key') in keys]
        elif group=='media' and account:rows.clear()
        return data

    def cached_group(self,p,g,db=None):
        raw=self.cache.get(self.cache.key(p,'catalog',g),db)
        if raw:
            try:
                data=json.loads(raw)
                if isinstance(rows_of(data,g),list):return data
            except (ValueError,TypeError,IndexError,KeyError):
                pass
        return None

    def task(self,key,ticket,fn,pool):
        with self.lock:
            now=monotonic()
            for ident,(origin,future,created) in list(self.jobs.items()):
                if future.done() and now-created>90:
                    del self.jobs[ident]
                    if self.latest.get(origin)==ident:
                        del self.latest[origin]
            if ticket:
                job=self.jobs.get(ticket)
                if not job or job[0]!=key:
                    raise WCEError('GALLERY_TICKET_STALE')
            else:
                ticket=self.latest.get(key)
                job=self.jobs.get(ticket)
                if not job or job[1].done():
                    if len(self.jobs)>=256:
                        oldest=next((t for t,(_,f,_) in self.jobs.items() if f.done()),None)
                        if oldest is None:
                            return None,None
                        origin=self.jobs.pop(oldest)[0]
                        if self.latest.get(origin)==oldest:
                            del self.latest[origin]
                    ticket=secrets.token_hex(12)
                    job=(key,pool.submit(fn),now)
                    self.jobs[ticket]=job
                    self.latest[key]=ticket
        return ticket,job[1].result() if job[1].done() else None

    def preview(self,p,args,data):
        k=args['kind'];digest=args['sha256']
        for row in rows_of(data,'media' if k in ('video','gif') else k):
            if k=='characters' and row.get('id')==args.get('version_id') and row['file']['sha256']==digest:break
            if k=='images' and row['sha256']==digest:break
            if k in ('video','gif') and row['kind']==k and row['family']==args.get('family') and row['attempt']==args.get('attempt_id') and row.get('asset',{}).get('sha256')==digest:break
        else:raise WCEError('GALLERY_ASSET_UNAVAILABLE')
        cachekey=self.cache.key(p,'jpeg-v1',k,digest,args.get('version_id'),args.get('connection_id'),args.get('platform'))
        saved=self.cache.get(cachekey)
        if saved:
            return {'mime_type':'image/jpeg','sha256':digest,'data':b64encode(saved).decode(),'cached':True}
        if row.get('gallery_state')=='UNAVAILABLE':raise WCEError('ASSET_UNREADABLE')
        render=partial(read_worker,self.store.registry,p,'preview',args,row)
        ticket,result=self.task(cachekey,args.get('ticket'),render,self.preview_pool)
        if result is None:return {'state':'PENDING','ticket':ticket or ''}
        self.cache.put(cachekey,result,'jpeg')
        return {'mime_type':'image/jpeg','sha256':digest,'data':b64encode(result).decode(),'cached':False}

    def call(self,command,args):
        projects=self.registry()
        selected=args.get('project_id')
        if selected and selected not in projects:raise WCEError('PROJECT_NOT_REGISTERED')
        account=args.get('connection_id')
        if account and not self.account(args.get('platform','wechat_official_account'),account):
            raise WCEError('ACCOUNT_ACCESS_REVOKED')
        if self.cache is None:self.cache=Cache(self.store)
        if command=='gallery_index':
            chosen=[p for p in projects.values() if not selected or selected==p['id']]
            listed=[{'id':p['id'],'name':p['name']} for p in chosen]
            snapshots=[]
            budget=96*1024
            with self.cache.reader() as db:
                if db is not None or self.cache.fallback:
                    for p in chosen:
                        for g in GROUPS:
                            if budget<1024:break
                            stored=self.cached_group(p,g,db)
                            if not stored:continue
                            data=self.scoped(stored,g,args)
                            if not rows_of(data,g):continue
                            page,_=page_of(data,g,0,16,min(budget-256,16*1024))
                            item={'project_id':p['id'],'group':g,'data':page,'state':'CACHED'}
                            size=len(encoded(item))
                            if rows_of(page,g) and size<=budget:
                                snapshots.append(item)
                                budget-=size
            if chosen and not snapshots and not self.preview_started:
                self.preview_pool.submit(preview_worker_ready)
                self.preview_started=True
            return {'projects':listed,'snapshots':snapshots}
        p=projects[selected]
        if command=='gallery_preview':
            g=args['kind'] if args['kind'] in ('images','characters') else 'media'
            return self.preview(p,args,self.scoped(self.cached_group(p,g) or empty(p,g),g,args))
        g=args['group'];key=self.cache.key(p,'catalog',g)
        old=self.cached_group(p,g) if not args.get('ticket') else None
        scan=partial(read_worker,self.store.registry,p,'scan',g,old)
        ticket,result=self.task(key,args.get('ticket'),scan,self.pool)
        identity={'project_id':selected,'group':g,'ticket':ticket or ''}
        if result is None:return identity|{'state':'PENDING'}
        projected,state,reason=result
        if state!='UNAVAILABLE' and not args.get('offset'):
            self.cache.put(key,encoded(self.scoped(projected,g,{})),'catalog')
        data=self.scoped(projected,g,args)
        data,next_offset=page_of(data,g,args.get('offset',0),96,192*1024)
        return identity|{'state':state,'reason':reason,'data':data,'next_offset':next_offset}
