"""Current lineage validation using the unchanged relation policy.

The pinned historical relation module is not modified. Only successful pure
semantic projections are reused for identical verified manifest bytes. A broker
request can reuse pure parsing too; all SQL and relationship checks stay fresh.
"""
from .contracts import WCEError
from .own_lineage import POLICY, root_id
from .own_lineage_request import manifest, semantic_verified


def validate(db):
    rows = db.execute('SELECT * FROM own_articles ORDER BY rowid').fetchall()
    maps = {r['version']: dict(r) for r in db.execute('SELECT * FROM own_article_lineages')}
    if set(maps) != {r['version'] for r in rows}:
        raise WCEError('OWN_LINEAGE_CORRUPT')
    previous, bundles, semantic_values = {}, {}, {}

    def semantic_once(value, verified_digest, verified_raw):
        # manifest(row) still verifies each row before this lookup. Reuse only
        # a successful pure projection of those exact bytes within this call;
        # no authority, proof, SQL view or validation result is reused.
        key = (verified_digest, verified_raw)
        if key not in semantic_values:
            semantic_values[key] = semantic_verified(value, verified_digest)
        return semantic_values[key]

    for row in rows:
        m, current = manifest(row), maps[row['version']]
        if current['normalization_policy'] != POLICY or type(current['legacy']) is not int or current['legacy'] not in (0, 1):
            raise WCEError('OWN_LINEAGE_CORRUPT')
        if current['root_version'] not in previous and current['root_version'] != row['version']:
            raise WCEError('OWN_LINEAGE_CORRUPT')
        root = m if current['root_version'] == row['version'] else previous[current['root_version']][0]
        if (root['binding'] != m['binding'] or root_id(root, current['root_version'], current['legacy']) != current['lineage']
                or (current['legacy'] and root['bundle_id'] != m['bundle_id'])):
            raise WCEError('OWN_LINEAGE_CORRUPT')
        core = (current['lineage'], current['root_version'], current['legacy'])
        if row['bundle'] in bundles and bundles[row['bundle']] != core:
            raise WCEError('OWN_LINEAGE_CORRUPT')
        if row['bundle'] not in bundles and not current['legacy']:
            exact = next((v for v, checksum, raw in previous.values()
                          if v['binding'] == m['binding']
                          and semantic_once(v, checksum, raw)
                          == semantic_once(m, row['digest'], row['manifest'])), None)
            if exact is not None:
                prior = maps[exact['version']]
                if core != (prior['lineage'], prior['root_version'], prior['legacy']):
                    raise WCEError('OWN_LINEAGE_CORRUPT')
            elif current['root_version'] != m['version']:
                raise WCEError('OWN_LINEAGE_CORRUPT')
        bundles[row['bundle']] = core
        previous[m['version']] = (m, row['digest'], row['manifest'])
    return maps

