"""Compile static path spelling only; never cache permission/stat results.

Every check repeats all original lstat predicates in original order. Prepared
programs hold no file descriptors, parsed runtime, grant or observation. They
must live only inside the concrete scan guard's existing Gate lifetime.
"""
from dataclasses import dataclass,field
import os,stat
from pathlib import Path
from .bounded_file import identity,file_state
from .contracts import WCEError


def unsafe():raise WCEError('BOOTSTRAP_UNSAFE_PATH')


@dataclass(frozen=True,init=False)
class PreparedPrivatePath:
    path:Path
    directory:bool
    _steps:tuple=field(repr=False)

    def __init__(self,path,directory=False):
        path=Path(path)
        if not path.is_absolute() or any(p in {'.','..'} for p in path.parts) or len(path.parts)>32:unsafe()
        current=Path('/');steps=[]
        for part in path.parts[1:]:
            current/=part
            # Preserve the original comparison, including unusual // spelling.
            steps.append((str(current),current!=path))
        object.__setattr__(self,'path',path)
        object.__setattr__(self,'directory',directory)
        object.__setattr__(self,'_steps',tuple(steps))

    def check(self):
        try:
            for name,intermediate in self._steps:
                info=os.lstat(name)
                if stat.S_ISLNK(info.st_mode):raise ValueError()
                if intermediate and not stat.S_ISDIR(info.st_mode):raise ValueError()
            # Empty root spelling has the original fail-closed undefined-info
            # outcome. No stat/identity/owner result is reused across checks.
            if (info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=(0o700 if self.directory else 0o600)
                    or not (stat.S_ISDIR(info.st_mode) if self.directory else stat.S_ISREG(info.st_mode))
                    or (not self.directory and info.st_nlink!=1)):raise ValueError()
            return identity(info) if self.directory else file_state(info)
        except Exception:unsafe()


@dataclass(frozen=True,init=False)
class PreparedPolicyPaths:
    """Four preselected paths; unexpected same-Gate policy replacement holds."""
    policy:object=field(repr=False,compare=False)
    policy_path:Path
    root:Path
    _programs:tuple=field(repr=False)

    def __init__(self,policy):
        object.__setattr__(self,'policy',policy)
        object.__setattr__(self,'policy_path',policy.path)
        object.__setattr__(self,'root',policy.root)
        values=(('policy',policy.path,False),('root',policy.root,True),
            ('images',policy.root/'images',True),('database',policy.root/'state.sqlite3',False))
        object.__setattr__(self,'_programs',tuple((key,PreparedPrivatePath(path,directory))
            for key,path,directory in values))

    def check(self,key,policy):
        if (policy is not self.policy or policy.path!=self.policy_path or policy.root!=self.root):
            raise WCEError('DRAFT_REVISION_SCAN_HOLD')
        for name,program in self._programs:
            if name==key:return program.check()
        raise WCEError('DRAFT_REVISION_SCAN_HOLD')
