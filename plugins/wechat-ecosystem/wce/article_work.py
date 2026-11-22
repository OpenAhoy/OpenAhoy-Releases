"""Project pointers into the existing account-owned article and delivery journals."""
from base64 import b64encode
from pathlib import Path
import sqlite3

from . import documents
from .contracts import WCEError
from .draft_group_history_context import readonly_history_snapshot
from .draft_revision_guard import historical_identity_guard, policy_binding
from .own_connection_policy import registry_path, resolve
from .own_prepared_history import PreparedHistoryValidation, stored
from .service import canonical, digest
from .video_director import require

CHUNK = 180 * 1024
READER = PreparedHistoryValidation()


def member(manifest, article_id):
    if manifest['schema'] == 1:
        require(article_id == 'article', 'ARTICLE_WORK_MEMBER_MISSING')
        row = manifest['article']
        return row | {'id': 'article', 'cover': row['cover_asset_ref']}, {
            'article--' + item['slot']: item for item in manifest['assets']}
    for row in manifest['document']['articles']:
        if row['id'] == article_id:
            return row, {item['slot']: item for item in manifest['assets']
                         if item['slot'].startswith(article_id + '--')}
    raise WCEError('ARTICLE_WORK_MEMBER_MISSING')


def scope(connection, registry):
    registry = Path(registry) if registry is not None else registry_path()
    policy = resolve(connection, registry, active=False, readonly=True)
    guard = historical_identity_guard(policy)
    return registry, policy, guard, policy_binding(policy, 'OPERATOR_ATTESTED')


class BoundProfile:
    def __init__(self, binding):
        self.value = binding

    def binding(self):
        return self.value


def original_receipts(db, binding, bundle, version, content_hash, index):
    rows = []
    for row in db.execute(
        "SELECT id,state,readback,intent,intent_digest FROM own_steps "
        "WHERE tenant=? AND principal=? AND connection=? AND resource=? AND operation='add' "
        "AND json_extract(intent,'$.selector.bundle_id')=? "
        "AND json_extract(intent,'$.selector.version')=? ORDER BY rowid",
        (binding['tenant'], binding['principal'], binding['connection'], binding['resource'], bundle, version),
    ):
        intent = stored(row['intent'], row['intent_digest'])
        selector = intent['selector']
        require(intent['binding'] == binding and selector == {
            'bundle_id': bundle, 'version': version, 'content_digest': content_hash},
            'ARTICLE_WORK_RECEIPT_SCOPE_CHANGED')
        rows.append({'attempt_id': row['id'], 'draft_state': row['state'],
                     'readback_state': row['readback'], 'position': index})
    return rows


def publication_status(policy, registry, receipt):
    if receipt['draft_state'] != 'SUCCEEDED':
        return receipt
    from .current_publication_service import local_status
    try:
        status = local_status(policy, registry, receipt['attempt_id'])
    except (WCEError, OSError):
        return receipt | {'publication_state': 'LOCAL_STATUS_UNAVAILABLE'}
    return receipt | {
        'publication_state': status['state'], 'publication_handle': status['intent_handle'],
        'url': dict(status['article_urls']).get(receipt['position']),
    }


def snapshot(pointer, registry, *, version=None, detail=False, known_version=None, slot=None, offset=0, thumbnail=False, excerpt=False):
    registry, policy, guard, binding = scope(pointer['connection_id'], registry)
    require(pointer['binding'] == digest(binding), 'ARTICLE_WORK_BINDING_CHANGED')
    bundle, article_id = pointer['bundle_id'], pointer['article_id']
    with readonly_history_snapshot(policy, policy.root / 'state.sqlite3') as (db, _history):
        row = db.execute(
            'SELECT version,digest,manifest FROM own_articles WHERE binding=? AND bundle=? '
            'AND (? IS NULL OR version=?) ORDER BY revision DESC LIMIT 1',
            (canonical(binding), bundle, version, version),
        ).fetchone()
        require(row is not None, 'ARTICLE_WORK_SOURCE_UNAVAILABLE')
        manifest = stored(row['manifest'], row['digest'])
        article, assets = member(manifest, article_id)
        require(manifest['version'] == row['version'] and manifest['bundle_id'] == bundle
                and manifest['binding'] == binding, 'ARTICLE_WORK_BINDING_CHANGED')
        if detail and known_version != row['version']:
            verified, _ = READER._bundle_full(db, BoundProfile(binding), bundle, row['version'])
            article, assets = member(verified, article_id)
        if slot is not None:
            metadata = assets.get(slot)
            require(metadata is not None, 'ARTICLE_WORK_IMAGE_MISSING')
            verified, raw = READER._asset(db, binding, metadata['asset_ref'])
            require(verified == {key: item for key, item in metadata.items() if key != 'slot'},
                    'ARTICLE_WORK_IMAGE_CHANGED')
            if thumbnail:
                from .video_director_media import preview_image_bytes
                guard()
                return preview_image_bytes(raw, metadata['sha256'], False)
            require(0 <= offset < len(raw), 'ARTICLE_WORK_IMAGE_RANGE')
            payload = raw[offset:offset + CHUNK]
            guard()
            return {key: metadata[key] for key in ('sha256', 'size', 'declared_type')} | {
                'slot': slot, 'version': row['version'], 'offset': offset,
                'next': offset + len(payload), 'data': b64encode(payload).decode('ascii'),
            }
        result = {
            'title': article['title'], 'version': row['version'], 'revision': manifest['revision'],
            'bundle_id': bundle, 'article_id': article_id, 'connection_id': pointer['connection_id'],
            'account_label': policy.data['appid'], 'account_hint': policy.data['appid'][-6:],
            'content_digest': row['digest'],
        }
        # The configured label is read from the registry, with the
        # full binding still checked by the historical identity guard.
        if policy.value['schema'] == 2:
            from .own_connection_registry import check_member
            result['account_label'] = check_member(policy, revocation=False, readonly=True)['label']
        if excerpt:
            text = documents.visible_text(article)
            lines = (line.strip() for line in text.splitlines())
            result['excerpt'] = ' '.join(line for line in lines if line and line != article['title'])[:360]
        if not detail:
            result['images'] = {key: {k: item[k] for k in ('sha256', 'size', 'declared_type', 'role')}
                                for key, item in assets.items()}
        if detail:
            result['versions'] = [dict(item) for item in db.execute(
                'SELECT version,revision FROM own_articles WHERE bundle=? AND binding=? ORDER BY revision DESC',
                (bundle, canonical(binding)),
            )]
            if known_version != row['version']:
                cover = next(item for item in assets.values() if item['role'] == 'cover')
                urls = {key: 'data:,jiusera-' + key for key in assets}
                if manifest['schema'] == 1:
                    from .own_wire import render
                    mappings = {slot.removeprefix('article--'): {'url': url} for slot, url in urls.items()}
                    mappings['cover']['media_id'] = cover['asset_ref']
                    result['layout'] = render(article, mappings)['content']
                else:
                    result['layout'] = documents.render_blocks(article, urls, preview=True)
                result['author'] = article.get('author', '')
                result['cover'] = cover['slot'] if manifest['schema'] != 1 else 'article--cover'
                result['images'] = {key: {k: item[k] for k in ('sha256', 'size', 'declared_type', 'role')}
                                    for key, item in assets.items()}
                result['source_sha256'] = article.get('provenance', {}).get('source_sha256')
            ids = [item['id'] for item in manifest['document']['articles']] if manifest['schema'] != 1 else ['article']
            receipts = original_receipts(db, binding, bundle, row['version'], row['digest'], ids.index(article_id) + 1)
        guard()
    if detail:
        result['receipts'] = [publication_status(policy, registry, receipt) for receipt in receipts]
        guard()
    return result


def read_work(director, registry, args, *, media=False):
    overview = director.overview(args['project_id'], args['work_id'])
    work = overview['work']
    require(work.get('kind') == 'article', 'ARTICLE_WORK_NOT_FOUND')
    if media:
        value = snapshot(work['article'], registry, version=args['version'], slot=args['slot'], offset=args['offset'])
    else:
        value = snapshot(work['article'], registry, version=args.get('version'), detail=True,
                         known_version=args.get('known_version'))
    return value | {'project_id': overview['project_id'], 'work_id': work['id']}


def register(director, registry, args):
    _, _, _, binding = scope(args['connection_id'], registry)
    pointer = {key: args[key] for key in ('connection_id', 'bundle_id', 'article_id')} | {'binding': digest(binding)}
    original = snapshot(pointer, registry, version=args['version'], detail=True)
    if 'source_sha256' in args:
        require(original['source_sha256'] == args['source_sha256'], 'ARTICLE_WORK_SOURCE_CHANGED')
    return director.edit({'action': 'register_article', 'project_id': args['project_id'],
                          'operation_id': args['operation_id'], 'fields': {'title': original['title']},
                          'article': pointer}, None)


def prepared_result(director, registry, arguments, result):
    """The original prepare succeeds independently of its project cross-reference."""
    sources = arguments.get('html_sources')
    if not sources:
        return result
    try:
        from .project_context import exact_path
        paths = [exact_path(source['absolute_path']) for source in sources]
        projects = director.projects.view()['projects']
        eligible = [row for row in projects if all(path.is_relative_to(row['root']) for path in paths)]
        if not eligible:
            return result | {'workbench': {'state': 'PROJECT_NOT_REGISTERED'}}
        project = max(eligible, key=lambda row: len(Path(row['root']).parts))
        root, pin = director.project(project['id'])
        state = director.load(project['id'], director.storage(root, pin))
        _, _, _, binding = scope(arguments['connection_id'], registry)
        existing = {
            row['article']['article_id']: row['id'] for row in state['works'].values()
            if row.get('kind') == 'article' and row['article']['bundle_id'] == result['bundle_id']
            and row['article']['connection_id'] == arguments['connection_id']
            and row['article']['binding'] == digest(binding)
        }
        rows = []
        for source in sources:
            article_id = source['article_id']
            if article_id in existing:
                rows.append({'article_id': article_id, 'work_id': existing[article_id]})
                continue
            key = digest(['article', project['id'], arguments['connection_id'],
                          result['bundle_id'], result['version'], article_id])[:32]
            saved = register(director, registry, {
                'project_id': project['id'], 'operation_id': key, 'connection_id': arguments['connection_id'],
                'bundle_id': result['bundle_id'], 'version': result['version'], 'article_id': article_id,
                'source_sha256': source['expected_sha256'],
            })
            rows.append({'article_id': source['article_id'], 'work_id': saved['work_id']})
        return result | {'workbench': {'state': 'REGISTERED', 'project_id': project['id'], 'works': rows}}
    except (OSError, sqlite3.Error, WCEError) as error:
        return result | {'workbench': {'state': 'REGISTRATION_INCOMPLETE',
                                        'reason': getattr(error, 'code', 'ARTICLE_WORK_STORAGE_UNAVAILABLE')}}


def catalog(director, registry, selected=None, *, excerpt=False):
    projects = [row for row in director.registered() if selected is None or row['id'] == selected]
    result = []
    for project in projects:
        try:
            root, pin = director.project(project['id'])
            state = director.load(project['id'], director.storage(root, pin))
        except (OSError, WCEError):
            project['unavailable'] = True
            continue
        for work in state['works'].values():
            if work.get('kind') != 'article':
                continue
            row = {'project_id': project['id'], 'project': project['name'], 'work_id': work['id']}
            try:
                article = snapshot(work['article'], registry, excerpt=excerpt)
                row.update({key: value for key, value in article.items() if key != 'images'})
            except (OSError, sqlite3.Error, WCEError) as error:
                row.update(title=work['title'], error=getattr(error, 'code', 'ARTICLE_WORK_SOURCE_UNAVAILABLE'))
            result.append(row)
    return {'articles': result, 'projects': projects}
