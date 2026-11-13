"""Article lineage identity and per-intent UNKNOWN isolation (formal schema5 and replacement6).

Relationships are conservative content checks, not a claim to infer a user's
intent after arbitrary rewriting. A revision always retains its original root.
"""
import json
import unicodedata

from .contracts import WCEError
from .service import canonical, digest

POLICY = 'ARTICLE_LINEAGE_NFKC_V1'
SCHEMA = """
CREATE TABLE own_article_lineages(
 version TEXT PRIMARY KEY REFERENCES own_articles(version),
 lineage TEXT NOT NULL, root_version TEXT NOT NULL REFERENCES own_articles(version),
 legacy INTEGER NOT NULL CHECK(typeof(legacy)='integer' AND legacy IN (0,1)),
 normalization_policy TEXT NOT NULL);
CREATE TABLE own_lineage_locks(
 tenant TEXT NOT NULL, resource TEXT NOT NULL, lineage TEXT NOT NULL,
 owner_id TEXT NOT NULL UNIQUE REFERENCES own_steps(id),
 PRIMARY KEY(tenant,resource,lineage));
"""


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def semantic(manifest):
    if manifest['schema'] in (2, 3):
        return {'format': manifest['schema'], 'members': members(manifest)}
    article = manifest['article']
    text = [(b['type'], normalized(b['text'])) for b in article['blocks'] if 'text' in b]
    return {'title': normalized(article['title']), 'text': text,
            'images': [(a['role'], a['slot'], a['sha256']) for a in manifest['assets']]}


def members(manifest):
    if manifest['schema'] == 1:
        a = semantic(manifest)
        return [{'title': a['title'], 'text': normalized(' '.join(
            b['text'] for b in manifest['article']['blocks'] if 'text' in b)),
            'images': sorted({x[2] for x in a['images']})}]
    from .documents import visible_text
    return [{'title': normalized(a['title']), 'text': normalized(visible_text(a)),
        'images': sorted({s['sha256'] for s in manifest['assets'] if s['slot'].startswith(a['id'] + '--')})}
        for a in manifest['document']['articles']]


def related(first, second):
    if first['schema'] == second['schema'] == 1:
        a, b = semantic(first), semantic(second)
        return (a['title'] == b['title'] or a['text'] == b['text']
                or bool({x[2] for x in a['images']} & {x[2] for x in b['images']}))
    return any(a['title'] == b['title'] or bool(a['text'] and a['text'] == b['text'])
               or bool(set(a['images']) & set(b['images']))
               for a in members(first) for b in members(second))


def root_id(manifest, root_version, legacy):
    return digest({'binding': manifest['binding'], 'policy': POLICY,
        'origin': {'legacy_bundle': manifest['bundle_id']} if legacy else {'root_version': root_version}})


def manifest(row):
    from .own_group_json import read
    return read(row['manifest'], row['digest'])


def mapping(db, version):
    row = db.execute('SELECT * FROM own_article_lineages WHERE version=?', (version,)).fetchone()
    if row is None:
        raise WCEError('OWN_LINEAGE_CORRUPT')
    return dict(row)


def seal(db, m):
    value = mapping(db, m['version'])
    return {k: value[k] for k in ('lineage', 'root_version', 'normalization_policy', 'legacy')} | {
        'tenant': m['binding']['tenant'], 'resource': m['binding']['resource']}


def unresolved(db):
    # The store's exact lock derivation already accounts for successful body
    # replacements. Legacy resource locks and scoped locks retain their owners.
    result = set()
    for row in db.execute('SELECT * FROM own_lineage_locks'):
        result.add(row['lineage'])
    for row in db.execute('SELECT kind,owner_id FROM own_resource_locks'):
        if row['kind'] == 'step':
            original = db.execute('SELECT intent FROM own_steps WHERE id=?', (row['owner_id'],)).fetchone()
        else:
            table = {'recovery': 'own_body_recoveries', 'body_followup': 'own_body_followups',
                     'body_attempt': 'own_body_attempts'}[row['kind']]
            original = db.execute('SELECT s.intent FROM own_steps s JOIN ' + table +
                ' r ON r.original_step_id=s.id WHERE r.id=?', (row['owner_id'],)).fetchone()
        if original is None:
            raise WCEError('OWN_LINEAGE_CORRUPT')
        result.add(mapping(db, json.loads(original['intent'])['selector']['version'])['lineage'])
    return result


def check_relations(db, m, current_id=None):
    own = mapping(db, m['version'])['lineage'] if db.execute(
        'SELECT 1 FROM own_article_lineages WHERE version=?', (m['version'],)).fetchone() else None
    blocked = unresolved(db)
    if current_id is not None:
        current = db.execute('SELECT * FROM own_lineage_locks WHERE owner_id=?', (current_id,)).fetchone()
        if current is not None:
            blocked.discard(current['lineage'])
    if own in blocked:
        raise WCEError('OWN_INTENT_RESULT_UNKNOWN')
    for row in db.execute('SELECT a.*,l.lineage FROM own_articles a JOIN own_article_lineages l ON l.version=a.version'):
        if row['lineage'] in blocked:
            old = manifest(row)
            if (old['binding']['tenant'], old['binding']['resource']) == (m['binding']['tenant'], m['binding']['resource']) and related(m, old):
                raise WCEError('OWN_RELATED_INTENT_RESULT_UNKNOWN')


def register(db, m, legacy=False):
    earlier = db.execute('SELECT a.*,l.lineage,l.root_version,l.legacy FROM own_articles a '
        'JOIN own_article_lineages l ON l.version=a.version ORDER BY a.rowid').fetchall()
    selected = next((r for r in earlier if r['bundle'] == m['bundle_id']), None)
    if selected is None and not legacy:
        selected = next((r for r in earlier if json.loads(r['binding']) == m['binding']
                         and semantic(manifest(r)) == semantic(m)), None)
    if selected is not None:
        lineage, root, old = selected['lineage'], selected['root_version'], selected['legacy']
        if old and selected['bundle'] != m['bundle_id']:
            raise WCEError('OWN_LEGACY_INTENT_WRITE_BLOCKED')
    else:
        root, old = m['version'], int(legacy)
        lineage = root_id(m, root, old)
    db.execute('INSERT INTO own_article_lineages VALUES(?,?,?,?,?)',
               (m['version'], lineage, root, old, POLICY))
    if not legacy:
        check_relations(db, m)


def validate(db):
    rows = db.execute('SELECT * FROM own_articles ORDER BY rowid').fetchall()
    maps = {r['version']: dict(r) for r in db.execute('SELECT * FROM own_article_lineages')}
    if set(maps) != {r['version'] for r in rows}:
        raise WCEError('OWN_LINEAGE_CORRUPT')
    previous, bundles = {}, {}
    for row in rows:
        m, current = manifest(row), maps[row['version']]
        if current['normalization_policy'] != POLICY or type(current['legacy']) is not int or current['legacy'] not in (0, 1):
            raise WCEError('OWN_LINEAGE_CORRUPT')
        if current['root_version'] not in previous and current['root_version'] != row['version']:
            raise WCEError('OWN_LINEAGE_CORRUPT')
        root = m if current['root_version'] == row['version'] else previous[current['root_version']]
        if (root['binding'] != m['binding'] or root_id(root, current['root_version'], current['legacy']) != current['lineage']
                or (current['legacy'] and root['bundle_id'] != m['bundle_id'])):
            raise WCEError('OWN_LINEAGE_CORRUPT')
        core = (current['lineage'], current['root_version'], current['legacy'])
        if row['bundle'] in bundles and bundles[row['bundle']] != core:
            raise WCEError('OWN_LINEAGE_CORRUPT')
        if row['bundle'] not in bundles and not current['legacy']:
            exact = next((v for v in previous.values() if v['binding'] == m['binding'] and semantic(v) == semantic(m)), None)
            if exact is not None:
                prior = maps[exact['version']]
                if core != (prior['lineage'], prior['root_version'], prior['legacy']):
                    raise WCEError('OWN_LINEAGE_CORRUPT')
            elif current['root_version'] != m['version']:
                raise WCEError('OWN_LINEAGE_CORRUPT')
        bundles[row['bundle']] = core
        previous[m['version']] = m
    return maps


def check_write(w, db, p, m, current_id=None, *, history_locators=None):
    # Every old proof, spent anchor and approval is still checked. This performs
    # no live token request and grants no permission to an old transaction.
    w.db._check_legacy_history(db, p.source_kind, history=history_locators)
    value = seal(db, m)
    if value['legacy']:
        raise WCEError('OWN_LEGACY_INTENT_WRITE_BLOCKED')
    check_relations(db, m, current_id)
    return value
