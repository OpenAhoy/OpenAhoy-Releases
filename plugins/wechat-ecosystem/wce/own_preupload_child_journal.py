"""Durable technical-child once records for the one original stopped phase.

This grants no business request or budget. A missing terminal never means a
dead child or permission to start again. Only the actual Popen owner records a
terminal after its own handle was reaped; slot once/UNKNOWN gates are separate.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import threading

from .contracts import WCEError
from .draft_group_pin_resources import capacity,close_all,full
from .own_bootstrap_security import path_check
from .own_connection_policy import locked
from .service import canonical


def need(value):
    if value is not True:raise WCEError('PREUPLOAD_CHILD_ONCE_HOLD')


class TechnicalChildJournal:
    """Mechanical owned handle. It is not a runtime Entry or sender."""
    def __init__(self,root,*,ordinal,resume_id,phase_sha,binding_sha):
        from .own_preupload_journal import _HASH
        need(type(ordinal) is int and 1<=ordinal<=109)
        for value in (phase_sha,binding_sha):need(type(value) is str and _HASH.fullmatch(value) is not None)
        import re
        need(type(resume_id) is str and re.fullmatch(r'preupload-resume-[0-9a-f]{32}',resume_id) is not None)
        self.root=Path(root);path_check(self.root,True)
        self.ordinal,self.resume_id=ordinal,resume_id
        self.phase_sha,self.binding_sha=phase_sha,binding_sha
        self.owner=(os.getpid(),threading.get_ident());self.closed=False
        self.records=[];self.parent=None;self.created_pid=None;self.terminal=False
        self.process=None;self.popen_attempted=False
        capacity(1,persistent=True)
        self.parent=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(self.parent)
            need(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700)
            self.root_pin=full(info)[:5]
            self.check()
        except BaseException as error:self.close(original=error);raise

    def _name(self,ordinal,kind):return f'preupload-child-{ordinal:03d}-{kind}.json'

    def check(self):
        need(not self.closed and self.owner==(os.getpid(),threading.get_ident())
             and self.root_pin==full(os.fstat(self.parent))[:5]==full(self.root.lstat())[:5])
        for leaf,fd,pin,raw in self.records:
            need(full(os.fstat(fd))==pin==full(os.stat(leaf,dir_fd=self.parent,follow_symlinks=False))
                 and os.pread(fd,len(raw)+1,0)==raw)

    def _read(self,ordinal,kind,*,retain=False):
        self.check();leaf=self._name(ordinal,kind)
        capacity(1,persistent=True)
        fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.parent)
        held=False;original=None
        try:
            info=os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
                 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and 0<info.st_size<=16384)
            raw=os.pread(fd,16385,0)
            need(len(raw)==info.st_size and full(info)==full(os.fstat(fd))
                 ==full(os.stat(leaf,dir_fd=self.parent,follow_symlinks=False)))
            from .own_preupload_sources import _json
            value=_json(raw)
            if retain:
                self.records.append((leaf,fd,full(info),raw));held=True
            return value,sha256(raw).hexdigest()
        except BaseException as error:
            original=error
            raise
        finally:
            # Inspect actual ownership, including an interrupt immediately
            # after append but before a local flag can be updated.
            if not any(record[1]==fd for record in self.records):
                close_all([lambda:os.close(fd)],original)

    def _create(self,kind,value):
        self.check();leaf=self._name(self.ordinal,kind);raw=canonical(value).encode()
        need(len(raw)<=16384);capacity(1,persistent=True)
        fd=os.open(leaf,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.parent)
        try:
            remaining=memoryview(raw)
            while remaining:
                amount=os.write(fd,remaining);need(amount>0);remaining=remaining[amount:]
            os.fsync(fd);os.fsync(self.parent)
            record=(leaf,fd,full(os.fstat(fd)),raw)
            self.records.append(record)
            self.check()
            return sha256(raw).hexdigest()
        except BaseException as original:
            if not any(record[1]==fd for record in self.records):
                close_all([lambda:os.close(fd)],original)
            raise  # Partial/unknown creation stays consumed; never unlink.

    def reserve(self,previous_terminal_ref):
        self.check();need(not self.records)
        capacity(2,persistent=True)  # locked() opens its parent and lock leaf.
        scope=locked(self.root/'preupload-child-start.lock',nonblocking=True)
        scope.__enter__()
        original=None
        try:
            self.check()
            for ordinal in range(self.ordinal,110):
                need(not any(os.path.lexists(self.root/self._name(ordinal,kind))
                    for kind in ('claim','created','terminal')))
            last_sha=None
            for ordinal in range(1,self.ordinal):
                claim,claim_sha=self._read(ordinal,'claim')
                terminal,terminal_sha=self._read(ordinal,'terminal')
                self._require_terminal_chain_in(ordinal,claim,claim_sha,terminal,last_sha)
                last_sha=terminal_sha
            if self.ordinal==1:need(previous_terminal_ref is None)
            else:
                need(type(previous_terminal_ref) is dict and set(previous_terminal_ref)=={'path','sha256','bytes'}
                     and previous_terminal_ref['path']==str(self.root/self._name(self.ordinal-1,'terminal'))
                     and previous_terminal_ref['sha256']==last_sha
                     and type(previous_terminal_ref['bytes']) is int
                     and previous_terminal_ref['bytes']==len(canonical(terminal).encode()))
            self.claim_sha=self._create('claim',{'schema':1,'profile':'PREUPLOAD_TECHNICAL_CHILD_CLAIM_V1',
                'authority':False,'ordinal':self.ordinal,'resume_id':self.resume_id,
                'phase_sha256':self.phase_sha,'binding_sha256':self.binding_sha,
                'parent_pid':os.getpid(),'previous_terminal_sha256':last_sha})

        except BaseException as error:
            original=error
            raise
        finally:
            close_all([lambda:scope.__exit__(None if original is None else type(original),original,
                None if original is None else original.__traceback__)],original)

    def _require_terminal_chain_in(self,ordinal,claim,claim_sha,terminal,previous_sha):
        from .own_preupload_journal import _HASH
        import re
        need(set(claim)=={'schema','profile','authority','ordinal','resume_id','phase_sha256',
            'binding_sha256','parent_pid','previous_terminal_sha256'}
            and type(claim['schema']) is int and claim['schema']==1
            and claim['profile']=='PREUPLOAD_TECHNICAL_CHILD_CLAIM_V1' and claim['authority'] is False
            and type(claim['ordinal']) is int and claim['ordinal']==ordinal
            and claim['phase_sha256']==self.phase_sha and claim['previous_terminal_sha256']==previous_sha
            and type(claim['parent_pid']) is int and claim['parent_pid']>0
            and type(claim['resume_id']) is str
            and re.fullmatch(r'preupload-resume-[0-9a-f]{32}',claim['resume_id']) is not None
            and type(claim['binding_sha256']) is str and _HASH.fullmatch(claim['binding_sha256']) is not None)
        need(set(terminal)=={'schema','profile','authority','ordinal','phase_sha256','claim_sha256',
            'created_sha256','state','returncode','allows_automatic_business_replay'}
            and type(terminal['schema']) is int and terminal['schema']==1
            and terminal['profile']=='PREUPLOAD_TECHNICAL_CHILD_TERMINAL_V1'
            and terminal['authority'] is False
            and type(terminal['ordinal']) is int and terminal['ordinal']==ordinal
            and terminal['phase_sha256']==self.phase_sha and terminal['claim_sha256']==claim_sha
            and terminal['allows_automatic_business_replay'] is False)
        if terminal['state']=='NO_CHILD_CREATED':
            need(terminal['created_sha256'] is None and terminal['returncode'] is None
                 and not os.path.lexists(self.root/self._name(ordinal,'created')))
        else:
            need(terminal['state']=='REAPED_BY_OWNED_HANDLE' and type(terminal['returncode']) is int)
            created,created_sha=self._read(ordinal,'created')
            need(set(created)=={'schema','profile','authority','ordinal','phase_sha256',
                'claim_sha256','parent_pid','child_pid'}
                and type(created['schema']) is int and created['schema']==1
                and created['profile']=='PREUPLOAD_TECHNICAL_CHILD_CREATED_V1'
                and created['authority'] is False and type(created['ordinal']) is int
                and created['ordinal']==ordinal and created['phase_sha256']==self.phase_sha
                and created['claim_sha256']==claim_sha and created['parent_pid']==claim['parent_pid']
                and type(created['parent_pid']) is int and type(created['child_pid']) is int
                and created['child_pid']>0 and created_sha==terminal['created_sha256'])

    def created(self,process):
        import subprocess
        need(type(process) is subprocess.Popen and self.created_pid is None and not self.terminal)
        need(type(process.pid) is int and process.pid>0)
        self.created_pid=process.pid;self.process=process
        self.created_sha=self._create('created',{'schema':1,'profile':'PREUPLOAD_TECHNICAL_CHILD_CREATED_V1',
            'authority':False,'ordinal':self.ordinal,'phase_sha256':self.phase_sha,
            'claim_sha256':self.claim_sha,'parent_pid':os.getpid(),'child_pid':process.pid})

    def finish(self,process):
        self.check();need(not self.terminal)
        if process is None:
            need(self.created_pid is None and self.popen_attempted is False)
            state,code='NO_CHILD_CREATED',None
        else:
            import subprocess
            need(type(process) is subprocess.Popen and process is self.process and process.pid==self.created_pid)
            code=process.poll();need(type(code) is int)
            state='REAPED_BY_OWNED_HANDLE'
        self._create('terminal',{'schema':1,'profile':'PREUPLOAD_TECHNICAL_CHILD_TERMINAL_V1',
            'authority':False,'ordinal':self.ordinal,'phase_sha256':self.phase_sha,
            'claim_sha256':self.claim_sha,'created_sha256':getattr(self,'created_sha',None),
            'state':state,'returncode':code,'allows_automatic_business_replay':False})
        self.terminal=True

    def observe_owned_child(self,*,binding_sha,parent_pid,child_pid,previous_terminal_ref):
        """Child-side actual peer/PID match, retaining the exact committed FDs."""
        need(not self.records and binding_sha==self.binding_sha
             and type(parent_pid) is int and parent_pid==os.getppid()
             and type(child_pid) is int and child_pid==os.getpid())
        if self.ordinal==1:
            need(previous_terminal_ref is None)
            previous_sha=None
        else:
            need(type(previous_terminal_ref) is dict
                 and set(previous_terminal_ref)=={'path','sha256','bytes'}
                 and previous_terminal_ref['path']==str(self.root/self._name(self.ordinal-1,'terminal')))
            previous_sha=previous_terminal_ref['sha256']
        claim,claim_sha=self._read(self.ordinal,'claim',retain=True)
        created,created_sha=self._read(self.ordinal,'created',retain=True)
        need(type(claim['schema']) is int and type(claim['ordinal']) is int
             and type(claim['parent_pid']) is int and claim['authority'] is False
             and type(created['schema']) is int and type(created['ordinal']) is int
             and type(created['parent_pid']) is int and type(created['child_pid']) is int
             and created['authority'] is False)
        need(claim=={'schema':1,'profile':'PREUPLOAD_TECHNICAL_CHILD_CLAIM_V1','authority':False,
            'ordinal':self.ordinal,'resume_id':self.resume_id,'phase_sha256':self.phase_sha,
            'binding_sha256':binding_sha,'parent_pid':parent_pid,
            'previous_terminal_sha256':previous_sha}
            and created=={'schema':1,'profile':'PREUPLOAD_TECHNICAL_CHILD_CREATED_V1','authority':False,
                'ordinal':self.ordinal,'phase_sha256':self.phase_sha,'claim_sha256':claim_sha,
                'parent_pid':parent_pid,'child_pid':child_pid})
        self.check()

    def close(self,*,original=None):
        if not self.closed:
            self.closed=True
            close_all([lambda fd=record[1]:os.close(fd) for record in self.records]
                +([lambda:os.close(self.parent)] if self.parent is not None else []),original)
