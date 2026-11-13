"""Per-member held selected files; path/byte facts, never source authority."""
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import threading

from .contracts import WCEError
from .draft_group_pin_resources import PinPool, close_all, full, path_value, MAX_RAW_BYTES
from .draft_group_selected_source_codec import _artifact
from .own_preupload_sources import _EvidenceView
from .service import canonical


def need(value):
    if value is not True:raise WCEError('PREUPLOAD_SELECTED_FILE_HOLD')


def decode_roots(raw, selection, original_flat_root, *, expected_flat_manifest_ref):
    from .own_preupload_sources import _json
    value=_json(raw)
    need(set(value)=={'schema','profile','authority','queue_sha256','flat_manifest_ref','roots'}
         and type(value['schema']) is int and value['schema']==1
         and value['profile']=='PREUPLOAD_SELECTED_ARTIFACT_ROOTS_V1'
         and value['authority'] is False and value['queue_sha256']==selection['queue_sha256']
         and type(value['roots']) is list and len(value['roots'])==29)
    from .own_preupload_qa import reference
    reference(value['flat_manifest_ref'])
    need(value['flat_manifest_ref']==expected_flat_manifest_ref)
    roots={}
    for row in value['roots']:
        need(type(row) is dict and set(row)=={'root_sha256','kind','article_id','absolute_path',
            'generation','physical_pin'} and type(row['generation']) is int and row['generation']>=1
            and type(row['physical_pin']) is list and len(row['physical_pin'])==9
            and all(type(item) is int and item>=0 for item in row['physical_pin']))
        path_value(row['absolute_path'])
        need(type(row['kind']) is str and row['kind'] in ('PROJECT_ARTICLE_ROOT','ORIGINAL_FLAT_ROOT')
             and stat.S_ISDIR(row['physical_pin'][2]) and row['physical_pin'][3]==os.getuid()
             and row['root_sha256']==sha256(canonical({k:v for k,v in row.items()
                 if k!='root_sha256'}).encode()).hexdigest() and row['root_sha256'] not in roots)
        roots[row['root_sha256']]=json.loads(canonical(row))
    wanted=set()
    for member in selection['members']:
        for artifact in (member['html'],member['body'],*[image['artifact'] for image in member['images']]):
            row=roots.get(artifact['root_sha256'])
            need(row is not None and row['kind']=='PROJECT_ARTICLE_ROOT'
                 and row['article_id']==member['article_id'])
            wanted.add(artifact['root_sha256'])
    flat=[row for row in roots.values() if row['kind']=='ORIGINAL_FLAT_ROOT']
    need(len(flat)==1 and flat[0]['article_id'] is None
         and flat[0]['absolute_path']==str(original_flat_root)
         and wanted | {flat[0]['root_sha256']}==set(roots)
         and len({row['absolute_path'] for row in roots.values()})==len(roots))
    return roots,flat[0]


class SelectedMemberFiles:
    """Short resource owner; closes every selected FD before next member.

    The fixed input owner supplies rows from its held roots table. This class
    cannot turn arbitrary files or a matching hash into an accepted request.
    """
    def __init__(self, resources, roots, member, *, extra_raw_bytes=0):
        self.parent_resources=resources
        need(type(member) is dict and type(roots) is dict)
        need(type(extra_raw_bytes) is int and 0<=extra_raw_bytes<=MAX_RAW_BYTES)
        self.extra_raw_bytes=extra_raw_bytes
        self.member_raw=canonical(member)
        snapshot=json.loads(self.member_raw)
        self.roots=json.loads(canonical(roots))
        for key,row in self.roots.items():
            need(row['root_sha256']==key==sha256(canonical({k:v for k,v in row.items()
                if k!='root_sha256'}).encode()).hexdigest())
        self.closed=False
        self.owner=(os.getpid(),threading.get_ident())
        self.pool=PinPool(self)
        self.evidence_bytes=0
        self.views=[]
        self.files={}
        self.root_pins={}
        try:
            self._open('html',snapshot['html'],('text/html',))
            self._open('body',snapshot['body'],('text/markdown',))
            for image in snapshot['images']:
                self._open(image['slot'],image['artifact'],('image/png','image/jpeg'))
            self.check()
        except BaseException as original:
            self.close(original=original)
            raise

    def _open(self, name, artifact, media):
        declared=json.loads(self.member_raw)
        expected=declared.get(name) if name in ('html','body') else next(
            (image['artifact'] for image in declared['images'] if image['slot']==name),None)
        need(expected is not None and artifact==expected)
        _artifact(artifact,frozenset(media))
        row=self.roots.get(artifact['root_sha256'])
        need(row is not None and row['kind']=='PROJECT_ARTICLE_ROOT'
             and row['article_id']==json.loads(self.member_raw)['article_id']
             and artifact['generation']==row['generation'])
        root=path_value(row['absolute_path'])
        root_fd=self.pool.directory(root,owner=self)
        pin=tuple(row['physical_pin'])
        need(full(os.fstat(root_fd))==pin==full(root.lstat()))
        self.root_pins[root]=(root_fd,pin)
        path=root.joinpath(*artifact['relative_path'].split('/'))
        maximum=4*1024*1024 if artifact['media_type']=='text/html' else (
            2*1024*1024 if artifact['media_type']=='text/markdown' else 1000000-1)
        current_bytes=(self.parent_resources.pool.raw_bytes+self.parent_resources.evidence_bytes
                       +self.extra_raw_bytes)
        need(current_bytes+self.evidence_bytes+artifact['size']<=MAX_RAW_BYTES)
        # Declared size has already passed the media envelope. Bound the
        # actual fstat/read by that exact size before allocating any raw blob.
        view=_EvidenceView(self,path,artifact['sha256'],artifact['size'])
        self.views.append(view)
        wanted=artifact['physical_pin'];actual=view.pin
        need(len(view.raw)==artifact['size']
             and (actual[0],actual[1],stat.S_IMODE(actual[2]),actual[3],actual[4],actual[5],actual[7],actual[8])
                ==tuple(wanted[key] for key in ('dev','ino','mode','uid','gid','nlink','mtime_ns','ctime_ns')))
        self.files[name]=view

    def check(self):
        need(not self.closed and self.owner==(os.getpid(),threading.get_ident()))
        self.parent_resources.guard()
        self.pool.check_all(owner=self)
        for path,(fd,pin) in self.root_pins.items():
            need(full(os.fstat(fd))==pin==full(path.lstat()))
        for view in self.views:view.check()

    def close(self, *, original=None):
        if not self.closed:
            self.closed=True
            close_all([view.close for view in reversed(self.views)]+
                [lambda:self.pool.close(owner=self,original=original)],original)

    def __enter__(self):self.check();return self
    def __exit__(self,kind,value,traceback):self.close(original=value);return False
