"""Immutable logical slots: maintenance metadata cannot create a second slot."""
from contextlib import closing,contextmanager
from hashlib import sha256
from pathlib import Path
import base64,json,os,sqlite3,stat
from .draft_revision_native_source import require,canonical,checked_guard
from .own_bootstrap_security import path_check
from .own_connection_policy import locked
from .own_history_source import owned_connection,connection_source

SCHEMA='''
CREATE TABLE owner(binding TEXT PRIMARY KEY);
CREATE TABLE slots(logical_sha TEXT PRIMARY KEY, handle TEXT UNIQUE NOT NULL, content_sha TEXT NOT NULL, envelope TEXT NOT NULL);
CREATE TABLE producer_progress(producer_key TEXT PRIMARY KEY, registration TEXT NOT NULL, cursor INTEGER NOT NULL);
CREATE TABLE pending_facts(producer_key TEXT NOT NULL,item_id TEXT NOT NULL,fact_json TEXT NOT NULL,state TEXT NOT NULL,handle TEXT,PRIMARY KEY(producer_key,item_id));
CREATE INDEX pending_state ON pending_facts(producer_key,state);
CREATE TABLE draft_refs(account_sha TEXT NOT NULL,reference_sha TEXT NOT NULL,logical_sha TEXT NOT NULL,PRIMARY KEY(account_sha,reference_sha));
CREATE TRIGGER slots_no_update BEFORE UPDATE ON slots BEGIN SELECT RAISE(ABORT,'immutable slot'); END;
CREATE TRIGGER slots_no_delete BEFORE DELETE ON slots BEGIN SELECT RAISE(ABORT,'immutable slot'); END;
CREATE TRIGGER refs_no_update BEFORE UPDATE ON draft_refs BEGIN SELECT RAISE(ABORT,'immutable original draft'); END;
CREATE TRIGGER refs_no_delete BEFORE DELETE ON draft_refs BEGIN SELECT RAISE(ABORT,'immutable original draft'); END;
'''

def fingerprint(value):return sha256(canonical(value)).hexdigest()


class SlotStore:
    def __init__(self,directory,owner_sha,guard):
        self.directory=Path(directory);self.pin=path_check(self.directory,True);self.owner=owner_sha;self.guard=guard
        self.path=self.directory/'completed-slots.sqlite3';self.lock=self.directory/'completed-slots.lock'
    def check(self):
        checked_guard(self.guard);require(path_check(self.directory,True)==self.pin,'SLOT_STORE_CHANGED')
    @contextmanager
    def _db(self,write=False):
        self.check()
        with locked(self.lock,nonblocking=True):
            if not os.path.lexists(self.path):
                fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.fsync(fd);os.close(fd)
            info=self.path.lstat();require(stat.S_ISREG(info.st_mode)and info.st_uid==os.getuid()
                and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'SLOT_STORE_CHANGED')
            with owned_connection(self.path,readonly=False,timeout=0,isolation_level=None)as db:
                db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
                if info.st_size==0 and db.execute('PRAGMA user_version').fetchone()[0]==0 and not db.execute('SELECT name FROM sqlite_master').fetchone():
                    db.executescript('BEGIN IMMEDIATE;'+SCHEMA);db.execute('INSERT INTO owner VALUES(?)',(self.owner,));db.execute('PRAGMA user_version=1');db.commit()
                require(db.execute('PRAGMA user_version').fetchone()[0]==1
                    and db.execute('SELECT binding FROM owner').fetchall()==[(self.owner,)],'SLOT_STORE_OWNER_CHANGED')
                # Derived, account-local cursor index; original immutable
                # envelopes and logical keys are not migrated or rewritten.
                db.execute("CREATE INDEX IF NOT EXISTS slots_account_cursor ON slots("
                    "json_extract(envelope,'$.logical.appid'),json_extract(envelope,'$.logical.principal'),"
                    "json_extract(envelope,'$.logical.tenant'))")
                db.execute('BEGIN IMMEDIATE'if write else'BEGIN')
                try:
                    yield db;self.check();connection_source(db).guard()
                    if write:db.commit()
                    else:db.rollback()
                    fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:os.fsync(fd)
                    finally:os.close(fd)
                finally:
                    if db.in_transaction:db.rollback()
    def cursor(self,key,registration):
        with self._db()as db:
            row=db.execute('SELECT registration,cursor FROM producer_progress WHERE producer_key=?',(key,)).fetchone()
            require(row is None or row[0]==registration,'SLOT_PRODUCER_CONTINUITY_REQUIRED')
            return 0 if row is None else row[1]
    def record_scan(self,key,registration,before,after,facts):
        with self._db(True)as db:
            row=db.execute('SELECT registration,cursor FROM producer_progress WHERE producer_key=?',(key,)).fetchone()
            require((row is None and before==0)or row==(registration,before),'SLOT_PRODUCER_CURSOR_CHANGED')
            for fact in facts:
                encoded=canonical(fact).decode();old=db.execute('SELECT fact_json FROM pending_facts WHERE producer_key=? AND item_id=?',(key,fact['item_id'])).fetchone()
                require(old is None or old==(encoded,),'SLOT_PRODUCER_FACT_CONFLICT')
                if old is None:db.execute("INSERT INTO pending_facts VALUES(?,?,?,'PENDING',NULL)",(key,fact['item_id'],encoded))
            db.execute('INSERT INTO producer_progress VALUES(?,?,?) ON CONFLICT(producer_key) DO UPDATE SET cursor=excluded.cursor',(key,registration,after))
    def pending(self,key,limit):
        with self._db()as db:
            return [json.loads(row[0])for row in db.execute("SELECT fact_json FROM pending_facts WHERE producer_key=? AND state='PENDING' ORDER BY rowid LIMIT ?",(key,limit))]
    def finish_fact(self,key,item_id,handle):
        with self._db(True)as db:
            row=db.execute('SELECT state,handle FROM pending_facts WHERE producer_key=? AND item_id=?',(key,item_id)).fetchone()
            require(row is not None and(row[0]=='PENDING'or row==('FROZEN',handle)),'SLOT_PRODUCER_FACT_CONFLICT')
            db.execute("UPDATE pending_facts SET state='FROZEN',handle=? WHERE producer_key=? AND item_id=?",(handle,key,item_id))

    def freeze(self,logical,content,envelope):
        logical_sha=fingerprint(logical);content_sha=fingerprint(content);handle='completed-slot-'+logical_sha[:48]
        frozen={'schema':1,'authority':False,'handle':handle,'logical':logical,'logical_sha256':logical_sha,
            'content_sha256':content_sha,'content':content,'frozen_evidence':envelope}
        with self._db(True)as db:
            old=db.execute('SELECT envelope,content_sha FROM slots WHERE logical_sha=?',(logical_sha,)).fetchone()
            if old is not None:
                require(old[1]==content_sha,'SLOT_FROZEN_CONTENT_CONFLICT');return json.loads(old[0])
            account=fingerprint({'appid':logical['appid'],'principal':logical['principal'],'tenant':logical['tenant']})
            prior_assignments=[]
            for group in content['groups']:
                ref=fingerprint(group['reference']);previous=db.execute('SELECT logical_sha FROM draft_refs WHERE account_sha=? AND reference_sha=?',(account,ref)).fetchone()
                if previous is None:db.execute('INSERT INTO draft_refs VALUES(?,?,?)',(account,ref,logical_sha))
                elif previous[0]!=logical_sha:
                    prior_assignments.append({'reference_sha256':ref,'original_logical_sha256':previous[0],
                        'state':'PRIOR_SOURCE_ASSOCIATION_ONLY_NOT_NEW_SEND_RIGHT'})
            frozen['prior_reference_ownership']=prior_assignments
            db.execute('INSERT INTO slots VALUES(?,?,?,?)',(logical_sha,handle,content_sha,canonical(frozen).decode()))
        require(self.read(handle)==frozen,'SLOT_FREEZE_RESULT_UNKNOWN');return frozen
    def _page_position(self,account,cursor):
        require(type(account)is dict and set(account)=={'appid','principal','tenant'}
            and all(type(v)is str and v for v in account.values()),'SLOT_PAGE_ACCOUNT_INVALID')
        if cursor is None:return 0
        require(type(cursor)is str and cursor.startswith('slot-page-v1.') and len(cursor)<=1024,
            'SLOT_PAGE_CURSOR_INVALID')
        encoded=cursor[len('slot-page-v1.'):]
        try:
            raw=base64.b64decode(encoded+'='*(-len(encoded)%4),altchars=b'-_',validate=True)
            value=json.loads(raw)
        except (ValueError,UnicodeError,TypeError):
            require(False,'SLOT_PAGE_CURSOR_INVALID')
        require(type(value)is dict and set(value)=={'owner_sha256','account_sha256','after_rowid'}
            and value['owner_sha256']==self.owner and value['account_sha256']==fingerprint(account)
            and type(value['after_rowid'])is int and 0<=value['after_rowid']<=2**63-1
            and canonical(value)==raw
            and base64.urlsafe_b64encode(raw).decode().rstrip('=')==encoded,'SLOT_PAGE_CURSOR_INVALID')
        return value['after_rowid']

    def _page_cursor(self,account,after):
        raw=canonical({'owner_sha256':self.owner,'account_sha256':fingerprint(account),'after_rowid':after})
        return 'slot-page-v1.'+base64.urlsafe_b64encode(raw).decode().rstrip('=')

    def frozen_page(self,account,cursor=None):
        """One full original Slot, not a grant or a whole-history scan.

        The cursor binds only stable account/owner and listing position. It is
        deliberately not a signed permission or a current code/CUP identity.
        """
        after=self._page_position(account,cursor)
        with self._db()as db:
            rows=db.execute("SELECT rowid,handle,envelope FROM slots INDEXED BY slots_account_cursor WHERE "
                "json_extract(envelope,'$.logical.appid')=? AND json_extract(envelope,'$.logical.principal')=? "
                "AND json_extract(envelope,'$.logical.tenant')=? AND rowid>? ORDER BY rowid LIMIT 2",
                (account['appid'],account['principal'],account['tenant'],after)).fetchall()
        selected=[]
        for rowid,handle,encoded in rows[:1]:
            value=json.loads(encoded)
            require(value['handle']==handle and fingerprint(value['logical'])==value['logical_sha256']
                and fingerprint(value['content'])==value['content_sha256']
                and {k:value['logical'][k]for k in account}==account,'SLOT_FROZEN_RECORD_CHANGED')
            selected.append({'rowid':rowid,'frozen':value});after=rowid
        return {'items':selected,'has_more':len(rows)>1,'next_cursor':self._page_cursor(account,after)}

    def read(self,handle):
        with self._db()as db:
            row=db.execute('SELECT envelope FROM slots WHERE handle=?',(handle,)).fetchone()
            require(row is not None,'SLOT_HANDLE_UNKNOWN');value=json.loads(row[0])
            require(value['handle']==handle and fingerprint(value['logical'])==value['logical_sha256']
                and fingerprint(value['content'])==value['content_sha256'],'SLOT_FROZEN_RECORD_CHANGED')
            return value
