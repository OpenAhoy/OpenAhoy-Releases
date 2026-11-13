"""Closed private preupload frames and mechanical peer observations.

This module never creates an account service, reads policy, accepts source, or
grants an upload. A kernel-peer handshake alone is not a fixed-entry witness:
the trusted launcher must also own the actual Popen and held program graph,
and the child must validate its fixed entry before constructing any core.
"""
from dataclasses import dataclass
from hashlib import sha256
import math
import os
import re
import secrets
import time

from .contracts import WCEError
from .own_bootstrap_ipc import peer, send, receive
from .own_connection_broker import _StartupStream


PURPOSE = 'OPERATOR_PREUPLOAD_V1'
ACCEPT = '_wce.preupload.accept_selected.v1'
STATUS = '_wce.preupload.original_slot_status.v1'
EXECUTE = '_wce.preupload.original_slot_execute.v1'
METHODS = frozenset((ACCEPT, STATUS, EXECUTE))
MAX_SEQUENCE = 512
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_COMMON = frozenset(('schema', 'profile', 'purpose', 'selection_sha256',
                    'resume_sha256', 'candidate_scope', 'absolute_deadline'))


def _hold():
    raise WCEError('PREUPLOAD_TRANSPORT_SCOPE_HOLD')


def _sha(value):
    if type(value) is not str or _HASH.fullmatch(value) is None:
        _hold()


def _integer(value, high=2**63-1):
    if type(value) is not int or not 1 <= value <= high:
        _hold()


def _identifier(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        _hold()


def _deadline(value):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not time.monotonic() < value <= time.monotonic()+300.001):
        _hold()


def _common(value, profile, extra):
    if (type(value) is not dict or set(value) != _COMMON | frozenset(extra)
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['profile']) is not str or value['profile'] != profile
            or type(value['purpose']) is not str or value['purpose'] != PURPOSE):
        _hold()
    for key in ('selection_sha256', 'resume_sha256', 'candidate_scope'):
        _sha(value[key])
    _deadline(value['absolute_deadline'])


def _scope(selection_sha256, resume_sha256, candidate_scope, deadline):
    for value in (selection_sha256, resume_sha256, candidate_scope):
        _sha(value)
    _deadline(deadline)
    return {'schema': 1, 'purpose': PURPOSE, 'selection_sha256': selection_sha256,
            'resume_sha256': resume_sha256, 'candidate_scope': candidate_scope,
            'absolute_deadline': deadline}


def _matches(value, scope):
    for key in scope:
        if type(value[key]) is not type(scope[key]) or value[key] != scope[key]:
            _hold()


@dataclass(frozen=True)
class PeerObservation:
    """Non-authoritative transport fact; never accepted as a service permit."""
    peer_pid: int
    parent_pid: int
    child_pid: int
    nonce_sha256: str
    selection_sha256: str
    resume_sha256: str
    candidate_scope: str
    absolute_deadline: float
    authority: bool = False


def parent_handshake(connection, *, owned_child_pid, program_sha256,
                     selection_sha256, resume_sha256, candidate_scope, deadline):
    """Observe the actual child after HELLO, while it waits for our ACK.

    On macOS a pre-spawn socketpair credential lookup reports its creator.
    Only the lookup after the child's frame is meaningful here. The owning
    controller must verify owned_child_pid against its own live Popen handle.
    """
    _integer(owned_child_pid)
    _sha(program_sha256)
    scope = _scope(selection_sha256, resume_sha256, candidate_scope, deadline)
    stream = _StartupStream(connection, deadline)
    nonce = secrets.token_hex(32)
    nonce_sha = sha256(nonce.encode()).hexdigest()
    send(stream, scope | {'profile': 'PREUPLOAD_PARENT_CHALLENGE_V1',
                         'parent_pid': os.getpid(), 'nonce': nonce})
    hello = receive(stream)
    _common(hello, 'PREUPLOAD_CHILD_HELLO_V1',
            ('parent_pid', 'child_pid', 'nonce_sha256', 'program_sha256'))
    _matches(hello, scope)
    for key in ('parent_pid', 'child_pid'):
        _integer(hello[key])
    _sha(hello['nonce_sha256'])
    _sha(hello['program_sha256'])
    if (peer(connection) != (owned_child_pid, os.getuid())
            or hello['child_pid'] != owned_child_pid or hello['parent_pid'] != os.getpid()
            or hello['nonce_sha256'] != nonce_sha or hello['program_sha256'] != program_sha256):
        _hold()
    send(stream, scope | {'profile': 'PREUPLOAD_PARENT_ACK_V1',
                         'parent_pid': os.getpid(), 'child_pid': owned_child_pid,
                         'nonce_sha256': nonce_sha})
    return (PeerObservation(owned_child_pid, os.getpid(), owned_child_pid, nonce_sha,
        selection_sha256, resume_sha256, candidate_scope, deadline), stream)


def child_handshake(connection, *, program_sha256, selection_sha256,
                    resume_sha256, candidate_scope, deadline):
    """Mechanical authentication before, not instead of, fixed-entry checks."""
    _sha(program_sha256)
    scope = _scope(selection_sha256, resume_sha256, candidate_scope, deadline)
    stream = _StartupStream(connection, deadline)
    challenge = receive(stream)
    _common(challenge, 'PREUPLOAD_PARENT_CHALLENGE_V1', ('parent_pid', 'nonce'))
    _matches(challenge, scope)
    _integer(challenge['parent_pid'])
    _sha(challenge['nonce'])
    parent_pid = os.getppid()
    if (challenge['parent_pid'] != parent_pid or parent_pid <= 1
            or peer(connection) != (parent_pid, os.getuid())):
        _hold()
    nonce_sha = sha256(challenge['nonce'].encode()).hexdigest()
    send(stream, scope | {'profile': 'PREUPLOAD_CHILD_HELLO_V1',
        'parent_pid': parent_pid, 'child_pid': os.getpid(),
        'nonce_sha256': nonce_sha, 'program_sha256': program_sha256})
    ack = receive(stream)
    _common(ack, 'PREUPLOAD_PARENT_ACK_V1', ('parent_pid', 'child_pid', 'nonce_sha256'))
    _matches(ack, scope)
    _integer(ack['parent_pid'])
    _integer(ack['child_pid'])
    _sha(ack['nonce_sha256'])
    if (ack['parent_pid'] != parent_pid or ack['child_pid'] != os.getpid()
            or ack['nonce_sha256'] != nonce_sha or os.getppid() != parent_pid
            or peer(connection) != (parent_pid, os.getuid())):
        _hold()
    # ACK and the first RPC may share one recv. The session must retain this
    # exact stream, including its unread buffer, rather than reopening it.
    return (PeerObservation(parent_pid, parent_pid, os.getpid(), nonce_sha,
        selection_sha256, resume_sha256, candidate_scope, deadline), stream)


def validate_request(value, *, observation, expected_sequence):
    """Validate routing data only. The service must requalify the exact slot."""
    if type(observation) is not PeerObservation or observation.authority is not False:
        _hold()
    _integer(expected_sequence, MAX_SEQUENCE)
    _common(value, 'PREUPLOAD_RPC_REQUEST_V1', ('nonce_sha256', 'sequence', 'method', 'arguments'))
    scope = _scope(observation.selection_sha256, observation.resume_sha256,
                   observation.candidate_scope, observation.absolute_deadline)
    _matches(value, scope)
    _sha(value['nonce_sha256'])
    _integer(value['sequence'], MAX_SEQUENCE)
    if (value['sequence'] != expected_sequence
            or value['nonce_sha256'] != observation.nonce_sha256
            or type(value['method']) is not str or value['method'] not in METHODS):
        _hold()
    arguments = value['arguments']
    expected = {'member_id'} if value['method'] == ACCEPT else {'member_id', 'slot'}
    if type(arguments) is not dict or set(arguments) != expected:
        _hold()
    for argument in arguments.values():
        _identifier(argument)
    # Detached data, no marker that could be confused with a current witness.
    return value['method'], dict(arguments)


def request_frame(observation, sequence, method, arguments):
    value = _scope(observation.selection_sha256, observation.resume_sha256,
                   observation.candidate_scope, observation.absolute_deadline) | {
        'profile': 'PREUPLOAD_RPC_REQUEST_V1', 'nonce_sha256': observation.nonce_sha256,
        'sequence': sequence, 'method': method, 'arguments': arguments}
    validate_request(value, observation=observation, expected_sequence=sequence)
    return value


def response_frame(observation, sequence, *, value=None, error=None):
    _integer(sequence, MAX_SEQUENCE)
    if error is not None and (type(error) is not str or re.fullmatch('[A-Z][A-Z0-9_]{0,127}', error) is None):
        _hold()
    if (value is None) == (error is None):
        _hold()
    return _scope(observation.selection_sha256, observation.resume_sha256,
                  observation.candidate_scope, observation.absolute_deadline) | {
        'profile': 'PREUPLOAD_RPC_RESPONSE_V1', 'nonce_sha256': observation.nonce_sha256,
        'sequence': sequence, 'value': value, 'error': error}


def validate_response(value, *, observation, expected_sequence):
    _common(value, 'PREUPLOAD_RPC_RESPONSE_V1', ('nonce_sha256', 'sequence', 'value', 'error'))
    expected = response_frame(observation, expected_sequence, value=value['value'], error=value['error'])
    if value != expected or type(value['sequence']) is not int:
        _hold()
    return value['value'], value['error']


def initialization_frame(observation, *, error=None):
    """Constructor outcome, never a business result or source permit."""
    if type(observation) is not PeerObservation or observation.authority is not False:_hold()
    if error is not None and (type(error) is not str or re.fullmatch('[A-Z][A-Z0-9_]{0,127}',error) is None):_hold()
    return _scope(observation.selection_sha256,observation.resume_sha256,
        observation.candidate_scope,observation.absolute_deadline)|{
            'profile':'PREUPLOAD_INITIALIZATION_V1','nonce_sha256':observation.nonce_sha256,
            'state':'READY_NO_BUSINESS_SENT' if error is None else 'INITIALIZATION_REJECTED',
            'error':error}


def validate_initialization(value, *, observation):
    _common(value,'PREUPLOAD_INITIALIZATION_V1',('nonce_sha256','state','error'))
    if value!=initialization_frame(observation,error=value['error']):_hold()
    return value['error']
