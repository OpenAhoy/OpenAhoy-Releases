"""Registered local producer bytes, not a claim to authenticate a Codex thread."""
from hashlib import sha256
import os
from pathlib import Path
import re
import stat

from .contracts import WCEError
from .bounded_file import file_state
from .service import canonical, digest
from .publication_contract import strict_json, exact, member_claims, fail, stable_account

SCHEMA = 'WCE_LOCAL_PUBLISH_CANDIDATE_V1'
MANIFEST = 'publication-manifest.json'
MAX_TOTAL = 128 * 1024 * 1024


class RegisteredRoot:
    def __init__(self, root, expected=None):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            fail('PUBLICATION_PRODUCER_ROOT_INVALID')
        resolved = self.root.resolve(strict=True)
        if resolved != self.root:
            fail('PUBLICATION_PRODUCER_ROOT_INVALID')
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            self.close(); fail('PUBLICATION_PRODUCER_ROOT_INVALID')
        self.identity = {'path': str(self.root), 'dev': info.st_dev, 'ino': info.st_ino,
                         'uid': info.st_uid}
        if expected is not None and self.identity != expected:
            self.close(); fail('PUBLICATION_PRODUCER_ROOT_CHANGED')
        self.total = 0

    def close(self):
        if getattr(self, 'fd', None) is not None:
            os.close(self.fd); self.fd = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def check_root(self):
        info = os.fstat(self.fd)
        actual = os.stat(self.root, follow_symlinks=False)
        if (self.root.resolve(strict=True) != self.root or not stat.S_ISDIR(actual.st_mode)
                or (info.st_dev, info.st_ino, info.st_uid) != (actual.st_dev, actual.st_ino, actual.st_uid)
                or self.identity != {'path': str(self.root), 'dev': actual.st_dev,
                                     'ino': actual.st_ino, 'uid': actual.st_uid}):
            fail('PUBLICATION_PRODUCER_ROOT_CHANGED')

    def read(self, relative, maximum=8 * 1024 * 1024):
        if (type(relative) is not str or not relative or len(relative) > 4096
                or '\\' in relative or relative.startswith('/')
                or any(x in ('', '.', '..') for x in relative.split('/'))):
            fail('PUBLICATION_PRODUCER_PATH_INVALID')
        components = relative.split('/')
        parent = os.dup(self.fd)
        opened, chain = [parent], []
        try:
            for component in components[:-1]:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                chain.append((parent, component, next_fd))
                opened.append(next_fd); parent = next_fd
            fd = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                before = os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                        or before.st_nlink != 1 or not 0 < before.st_size <= maximum):
                    fail('PUBLICATION_PRODUCER_INPUT_INVALID')
                chunks, size = [], 0
                while True:
                    chunk = os.read(fd, min(65536, maximum + 1 - size))
                    if not chunk: break
                    chunks.append(chunk); size += len(chunk)
                    if size > maximum: fail('PUBLICATION_INPUT_ENVELOPE')
                if (file_state(os.fstat(fd)) != file_state(before)
                        or file_state(os.stat(components[-1], dir_fd=parent, follow_symlinks=False)) != file_state(before)):
                    fail('PUBLICATION_PRODUCER_INPUT_CHANGED')
                self.check_root()
                for ancestor, name, child in chain:
                    if file_state(os.fstat(child)) != file_state(os.stat(name, dir_fd=ancestor, follow_symlinks=False)):
                        fail('PUBLICATION_PRODUCER_INPUT_CHANGED')
                self.total += size
                if self.total > MAX_TOTAL: fail('PUBLICATION_INPUT_ENVELOPE')
                return b''.join(chunks), {'relative_path': relative, 'size': size,
                    'sha256': sha256(b''.join(chunks)).hexdigest(), 'state': list(file_state(before))}
            finally: os.close(fd)
        finally:
            for directory in reversed(opened): os.close(directory)

    def candidate(self, handle):
        if type(handle) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,95}', handle):
            fail('PUBLICATION_ARTIFACT_HANDLE_INVALID')
        base = handle + '/'
        raw, pin = self.read(base + MANIFEST, 512 * 1024)
        value = strict_json(raw)
        exact(value, 'schema draft_request_key document_path sources preview_paths intent')
        if value['schema'] != SCHEMA or value['intent'] not in ('FREEPUBLISH', 'HUMAN_EXPLICIT_MASS'):
            fail('PUBLICATION_CANDIDATE_INVALID')
        if (type(value['draft_request_key']) is not str or not re.fullmatch('[A-Za-z0-9._:-]{1,128}', value['draft_request_key'])
                or type(value['sources']) is not list or not 1 <= len(value['sources']) <= 64
                or type(value['preview_paths']) is not list or not 1 <= len(value['preview_paths']) <= 16):
            fail('PUBLICATION_CANDIDATE_INVALID')
        document_raw, document_pin = self.read(base + value['document_path'], 1024 * 1024)
        doc = strict_json(document_raw, 1024 * 1024)
        exact(doc, 'document')
        normalized = doc['document']
        if type(normalized) is dict and normalized.get('format') == 3:
            from .html_document import normalize
            normalized = normalize(normalized)
        sources, previews, pins = [], [], [pin, document_pin]
        total_sources = 0
        for source in value['sources']:
            exact(source, 'id path url')
            if (type(source['id']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', source['id'])
                    or type(source['url']) is not str or not source['url'].startswith('https://')):
                fail('PUBLICATION_SOURCE_INVALID')
            body, meta = self.read(base + source['path'])
            total_sources += len(body)
            if total_sources > 32 * 1024 * 1024: fail('PUBLICATION_SOURCE_ENVELOPE')
            try: text = body.decode('utf-8', 'strict')
            except UnicodeError: fail('PUBLICATION_SOURCE_INVALID')
            sources.append({'id': source['id'], 'url': source['url'], 'text': text, 'sha256': meta['sha256']})
            pins.append(meta)
        if len({s['id'] for s in sources}) != len(sources): fail('PUBLICATION_SOURCE_INVALID')
        for path in value['preview_paths']:
            body, meta = self.read(base + path, 8 * 1024 * 1024)
            if not (body.startswith(b'\x89PNG\r\n\x1a\n') or body.startswith(b'\xff\xd8')):
                fail('PUBLICATION_PREVIEW_INVALID')
            previews.append({'id': 'preview-' + str(len(previews) + 1), 'data': body, 'sha256': meta['sha256']})
            pins.append(meta)
        return {'handle': handle, 'manifest': value, 'document': normalized,
                'sources': sources, 'previews': previews, 'pins': pins,
                'root_identity': dict(self.identity)}

    def unchanged(self, pins):
        for pin in pins:
            _, actual = self.read(pin['relative_path'], max(8 * 1024 * 1024, pin['size']))
            if actual != pin: fail('PUBLICATION_PRODUCER_INPUT_CHANGED')


MAX_HISTORY = 10000
MAX_ASSET = 2 * 1024 * 1024
MAX_BASELINE_BYTES = 2 * 1024**3
BASELINE_PROFILE = 'PUBLICATION_BASELINE_REAL_ASSETS_V2'
MAX_BASELINE_CLAIMS = MAX_HISTORY * 32


def _account_binding(value, account):
    if type(value) is not dict:
        fail('PUBLICATION_BASELINE_INCOMPLETE')
    return value.get('account') == account and value.get('resource') == account


def _asset(db, ref, binding, expected=None):
    size_row = db.execute('SELECT length(data) AS actual,size FROM own_assets WHERE id=?', (ref,)).fetchone()
    if size_row is None or type(size_row['size']) is not int or not 0 < size_row['size'] <= MAX_ASSET or size_row['actual'] != size_row['size']:
        fail('PUBLICATION_BASELINE_ASSET_INVALID')
    row = db.execute('SELECT * FROM own_assets WHERE id=?', (ref,)).fetchone()
    if row is None:
        fail('PUBLICATION_BASELINE_ASSET_MISSING')
    raw = bytes(row['data'])
    fingerprint = sha256(raw).hexdigest()
    if (not 0 < len(raw) <= MAX_ASSET or len(raw) != row['size']
            or fingerprint != row['sha256'] or row['binding'] != canonical(binding)
            or row['mime'] not in ('image/png', 'image/jpeg')):
        fail('PUBLICATION_BASELINE_ASSET_INVALID')
    if expected is not None and (expected['sha256'] != fingerprint
            or expected['size'] != len(raw) or expected['declared_type'] != row['mime']
            or expected['role'] != row['role']):
        fail('PUBLICATION_BASELINE_ASSET_INVALID')
    return fingerprint, len(raw)


def _body_images(document, article, lookup):
    if document.get('format') == 3:
        from .html_document import Fragment, POLICY
        slots = Fragment(article['canonical_html'], policy=article.get('style_policy', POLICY)).slots
        refs = {item['slot']: item['asset_ref'] for item in article['image_slots']}
        if set(slots) != set(refs): fail('PUBLICATION_BASELINE_INCOMPLETE')
        return [lookup[refs[slot]] for slot in slots]
    return [lookup[block['asset_ref']] for block in article['blocks'] if block['type'] == 'image']


def document_members(manifest, db=None):
    """One shared content rule. Only body images are substantive publication images.

    db is mandatory at baseline/admission boundaries. Without it callers may only
    consume an already validated manifest (e.g. the frozen QA projection).
    """
    from .documents import visible_text, assets
    lookup = {}
    for meta in manifest['assets']:
        lookup[meta['asset_ref']] = (_asset(db, meta['asset_ref'], manifest['binding'], meta)[0]
                                   if db is not None else meta['sha256'])
    if manifest['schema'] == 1:
        article = manifest['article']
        return [{'id': '1', 'title': article['title'],
            'text': '\n'.join(b['text'] for b in article['blocks'] if 'text' in b),
            'images': [lookup[a['asset_ref']] for a in manifest['assets'] if a['role'] == 'body']}]
    mapped = list(assets(manifest['document']))
    expected = {(a['slot'], a['asset_ref'], a['role']) for a in manifest['assets']}
    if len(expected) != len(manifest['assets']) or set(mapped) != expected:
        fail('PUBLICATION_BASELINE_INCOMPLETE')
    return [{'id': a['id'], 'title': a['title'], 'text': visible_text(a),
        'images': _body_images(manifest['document'], a, lookup)}
        for a in manifest['document']['articles']]


def _root_members(document, db, account):
    from .documents import normalize, assets, visible_text
    document = normalize(document)
    mapped = list(assets(document))
    lookup, used_bytes = {}, 0
    for slot, ref, role in mapped:
        row = db.execute('SELECT binding,role FROM own_assets WHERE id=?', (ref,)).fetchone()
        if row is None:
            fail('PUBLICATION_BASELINE_ASSET_MISSING')
        bound = strict_json(row['binding'].encode())
        if not _account_binding(bound, account) or row['role'] != role:
            fail('PUBLICATION_BASELINE_ASSET_INVALID')
        fp, size = _asset(db, ref, bound)
        lookup[ref] = fp
        used_bytes += size
    return [{'id': a['id'], 'title': a['title'], 'text': visible_text(a),
        'images': _body_images(document, a, lookup)}
        for a in document['articles']], used_bytes


def _tree(source):
    """Bounded fd-relative inventory, including noncandidate files; no symlinks."""
    entries, total = [], 0
    def walk(fd, prefix):
        nonlocal total
        if prefix.count('/') > 32 or len(prefix) > 4096:
            fail('PUBLICATION_BASELINE_ENVELOPE')
        before_names = sorted(os.listdir(fd))
        for name in before_names:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            relative = prefix + name
            if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid()
                    or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
                fail('PUBLICATION_BASELINE_INCOMPLETE')
            if stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1: fail('PUBLICATION_BASELINE_INCOMPLETE')
                total += info.st_size
            entries.append((relative, list(file_state(info)), 'DIR' if stat.S_ISDIR(info.st_mode) else 'FILE'))
            if len(entries) > MAX_HISTORY or total > MAX_BASELINE_BYTES:
                fail('PUBLICATION_BASELINE_ENVELOPE')
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    if file_state(os.fstat(child)) != file_state(info):
                        fail('PUBLICATION_BASELINE_INCOMPLETE')
                    walk(child, relative + '/')
                    if (file_state(os.fstat(child)) != file_state(info)
                            or file_state(os.stat(name, dir_fd=fd, follow_symlinks=False)) != file_state(info)):
                        fail('PUBLICATION_BASELINE_INCOMPLETE')
                finally: os.close(child)
        if before_names != sorted(os.listdir(fd)):
            fail('PUBLICATION_BASELINE_INCOMPLETE')
    walk(source.fd, '')
    source.check_root()
    return entries, total


def _history(db, account):
    """The complete bounded own_articles generation for this platform account."""
    from .own_group_json import read as read_manifest
    if db.execute('SELECT COUNT(*) FROM own_articles').fetchone()[0] > MAX_HISTORY:
        fail('PUBLICATION_BASELINE_ENVELOPE')
    cutoff = db.execute('SELECT COALESCE(MAX(rowid),0) FROM own_articles').fetchone()[0]
    claims, pins, total = set(), [], 0
    for row in db.execute('SELECT rowid AS baseline_rowid,* FROM own_articles ORDER BY rowid'):
        binding = strict_json(row['binding'].encode())
        if not _account_binding(binding, account):
            continue
        manifest = read_manifest(row['manifest'], row['digest'])
        if manifest['binding'] != binding or manifest['version'] != row['version']:
            fail('PUBLICATION_BASELINE_INCOMPLETE')
        lineage = db.execute('SELECT * FROM own_article_lineages WHERE version=?', (row['version'],)).fetchone()
        if lineage is None:
            fail('PUBLICATION_BASELINE_LINEAGE_MISSING')
        root = db.execute('SELECT * FROM own_articles WHERE version=?', (lineage['root_version'],)).fetchone()
        if root is None or not _account_binding(strict_json(root['binding'].encode()), account):
            fail('PUBLICATION_BASELINE_INCOMPLETE')
        from .own_lineage import POLICY, root_id
        root_manifest = read_manifest(root['manifest'], root['digest'])
        if (lineage['normalization_policy'] != POLICY or lineage['legacy'] not in (0, 1)
                or lineage['lineage'] != root_id(root_manifest, lineage['root_version'], lineage['legacy'])):
            fail('PUBLICATION_BASELINE_INCOMPLETE')
        members = document_members(manifest, db)
        claims.update(member_claims(members))
        claims.update({('VERSION', row['version']), ('ROOT', lineage['lineage'])})
        asset_pins = []
        for meta in manifest['assets']:
            fp, size = _asset(db, meta['asset_ref'], binding, meta)
            total += size
            if total > MAX_BASELINE_BYTES: fail('PUBLICATION_BASELINE_ENVELOPE')
            asset_pins.append((meta['asset_ref'], fp, size))
        pins.append({'rowid': row['baseline_rowid'], 'version': row['version'],
            'manifest_sha': row['digest'], 'lineage': dict(lineage), 'assets': asset_pins})
    return claims, {'cutoff_rowid': cutoff, 'account': account,
        'rows': len(pins), 'asset_bytes': total, 'inventory_sha': digest(pins)}


def baseline(root, *, db, account, expected_root=None):
    """Caller owns dispatch lock + an explicit SQLite snapshot throughout.

    Complete registered-root inventory plus all known account versions, including
    unsaved roots. Any unreadable/missing asset, lineage or unstable entry holds.
    """
    if not db.in_transaction:
        fail('PUBLICATION_BASELINE_SNAPSHOT_REQUIRED')
    account_key = stable_account({'appid': account})
    found, history = _history(db, account)
    pins = []
    try:
        with RegisteredRoot(root, expected_root) as source:
            entries, total = _tree(source)
            handles = []
            for relative, state, kind in entries:
                if relative.endswith('/' + MANIFEST):
                    if len(relative.split('/')) != 2:
                        fail('PUBLICATION_BASELINE_INCOMPLETE')
                    handles.append(relative.split('/')[0])
                elif relative == MANIFEST:
                    fail('PUBLICATION_BASELINE_INCOMPLETE')
            direct_directories = {relative for relative, state, kind in entries
                                  if '/' not in relative and kind == 'DIR'}
            if set(handles) != direct_directories:
                fail('PUBLICATION_BASELINE_INCOMPLETE')
            read_bytes = history['asset_bytes']
            for handle in handles:
                source.total = 0
                candidate = source.candidate(handle)
                members, used = _root_members(candidate['document'], db, account)
                read_bytes += used
                if read_bytes > MAX_BASELINE_BYTES: fail('PUBLICATION_BASELINE_ENVELOPE')
                found.update(member_claims(members))
                source.total = 0
                source.unchanged(candidate['pins'])
                pins.extend(candidate['pins'])
            if _tree(source) != (entries, total):
                fail('PUBLICATION_BASELINE_INCOMPLETE')
            again, current = _history(db, account)
            if current != history or not again <= found:
                fail('PUBLICATION_BASELINE_INCOMPLETE')
            if len(found) > MAX_BASELINE_CLAIMS:
                fail('PUBLICATION_BASELINE_ENVELOPE')
            return {'schema': BASELINE_PROFILE, 'account_key': account_key,
                'root_identity': source.identity, 'claims': sorted(found),
                'files': len(entries), 'bytes': total, 'pins_sha': digest(pins),
                'tree_sha': digest(entries), 'history': history}
    except (OSError, KeyError, TypeError, ValueError):
        fail('PUBLICATION_BASELINE_INCOMPLETE')


def check_baseline(db, account_key, channel_id, policy):
    """Coverage rows are useful only while their entire anchored set is intact."""
    if policy.get('baseline_profile') != BASELINE_PROFILE:
        fail('PUBLICATION_BASELINE_UNVERIFIED')
    rows = db.execute('SELECT kind,fingerprint FROM publication_baseline_members '
        'WHERE account_key=? AND channel_id=? ORDER BY kind,fingerprint',
        (account_key, channel_id)).fetchmany(MAX_BASELINE_CLAIMS + 1)
    claims = [tuple(row) for row in rows]
    if (len(claims) > MAX_BASELINE_CLAIMS or len(claims) != policy.get('baseline_claims_count')
            or digest(claims) != policy.get('baseline_claims_sha')):
        fail('PUBLICATION_BASELINE_UNVERIFIED')
