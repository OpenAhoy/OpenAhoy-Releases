"""Explicit user-clicked support reports, immutable snapshots and GitHub receipts.

Uses existing gh identity only. No token reads, OAuth, login or background send.
"""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import subprocess
import urllib.parse
import uuid

from .support_diagnostics import Diagnostics, private_directory, private_file
from .support_privacy import redact
from .own_configuration_export import _directory

REPOSITORY = 'OpenAhoy/OpenAhoy-Feedback'
MARKER = 'OpenAhoy-feedback:'
FIELDS = ('description','steps','expected','actual')


class GitHubUnavailable(Exception):
    def __init__(self, http_status=None):
        self.http_status=http_status if type(http_status)is int and http_status in {400,401,403,404,422,429}else None
        super().__init__('GITHUB_REJECTED' if self.http_status else 'GITHUB_UNAVAILABLE')


class GitHub:
    def request(self, endpoint, payload=None):
        if not shutil.which('gh'):
            raise GitHubUnavailable()
        command = ['gh','api','--hostname','github.com',endpoint]
        if payload is not None:
            command += ['-X','POST','--input','-']
        try:
            result = subprocess.run(command,input=json.dumps(payload) if payload is not None else None,
                capture_output=True,text=True,timeout=20,stdin=None if payload is not None else subprocess.DEVNULL)
            if result.returncode != 0:
                match=re.search(r'HTTP (400|401|403|404|422|429)\b',result.stderr)
                raise GitHubUnavailable(int(match.group(1))if match else None)
            if len(result.stdout) > 2*1024*1024:
                raise GitHubUnavailable()
            return json.loads(result.stdout)
        except (OSError,subprocess.SubprocessError,ValueError):
            raise GitHubUnavailable() from None

    def available(self):
        try:
            value = self.request('user')
            return type(value) is dict and type(value.get('id')) is int
        except GitHubUnavailable:
            return False

    def create(self, repository, title, body):
        return self.request('repos/'+repository+'/issues',{'title':title,'body':body})

    def find(self, repository, marker):
        query = urllib.parse.quote('repo:'+repository+' "'+marker+'" in:body',safe='')
        result = self.request('search/issues?q='+query+'&per_page=100')
        return result.get('items',[]) if type(result) is dict else []


class Support:
    def __init__(self, root, *, version, github=None, repository=REPOSITORY, downloads=None):
        self.root = Path(root)
        self.version = version if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version) else 'unknown'
        if not re.fullmatch(r'OpenAhoy/OpenAhoy-Feedback',repository):
            raise ValueError('SUPPORT_REPOSITORY_INVALID')
        self.repository, self.github = repository, github or GitHub()
        self.downloads = Path(downloads) if downloads is not None else Path.home()/'Downloads'
        self.logs = Diagnostics(self.root)

    @contextmanager
    def _db(self):
        root=private_directory(self.root)
        fd=private_file(root/'feedback.sqlite3',os.O_RDWR|os.O_CREAT);os.close(fd)
        db=sqlite3.connect(root/'feedback.sqlite3',timeout=2)
        try:
            with db:
                db.execute('PRAGMA journal_mode=DELETE')
                db.execute('CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,digest TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,url TEXT)')
                yield db
        finally:
            db.close()

    def _put(self, value):
        raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(raw.encode()).hexdigest()
        with self._db() as db:
            db.execute('INSERT INTO reports VALUES(?,?,?,?,NULL)',(value['report_id'],digest,raw,'PREPARED'))
        return self._get(value['report_id'],digest)

    def _get(self, report_id, digest):
        if type(report_id) is not str or not re.fullmatch('[a-f0-9]{32}',report_id) or type(digest) is not str or not re.fullmatch('[a-f0-9]{64}',digest):
            raise ValueError('SUPPORT_REPORT_INVALID')
        with self._db() as db:
            row=db.execute('SELECT payload,state,url,digest FROM reports WHERE id=?',(report_id,)).fetchone()
        if row is None or row[3]!=digest or hashlib.sha256(row[0].encode()).hexdigest()!=digest:
            raise ValueError('SUPPORT_REPORT_INVALID')
        value=json.loads(row[0])
        return dict(value,digest=digest,state=row[1],url=row[2])

    def read(self):
        with self._db()as db:
            rows=db.execute("SELECT id,digest,payload,state FROM reports WHERE state IN ('PENDING','WEB_DRAFT') ORDER BY rowid DESC").fetchall()
        pending=[]
        for rid,digest,raw,state in rows:
            if hashlib.sha256(raw.encode()).hexdigest()!=digest:continue
            value=json.loads(raw)
            if value.get('kind')=='feedback' and value.get('source','app')=='app':pending.append({'report_id':rid,'digest':digest,'title':value['title'],'state':state})
        return {'repository':self.repository,'diagnostics':self.logs.snapshot(), 'pending':pending,
            'version':self.version,'privacy':'LOCAL_ONLY; sanitized diagnostics attach only on explicit submit'}

    def open_report(self, report_id, digest):
        return self._get(report_id,digest)

    def preview(self, fields, selected_platform, *, source=None):
        if type(fields) is not dict or set(fields)!=set(FIELDS) or selected_platform not in {'wechat','x','general','updates'}:
            raise ValueError('SUPPORT_REPORT_INVALID')
        clean={key:redact(fields[key]) for key in FIELDS}
        if not clean['description']:
            clean['description']='功能异常或使用问题（自动诊断反馈）'
        rid=uuid.uuid4().hex
        title='[OpenAhoy '+self.version+'] '+clean['description'].splitlines()[0][:100]
        environment={'version':self.version,'platform':selected_platform,
            'system':platform.system() if platform.system() in {'Darwin','Windows','Linux'} else 'Other',
            'architecture':platform.machine() if platform.machine() in {'arm64','x86_64','aarch64','AMD64'} else 'Other'}
        body='## 问题\n'+clean['description']
        for key,label in [('steps','复现步骤'),('expected','预期'),('actual','实际')]:
            if clean[key]:body+='\n\n## '+label+'\n'+clean[key]
        events=self.logs.snapshot()['events']
        failures=[e for e in events if e.get('code')not in {None,'PARSED_SUCCESS'} or e['result']in {'TOOL_ERROR','CHECK_UNAVAILABLE','UNKNOWN','ACTION_REQUIRED'}][-20:]
        selected={e['report_id']:e for e in failures+events[-20:]}
        attached=list(selected.values())
        marker='\n\n<!-- '+MARKER+rid+' -->'
        body+='\n\n## 环境\n'+json.dumps(environment,ensure_ascii=False)+'\n\n## 自动附加的脱敏诊断\n```json\n'+json.dumps(attached,ensure_ascii=False,indent=2)+'\n```'+marker
        # A browser URL has a finite carrier. Keep an automatically filled,
        # frozen diagnostic summary instead of asking users to paste logs.
        web_body=body
        def url_length(text):
            return len('https://github.com/'+self.repository+'/issues/new?'+urllib.parse.urlencode({'title':title,'body':text}))
        if url_length(web_body)>7500:
            compact={e['report_id']:e for e in failures[-5:]+events[-3:]}
            lines=[e['at']+' '+e.get('tool',e['module'])+' '+e['result']+' '+e.get('code','')+
                (' http_status='+str(e['http_status'])if 'http_status'in e else '')+
                (' phase='+e['operation_phase']if 'operation_phase'in e else '')+
                (' response='+','.join(k+':'+v for k,v in e['relay_response'].items())if e.get('relay_response') else '')+
                (' error_kind='+e['error_kind']if 'error_kind'in e else '')+
                (' proof_check='+e['proof_check']if 'proof_check'in e else '')+
                (' fields='+','.join(e['different_fields'])if e.get('different_fields')else '')+
                (' differences='+str(e['difference_count'])if 'difference_count'in e else '')+
                (' candidate_created='+str(e['candidate_created'])if 'candidate_created'in e else '')+
                (' retired='+str(e['source_retired_count'])+'/'+str(e.get('source_container_count',''))if 'source_retired_count'in e else '')
                for e in compact.values()]
            description=clean['description'][:300]
            while True:
                web_body='## 问题\n'+description+'\n\n## 环境\n'+json.dumps(environment,ensure_ascii=False)+'\n\n## 自动附加的脱敏诊断\n'+'\n'.join(lines)+'\n\n完整诊断保留在本机，以上摘要已自动附加。'+marker
                if url_length(web_body)<=7500:break
                if len(description)>40:description=description[:len(description)//2]
                elif len(lines)>1:lines=lines[:-1]
                else:raise ValueError('SUPPORT_DRAFT_CARRIER_INVALID')
        report = {'report_id':rid,'kind':'feedback','repository':self.repository,'title':title,'body':body,'web_body':web_body}
        if source is not None:
            report['source'] = source
        return self._put(report)

    def diagnostics(self):
        rid=uuid.uuid4().hex
        return self._put({'report_id':rid,'kind':'diagnostics','repository':self.repository,
            'title':'OpenAhoy 脱敏诊断日志','body':json.dumps(self.logs.snapshot(),ensure_ascii=False,indent=2)+'\n'})

    def _result(self, row):
        result={key:row.get(key)for key in ('report_id','digest','state','url')}
        if re.fullmatch(r'REJECTED_(400|401|403|404|422|429)',row['state']):
            result.update(state='REJECTED',http_status=int(row['state'].split('_')[1]))
        return result

    def _issue(self, value, row):
        if type(value) is not dict or type(value.get('number')) is not int or value['number']<1:
            return None
        expected='https://github.com/'+self.repository+'/issues/'+str(value['number'])
        return expected if value.get('html_url')==expected else None

    def _feedback(self, report_id, digest, source):
        row = self._get(report_id, digest)
        if row['kind'] != 'feedback' or row.get('source', 'app') != source:
            raise ValueError('SUPPORT_REPORT_INVALID')
        return row

    def send(self, report_id, digest, *, source='app'):
        row = self._feedback(report_id, digest, source)
        if row['state']!='PREPARED':return self.status(report_id,digest,source=source)
        if not self.github.available():
            url='https://github.com/'+self.repository+'/issues/new?'+urllib.parse.urlencode({'title':row['title'],'body':row.get('web_body',row['body'])})
            # Browsers have finite URL carriers; preserve full report for copy/export.
            if len(url)>7500:url='https://github.com/'+self.repository+'/issues/new?'+urllib.parse.urlencode({'title':row['title'],'body':'请粘贴 OpenAhoy 反馈预览中的已脱敏内容。\n\n<!-- '+MARKER+report_id+' -->'})
            with self._db()as db:db.execute('UPDATE reports SET state=?,url=? WHERE id=? AND state=?',('WEB_DRAFT',url,report_id,'PREPARED'))
            return self._result(self._get(report_id,digest))
        with self._db()as db:
            change=db.execute('UPDATE reports SET state=? WHERE id=? AND state=?',('PENDING',report_id,'PREPARED')).rowcount
        if not change:return self.status(report_id,digest,source=source)
        try:
            result=self.github.create(self.repository,row['title'],row['body'])
            url=self._issue(result,row)
            if url:
                with self._db()as db:db.execute('UPDATE reports SET state=?,url=? WHERE id=?',('SUBMITTED',url,report_id))
        except GitHubUnavailable as error:
            if error.http_status:
                with self._db()as db:db.execute('UPDATE reports SET state=? WHERE id=?',('REJECTED_'+str(error.http_status),report_id))
        except Exception:
            pass  # Original request is now PENDING; never POST a second time.
        return self._result(self._get(report_id,digest))

    def status(self, report_id, digest, *, source='app'):
        row = self._feedback(report_id, digest, source)
        if row['state']not in {'PENDING','WEB_DRAFT'}:return self._result(row)
        try:
            matches=[]
            for item in self.github.find(self.repository,MARKER+report_id):
                url=self._issue(item,row)
                if url and item.get('body') in {row['body'],row.get('web_body',row['body'])}:matches.append(url)
            if len(matches)==1:
                with self._db()as db:db.execute('UPDATE reports SET state=?,url=? WHERE id=?',('SUBMITTED',matches[0],report_id))
        except Exception:
            pass
        return self._result(self._get(report_id,digest))

    def export(self, report_id, digest, action):
        if action not in {'write','query'}:raise ValueError('SUPPORT_EXPORT_INVALID')
        row=self._get(report_id,digest);raw=row['body'].encode();filename='OpenAhoy-诊断-'+report_id+'.txt'
        directory=_directory(self.downloads)
        try:
            try:
                fd=os.open(filename,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            except FileNotFoundError:
                if action=='query':return {'state':'EXPORT_NOT_FOUND','report_id':report_id}
                fd=os.open(filename,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
                try:
                    view=memoryview(raw)
                    while view:view=view[os.write(fd,view):]
                    os.fsync(fd)
                finally:os.close(fd)
                fd=os.open(filename,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            try:
                import stat
                s=os.fstat(fd)
                if not stat.S_ISREG(s.st_mode)or s.st_nlink!=1 or s.st_uid!=os.getuid()or s.st_mode&0o077:
                    raise ValueError('SUPPORT_EXPORT_CONFLICT')
                parts=[]
                while True:
                    block=os.read(fd,65536)
                    if not block:break
                    parts.append(block)
                    if sum(map(len,parts))>len(raw):raise ValueError('SUPPORT_EXPORT_CONFLICT')
                if b''.join(parts)!=raw:raise ValueError('SUPPORT_EXPORT_CONFLICT')
            finally:os.close(fd)
            return {'state':'EXPORTED','report_id':report_id,'destination':'Downloads','filename':filename,
                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        finally:os.close(directory)
