"""Proposed direct own-account publication routing; never starts a broker.

Installation in ConnectionRouter is separate; this module alone exposes nothing.
"""
from copy import deepcopy
from pathlib import Path
from .contracts import WCEError
from .own_connection_policy import resolve, registry_path
from .prepared_contracts import ID, strict_validate, string
from .publication_service import PublicationService
from .tools import schema

HANDLE = string(96, r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')
NAMES = {
    'own.admission.read': schema({'connection_id': ID}),
    'own.publications.dispatch': schema({'connection_id': ID, 'registered_artifact_handle': HANDLE, 'intent_key': ID}),
    'own.publications.status': schema({'connection_id': ID, 'intent_handle': ID}),
    'own.publications.poll': schema({'connection_id': ID, 'intent_handle': ID}),
}

def descriptors():
    descriptions = {
        'own.admission.read': 'Read local publication admission status; no token or platform call.',
        'own.publications.dispatch': 'Publish a registered new artifact only under existing human authorization. Unknown results never retry.',
        'own.publications.status': 'Read an original publication intent locally without a network call.',
        'own.publications.poll': 'Query an original publication intent under existing authorization; never resubmit.',
    }
    return [{'name': key, 'description': descriptions[key], 'inputSchema': deepcopy(spec)} for key, spec in NAMES.items()]


def call(name, arguments, registry=None):
    if name not in NAMES:
        raise WCEError('TOOL_NOT_IMPLEMENTED')
    strict_validate(arguments, NAMES[name])
    # Resolve a bound identity; no generic broker/ensure_started path is used.
    policy = resolve(arguments['connection_id'], registry, active=False)
    service = PublicationService(policy, Path(registry) if registry is not None else registry_path())
    if name == 'own.publications.status':
        return service.status(arguments['intent_handle'])
    if name == 'own.admission.read':
        # Existing status is a local-only conservative summary, not a fresh
        # permission attestation or a platform operation.
        state = service.status()
        return {'state': state['state'], 'enabled': state['enabled'],
                'admission': state['admission'], 'mass': state['mass'],
                'qa_runtime': state['qa_runtime'], 'qa_reason': state['qa_reason'],
                'quota': state['quota'], 'producer': state['producer'],
                'platform_business_capabilities': 'NOT_VERIFIED'}
    if name == 'own.publications.dispatch':
        return service.dispatch(arguments['registered_artifact_handle'], arguments['intent_key'])
    return service.poll(arguments['intent_handle'])
