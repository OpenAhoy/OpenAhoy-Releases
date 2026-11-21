"""Owner-local default media location and immutable per-asset attribution."""
from hashlib import sha256
import os
from pathlib import Path
import unicodedata

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional
from .own_connection_registry import mkdir

LIBRARY_ID = sha256(b'openahoy-unified-media-library-v1').hexdigest()[:32]


class MediaLibrary:
    def __init__(self, projects):
        self.projects = projects
        self.root = projects.root / 'media-library'
        self.attributions = self.root / '.attribution'

    def project(self, *, create=False):
        if create:
            self.projects.owner()
            try:
                self.root.parent.mkdir(mode=0o700)
            except FileExistsError:
                pass
            path_check(self.root.parent, True)
            try:
                mkdir(self.root.parent, self.root.name)
            except FileExistsError:
                pass
        elif not os.path.lexists(self.root):
            return None
        path_check(self.root, True)
        return {'id': LIBRARY_ID, 'name': 'Jiusera', 'root': str(self.root)}

    def _marker(self, kind, attempt):
        # Callers have already validated the exact media kind and attempt ID.
        key = sha256(f'{kind}\0{attempt}'.encode()).hexdigest()
        return self.attributions / (key + '.json')

    def reserve(self, kind, attempt, account=None, *, inherited=None, project_label=None):
        self.project(create=True)
        try:
            mkdir(self.root, self.attributions.name)
        except FileExistsError:
            pass
        path_check(self.attributions, True)
        path = self._marker(kind, attempt)
        with locked(self.attributions / 'write.lock'):
            existing = read_optional(path)
            if existing is not None:
                if account is not None and existing.get('account_key') != account['account_key']:
                    raise WCEError('MEDIA_ACCOUNT_CONFLICT')
                return existing
            value = dict(account or inherited or {})
            if project_label:
                value['project_label'] = project_label
            atomic_write(path, value)
            return value

    def account(self, kind, attempt, project):
        if project != LIBRARY_ID or not os.path.lexists(self.attributions):
            return {}
        path_check(self.attributions, True)
        return read_optional(self._marker(kind, attempt)) or {}

    @staticmethod
    def attribution(platform, connection, name):
        key = sha256(f'{platform}\0{connection}'.encode()).hexdigest()
        name = unicodedata.normalize('NFC', name).strip()
        label = ''.join(c for c in name if c.isprintable()).strip()[:96] or platform
        return {'account_key': key, 'account_label': label}

    @staticmethod
    def filename(project, account, title, attempt, digest, extension):
        labels = [project, account, title]
        limits = (48, 48, 94)
        parts = []
        for label, cap in zip(labels, limits):
            if not isinstance(label, str) or not label.strip():
                continue
            normalized = unicodedata.normalize('NFC', label)
            clean = ''.join(char if char.isprintable() and char not in '/\\:*?"<>|' else ' '
                            for char in normalized)
            clean = ' '.join(clean.split()).strip(' .')
            if clean:
                parts.append(clean.encode('utf-8')[:cap].decode('utf-8', 'ignore').strip(' .'))
        suffix = sha256(f'{attempt}\0{digest}'.encode()).hexdigest()[:12]
        return ' · '.join(parts or ['Jiusera']) + '-' + suffix + extension
