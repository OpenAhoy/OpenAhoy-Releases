"""Unattended workspace proof in one dedicated macOS Keychain slot."""
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
import os
from pathlib import Path
import re
import secrets

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .x_keychain import XKeychain

FORMAT = re.compile(r'[A-Za-z0-9_-]{43}')


class WorkspaceKeychain(XKeychain):
    service = 'com.readysteadyscience.jiusera.wechat.workspace-proof.v1'
    label = 'Jiusera WeChat workspace proof'


def valid_proof(value):
    if type(value) is not str or not FORMAT.fullmatch(value):
        return False
    return urlsafe_b64encode(urlsafe_b64decode(value + '=')).decode('ascii') == value + '='


class WorkspaceProof:
    def __init__(self, registry, backend=None):
        self.registry = Path(registry).absolute()
        self.backend = backend
        self.scope = sha256(b'jiusera-wechat-workspace-v1\0' + os.fsencode(self.registry)).hexdigest()

    def read(self, *, create=False):
        if self.backend is None:
            # The existing workspace is required. A read never initializes a registry.
            path_check(self.registry.parent, True)
            path_check(self.registry)
        backend = self.backend or WorkspaceKeychain()
        try:
            with backend.without_user_interaction():
                proof = backend.load(self.scope)
                if proof is None and create:
                    try:
                        backend.store(self.scope, secrets.token_urlsafe(32))
                    except WCEError as error:
                        if error.code != 'BOOTSTRAP_KEYCHAIN_ITEM_EXISTS':
                            raise
                    proof = backend.load(self.scope)
                if proof is None:
                    return None
                if not valid_proof(proof.reveal_for_adapter()):
                    raise WCEError('WECHAT_WORKSPACE_PROOF_INVALID')
                return proof
        except WCEError as error:
            if error.code == 'WECHAT_WORKSPACE_PROOF_INVALID':
                raise
            raise WCEError('WECHAT_WORKSPACE_KEYCHAIN_UNAVAILABLE') from None

    def enrollment_digest(self):
        proof = self.read(create=True)
        if proof is None:
            raise WCEError('WECHAT_WORKSPACE_KEYCHAIN_UNAVAILABLE')
        return sha256(proof.reveal_for_adapter().encode('utf-8')).hexdigest()
