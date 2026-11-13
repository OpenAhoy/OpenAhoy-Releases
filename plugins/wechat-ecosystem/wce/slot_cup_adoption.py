"""CUP-pinned producer metadata, distinct from native human authority.

Only reviewed installer code publishes the receipt after the original SDK
query confirms its commit. Runtime consumes fixed private paths and the exact
current transaction; no tool accepts a role, source, path or approval flag.
Native StandingSource and producer evidence remain independently mandatory.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import os
import secrets

from .contracts import WCEError
from .service import canonical, digest
from .own_account_metadata import AccountMetadataReader, decode_metadata
from .own_connection_policy import atomic_write, registry_path

PROFILE='CUP_PINNED_SLOT_SOURCE_DATA_V1'
RECEIPT='slot-source-adoption.json'
CONFIG='current-draft-publication-source.json'
ROLES='slot-producer-roles.json'
FIELDS={'profile','owner_digest','code_scope','standing_config_sha256','producer_roles_sha256'}
HASH=re.compile(r'[a-f0-9]{64}\Z')


def need(value):
    if value is not True:raise WCEError('SLOT_SOURCE_ADOPTION_UNAVAILABLE')


def validate_shape(value):
    need(type(value)is dict and set(value)==FIELDS and value['profile']==PROFILE
        and all(type(value[k])is str and HASH.fullmatch(value[k])is not None for k in FIELDS-{'profile'}))
    return value


def read(root,path,guard):
    guard();reader=AccountMetadataReader(root)
    meta,raw=reader.read(path,keep=True);guard()
    again,second=reader.read(path,keep=True)
    need(meta==again and raw==second)
    return decode_metadata(raw),meta['sha256'],raw


class _Snapshot:
    """Current read witnesses; a request-local fact, never permission."""
    def __init__(self,root,guard):
        self.root,self.guard=Path(root),guard
        self.reader=AccountMetadataReader(root);self.observed={}

    def raw(self,path):
        path=Path(path);self.guard()
        meta,raw=self.reader.read(path,keep=True)
        if path in self.observed:need(self.observed[path]==meta)
        else:self.observed[path]=meta
        self.guard()
        return meta,raw

    def read(self,path):
        meta,raw=self.raw(path)
        return decode_metadata(raw),meta['sha256'],raw

    @property
    def proofs(self):
        snapshot=self
        class ProofReader:
            def read(self,path,keep=False):
                meta,raw=snapshot.raw(path)
                return meta,raw if keep else None
        return ProofReader()

    def fence(self):
        from .own_identity_checkpoint import file_metadata
        # Full reread plus a final physical sweep catches an earlier source
        # changed while a later member of this snapshot was being checked.
        for path in sorted(self.observed):self.read(path)
        for path,expected in sorted(self.observed.items()):
            with self.reader.directory(path.parent)as directory:
                actual=file_metadata(os.stat(path.name,dir_fd=directory,follow_symlinks=False))
                need(actual=={k:v for k,v in expected.items()if k!='sha256'})
        self.guard()


def validate_data(value,base,guard,*,snapshot=None):
    validate_shape(value);base=Path(base)
    selected=(lambda path:read(base,path,guard)) if snapshot is None else snapshot.read
    config,config_sha,_=selected(base/CONFIG)
    roles,role_sha,_=selected(base/ROLES)
    need(config_sha==value['standing_config_sha256'] and role_sha==value['producer_roles_sha256']
        and type(config)is dict and type(roles)is dict
        and roles.get('schema')==1 and roles.get('purpose')=='HOST_REGISTERED_SLOT_PRODUCERS_V1'
        and roles.get('code_scope')==value['code_scope']
        and roles.get('standing_config_sha256')==config_sha)
    # This validates metadata association only. RoleRegistry validates every
    # closed role, actual native creator, activation tail and original source.
    return deepcopy(value)


def validate_installer_data(value,pins):
    from . import own_compatible_upgrade as sdk
    validate_shape(value)
    need(value['owner_digest']==pins.owner_digest and value['code_scope']==pins.installed['code_scope'])
    base=Path(sdk.registry_path()).parent
    dependencies=dict(pins.dependencies)
    need(dependencies.get(base/CONFIG)==value['standing_config_sha256']
        and dependencies.get(base/ROLES)==value['producer_roles_sha256'])
    return validate_data(value,base,lambda:None)


def _attestation_name(checksum):
    need(type(checksum)is str and HASH.fullmatch(checksum)is not None)
    return 'slot-source-attestation-'+checksum+'.json'


def publish_after_commit(raw,pins):
    """Installer-only metadata publication; not exposed by an MCP route."""
    from . import own_compatible_upgrade as sdk
    from . import own_normal_operations_upgrade as normal
    need(type(pins)is sdk.TrustedInstallerPins and type(raw)is bytes)
    attestation=decode_metadata(raw)
    registration=attestation['authority'].get('normal_operations_extension',{}).get('source_registration')
    if registration is None:return {'state':'NO_SOURCE_REGISTRATION','authority':False}
    validate_installer_data(registration,pins)
    result=sdk.query_metadata_upgrade(attestation['operation_id'],raw,pins)
    need(result['state']=='COMMITTED' and result['receipt_state']=='COMMITTED'
        and attestation['authority']['schema']==8
        and attestation['authority']['mode']==normal.MODE
        and sha256(raw).hexdigest()==pins.attestation_sha256)
    base=Path(sdk.registry_path()).parent
    name=_attestation_name(pins.attestation_sha256)
    # Keep exact original request bytes, including its original newline policy.
    # Content-addressed snapshots are never replaced or inferred from parsed JSON.
    from .own_bootstrap_security import path_check
    from .bounded_file import identity
    expected_parent=path_check(base,True)
    parent=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temporary='.slot-source-'+secrets.token_hex(16)
    created=False
    try:
        need(identity(os.fstat(parent))==expected_parent)
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        created=True
        try:
            offset=0
            while offset<len(raw):
                written=os.write(fd,raw[offset:]);need(written>0);offset+=written
            os.fsync(fd)
        finally:os.close(fd)
        need(path_check(base,True)==expected_parent)
        try:os.link(temporary,name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
        except FileExistsError:pass
        os.unlink(temporary,dir_fd=parent);created=False
        os.fsync(parent)
        need(path_check(base,True)==expected_parent)
    finally:
        if created:os.unlink(temporary,dir_fd=parent)
        os.close(parent)
    existing,checksum,stored=read(base,base/name,lambda:None)
    need(existing==attestation and stored==raw and checksum==pins.attestation_sha256)
    receipt={'schema':1,'profile':PROFILE,'authority':False,
        'operation_id':attestation['operation_id'],'transaction_id':attestation['transaction_id'],
        'original_attestation_sha256':pins.attestation_sha256,'stored_attestation_sha256':checksum,
        'source_registration':registration}
    atomic_write(base/RECEIPT,receipt,maximum=None)
    observed,_,_=read(base,base/RECEIPT,lambda:None);need(observed==receipt)
    return {'state':'CUP_SOURCE_METADATA_ADOPTED','authority':False,
        'operation_id':attestation['operation_id'],'producer_roles_sha256':registration['producer_roles_sha256']}


class RuntimeAdoption:
    """Current committed metadata association, never a publication permit."""
    def __init__(self,policy,registry,guard):
        self.policy=policy;self.registry=Path(registry);self.base=self.registry.parent;self.guard=guard
        self.value,self.receipt_sha,_=read(self.base,self.base/RECEIPT,guard)
        self._verified_anchor_sha=None
        self.registration=self._verify()

    def _verify(self):
        try:return self._verify_checked()
        except (KeyError,TypeError,ValueError,AttributeError,OSError):
            raise WCEError('SLOT_SOURCE_ADOPTION_UNAVAILABLE') from None

    def _verify_checked(self):
        from . import own_compatible_upgrade as sdk
        from . import own_normal_operations_upgrade as normal
        from .own_connection_registry import transaction_path
        self.guard();self.policy.check(readonly=True)
        snapshot=_Snapshot(self.base,self.guard)
        value,checksum,_=snapshot.read(self.base/RECEIPT)
        need(value==self.value and checksum==self.receipt_sha
            and set(value)=={'schema','profile','authority','operation_id','transaction_id',
                'original_attestation_sha256','stored_attestation_sha256','source_registration'}
            and type(value['schema'])is int and value['schema']==1
            and value['profile']==PROFILE and value['authority']is False)
        registration=validate_data(value['source_registration'],self.base,self.guard,snapshot=snapshot)
        policy=self.policy;cid=policy.data['connection_id']
        need(registration['owner_digest']==policy.value['owner_digest']
            and registration['code_scope']==policy.value['candidate_scope']
            and value['transaction_id']==policy.value['transaction']
            and re.fullmatch(r'cup-[a-f0-9]{32}',value['operation_id'])is not None)
        att,att_sha,_=snapshot.read(self.base/_attestation_name(value['original_attestation_sha256']))
        need(att_sha==value['stored_attestation_sha256']==value['original_attestation_sha256'])
        op,op_sha,_=snapshot.read(self.base/'compatible-upgrades'/(value['operation_id']+'.json'))
        transaction,_,_=snapshot.read(transaction_path(self.registry,value['transaction_id']))
        if self._verified_anchor_sha is None:
            sdk.anchor_shape(op,proof_reader=snapshot.proofs)
        else:need(op_sha==self._verified_anchor_sha)
        plan=op['plan'];authority=att['authority']
        need(sdk.account_seals(plan['base'],proof_reader=snapshot.proofs)==att['accounts'])
        expected_transaction=deepcopy(plan['transaction']);expected_transaction['state']='COMMITTED'
        need(op['state']=='COMMITTED' and op['id']==att['operation_id']==value['operation_id']
            and op['completion_origin']==sdk.ORIGINS[normal.MODE]
            and op['attestation_sha256']==plan['attestation_sha256']==value['original_attestation_sha256']
            and plan['transaction_id']==att['transaction_id']==value['transaction_id']
            and transaction==expected_transaction
            and transaction['policies'][str(policy.path)]['after']==policy.value
            and plan['base']['registry']==str(self.registry)
            and digest(plan['base'])==att['before_snapshot_sha256']
            and att['installed']['code_scope']==registration['code_scope']
            and att['registry']['owner_digest']==registration['owner_digest']
            and authority['schema']==8 and authority['mode']==normal.MODE
            and authority['standing_rights']==sdk.RIGHTS
            and authority['normal_operations_extension']==normal.extension(registration)
            and att['contract']['to_sha256']==normal.AFTER_SHA)
        normal.full_contracts();self.guard();policy.check(readonly=True)
        snapshot.fence()
        self._verified_anchor_sha=op_sha
        return registration

    @property
    def role_sha256(self):return self._verify()['producer_roles_sha256']

    def fence(self):self._verify();return True
