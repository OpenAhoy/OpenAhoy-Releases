"""Versioned, bundled creative material. No credentials or platform requests.

Files are fixed by a reviewed catalog. ZIP and preview consume the same bytes.
Chunking is transport framing, not a content quota or account policy.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import uuid
import zipfile

from .contracts import WCEError

CHUNK = 49152
MARKER = re.compile(r'\[OpenAhoy template:([a-z0-9-]+)@([0-9]+\.[0-9]+\.[0-9]+)#([a-f0-9]{64})\]')


def need(ok, code='TEMPLATE_INVALID_REQUEST'):
    if not ok:
        raise WCEError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Templates:
    def __init__(self, root=None):
        package = Path(__file__).resolve().parents[1]
        self.root = Path(root) if root is not None else package/'content-templates'
        if root is None and not self.root.exists():
            self.root = package/'integrations/codex/content-templates'

    def _read(self, relative):
        need(type(relative) is str and relative and not relative.startswith('/')
             and all(p not in ('', '.', '..') for p in relative.split('/')))
        path = self.root
        need(not path.is_symlink(), 'TEMPLATE_UNAVAILABLE')
        for part in relative.split('/'):
            path = path/part
            need(not path.is_symlink(), 'TEMPLATE_UNAVAILABLE')
        need(path.is_file(), 'TEMPLATE_UNAVAILABLE')
        return path.read_bytes()

    def catalog(self):
        value = json.loads(self._read('catalog.json'))
        need(value.get('schema') == 1 and type(value.get('templates')) is list, 'TEMPLATE_UNAVAILABLE')
        return {'state': 'TEMPLATE_CATALOG', **value,
                'updates': 'BUNDLED_WITH_PLUGIN; software update installs new template versions; never auto-applies preferences'}

    def materials(self, template_id, version):
        catalog = self.catalog()
        # Current cards and retained versions share the same immutable material
        # contract. Old selected references remain readable after an upgrade.
        rows = catalog['templates'] + catalog.get('archived_templates', [])
        row = next((t for t in rows if t['id'] == template_id and t['version'] == version), None)
        need(row is not None, 'TEMPLATE_NOT_FOUND')
        prefix = row['id']+'/'+row['version']+'/'
        raw = self._read(prefix+'manifest.json')
        need(sha(raw) == row['manifest_sha256'], 'TEMPLATE_CHANGED')
        manifest = json.loads(raw)
        files = {name: self._read(prefix+name) for name in manifest['files']}
        need(all(sha(value) == manifest['files'][name]['sha256'] and
                 len(value) == manifest['files'][name]['bytes'] for name, value in files.items()), 'TEMPLATE_CHANGED')
        files['manifest.json'] = raw
        return row, manifest, files

    def bundle(self, template_id, version):
        row, manifest, files = self.materials(template_id, version)
        html = files['example/source.html'].decode()
        for image in manifest['assets']:
            url = 'data:'+image['mime']+';base64,'+base64.b64encode(files[image['file']]).decode()
            html = html.replace('../'+image['file'], url)
        files = dict(files, **{'example/complete.html': html.encode()})
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in sorted(files.items()):
                info = zipfile.ZipInfo(template_id+'/'+name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, value)
        return out.getvalue()

    def manifest(self, template_id, version):
        row, manifest, _ = self.materials(template_id, version)
        raw = self.bundle(template_id, version)
        return {'state': 'TEMPLATE_MANIFEST', **manifest, 'manifest_sha256': row['manifest_sha256'],
                'manifest_file': {'sha256': row['manifest_sha256'], 'bytes': len(self._read(template_id+'/'+version+'/manifest.json')),
                                  'chunks': (len(self._read(template_id+'/'+version+'/manifest.json'))+CHUNK-1)//CHUNK},
                'bundle': {'file': '@bundle', 'sha256': sha(raw), 'bytes': len(raw),
                           'chunks': (len(raw)+CHUNK-1)//CHUNK}, 'chunk_bytes': CHUNK}

    def part(self, template_id, version, manifest_sha256, file, index):
        row, manifest, files = self.materials(template_id, version)
        need(manifest_sha256 == row['manifest_sha256'], 'TEMPLATE_CHANGED')
        need(file == '@bundle' or file in files, 'TEMPLATE_FILE_NOT_FOUND')
        raw = self.bundle(template_id, version) if file == '@bundle' else files[file]
        need(type(index) is int and 0 <= index < max(1, (len(raw)+CHUNK-1)//CHUNK))
        chunk = raw[index*CHUNK:(index+1)*CHUNK]
        return {'state': 'TEMPLATE_PART', 'file': file, 'index': index,
                'manifest_sha256': manifest_sha256, 'sha256': sha(chunk),
                'base64': base64.b64encode(chunk).decode()}

    def selected(self, store, connection_id):
        need(type(connection_id) is str and bool(connection_id))
        target = {'connection_id': connection_id, 'scope': 'account'}
        current = store.summary(**target, effective=True)
        item = current['fields']['additional_notes']
        text = ''.join(store.read_chunk(**target, version_id=item['version_id'],
                                      field='additional_notes', index=i)['text'] for i in range(item['chunks']))
        need(sha(text.encode()) == item['sha256'], 'TEMPLATE_RULES_CHANGED')
        need(store.summary(**target, effective=True) == current, 'TEMPLATE_RULES_CHANGED')
        refs = [{'id': m[0], 'version': m[1], 'manifest_sha256': m[2]} for m in MARKER.findall(text)]
        return {'state': 'TEMPLATE_SELECTED', 'connection_id': connection_id, 'templates': refs,
                'preferences_only': True}

    def export(self, template_id, version, manifest_sha256, action, *, directory=None):
        """Fixed content-addressed ZIP; uncertain result is queried, never renamed."""
        from .own_configuration_export import _directory
        need(action in ('write', 'query'))
        row, _, _ = self.materials(template_id, version)
        need(row['manifest_sha256'] == manifest_sha256, 'TEMPLATE_CHANGED')
        raw = self.bundle(template_id, version)
        filename = 'OpenAhoy-'+template_id+'-'+version+'-'+sha(raw)[:16]+'.zip'
        folder = _directory(Path(directory) if directory is not None else Path.home()/'Downloads')
        temporary = '.openahoy-template-'+uuid.uuid4().hex
        created = False
        try:
            try:
                fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
            except FileNotFoundError:
                if action == 'query':
                    return {'state': 'TEMPLATE_EXPORT_NOT_FOUND'}
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
                created = True
                with os.fdopen(fd, 'wb') as output:
                    output.write(raw)
                    output.flush()
                    os.fsync(output.fileno())
                try:
                    os.link(temporary, filename, src_dir_fd=folder, dst_dir_fd=folder, follow_symlinks=False)
                except FileExistsError:
                    pass
                os.fsync(folder)
                fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
            with os.fdopen(fd, 'rb') as value:
                info = os.fstat(value.fileno())
                need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                     and info.st_size == len(raw) and not info.st_mode & 0o077, 'TEMPLATE_EXPORT_CONFLICT')
                need(value.read() == raw, 'TEMPLATE_EXPORT_CONFLICT')
            return {'state': 'TEMPLATE_EXPORTED', 'destination': 'Downloads', 'filename': filename,
                    'sha256': sha(raw), 'bytes': len(raw)}
        finally:
            if created:
                os.unlink(temporary, dir_fd=folder)
            os.close(folder)
