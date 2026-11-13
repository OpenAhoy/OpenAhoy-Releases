"""One fixed existing Audio journal's physical-head CAS, through normal SDK.

No SQL writes, initialization, resource/budget grants, rollback or model route.
Intent, byte archives, one claim and completion are append-only. Same operation
resumes before/after only; later legal journal events cannot replay its CAS.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import os,sqlite3,stat

from .contracts import WCEError
from .service import canonical,digest
from .draft_revision_store import RevisionStore,APP_ID,DDL,ZERO
from . import draft_revision_files as files
from .own_identity_checkpoint import Reader,file_metadata
from .own_connection_policy import locked
from .own_connection_registry import container,sync
from .own_history_source import owned_connection
from .own_revision_history import revision_read_scope
from .own_revision_relocation_source import checked,source_scope,CID,APPID,PURPOSE

OP='audio-original-revision-physical-relocation-20261104-v1'
DIRECTORY='revision-physical-relocations'
DB_SHA='180862019d1e35475e07194f6279601d8ac05abdfdf5dbc21bff9e2a1a344cf0'
ANCHOR_SHA='8daab3856c5757c40cbf26b7bf90179d5fec0f0c445406d5fb29ee4a5478b8ec'
PROFILE='AUDIO_REVISION_PHYSICAL_RELOCATION_V1'


def need(condition):
    if condition is not True:raise WCEError('REVISION_PHYSICAL_RELOCATION_HOLD')


def _raw(path,maximum):
    reader=Reader(Path(path).parent)
    meta,raw=reader.read(path,keep=True)
    need(0<len(raw)<=maximum)
    return meta,raw


def _new_raw(path,raw):
    """Exact raw archive, fsync file and containing directory, independent read."""
    path=Path(path);need(type(raw) is bytes and 0<len(raw)<=128*1024*1024)
    with Reader(path.parent).directory(path.parent) as parent:
        before=file_metadata(os.fstat(parent))
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        try:
            offset=0
            while offset<len(raw):
                count=os.write(fd,raw[offset:]);need(type(count) is int and count>0);offset+=count
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(parent)
        need(all(file_metadata(os.fstat(parent))[k]==before[k] for k in ('dev','ino','mode','uid','gid')))
    meta,actual=_raw(path,len(raw));need(actual==raw)
    return meta


def _dir(root):return Path(root)/DIRECTORY/OP


def _records(root):
    path=_dir(root)
    if not os.path.lexists(path):return None
    files.folder(path)
    names=set(os.listdir(path))
    need(names<={'anchor.before.json','database.before.sqlite3','intent.json','claim.json','complete.json'})
    # Archives may be durable before intent. They confer no operation or write.
    if 'intent.json' not in names:
        need('claim.json' not in names and 'complete.json' not in names)
        return {'state':'ARCHIVES_ONLY','directory':path}
    intent,intent_sha=files.read(path/'intent.json')
    need(type(intent) is dict and set(intent)=={'schema','profile','op','purpose','connection_id','binding',
        'source','migration','before_anchor','after_anchor','before_anchor_pin','before_database_pin',
        'directory_pin','account_pin','archives'}
        and type(intent['schema']) is int and intent['schema']==1 and intent['profile']==PROFILE and intent['op']==OP
        and intent['purpose']==PURPOSE and intent['connection_id']==CID
        and intent['before_anchor_pin']['sha256']==ANCHOR_SHA
        and intent['before_database_pin']['sha256']==DB_SHA)
    before=(canonical(intent['before_anchor'])+'\n').encode()
    after=(canonical(intent['after_anchor'])+'\n').encode()
    need(sha256(before).hexdigest()==ANCHOR_SHA)
    need({k for k in intent['before_anchor'] if intent['before_anchor'][k]!=intent['after_anchor'].get(k)}=={'root','database'}
        and set(intent['before_anchor'])==set(intent['after_anchor']))
    for name,maximum in (('anchor.before.json',16384),('database.before.sqlite3',128*1024*1024)):
        meta,raw=_raw(path/name,maximum)
        need(meta==intent['archives'][name])
        need(raw==before if name.startswith('anchor') else sha256(raw).hexdigest()==DB_SHA)
    claim=None;completion=None
    if 'claim.json' in names:
        claim,claim_sha=files.read(path/'claim.json')
        need(canonical(claim)==canonical({'schema':1,'profile':PROFILE,'op':OP,'intent_sha256':intent_sha,'cas_budget':1}))
    if 'complete.json' in names:
        need(claim is not None)
        completion,_=files.read(path/'complete.json')
        need(canonical(completion)==canonical({'schema':1,'profile':PROFILE,'op':OP,'state':'COMMITTED',
            'intent_sha256':intent_sha,'claim_sha256':claim_sha,'old_anchor_sha256':ANCHOR_SHA,
            'new_anchor_sha256':sha256(after).hexdigest(),'database_sha256':DB_SHA,
            'origin':'TRUSTED_PHYSICAL_FIELDS_ONLY_CAS'}))
    return {'state':'COMMITTED' if completion else 'CLAIMED' if claim else 'PREPARED',
        'directory':path,'intent':intent,'intent_sha':intent_sha,'claim':claim,'completion':completion}


def _physical(store):
    head,fixed=store._head()
    anchor_meta,raw=_raw(store.anchor,16384)
    database_meta,dbraw=_raw(store.path,128*1024*1024)
    need(raw==(canonical(head)+'\n').encode())
    directory=file_metadata(store.root.stat());account=file_metadata(store.account.stat())
    return head,fixed,anchor_meta,raw,database_meta,dbraw,{
        k:directory[k] for k in ('dev','ino','mode','uid','gid')}, {
        k:account[k] for k in ('dev','ino','mode','uid','gid')}


def _semantics(store,policy,*,historical):
    """Real owned FD, exact DDL/meta/events/proofs/targets. No RO frame writes."""
    with owned_connection(store.path,readonly=True,timeout=1,isolation_level=None,_revision_header=True) as db:
        db.row_factory=sqlite3.Row
        with revision_read_scope(policy,db) as frame:
            head=store._pins(_readonly_frame=frame,_readonly_db=db) if historical else store._pins()
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            actual=tuple(row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql"))
            need(db.execute('PRAGMA application_id').fetchone()[0]==APP_ID
                and db.execute('PRAGMA user_version').fetchone()[0]==4 and actual==tuple(sorted(DDL)))
            store._verify(db,head)
            need(head['seq']==head['confirmed_seq']==0 and head['event_sha']==ZERO
                and all(db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]==0 for name in ('cases','events','targets')))
            relation=None
            if historical:
                case=frame._case(policy)
                # anchor() validates original witness, period and current real FD.
                frame.anchor(store.account,db,head,store.binding)
                relation={'prior_transaction':case['prior']['id'],
                    'checkpoint_sha256':next(v[0] for v in frame.checkpoints.values()),
                    'preservation_sha256':digest({'files':case['data']['files'],'members':case['data']['members']}),
                    'old_anchor_pin':case['data']['files'][str(store.anchor)],
                    'old_database_pin':case['data']['files'][str(store.path)],
                    'old_directory_pin':case['data']['directories'][str(store.root)]}
            store._verify(db,head);db.rollback()
            return relation


def verify_current_head(account,binding,anchor,*,reestablish_durability=False):
    """Normal strict consumer: proof permits just this physical transition.

    Once events advance, validate fixed physical identity plus normal SQL/event
    semantics at the caller, never compare or restore the old SQL snapshot.
    """
    record=_records(account)
    if record is None:return
    need(record['state']=='COMMITTED')
    if reestablish_durability:_sync_record(record)
    intent=record['intent'];after=intent['after_anchor']
    need(intent['binding']==binding and anchor['binding']==binding
         and all(anchor[k]==after[k] for k in after if k not in {'seq','confirmed_seq','event_sha'})
         and type(anchor['seq']) is int and anchor['seq']>=after['seq'])
    directory=file_metadata((Path(account)/'draft-revisions').stat())
    database=file_metadata((Path(account)/'draft-revisions/revision.sqlite3').stat())
    need(anchor['root']==[directory['dev'],directory['ino']]
         and anchor['database']==[database['dev'],database['ino']])
    _verify_migration_witness(account,intent)
    if anchor['seq']==0:
        need(anchor==after and _raw(Path(account)/'draft-revisions/revision.sqlite3',128*1024*1024)[0]['sha256']==DB_SHA)


def _query(store,record):
    if record is None:return {'op':OP,'state':'NOT_STARTED'}
    if record['state']=='ARCHIVES_ONLY':return {'op':OP,'state':'ARCHIVES_ONLY'}
    intent=record['intent'];head,fixed,am,raw,dm,dbraw,directory,account=_physical(store)
    need(directory==intent['directory_pin'] and account==intent['account_pin'])
    if record['completion'] is not None:
        verify_current_head(store.account,store.binding,head)
        # Full normal verification accepts later legal events, never old rollback.
        _verify_extending_journal(store,head)
        return {'op':OP,'state':'COMMITTED','cas_replayed':False,
            'durability':'NOT_REESTABLISHED_BY_READ_ONLY_QUERY',
            'old_anchor_sha256':ANCHOR_SHA,'new_anchor_sha256':sha256((canonical(intent['after_anchor'])+'\n').encode()).hexdigest()}
    _verify_migration_witness(store.account,intent)
    before=(canonical(intent['before_anchor'])+'\n').encode()
    after=(canonical(intent['after_anchor'])+'\n').encode()
    need(dm==intent['before_database_pin'] and sha256(dbraw).hexdigest()==DB_SHA)
    if raw==before and am==intent['before_anchor_pin']:
        return {'op':OP,'state':'BEFORE','claim_consumed':record['claim'] is not None}
    if raw==after:
        need(record['claim'] is not None and head['root']==fixed['root'] and head['database']==fixed['database'])
        return {'op':OP,'state':'AFTER_UNCONFIRMED','claim_consumed':True}
    raise WCEError('REVISION_PHYSICAL_RELOCATION_HOLD')


def query_audio_revision(policy):
    """No source issuance, initialization, claim or repair in query."""
    from .draft_revision_guard import identity_binding
    from .own_connection_policy import ConnectionPolicy
    need(type(policy) is ConnectionPolicy and policy.data['connection_id']==CID and policy.data['appid']==APPID)
    policy.check(readonly=True)
    store=RevisionStore(policy.root,digest(identity_binding(policy.data,'OPERATOR_ATTESTED')),
        lambda:policy.check(readonly=True))
    with locked(policy.root/'draft-revision-journal.lock',shared=True,existing=True,readonly=True,nonblocking=True):
        return _query(store,_records(policy.root))


def _complete(record):
    intent=record['intent'];path=record['directory']
    claim,claim_sha=files.read(path/'claim.json')
    value={'schema':1,'profile':PROFILE,'op':OP,'state':'COMMITTED',
        'intent_sha256':record['intent_sha'],'claim_sha256':claim_sha,
        'old_anchor_sha256':ANCHOR_SHA,
        'new_anchor_sha256':sha256((canonical(intent['after_anchor'])+'\n').encode()).hexdigest(),
        'database_sha256':DB_SHA,'origin':'TRUSTED_PHYSICAL_FIELDS_ONLY_CAS'}
    if os.path.lexists(path/'complete.json'):need(files.read(path/'complete.json')[0]==value)
    else:files.exclusive(path/'complete.json',value)
    _sync_record(_records(path.parent.parent))


def relocate_audio_revision(raw,pins,*,deadline,fault=lambda phase:None):
    """Normal internal trusted maintenance action; fixed target, source and op."""
    from .draft_revision_guard import identity_binding
    need(callable(fault))
    with source_scope(raw,pins,deadline) as source:
        policy=checked(source).policy;registry=Path(policy.value['registry_path'])
        need(policy.data['connection_id']==CID and policy.data['appid']==APPID
             and source.evidence['purpose']==PURPOSE
             and source.evidence['identity_sha256']==digest(policy.data))
        with _idle_maintenance_gate(registry) as maintenance_guard,locked(
                registry.parent/'connection-setup.lock',nonblocking=True,existing=True) as setup_fd:
            # Lifetime/start locks are actual idle exclusion. Root's normal idle
            # drain must already have completed; a live owner is HOLD.
            with _account_gate(policy,registry) as account_guard:
                with locked(policy.root/'draft-revision-journal.lock',nonblocking=True,existing=True) as journal_fd:
                    setup_guard=_lock_witness(registry.parent/'connection-setup.lock',setup_fd)
                    journal_guard=_lock_witness(policy.root/'draft-revision-journal.lock',journal_fd)
                    def guard():
                        source.check();maintenance_guard();setup_guard();account_guard();journal_guard()
                        return True
                    guard()
                    for name in ('connection-runtime.json','connection.sock','runtime.json','operator.sock'):
                        need(not os.path.lexists(policy.root/name))
                    store=RevisionStore(policy.root,digest(identity_binding(policy.data,'OPERATOR_ATTESTED')),guard)
                    record=_records(policy.root)
                    if record and record['state']=='COMMITTED':
                        _sync_record(record)
                        guard()
                        # Avoid reacquiring our EX journal lock in _query.
                        head=store._pins();verify_current_head(store.account,store.binding,head)
                        _verify_extending_journal(store,head)
                        return {'op':OP,'state':'COMMITTED','cas_replayed':False,
                            'durability':'REESTABLISHED_AND_INDEPENDENTLY_READBACK'}
                    if record and record['state']!='ARCHIVES_ONLY':
                        intent=record['intent']
                        need(intent['binding']==store.binding
                             and intent['source']['native_user']['source_sha256']==source.evidence['native_user']['source_sha256']
                             and intent['source']['authority_source_sha256']==source.evidence['authority_source_sha256']
                             and intent['source']['owner_digest']==source.evidence['owner_digest'])
                        current=_physical(store)
                        need(current[6]==intent['directory_pin'] and current[7]==intent['account_pin']
                             and current[4]==intent['before_database_pin'])
                        raw_anchor=current[3]
                        if raw_anchor==(canonical(intent['after_anchor'])+'\n').encode():
                            need(record['claim'] is not None)
                            # Post-replace recovery cannot use old witness/pins.
                            _semantics_uncompleted_after(store,policy,intent)
                            sync(store.anchor);sync(store.account,directory=True)
                            guard();_complete(record);fault('after_complete')
                            return {'op':OP,'state':'COMMITTED','cas_replayed':False,
                            'durability':'REESTABLISHED_AND_INDEPENDENTLY_READBACK'}
                        need(raw_anchor==(canonical(intent['before_anchor'])+'\n').encode()
                             and current[2]==intent['before_anchor_pin'])
                    relation=_semantics(store,policy,historical=True)
                    head,fixed,am,before,dm,dbraw,directory,account=_physical(store)
                    need(am['sha256']==ANCHOR_SHA and dm['sha256']==DB_SHA
                         and head['root']!=fixed['root'] and head['database']!=fixed['database'])
                    after=dict(head,root=fixed['root'],database=fixed['database'])
                    path=_dir(policy.root)
                    if record is None:
                        container(policy.root,DIRECTORY);container(policy.root/DIRECTORY,OP)
                    archives={}
                    for name,bytes_ in (('anchor.before.json',before),('database.before.sqlite3',dbraw)):
                        if os.path.lexists(path/name):
                            archives[name],saved=_raw(path/name,len(bytes_));need(saved==bytes_)
                        else:archives[name]=_new_raw(path/name,bytes_)
                    intent={'schema':1,'profile':PROFILE,'op':OP,'purpose':PURPOSE,'connection_id':CID,
                        'binding':store.binding,'source':(record['intent']['source'] if record and 'intent' in record else source.evidence),'migration':relation,
                        'before_anchor':head,'after_anchor':after,'before_anchor_pin':am,'before_database_pin':dm,
                        'directory_pin':directory,'account_pin':account,'archives':archives}
                    fault('before_intent')
                    if record and record['state']!='ARCHIVES_ONLY':need(record['intent']==intent)
                    elif os.path.lexists(path/'intent.json'):need(files.read(path/'intent.json')[0]==intent)
                    else:files.exclusive(path/'intent.json',intent)
                    fault('after_intent');record=_records(policy.root)
                    _sync_record(record)
                    guard()
                    if record['claim'] is None:
                        files.exclusive(path/'claim.json',{'schema':1,'profile':PROFILE,'op':OP,
                            'intent_sha256':record['intent_sha'],'cas_budget':1})
                    fault('after_claim')
                    _sync_record(_records(policy.root))
                    guard()
                    final=_physical(store)
                    need(final==(head,fixed,am,before,dm,dbraw,directory,account))
                    fault('before_replace')
                    _cas(store.anchor,before,am,(canonical(after)+'\n').encode(),guard,fault)
                    fault('after_replace')
                    _semantics_uncompleted_after(store,policy,intent)
                    guard();fault('before_complete');guard();_complete(_records(policy.root));fault('after_complete')
                    verify_current_head(store.account,store.binding,store._pins())
                    return {'op':OP,'state':'COMMITTED','cas_replayed':False,
                        'durability':'REESTABLISHED_AND_INDEPENDENTLY_READBACK',
                        'old_anchor_sha256':ANCHOR_SHA,'new_anchor_sha256':sha256((canonical(after)+'\n').encode()).hexdigest()}


def _semantics_uncompleted_after(store,policy,intent):
    # Narrow local after verification: no proof bypass is installed on the
    # normal store. _head plus explicit exact physical fields and full _verify.
    head,fixed,am,raw,dm,dbraw,directory,account=_physical(store)
    need(head==intent['after_anchor'] and dm==intent['before_database_pin']
         and sha256(dbraw).hexdigest()==DB_SHA and directory==intent['directory_pin']
         and account==intent['account_pin'] and head['root']==fixed['root'] and head['database']==fixed['database'])
    with owned_connection(store.path,readonly=True,timeout=1,isolation_level=None,_revision_header=True) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
        need(db.execute('PRAGMA application_id').fetchone()[0]==APP_ID
             and db.execute('PRAGMA user_version').fetchone()[0]==4
             and tuple(r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql"))==tuple(sorted(DDL)))
        db.execute('BEGIN');store._verify(db,head);db.rollback()
    policy.check()


def _cas(path,before,before_pin,after,guard,fault):
    # Keep the directory FD and original FD until replacement. Temp is an
    # exclusive same-directory private file; no delete/recreate of old head.
    path=Path(path)
    with Reader(path.parent).directory(path.parent) as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        temp='.'+OP+'.anchor.tmp';tempfd=None
        try:
            need(file_metadata(os.fstat(fd))=={k:v for k,v in before_pin.items() if k!='sha256'})
            need(os.pread(fd,len(before)+1,0)==before)
            # A crash-before-replace may leave exactly our temp. Read its real
            # descriptor and require full bytes/mode/owner before reusing it.
            try:tempfd=os.open(temp,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            except FileExistsError:
                tempfd=os.open(temp,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
                info=os.fstat(tempfd)
                need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
                     and stat.S_IMODE(info.st_mode)==0o600 and info.st_gid==before_pin['gid']
                     and info.st_size<=len(after)
                     and os.pread(tempfd,len(after)+1,0)==after[:info.st_size])
                offset=info.st_size;os.lseek(tempfd,offset,os.SEEK_SET)
                while offset<len(after):
                    guard();n=os.write(tempfd,after[offset:]);need(n>0);offset+=n
                    fault('temp_write')
            else:
                os.fchmod(tempfd,0o600)
                os.fchown(tempfd,before_pin['uid'],before_pin['gid'])
                offset=0
                while offset<len(after):
                    guard();n=os.write(tempfd,after[offset:]);need(n>0);offset+=n
                    fault('temp_write')
            os.fsync(tempfd);fault('temp_fsync')
            guard()
            need(file_metadata(os.fstat(fd))=={k:v for k,v in before_pin.items() if k!='sha256'}
                 and file_metadata(os.stat(path.name,dir_fd=parent,follow_symlinks=False))==file_metadata(os.fstat(fd))
                 and os.pread(fd,len(before)+1,0)==before)
            t=os.fstat(tempfd)
            need(stat.S_ISREG(t.st_mode) and t.st_uid==before_pin['uid']
                 and t.st_gid==before_pin['gid'] and stat.S_IMODE(t.st_mode)==0o600
                 and t.st_nlink==1 and t.st_size==len(after)
                 and os.pread(tempfd,len(after)+1,0)==after
                 and file_metadata(os.stat(temp,dir_fd=parent,follow_symlinks=False))==file_metadata(t))
            guard()
            need(files.folder(path.parent)==(os.fstat(parent).st_dev,os.fstat(parent).st_ino)
                 and file_metadata(os.fstat(fd))=={k:v for k,v in before_pin.items() if k!='sha256'}
                 and file_metadata(os.stat(path.name,dir_fd=parent,follow_symlinks=False))==file_metadata(os.fstat(fd))
                 and os.pread(fd,len(before)+1,0)==before
                 and file_metadata(os.fstat(tempfd))==file_metadata(t)
                 and file_metadata(os.stat(temp,dir_fd=parent,follow_symlinks=False))==file_metadata(t))
            os.replace(temp,path.name,src_dir_fd=parent,dst_dir_fd=parent)
            fault('replace_before_dir_fsync');os.fsync(parent);fault('after_dir_fsync')
        finally:
            if tempfd is not None:os.close(tempfd)
            os.close(fd)
    meta,actual=_raw(path,16384);need(actual==after)


def _verify_extending_journal(store,head):
    with owned_connection(store.path,readonly=True,timeout=1,isolation_level=None,_revision_header=True) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
        need(db.execute('PRAGMA application_id').fetchone()[0]==APP_ID
             and db.execute('PRAGMA user_version').fetchone()[0] in (4,5)
             and tuple(r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql"))==tuple(sorted(DDL)))
        db.execute('BEGIN');store._verify(db,head);db.rollback()


def _verify_migration_witness(account,intent):
    # Reopen the real current migration graph, never a caller-selected CP. The
    # old anchor archive supplies old bytes; its old checkpoint pin stays old.
    from .own_connection_policy import load_policy
    policy=load_policy(Path(account)/'connection-policy.json')
    need(policy.data['connection_id']==CID and policy.data['appid']==APPID
         and intent['source']['purpose']==PURPOSE
         and intent['source']['identity_sha256']==digest(policy.data))
    database=Path(account)/'draft-revisions/revision.sqlite3'
    with owned_connection(database,readonly=True,timeout=1,isolation_level=None,_revision_header=True) as db:
        with revision_read_scope(policy,db) as frame:
            case=frame._case(policy);saved=intent['migration']
            need(saved=={'prior_transaction':case['prior']['id'],
                'checkpoint_sha256':next(v[0] for v in frame.checkpoints.values()),
                'preservation_sha256':digest({'files':case['data']['files'],'members':case['data']['members']}),
                'old_anchor_pin':case['data']['files'][str(Path(account)/'draft-revision-safety-anchor.json')],
                'old_database_pin':case['data']['files'][str(database)],
                'old_directory_pin':case['data']['directories'][str(database.parent)]})
            need(saved['old_anchor_pin']['sha256']==ANCHOR_SHA
                 and saved['old_database_pin']['sha256']==DB_SHA
                 and saved['old_directory_pin']==intent['directory_pin']
                 and [saved['old_database_pin'][k] for k in ('dev','ino')]==intent['after_anchor']['database']
                 and intent['before_anchor']['root']==[case['prior']['registry_parent'][0],saved['old_directory_pin']['ino']]
                 and intent['before_anchor']['database']==[case['prior']['registry_parent'][0],saved['old_database_pin']['ino']])


@contextmanager
def _idle_maintenance_gate(registry):
    """Own the existing shared execution exclusion, without issuing stop writes.

    Root completes normal idle drain first. Any active executor conflicts with
    the existing EX lock. An inactive other-account pointer is preserved byte
    for byte; this fixed maintenance action never cancels another batch.
    """
    from .own_replacement_batch import _maintenance_pointers,base
    with _maintenance_pointers(registry) as (families,present,guard):
        guard()
        if not present:
            yield guard;guard();return
        with locked(base(registry)/'execution.lock',nonblocking=True,existing=True) as execution_fd:
            with _maintenance_pointers(registry) as (again,still_present,fresh):
                need(still_present is True and again==families)
                execution_guard=_lock_witness(base(registry)/'execution.lock',execution_fd)
                def held():
                    fresh();guard();execution_guard()
                    return True
                held();yield held;held()


def _sync_record(record):
    """Reestablish exact visible record durability before trusting/continuing it.

    A visible file is not proof that its earlier fsync completed. Every existing
    required file and each newly introduced directory link is synced again,
    then independently reopened. No bytes, claims, budgets or IDs are changed.
    """
    path=record['directory'];need(record['state']!='ARCHIVES_ONLY')
    names=['anchor.before.json','database.before.sqlite3','intent.json']
    if record['claim'] is not None:names.append('claim.json')
    if record['completion'] is not None:names.append('complete.json')
    for name in names:sync(path/name)
    for directory in (path,path.parent,path.parent.parent):sync(directory,directory=True)
    need(_records(path.parent.parent)==record)


@contextmanager
def _account_gate(policy,registry):
    """Normal lifetime -> stable/local draft writer -> policy -> journal order."""
    from .publication_lock import draft_writer,_writer_guard
    root=policy.root
    # These established domains must exist. Maintenance cannot create a weaker
    # local-only writer lane by silently repairing missing coordination state.
    need(os.path.lexists(root/'publication-dispatch.lock'))
    with locked(root/'connection-start.lock',nonblocking=True,existing=True) as start_fd:
        with locked(root/'connection.lock',nonblocking=True,existing=True) as lifetime_fd:
            with draft_writer(root,policy.data['appid']):
                with locked(root/'connection-policy.lock',nonblocking=True,existing=True) as policy_fd:
                    with locked(registry.parent/'connections.lock',nonblocking=True,existing=True) as registry_fd:
                        writer=_writer_guard(root,policy.data['appid'])
                        witnesses=[_lock_witness(path,fd) for path,fd in (
                            (root/'connection-start.lock',start_fd),(root/'connection.lock',lifetime_fd),
                            (root/'connection-policy.lock',policy_fd),(registry.parent/'connections.lock',registry_fd))]
                        def held():
                            need(writer() is True)
                            for witness in witnesses:witness()
                            return True
                        held();yield held;held()


def _lock_witness(path,fd):
    """Capture only a real held descriptor, not a caller's lock boolean/pin."""
    path=Path(path);pin=file_metadata(os.fstat(fd));parent=files.folder(path.parent)
    def held():
        current=os.fstat(fd);named=path.lstat()
        need(stat.S_ISREG(current.st_mode) and stat.S_ISREG(named.st_mode)
             and current.st_uid==os.getuid() and stat.S_IMODE(current.st_mode)==0o600
             and current.st_nlink==1 and current.st_size==0
             and file_metadata(current)==pin==file_metadata(named)
             and files.folder(path.parent)==parent)
        return True
    held();return held
