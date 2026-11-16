"""Bind a committed account proof to the filesystem of an owned open path."""
from ctypes import CDLL, POINTER, Structure, byref, c_int, c_size_t, c_uint16, c_uint32, c_ulong, c_void_p
from functools import lru_cache
import os
from pathlib import Path
import sys
from uuid import UUID

from .contracts import WCEError
from .service import digest

DIRECTORY = 'connection-volume-witnesses'
REVISION_FILE = 'volume-witness.json'
ADOPTION_FILE = 'confirmed-storage-volume.json'


class _Attributes(Structure):
    _fields_ = [('count', c_uint16), ('reserved', c_uint16), ('common', c_uint32),
                ('volume', c_uint32), ('directory', c_uint32), ('file', c_uint32), ('fork', c_uint32)]


class _Volume(Structure):
    _fields_ = [('length', c_uint32), ('uuid', c_uint32 * 4)]


@lru_cache(maxsize=1)
def _read_volume():
    api = CDLL(None, use_errno=True).fgetattrlist
    api.argtypes = [c_int, POINTER(_Attributes), c_void_p, c_size_t, c_ulong]
    api.restype = c_int
    return api


def fd_volume(fd):
    if sys.platform != 'darwin':
        return None
    # Darwin sys/attr.h: ATTR_BIT_MAP_COUNT, ATTR_VOL_INFO | ATTR_VOL_UUID.
    attrs = _Attributes(5, 0, 0, 0x80040000, 0, 0, 0)
    result = _Volume()
    if _read_volume()(fd, byref(attrs), byref(result), c_size_t(20), 0) or result.length != 20:
        raise WCEError('CONNECTION_VOLUME_UNAVAILABLE')
    value = UUID(bytes=bytes(result.uuid))
    if not value.int:
        raise WCEError('CONNECTION_VOLUME_UNAVAILABLE')
    return value.hex


def directory_volume(path):
    from .own_identity_checkpoint import Reader
    with Reader(path).directory(path) as fd:
        info = os.fstat(fd)
        volume = fd_volume(fd)
        observed = Path(path).lstat()
        if (info.st_dev, info.st_ino) != (observed.st_dev, observed.st_ino):
            raise WCEError('CONNECTION_VOLUME_CHANGED')
        return volume, [info.st_dev, info.st_ino]


def _record_path(registry, proof):
    from .own_connection_registry import transaction_path
    leaf = transaction_path(registry, proof['id']).name
    return registry.parent / DIRECTORY / leaf


def _read(registry, proof):
    from .own_connection_registry import metadata
    path = _record_path(registry, proof)
    result = None
    adoption = read_adoption(registry.parent)
    if adoption is not None and adoption['proofs'].get(proof['id']) == digest(proof):
        return {'schema':1,'proof':digest(proof),'volume':adoption['volume']}
    if os.path.lexists(path.parent):
        from .own_bootstrap_security import path_check
        path_check(path.parent, True)
        result = metadata(path)
    if result is None:
        return None
    if (type(result) is not dict or set(result) != {'schema', 'proof', 'volume'}
            or type(result['schema']) is not int or result['schema'] != 1
            or result['proof'] != digest(proof) or type(result['volume']) is not str
            or len(result['volume']) != 32):
        raise WCEError('CONNECTION_VOLUME_WITNESS_CHANGED')
    verify_confirmation(digest(result))
    return result


def read_adoption(base):
    from .own_connection_registry import metadata
    value = metadata(base / ADOPTION_FILE)
    if value is not None and (type(value) is not dict or
            set(value) != {'schema', 'volume', 'proofs', 'revisions', 'review'}
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['proofs']) is not dict or len(value['proofs']) != 2
            or type(value['revisions']) is not dict or len(value['revisions']) != 2
            or type(value['volume']) is not str or len(value['volume']) != 32
            or type(value['review']) is not str or len(value['review']) != 64):
        raise WCEError('CONNECTION_VOLUME_WITNESS_CHANGED')
    if value is not None:
        verify_confirmation(digest(value))
    return value


def verify_confirmation(fingerprint):
    from .own_inline_crypto import NativeCrypto
    helper = NativeCrypto(storage=True)
    try:
        reply = helper.call({'operation':'storage_verify','context':fingerprint})
    finally:
        helper.close()
    if reply != {'ok':True,'context':fingerprint}:
        raise WCEError('CONNECTION_VOLUME_WITNESS_UNVERIFIED')


def seal_current(kind, path, expected):
    from .own_inline_crypto import NativeCrypto
    helper = NativeCrypto(storage=True)
    try:
        reply = helper.call({'operation':'storage_register','kind':kind,'path':str(path)})
    finally:
        helper.close()
    if reply != {'ok':True,'context':digest(expected)}:
        raise WCEError('CONNECTION_VOLUME_WITNESS_UNVERIFIED')


def matches(registry, proof, current_paths):
    """Check stable volume plus per-path inode, or original exact pins on old receipts."""
    witness = _read(registry, proof)
    if witness is None:
        return None
    volume, root_pin = directory_volume(registry.parent)
    if volume != witness['volume'] or root_pin[1:] != proof['registry_parent'][1:]:
        raise WCEError('CONNECTION_VOLUME_CHANGED')
    for path, old, current in current_paths:
        if (type(old) is not list or len(old) != 2 or old[0] != proof['registry_parent'][0]
                or old[1] != current[1] or root_pin[0] != current[0]):
            raise WCEError('CONNECTION_COMMITTED_IDENTITY_CHANGED')
        info = path.lstat()
        if (info.st_dev, info.st_ino) != tuple(current):
            raise WCEError('CONNECTION_COMMITTED_IDENTITY_CHANGED')
    return True


def record_current(registry, proof):
    """Called from a normal write that has validated all live physical pins."""
    from .own_connection_registry import container
    from .own_connection_enrollment import exclusive
    if sys.platform != 'darwin':
        return
    volume, root_pin = directory_volume(registry.parent)
    if root_pin != proof['registry_parent']:
        raise WCEError('CONNECTION_VOLUME_CHANGED')
    current = _read(registry, proof)
    if current is not None:
        if current['volume'] != volume:
            raise WCEError('CONNECTION_VOLUME_CHANGED')
        return
    path = _record_path(registry, proof)
    directory = container(registry.parent, DIRECTORY)
    _, pin = directory_volume(directory)
    if pin[0] != root_pin[0]:
        raise WCEError('CONNECTION_VOLUME_CHANGED')
    value = {'schema':1,'proof':digest(proof),'volume':volume}
    from .own_connection_registry import transaction_path
    seal_current('connection',transaction_path(registry,proof['id']),value)
    exclusive(path,value,pin)


def _revision_payload(anchor, volume):
    return {'schema': 1, 'binding': anchor['binding'], 'volume': volume,
            'root': anchor['root'], 'database': anchor['database']}


def record_revision(root, anchor):
    """Record the volume of a newly initialized revision journal."""
    if sys.platform != 'darwin':
        return
    from .own_connection_enrollment import exclusive
    volume, pin = directory_volume(root)
    if pin != anchor['root'] or anchor['database'][0] != pin[0]:
        raise WCEError('CONNECTION_VOLUME_CHANGED')
    record=_revision_payload(anchor,volume)
    seal_current('revision',root.parent/'draft-revision-safety-anchor.json',record)
    exclusive(root/REVISION_FILE,record,pin)


def revision_matches(root, anchor, fixed):
    from .own_connection_registry import metadata
    witness = None
    if root.parent.parent.name in {'accounts', 'own'}:
        adopted = read_adoption(root.parent.parent.parent)
        if adopted is not None:
            witness = adopted['revisions'].get(str(root))
    if witness is None:
        witness = metadata(root/REVISION_FILE)
        if witness is not None:
            verify_confirmation(digest(witness))
    if witness is None:
        return False
    volume, current = directory_volume(root)
    if (witness != _revision_payload(anchor, volume) or volume is None
            or current != fixed['root'] or current[1] != anchor['root'][1]
            or fixed['database'][0] != current[0]
            or fixed['database'][1] != anchor['database'][1]):
        raise WCEError('CONNECTION_VOLUME_WITNESS_CHANGED')
    return True
