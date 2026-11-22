"""Project-owned character references shared by the library and storyboard editor."""

from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import os
import stat
import subprocess
from pathlib import Path
from secrets import token_hex
import tempfile
import wave

from .bounded_file import FileSource, MAX_SOURCE_HTML_BYTES, file_state, identity
from .contracts import WCEError
from .prepared_contracts import strict_validate
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked
from .project_context import text as project_text
from .service import digest
from .video_director import require
from .video_jobs import Jobs
from .video_director_media import IMAGE_CHUNK, local_file, preview_image, rename_image, source_image


INDEX = 'character-library.json'
APPEARANCE_INDEX = 'character-library-appearance.json'
ASSET_ROOT = 'JiuseraAssets'
LEGACY_ASSET_FOLDER = ('Jiusera资产', '形象')
ID = {'type': 'string', 'pattern': '^[a-z0-9][a-z0-9._-]{0,79}$', 'maxLength': 80}
DIGEST = {'type': 'string', 'pattern': '^[a-f0-9]{64}$', 'maxLength': 64}
PATH = {'type': 'string', 'minLength': 1, 'maxLength': 4096}
USE = {'type': 'string', 'enum': ['full_body', 'face', 'expression', 'pose', 'style',
                                  'angle', 'wardrobe', 'accessory', 'voice']}
EXTENDED_USES = {'angle', 'wardrobe', 'accessory', 'voice'}
NORMAL_FORM = {'id': 'normal', 'name': '常态'}
STATUS = {'type': 'string', 'enum': ['candidate', 'current', 'historical']}
NAME = {'type': 'string', 'minLength': 1, 'maxLength': 160, 'x-wce-maxUtf8Bytes': 640}
NOTE = {'type': 'string', 'maxLength': 1000, 'x-wce-maxUtf8Bytes': 4000}


def object_schema(properties, optional=None):
    return {'type': 'object', 'properties': properties | (optional or {}), 'required': list(properties),
            'additionalProperties': False}


FORM = object_schema({'id': ID, 'name': NAME})
PROFILE = object_schema({}, {key: NAME for key in ('height', 'blood_type', 'zodiac', 'mbti', 'personality')})
CROP = object_schema({'source_version_id': ID} | {
    key: {'type': 'integer', 'minimum': 0 if key in ('x', 'y') else 1}
    for key in ('x', 'y', 'width', 'height')
})
PINNED_CROP = object_schema(CROP['properties'] | {'source_sha256': DIGEST})
APPEARANCE_GROUPS = ('base', 'features', 'hair', 'wardrobe', 'accessories')
GEAR_GROUPS = ('hair', 'wardrobe', 'accessories')
GROUP = {'type': 'string', 'enum': list(APPEARANCE_GROUPS)}
VIEWS = {'type': 'string', 'enum': [
    'head_front', 'head_blank', 'body_blank', 'front', 'three_quarter', 'side', 'back', 'overview', 'asset',
]}
TRY_ON_PARTS = {
    'base': ('body',),
    'hair': ('hair-silver', 'hair-bob', 'hair-tied'),
    'wardrobe': ('wardrobe-training', 'wardrobe-suit', 'wardrobe-gala'),
    'accessories': ('accessories-none', 'accessories-boots', 'accessories-jewels'),
}
TRY_ON = object_schema({'rig': {'type': 'string', 'const': 'atelier-demo-v1'}, 'part': {
    'type': 'string', 'enum': [part for group in TRY_ON_PARTS.values() for part in group],
}})
APPEARANCE_PIN = object_schema({'group': GROUP, 'item_id': ID, 'view': VIEWS}, {'try_on': TRY_ON})
APPEARANCE = object_schema({key: APPEARANCE_PIN['properties'][key] for key in APPEARANCE_PIN['required']} | {
    'item_name': NAME,
    'format': {'type': 'string', 'enum': ['individual', 'source_detail', 'combined', 'full_look']},
}, {
    'version_label': NAME, 'set_id': ID, 'try_on': TRY_ON,
    'details': {'type': 'array', 'maxItems': 24, 'items': object_schema({
        'name': NAME, 'visibility': {'type': 'string', 'enum': ['visible', 'partial', 'covered']},
    }, {'focus': {'type': 'string', 'enum': ['left-eye', 'right-eye']},
        'region': object_schema({part: {'type': 'integer', 'minimum': 1 if part in ('width', 'height') else 0,
                                       'maximum': 10000} for part in ('x', 'y', 'width', 'height')})})},
    'combination': {'type': 'array', 'minItems': 1, 'maxItems': 3, 'items': ID},
})
REFERENCE = object_schema({'character_id': ID, 'form_id': ID, 'version_id': ID},
                          {'work_id': ID, 'crop': PINNED_CROP, 'appearance': APPEARANCE_PIN})
LAYOUT = {
    'form': FORM, 'category': {'type': 'string', 'enum': ['standard', 'special']},
    'work_id': ID, 'crop': CROP, 'face_visible': {'type': 'boolean'}, 'appearance': APPEARANCE,
}


ENTRY = object_schema({
    'id': ID, 'character': object_schema({
        'id': ID, 'name': NAME, 'series': NAME,
        'aliases': {'type': 'array', 'items': NAME, 'maxItems': 24},
    }, {'profile': PROFILE}),
    'use': USE, 'initial_status': STATUS, 'label': NAME, 'description': NOTE,
    'source': NOTE, 'path': PATH, 'sha256': DIGEST,
}, LAYOUT)
ORIGIN = object_schema({'project_id': ID, 'version_id': ID, 'sha256': DIGEST})
SELECTOR = {'version_id': ID}
SOURCE = object_schema({'path': PATH, 'sha256': DIGEST})


BROWSE_GUIDE_PATH = f'{ASSET_ROOT}/Characters/browse-guide.json'
BROWSE_REVISIONS_PATH = f'{ASSET_ROOT}/Characters/browse-revisions.json'
BROWSE_FITS_PATH = f'{ASSET_ROOT}/Characters/browse-front-fits.json'
BROWSE_ACCESSORY_FITS_PATH = f'{ASSET_ROOT}/Characters/browse-front-accessories.json'
BROWSE_LAYERS_PATH = f'{ASSET_ROOT}/Characters/browse-front-layers.json'
BROWSE_DISPLAY_PATH = f'{ASSET_ROOT}/Characters/browse-wardrobe-display.json'
BROWSE_GROUP_NAMES = ('base', 'features', 'torso', 'limbs', 'details', 'hair', 'wardrobe', 'accessories', 'voice')
BROWSE_GROUP = {'type': 'string', 'enum': list(BROWSE_GROUP_NAMES)}
BROWSE_PIN = {'version': ID, 'sha256': DIGEST}


def guide_list(items, limit):
    return {'type': 'array', 'maxItems': limit, 'items': object_schema(items)}


BROWSE_PROVENANCE = object_schema({
    'treatment': {'type': 'string', 'enum': ['source_upscale', 'generated_upscale']},
    'confirmation': {'type': 'string', 'enum': ['reference', 'unconfirmed']},
    'source_name': NAME, 'source_sha256': DIGEST,
    'restoration': NAME,
}, {'source_box': {'type': 'array', 'minItems': 4, 'maxItems': 4,
                   'items': {'type': 'integer', 'minimum': 0}}})
BROWSE_ENTRY = BROWSE_PIN | {'group': BROWSE_GROUP, 'label': NAME, 'note': NOTE, 'caption': NOTE}
BROWSE_GUIDE_FIELDS = {
    'character': ID, 'form': ID, 'baseline': ID,
    'entries': guide_list(BROWSE_ENTRY, 128),
    'archive': guide_list(BROWSE_PIN, 128),
    'measurements': guide_list({'label': NAME, 'value': NAME, 'basis': NOTE}, 24),
    'reviews': guide_list({'group': BROWSE_GROUP, 'title': NAME, 'text': NOTE}, 24),
    'pending': guide_list({'group': BROWSE_GROUP, 'title': NAME, 'text': NOTE}, 24),
}
BROWSE_GUIDES = object_schema({
    'schema': {'type': 'integer', 'enum': [1]},
    'guides': {'type': 'array', 'maxItems': 24, 'items': object_schema(BROWSE_GUIDE_FIELDS)},
})
BROWSE_REVISIONS = object_schema({
    'schema': {'type': 'integer', 'enum': [1]},
    'guides': {'type': 'array', 'maxItems': 24, 'items': object_schema(BROWSE_GUIDE_FIELDS | {
        'revision': ID, 'title': NAME,
        'entries': {'type': 'array', 'maxItems': 128,
                    'items': object_schema(BROWSE_ENTRY, {'provenance': BROWSE_PROVENANCE})},
    })},
})


BROWSE_FIT_KEYS = {'revision': ID, 'base': object_schema(BROWSE_PIN), 'result': object_schema(BROWSE_PIN)}
BROWSE_FITS = object_schema({
    'schema': {'type': 'integer', 'enum': [1]},
    'fits': {'type': 'array', 'maxItems': 32, 'items': object_schema(
        BROWSE_FIT_KEYS | {'garment': object_schema(BROWSE_PIN)})},
})
BROWSE_ACCESSORY_FITS = object_schema({
    'schema': {'type': 'integer', 'enum': [1]},
    'fits': {'type': 'array', 'maxItems': 32, 'items': object_schema(
        BROWSE_FIT_KEYS | {'accessory': object_schema(BROWSE_PIN)},
        {'garment': object_schema(BROWSE_PIN)})},
})

BROWSE_LAYER_VARIANT = {'garment': object_schema(BROWSE_PIN), 'asset': object_schema(BROWSE_PIN)}
BROWSE_LAYER_PIECE = object_schema({
    'asset': object_schema(BROWSE_PIN),
    'box': {'type': 'array', 'minItems': 4, 'maxItems': 4,
            'items': {'type': 'integer', 'minimum': 0, 'maximum': 4096}},
    'variants': guide_list(BROWSE_LAYER_VARIANT, 8),
}, {'legacy_accessory': ID})
BROWSE_LAYERS = object_schema({
    'schema': {'type': 'integer', 'enum': [1]},
    'sets': guide_list({
        'revision': ID, 'baseline': object_schema(BROWSE_PIN),
        'underlays': guide_list(BROWSE_LAYER_VARIANT, 8),
        'pieces': {'type': 'array', 'maxItems': 24, 'items': BROWSE_LAYER_PIECE},
    }, 24),
})

def display_box(limit):
    return {'type': 'array', 'minItems': 4, 'maxItems': 4,
            'items': {'type': 'integer', 'minimum': 0, 'maximum': limit}}


BROWSE_DISPLAY_ITEM = object_schema({
    'id': ID, 'label': NAME, 'asset': object_schema(BROWSE_PIN),
    'source_box': display_box(720), 'display_box': display_box(1000),
    'outline': {'type': 'string', 'minLength': 3, 'maxLength': 4000,
                'pattern': r'^[0-9 MLCHVQSZTAmlchvqszta.,-]+$'},
    'group': {'type': 'string', 'enum': ['wardrobe', 'accessories']},
}, {'part': NAME, 'hanger': {'type': 'boolean'}, 'rotate': {'type': 'integer', 'minimum': -90, 'enum': [90, -90]}})
BROWSE_DISPLAY = object_schema({
    'schema': {'type': 'integer', 'enum': [1]},
    'sets': guide_list({'character': ID, 'form': ID, 'revision': ID, 'items': {
        'type': 'array', 'minItems': 1, 'maxItems': 28, 'items': BROWSE_DISPLAY_ITEM,
    }}, 24),
})


def pinned_wardrobe_display(guide, sets, assets, owner):
    visible = {entry['version'] for entry in guide['entries']}
    for layout in sets:
        if (layout['character'], layout['form']) != owner or layout['revision'] != guide.get('revision'):
            continue
        items = layout['items']
        if len({item['id'] for item in items}) != len(items):
            continue
        for item in items:
            version, digest = item['asset']['version'], item['asset']['sha256']
            row = assets.get(version)
            if (version not in visible or not row or digest != row['sha256']
                    or 'crop' in row or 'work_id' in row):
                break
            group = row.get('appearance', {}).get('group')
            baseline = version == guide['baseline']
            if (item['group'] == 'wardrobe' and not baseline and group != 'wardrobe'
                    or item['group'] == 'accessories' and group != 'accessories'):
                break
            sx, sy, sw, sh = item['source_box']
            x, y, width, height = item['display_box']
            if not (sw and sh and sx + sw <= 720 and sy + sh <= 720
                    and width and height and x + width <= 510 and y + height <= 1000):
                break
        else:
            return items
    return None


def browse_document(root, path, schema, key='guides'):
    try:
        pin = path_check(root / path)
        if not 0 < pin[2] <= 65536:
            return []
        raw = b''.join(FileSource(root).iter_html(path, expected_state=pin))
        document = json.loads(raw)
        strict_validate(document, schema)
        return document[key]
    except (OSError, WCEError, ValueError, TypeError, RecursionError):
        return []


def pinned_browse_fits(guide, fits, assets, owner):
    visible = {item['version'] for item in guide['entries']}
    matched = {}
    for fit in fits:
        base, result = fit['base'], fit['result']
        garment, accessory = fit.get('garment'), fit.get('accessory')
        garment_id = garment['version'] if garment else ''
        accessory_id = accessory['version'] if accessory else ''
        if (guide.get('revision') != fit['revision'] or base['version'] != guide['baseline']
                or result['version'] in visible or garment and garment_id not in visible):
            continue
        pins = [base, result] + [pin for pin in (garment, accessory) if pin]
        for pin in pins:
            asset = assets.get(pin['version'])
            if (not asset or asset['sha256'] != pin['sha256']
                    or (asset['character']['id'], form_of(asset)['id']) != owner
                    or 'work_id' in asset or 'crop' in asset):
                break
        else:
            if garment and assets[garment_id].get('appearance', {}).get('group') != 'wardrobe':
                continue
            if accessory and assets[accessory_id].get('appearance', {}).get('group') != 'accessories':
                continue
            result_asset = assets[result['version']]
            result_look = result_asset.get('appearance', {})
            components = [version for version in (garment_id, accessory_id) if version]
            if (result_asset['use'] == 'full_body' and result_look.get('group') == 'base'
                    and result_look.get('format') == 'full_look' and result_look.get('view') == 'front'
                    and result_look.get('combination') == components):
                matched.setdefault((garment_id, accessory_id), fit)
    # The accessory may be used with the base or with an already registered outfit.
    return [fit for (garment, accessory), fit in matched.items()
            if not accessory or not garment or (garment, '') in matched]


def pinned_browse_layers(guide, sets, assets, owner, fits):
    garments = {fit['garment']['version'] for fit in fits if 'garment' in fit and 'accessory' not in fit}

    def pinned(pin, group):
        row = assets.get(pin['version'])
        return (row and row['sha256'] == pin['sha256']
                and (row['character']['id'], form_of(row)['id']) == owner
                and 'crop' not in row and 'work_id' not in row
                and row.get('appearance', {}).get('group') == group)

    def variant(item, group):
        return (item['garment']['version'] in garments and pinned(item['garment'], 'wardrobe')
                and pinned(item['asset'], group))

    for item in sets:
        if (item['revision'] != guide.get('revision') or item['baseline']['version'] != guide['baseline']
                or not pinned(item['baseline'], 'base')):
            continue
        underlays = [row for row in item['underlays'] if variant(row, 'base')]
        pieces = {}
        for piece in item['pieces']:
            x, y, width, height = piece['box']
            if (not width or not height or x + width > 4096 or y + height > 4096
                    or not pinned(piece['asset'], 'accessories')):
                continue
            valid = [row for row in piece['variants'] if variant(row, 'accessories')]
            pieces.setdefault(piece['asset']['version'], piece | {'variants': valid})
        if pieces:
            return {'underlays': underlays, 'pieces': list(pieces.values())}
    return None


def read_browse_guides(root, assets):
    """Display revisions reference immutable library rows. The legacy guide can still be read on its own."""
    documents = (browse_document(root, BROWSE_REVISIONS_PATH, BROWSE_REVISIONS)
                 + browse_document(root, BROWSE_GUIDE_PATH, BROWSE_GUIDES))
    fits = (browse_document(root, BROWSE_FITS_PATH, BROWSE_FITS, 'fits')
            + browse_document(root, BROWSE_ACCESSORY_FITS_PATH, BROWSE_ACCESSORY_FITS, 'fits'))
    layers = browse_document(root, BROWSE_LAYERS_PATH, BROWSE_LAYERS, 'sets')
    displays = browse_document(root, BROWSE_DISPLAY_PATH, BROWSE_DISPLAY, 'sets')
    guides = []
    seen = set()
    for guide in documents:
        key = (guide['character'], guide['form'])
        revision_key = (*key, guide.get('revision'))
        if revision_key in seen:
            continue
        refs = guide['entries'] + guide['archive']
        if len({ref['version'] for ref in refs}) != len(refs):
            continue
        if not any(ref['version'] == guide['baseline'] for ref in guide['entries']):
            continue
        for ref in refs:
            asset = assets.get(ref['version'])
            if (not asset or asset['sha256'] != ref['sha256']
                    or (asset['character']['id'], form_of(asset)['id']) != key):
                break
        else:
            baseline = assets[guide['baseline']]
            if baseline['use'] == 'full_body' and 'crop' not in baseline:
                front_fits = pinned_browse_fits(guide, fits, assets, key)
                overlay_set = pinned_browse_layers(guide, layers, assets, key, front_fits)
                wardrobe_display = pinned_wardrobe_display(guide, displays, assets, key)
                guides.append(guide | ({'front_fits': front_fits} if front_fits else {})
                              | ({'front_layers': overlay_set} if overlay_set else {})
                              | ({'wardrobe_display': wardrobe_display} if wardrobe_display else {}))
                seen.add(revision_key)
    return guides


def manifest_error(field, position=None, code='DIRECTOR_CHARACTER_MANIFEST_INVALID'):
    error = WCEError(code)
    error.manifest_field = field
    error.manifest_position = position
    raise error


def invalid_field(value, schema, path):
    """Find the first failed field using the same schema as persisted rows."""
    try:
        strict_validate(value, schema)
    except WCEError:
        if schema['type'] == 'object' and type(value) is dict:
            for key, field in schema['properties'].items():
                name = f'{path}.{key}' if path else key
                if key not in value:
                    if key in schema['required']:
                        return name
                    continue
                invalid = invalid_field(value[key], field, name)
                if invalid:
                    return invalid
        return path or 'entry'
    return None


def manifest_parts(relative):
    parts = project_text(relative).split('/')
    require(all(part and not part.startswith('.') and '\\' not in part and ':' not in part for part in parts),
            'DIRECTOR_ASSET_OUTSIDE_PROJECT')
    return parts


def imported_id(origin):
    key = '\0'.join((origin['project_id'], origin['version_id'], origin['sha256']))
    return 'imported-' + sha256(key.encode()).hexdigest()


def managed_path(checksum, suffix):
    kind = 'Audio' if suffix == 'wav' else 'Characters'
    return Path(ASSET_ROOT, kind, f'{checksum}.{suffix}')


def save_asset(root, project_pin, target, data, check_project):
    """Publish checked bytes into the same project's content-addressed asset folder."""
    check_project()
    parts = target.parts[:2]
    require(len(target.parts) == 3 and parts[0] == ASSET_ROOT, 'DIRECTOR_ASSET_OUTSIDE_PROJECT')
    folder = Jobs._project_video_folder({'root': str(root)}, list(project_pin), create=True,
                                        components=parts)
    try:
        directory_pin = identity(os.fstat(folder))
        source = FileSource(root)

        def check_folder():
            check_project()
            with source.open_directory(parts) as registered:
                info = os.fstat(registered)
                require(identity(info) == directory_pin and not info.st_mode & 0o022, 'DIRECTOR_PROJECT_CHANGED')

        try:
            info = os.stat(target.name, dir_fd=folder, follow_symlinks=False)
        except FileNotFoundError:
            stage = '.character-' + token_hex(16)
            staged = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
            try:
                with os.fdopen(staged, 'wb') as temporary:
                    temporary.write(data)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                check_folder()
                try:
                    rename_image(folder, stage, target.name)
                except FileExistsError:
                    pass
                else:
                    stage = None
            finally:
                if stage is not None:
                    os.unlink(stage, dir_fd=folder)
            info = os.stat(target.name, dir_fd=folder, follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == len(data), 'DIRECTOR_ASSET_CHANGED')
        current = b''.join(source.iter_html(target.as_posix(), expected_state=file_state(info)))
        require(current == data, 'DIRECTOR_ASSET_CHANGED')
        check_folder()
        os.fsync(folder)
    finally:
        os.close(folder)


@lru_cache(maxsize=2)
def voice_original(root, relative, checksum, pin):
    raw = b''.join(FileSource(root).iter_html(relative, expected_state=pin))
    require(sha256(raw).hexdigest() == checksum, 'DIRECTOR_ASSET_CHANGED')
    try:
        with wave.open(BytesIO(raw)) as stream:
            frames = stream.getnframes()
            size = frames * stream.getnchannels() * stream.getsampwidth()
            require(0 < frames and 0 < size <= len(raw) and stream.getframerate() > 0
                    and len(stream.readframes(frames)) == size, 'DIRECTOR_CHARACTER_VOICE_INVALID')
    except (wave.Error, EOFError, ValueError, OverflowError):
        raise WCEError('DIRECTOR_CHARACTER_VOICE_INVALID') from None
    return 'audio/wav', raw


def adopted_bytes(root, record):
    pin = file_pin(root, record)
    return read_character_original(record, root, record['path'], record['sha256'], pin)


def descriptor(record, project_id):
    return {'project_id': project_id, 'path': record['path'], 'sha256': record['sha256']}


def needs_layout(record):
    return bool(record.keys() & LAYOUT.keys() or record['use'] in EXTENDED_USES
                or 'registered_path' in record or 'profile' in record['character'])


def needs_appearance(record):
    return 'appearance' in record or 'profile' in record['character']


def form_of(record):
    return record.get('form', NORMAL_FORM)


def primary_slot(record):
    return record['character']['id'] + '/' + form_of(record)['id']


def slot(record, *, compatibility=False):
    form = form_of(record)['id']
    parts = [record['character']['id']]
    if 'work_id' in record:
        parts.extend((form, 'work', record['work_id']))
    elif form != NORMAL_FORM['id']:
        parts.append(form)
    if not compatibility and (look := record.get('appearance')):
        return '/'.join((*parts, 'appearance', look['group'], look['item_id'], look['view']))
    return '/'.join((*parts, record['use']))


def main_eligible(record):
    return ('work_id' not in record and record['use'] != 'voice'
            and record.get('face_visible', record['use'] == 'face'))


def version_pin(assets, record):
    value = {'character_id': record['character']['id'], 'form_id': form_of(record)['id'],
             'version_id': record['id']}
    if 'work_id' in record:
        value['work_id'] = record['work_id']
    if look := record.get('appearance'):
        value['appearance'] = {key: look[key] for key in APPEARANCE_PIN['properties'] if key in look}
    if crop := record.get('crop'):
        value['crop'] = crop | {'source_sha256': assets[crop['source_version_id']]['sha256']}
    return value


def validate_scope(record):
    form = form_of(record)
    if form['id'] == NORMAL_FORM['id']:
        require(form == NORMAL_FORM, 'DIRECTOR_CHARACTER_FORM_CONFLICT')
    require(('work_id' in record) == (record.get('category', 'standard') == 'special'),
            'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')


def layouts(assets):
    names = {}
    items = {}
    profiles = {}
    for row in assets.values():
        validate_scope(row)
        character = row['character']
        profile = profiles.setdefault(character['id'], {})
        for field, value in character.get('profile', {}).items():
            require(profile.setdefault(field, value) == value, 'DIRECTOR_CHARACTER_PROFILE_CONFLICT')
        form_name = form_of(row)['name']
        require(names.setdefault(primary_slot(row), form_name) == form_name, 'DIRECTOR_CHARACTER_FORM_CONFLICT')
        if look := row.get('appearance'):
            group, form = look['group'], form_of(row)['id']
            key = (row['character']['id'], form, row.get('work_id'), group, look['item_id'])
            require(row['use'] != 'voice' and items.setdefault(key, look['item_name']) == look['item_name'],
                    'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
            require(look['view'] == 'asset' or group == 'base', 'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
            if look['format'] == 'source_detail':
                require(group == 'features' and bool(look.get('details')), 'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
            if look['format'] == 'full_look':
                require(group == 'base', 'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
            if 'set_id' in look:
                require(group in ('wardrobe', 'accessories'), 'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
            if rig := look.get('try_on'):
                require(rig['part'] in TRY_ON_PARTS.get(group, ()), 'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
            for detail in look.get('details', []):
                if region := detail.get('region'):
                    require(region['x'] + region['width'] <= 10000 and region['y'] + region['height'] <= 10000
                            and detail['visibility'] != 'covered', 'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
            if 'combination' in look:
                require(look['format'] == 'full_look', 'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
                found = set()
                for version_id in look['combination']:
                    member = assets.get(version_id)
                    section = member.get('appearance', {}).get('group') if member else None
                    require(section in GEAR_GROUPS and section not in found
                            and member['character']['id'] == row['character']['id']
                            and form_of(member)['id'] == form
                            and ('work_id' not in member or member['work_id'] == row.get('work_id')),
                            'DIRECTOR_CHARACTER_APPEARANCE_INVALID')
                    found.add(section)
        if crop := row.get('crop'):
            source = assets.get(crop['source_version_id'])
            require(row['use'] != 'voice' and source and source['id'] != row['id']
                    and source['use'] != 'voice' and 'crop' not in source
                    and source['character']['id'] == row['character']['id']
                    and ('work_id' not in source or source['work_id'] == row.get('work_id')),
                    'DIRECTOR_CHARACTER_CROP_INVALID')


def status_of(index, row):
    if index['current'].get(slot(row)) == row['id']:
        return 'current'
    return 'historical' if row.get('was_current') else row['initial_status']


def validate_labels(row):
    for label in (row['character']['name'], row['character']['series'], *row['character']['aliases'],
                  row['label'], row['description'], row['source'], form_of(row)['name']):
        project_text(label)
    for profile_label in row['character'].get('profile', {}).values():
        project_text(profile_label)
    if look := row.get('appearance'):
        for label in (look['item_name'], look.get('version_label', ''),
                      *(detail['name'] for detail in look.get('details', []))):
            project_text(label)


def index_document(directory, name):
    path = directory / name
    if not os.path.lexists(path):
        return None
    pin = path_check(path)
    return json.loads(b''.join(FileSource(directory).iter_html(name, expected_state=pin)))


def appearance_snapshot(project_id, directory, base):
    journal = index_document(directory, APPEARANCE_INDEX)
    if journal is None:
        return None
    require(type(journal) is dict and set(journal) == {'schema', 'project_id', 'before', 'next'}
            and journal['schema'] == 1 and journal['project_id'] == project_id,
            'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
    before, prepared = journal['before'], journal['next']
    for snapshot in (before, prepared):
        if snapshot is None:
            continue
        require(type(snapshot) is dict and
                set(snapshot) == {'base', 'revision', 'legacy_current', 'current', 'details'}
                and type(snapshot['base']) is str and type(snapshot['revision']) is int
                and all(type(snapshot[key]) is dict for key in ('legacy_current', 'current', 'details')),
                'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
    current_digest = digest(base)
    if prepared and prepared['base'] == current_digest:
        return prepared
    if before and before['revision'] <= base['revision']:
        # The old plugin may have saved after downgrade. In that case start
        # from the last confirmed rich state and apply the old slot changes.
        return before
    return None


def compatible_row(row):
    plain = {key: value for key, value in row.items() if key != 'appearance'}
    plain['character'] = {key: value for key, value in row['character'].items() if key != 'profile'}
    if 'appearance' in row and row['initial_status'] == 'current':
        # Several rich slots can map to one old slot. Only its projected
        # selection should be "current" in the old library.
        plain['initial_status'] = 'candidate'
    return plain


def detail_identity(row):
    return digest({key: value for key, value in row.items() if key != 'was_current'})


def connect_appearance(base, snapshot):
    if base['schema'] != 2:
        return base
    assets = {}
    for version, row in base['assets'].items():
        detail = snapshot['details'].get(version)
        if detail and detail['identity'] == detail_identity(row):
            row = row | ({'appearance': detail['appearance']} if 'appearance' in detail else {})
            if 'profile' in detail:
                row['character'] = row['character'] | {'profile': detail['profile']}
            if 'initial_status' in detail:
                row['initial_status'] = detail['initial_status']
        assets[version] = row
    current = {key: value for key, value in snapshot['current'].items()
               if value in assets and slot(assets[value]) == key}
    for key, value in base['current'].items():
        rich_key = slot(assets[value])
        if rich_key not in current or snapshot['legacy_current'].get(key) != value:
            current[rich_key] = value
    return base | {'schema': 3, 'assets': assets, 'current': current}


def write_index(directory, index, prior, directory_pin):
    if index['schema'] < 3:
        atomic_write(directory / INDEX, index, maximum=None, expected_parent=directory_pin)
        return
    assets = {version: compatible_row(row) for version, row in index['assets'].items()}
    legacy_current = {}
    projected = prior['legacy_current'] if prior else {}
    for key, target in sorted(index['current'].items()):
        row = index['assets'][target]
        old_key = slot(row, compatibility=True)
        if (old_key not in legacy_current or key == old_key
                or (projected.get(old_key) == target and slot(index['assets'][legacy_current[old_key]]) != old_key)):
            legacy_current[old_key] = target
    base = index | {'schema': 2, 'assets': assets, 'current': legacy_current}
    details = {}
    for version, row in index['assets'].items():
        optional = {key: value for key, value in
                    (('appearance', row.get('appearance')), ('profile', row['character'].get('profile')))
                    if value is not None}
        if assets[version]['initial_status'] != row['initial_status']:
            optional['initial_status'] = row['initial_status']
        if optional:
            details[version] = optional | {'identity': detail_identity(assets[version])}
    snapshot = {'base': digest(base), 'revision': base['revision'], 'legacy_current': legacy_current,
                'current': index['current'], 'details': details}
    journal = {'schema': 1, 'project_id': index['project_id'], 'before': prior, 'next': snapshot}
    # The old-readable index is the commit point. Until that switch, readers
    # can still use the previous snapshot, even if the writer stops mid-save.
    atomic_write(directory / APPEARANCE_INDEX, journal, maximum=None, expected_parent=directory_pin)
    atomic_write(directory / INDEX, base, maximum=None, expected_parent=directory_pin)
    atomic_write(directory / APPEARANCE_INDEX, journal | {'before': snapshot, 'next': None},
                 maximum=None, expected_parent=directory_pin)


def read_index(project_id, directory, *, with_storage=False):
    path = directory / INDEX
    if not os.path.lexists(path):
        blank = {'schema': 1, 'project_id': project_id, 'revision': 0, 'assets': {}, 'current': {}}
        return (blank, None) if with_storage else blank
    try:
        file_version = path_check(path)
        data = index_document(directory, INDEX)
        storage_schema = data['schema']
        require(type(data) is dict and type(data.get('schema')) is int and data['schema'] in (1, 2, 3),
                'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        extra = {'primary'} if data['schema'] >= 2 else set()
        require(set(data) == {'schema', 'project_id', 'revision', 'assets', 'current'} | extra
                and data['project_id'] == project_id and type(data['revision']) is int and data['revision'] >= 0
                and all(type(data[key]) is dict for key in {'assets', 'current'} | extra),
                'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        storage = None
        if storage_schema < 3:
            for key, target in data['current'].items():
                row = data['assets'].get(target)
                require(row and slot(row, compatibility=True) == key, 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            storage = appearance_snapshot(project_id, directory, data)
            require(file_version == path_check(path), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            if storage is not None:
                data = connect_appearance(data, storage)
        for version_id, row in data['assets'].items():
            fields = {key: value for key, value in row.items()
                      if key not in {'was_current', 'origin', 'registered_path'}}
            strict_validate(fields, ENTRY)
            if 'registered_path' in row:
                strict_validate(row['registered_path'], PATH)
                suffixes = ('wav',) if row['use'] == 'voice' else ('png', 'jpg')
                managed = {managed_path(row['sha256'], ext).as_posix() for ext in suffixes}
                managed.update(Path(*LEGACY_ASSET_FOLDER, f"{row['sha256']}.{ext}").as_posix() for ext in suffixes)
                require(row['path'] in managed, 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            require(data['schema'] >= 2 or not needs_layout(row), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            require(data['schema'] >= 3 or not needs_appearance(row), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            if 'origin' in row:
                origin = row['origin']
                strict_validate(origin, ORIGIN)
                require(origin['project_id'] != project_id and origin['sha256'] == row['sha256']
                        and imported_id(origin) == version_id, 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            validate_labels(row)
            require(version_id == row['id'] and type(row.get('was_current', False)) is bool,
                    'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        layouts(data['assets'])
        for key, target in data.get('primary', {}).items():
            row = data['assets'].get(target)
            require(row and primary_slot(row) == key and main_eligible(row), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        for key, target in data['current'].items():
            require(target in data['assets'] and slot(data['assets'][target]) == key,
                    'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        if with_storage:
            return data, (storage_schema, storage)
        return data
    except (OSError, ValueError, TypeError, KeyError, AttributeError, WCEError):
        raise WCEError('DIRECTOR_CHARACTER_INDEX_UNAVAILABLE') from None


def verify_reference(directory, project_id, row, work_id=None, *, selecting=False, voice=False):
    version = row.get('asset_version')
    if version is None:
        require(not voice and 'character_reference' not in row, 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
        return row['file'], None
    assets = read_index(project_id, directory)['assets']
    record = assets.get(version)
    require(record and (record['use'] == 'voice') == voice, 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
    file = descriptor(record, project_id)
    prior_path = record.get('registered_path')
    require(file == row['file'] or (selecting and prior_path and row['file'] == file | {'path': prior_path}),
            'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
    require('work_id' not in record or record['work_id'] == work_id, 'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')
    pinned = version_pin(assets, record)
    # The asset version and digest already bind its immutable appearance.
    # Retain validation for old previews that stored the optional expanded pin.
    compatible = {key: value for key, value in pinned.items() if key != 'appearance'}
    require(row.get('character_reference', compatible) in (compatible, pinned),
            'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
    return file, compatible


def file_pin(root, spec):
    path = local_file(root, spec)
    pin = file_state(path.lstat())
    # Zero-byte read still checks root, every directory, owner and the opened file.
    list(FileSource(root).iter_html(path.relative_to(root).as_posix(), expected_state=pin, length=0))
    return pin


@lru_cache(maxsize=96)
def thumbnail(root, relative, checksum, pin, *, small=True):
    result = preview_image(root, {'path': relative, 'sha256': checksum}, small)
    require(file_pin(root, {'path': relative, 'sha256': checksum}) == pin, 'DIRECTOR_ASSET_CHANGED')
    return result


@lru_cache(maxsize=1)
def original(root, relative, checksum, pin):
    with tempfile.TemporaryDirectory(prefix='openahoy-character-') as folder:
        spec = {'path': relative, 'sha256': checksum}
        result = source_image(root, spec, Path(folder))
        require(file_pin(root, spec) == pin, 'DIRECTOR_ASSET_CHANGED')
        return result


@lru_cache(maxsize=32)
def accessory_layer(root, relative, checksum, pin):
    require(0 < pin[2] <= 1024 * 1024, 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
    raw = b''.join(FileSource(root).iter_html(relative, expected_state=pin))
    require(sha256(raw).hexdigest() == checksum, 'DIRECTOR_ASSET_CHANGED')
    require(raw.startswith(b'\x89PNG\r\n\x1a\n') and raw[12:16] == b'IHDR'
            and raw[24:26] == b'\x08\x06'
            and all(0 < int.from_bytes(raw[i:i+4], 'big') <= 4096 for i in (16, 20)),
            'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
    return 'image/png', raw


def read_character_original(row, root, relative, checksum, pin):
    if row['use'] == 'voice':
        return voice_original(root, relative, checksum, pin)
    if row['use'] == 'accessory' and relative.lower().endswith('.png') and pin[2] <= 1024 * 1024:
        try:
            return accessory_layer(root, relative, checksum, pin)
        except WCEError as problem:
            if problem.code != 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE':
                raise
    return original(root, relative, checksum, pin)


def validate_crop(root, source, crop):
    try:
        _, raw = original(root, source['path'], source['sha256'], file_pin(root, source))
        with tempfile.NamedTemporaryFile(prefix='character-crop-') as image:
            image.write(raw)
            image.flush()
            result = subprocess.run(['/usr/bin/sips', '-g', 'pixelWidth', '-g', 'pixelHeight', image.name],
                                    capture_output=True, text=True, check=True, timeout=12)
        dimensions = {}
        for line in result.stdout.splitlines():
            key, _, value = line.strip().partition(':')
            if key in ('pixelWidth', 'pixelHeight'):
                dimensions[key] = int(value)
        require(crop['x'] + crop['width'] <= dimensions['pixelWidth']
                and crop['y'] + crop['height'] <= dimensions['pixelHeight'], 'DIRECTOR_CHARACTER_CROP_INVALID')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, WCEError):
        raise WCEError('DIRECTOR_CHARACTER_CROP_INVALID') from None


def safe_availability(root, spec):
    try:
        pin = file_pin(root, spec)
        if spec['use'] in ('voice', 'accessory'):
            read_character_original(spec, root, spec['path'], spec['sha256'], pin)
        else:
            thumbnail(root, spec['path'], spec['sha256'], pin)
        return 'available'
    except FileNotFoundError:
        return 'missing'
    except (WCEError, OSError):
        return 'unavailable'


class CharacterLibrary:
    def __init__(self, director):
        self.director = director

    def index(self, project_id):
        root, pin = self.director.project(project_id)
        directory = self.director.storage(root, pin)
        return read_index(project_id, directory)

    def list(self):
        projects = []
        for project in self.director.registered():
            try:
                root, pin = self.director.project(project['id'])
                directory = self.director.storage(root, pin)
                index, storage = read_index(project['id'], directory, with_storage=True)
                if storage and storage[0] == 3:
                    # Preview installations could have written the full v3 document.
                    with locked(directory / 'writer.lock'):
                        index, storage = read_index(project['id'], directory, with_storage=True)
                        if storage and storage[0] == 3:
                            require(self.director.project(project['id']) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
                            write_index(directory, index, None, path_check(directory, True))
                works = (self.director.load(project['id'], directory)['works']
                         if any('work_id' in row for row in index['assets'].values()) else {})
                rows = []
                for row in index['assets'].values():
                    current = index['current'].get(slot(row))
                    primary = index.get('primary', {}).get(primary_slot(row))
                    rows.append({key: row[key] for key in ('id', 'character', 'use', 'label', 'description', 'source')}
                                | {key: row[key] for key in ('work_id', 'crop', 'face_visible', 'origin', 'appearance', 'registered_path') if key in row}
                                | {'status': status_of(index, row), 'current': current,
                                   'file': descriptor(row, project['id']), 'form': form_of(row),
                                   'category': row.get('category', 'standard'), 'primary': primary == row['id'],
                                   'primary_version_id': primary}
                                | ({'work_title': works.get(row['work_id'], {}).get('title')}
                                   if 'work_id' in row else {}))
                guides = read_browse_guides(root, index['assets'])
                projects.append(project | {'revision': index['revision'], 'assets': rows}
                                | ({'browse_guides': guides} if guides else {}))
            except (WCEError, OSError):
                projects.append(project | {'unavailable': True, 'assets': []})
        return {'projects': projects}

    def manifest_files(self, project_id, relative):
        root, pin = self.director.project(project_id)
        parts = manifest_parts(relative) if relative else []
        folders, files = [], []
        with FileSource(root).open_directory(parts) as directory, os.scandir(directory) as entries:
            for entry in entries:
                try:
                    manifest_parts(entry.name)
                    info = entry.stat(follow_symlinks=False)
                except (OSError, WCEError):
                    continue
                if info.st_uid != os.getuid():
                    continue
                if stat.S_ISDIR(info.st_mode):
                    folders.append(entry.name)
                elif (entry.name.lower().endswith('.json') and stat.S_ISREG(info.st_mode)
                      and info.st_nlink == 1 and 0 < info.st_size <= MAX_SOURCE_HTML_BYTES):
                    files.append(entry.name)
        require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        return {'directory': relative, 'folders': sorted(folders), 'files': sorted(files)}

    def pick_manifest(self, project_id, relative):
        manifest_parts(relative)
        require(relative.lower().endswith('.json'), 'DIRECTOR_CHARACTER_MANIFEST_INVALID')
        root, pin = self.director.project(project_id)
        raw = self.manifest_bytes(root, {'path': relative})
        require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        source = {'path': relative, 'sha256': sha256(raw).hexdigest()}
        return self.preview(project_id, source) | {'source': source}

    @staticmethod
    def manifest_bytes(root, spec):
        path = local_file(root, spec)
        pin = file_pin(root, spec)
        require(0 < pin[2] <= MAX_SOURCE_HTML_BYTES, 'LOCAL_FILE_LIMIT')
        return b''.join(FileSource(root).iter_html(path.relative_to(root).as_posix(), expected_state=pin))

    def manifest(self, root, request):
        raw = self.manifest_bytes(root, request)
        require(sha256(raw).hexdigest() == request['sha256'], 'DIRECTOR_CHARACTER_MANIFEST_CHANGED')
        try:
            plan = json.loads(raw)
        except (UnicodeError, ValueError, RecursionError):
            manifest_error('json')
        if type(plan) is not dict or set(plan) != {'schema', 'assets'}:
            manifest_error('manifest')
        if type(plan['schema']) is not int or plan['schema'] not in (1, 2, 3):
            manifest_error('schema')
        if type(plan['assets']) is not list or not plan['assets']:
            manifest_error('assets')
        seen = set()
        for position, row in enumerate(plan['assets'], 1):
            field = invalid_field(row, ENTRY, '')
            if not field and (plan['schema'] == 1 and needs_layout(row)
                              or plan['schema'] < 3 and needs_appearance(row)):
                field = 'schema'
            if field:
                manifest_error(field, position)
            if row['id'] in seen:
                manifest_error('id', position, 'DIRECTOR_CHARACTER_DUPLICATE')
            seen.add(row['id'])
            try:
                local_file(root, row)
            except WCEError as error:
                manifest_error('path', position, error.code)
            validate_labels(row)
        return plan['assets']

    def preview(self, project_id, source):
        root, pin = self.director.project(project_id)
        directory = self.director.storage(root, pin)
        index = read_index(project_id, directory)
        records = self.manifest(root, source)
        self.check_layout(root, directory, index, records)
        slots = set(index['current'])
        results = []
        for row in records:
            existing = index['assets'].get(row['id'])
            entry = 'new'
            if existing:
                entry = 'existing' if self.same_record(existing, row) else 'conflict'
            elif row['initial_status'] == 'current':
                key = slot(row)
                if key in slots:
                    entry = 'conflict'
                slots.add(key)
            results.append({'id': row['id'], 'name': row['character']['name'],
                            'status': status_of(index, existing) if existing else row['initial_status'],
                            'availability': safe_availability(root, existing or row), 'entry': entry})
        require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        return {'revision': index['revision'], 'assets': results}

    @staticmethod
    def same_record(existing, record):
        fields = {key: existing[key] for key in ENTRY['properties'] if key in existing}
        fields['path'] = existing.get('registered_path', fields['path'])
        return fields == record

    def edit(self, args):
        project_id = args['project_id']
        root, pin = self.director.project(project_id)
        command = args['action']
        adopting = command == 'character_import_version'
        origin = args['origin'] if adopting else None
        source = self.copy_source(project_id, origin) if adopting else None
        directory = self.director.storage(root, pin, create=adopting or command == 'character_import')
        require(directory.is_dir(), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        directory_pin = path_check(directory, True)
        with locked(directory / 'writer.lock'):
            index, storage = read_index(project_id, directory, with_storage=True)
            if command == 'character_import':
                receipt, changed = self.import_assets(root, pin, directory, index, args)
            elif command == 'character_set_primary':
                receipt, changed = self.set_primary(root, index, args)
            elif adopting:
                receipt, changed = self.import_version(project_id, root, pin, index, origin, source)
            else:
                receipt, changed = self.set_current(root, index, args)
            if changed:
                require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
                index['revision'] += 1
                receipt['revision'] = index['revision']
                write_index(directory, index, storage[1] if storage else None, directory_pin)
            return receipt

    def copy_source(self, project_id, origin):
        source_id = origin['project_id']
        require(source_id != project_id, 'DIRECTOR_CHARACTER_ALREADY_IN_PROJECT')
        root, pin = self.director.project(source_id)
        index = read_index(source_id, self.director.storage(root, pin))
        record = index['assets'].get(origin['version_id'])
        require(record and record['sha256'] == origin['sha256'], 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
        require('work_id' not in record, 'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')
        require('crop' not in record, 'DIRECTOR_CHARACTER_CROP_ORIGINAL_PROJECT_REQUIRED')
        try:
            checked = file_pin(root, record)
            reader = voice_original if record['use'] == 'voice' else original
            mime, data = reader(root, record['path'], record['sha256'], checked)
            require(file_pin(root, record) == checked, 'DIRECTOR_ASSET_CHANGED')
            require(self.director.project(source_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        except FileNotFoundError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_MISSING') from None
        except OSError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE') from None
        return record, mime, data

    def import_version(self, project_id, root, pin, index, origin, source):
        upstream, mime, data = source
        checksum = origin['sha256']
        ext = {'image/png': 'png', 'image/jpeg': 'jpg', 'audio/wav': 'wav'}[mime]
        version_id = imported_id(origin)
        previous = index['assets'].get(version_id)
        target = Path(previous['path']) if previous else managed_path(checksum, ext)
        row = {key: upstream[key] for key in ENTRY['properties'] if key in upstream}
        row.update(id=version_id, path=target.as_posix(), initial_status='candidate', origin=origin)
        if row.get('appearance', {}).get('combination'):
            # The exact component IDs belong to the source project.
            row['appearance'] = {key: val for key, val in row['appearance'].items() if key != 'combination'}
        require(previous is None or (previous.get('origin') == origin
                and descriptor(previous, project_id) == descriptor(row, project_id)),
                'DIRECTOR_CHARACTER_VERSION_CONFLICT')

        def check_project():
            require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')

        if previous is None:
            layouts(index['assets'] | {version_id: row})
        if target.parts[0] == ASSET_ROOT:
            save_asset(root, pin, target, data, check_project)
        else:
            # Re-read the old saved copy at its original path. A historical
            # import must not replace its established file or reference.
            require(adopted_bytes(root, row) == (mime, data), 'DIRECTOR_ASSET_CHANGED')
        if previous is None:
            index['assets'][version_id] = row
            if needs_layout(row):
                self.enable_layout(index, needs_appearance(row))
        return {'state': 'UNCHANGED' if previous else 'IMPORTED', 'revision': index['revision'],
                'version_id': version_id, 'file': descriptor(row, project_id), 'origin': origin}, previous is None

    @staticmethod
    def enable_layout(index, appearance=False):
        index['schema'] = max(index['schema'], 3 if appearance else 2)
        index.setdefault('primary', {})

    def check_layout(self, root, directory, index, records):
        new = {row['id']: row for row in records if row['id'] not in index['assets']}
        assets = index['assets'] | new
        layouts(assets)
        if any('work_id' in row for row in new.values()):
            works = self.director.load(index['project_id'], directory)['works']
            require(all(row['work_id'] in works for row in new.values() if 'work_id' in row),
                    'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')
        for row in new.values():
            if crop := row.get('crop'):
                validate_crop(root, assets[crop['source_version_id']], crop)

    def import_assets(self, root, pin, directory, index, args):
        project_id = index['project_id']
        records = self.manifest(root, args['source'])
        new = [row for row in records if row['id'] not in index['assets']]
        require(all(self.same_record(index['assets'][row['id']], row)
                    for row in records if row['id'] in index['assets']), 'DIRECTOR_CHARACTER_VERSION_CONFLICT')
        if new:
            require(index['revision'] == args['expected_revision'], 'DIRECTOR_CHARACTER_STALE_INDEX')
            self.check_layout(root, directory, index, new)

        def check_project():
            require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')

        for row in records:
            existing = index['assets'].get(row['id'])
            if existing is not None:
                target = Path(existing['path'])
                if 'registered_path' in existing and target.parts[0] == ASSET_ROOT and not os.path.lexists(root / target):
                    # A previously missing candidate can be recovered by reimporting
                    # the same source without changing its version or recorded path.
                    try:
                        _, raw = adopted_bytes(root, row)
                    except (OSError, WCEError):
                        continue
                    save_asset(root, pin, target, raw, check_project)
                continue
            if row['initial_status'] == 'current':
                key = slot(row)
                require(key not in index['current'], 'DIRECTOR_CHARACTER_CURRENT_CONFLICT')
                index['current'][key] = row['id']
            try:
                mime, raw = adopted_bytes(root, row)
            except (OSError, WCEError):
                require(row['initial_status'] != 'current', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
                raw = None
                suffix = 'wav' if row['use'] == 'voice' else (
                    'png' if Path(row['path']).suffix.lower() == '.png' else 'jpg')
            else:
                suffix = {'image/png': 'png', 'image/jpeg': 'jpg', 'audio/wav': 'wav'}[mime]
            target = managed_path(row['sha256'], suffix)
            if raw is not None:
                save_asset(root, pin, target, raw, check_project)
            index['assets'][row['id']] = row | {'path': target.as_posix(), 'registered_path': row['path']}
        if new:
            self.enable_layout(index, any(needs_appearance(row) for row in new))
        return {'state': 'SAVED' if new else 'UNCHANGED', 'revision': index['revision'], 'added': len(new)}, bool(new)

    @staticmethod
    def set_current(root, index, args):
        version_id = args['version_id']
        row = index['assets'].get(version_id)
        require(row, 'DIRECTOR_CHARACTER_VERSION_NOT_FOUND')
        key = slot(row)
        previous = index['current'].get(key)
        require(previous == args.get('expected_current'), 'DIRECTOR_CHARACTER_CURRENT_CONFLICT')
        require(safe_availability(root, row) == 'available', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
        if previous != version_id:
            if previous is not None:
                index['assets'][previous]['was_current'] = True
            index['current'][key] = version_id
        return {'state': 'SAVED' if previous != version_id else 'UNCHANGED',
                'revision': index['revision'], 'current': version_id}, previous != version_id

    @classmethod
    def set_primary(cls, root, index, args):
        version_id = args['version_id']
        row = index['assets'].get(version_id)
        require(row, 'DIRECTOR_CHARACTER_VERSION_NOT_FOUND')
        require(main_eligible(row), 'DIRECTOR_CHARACTER_FACE_REFERENCE_REQUIRED')
        key = primary_slot(row)
        previous = index.get('primary', {}).get(key)
        require(previous == args.get('expected_primary'), 'DIRECTOR_CHARACTER_CURRENT_CONFLICT')
        require(safe_availability(root, row) == 'available', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
        if previous != version_id:
            cls.enable_layout(index)
            index['primary'][key] = version_id
        return {'state': 'SAVED' if previous != version_id else 'UNCHANGED',
                'revision': index['revision'], 'primary_version_id': version_id}, previous != version_id

    def media(self, args):
        project_id = args['project_id']
        root, project_pin = self.director.project(project_id)
        directory = self.director.storage(root, project_pin)
        row = read_index(project_id, directory)['assets'].get(args['version_id'])
        require(row, 'DIRECTOR_CHARACTER_VERSION_NOT_FOUND')
        spec = descriptor(row, project_id)
        require(spec['sha256'] == args['sha256'], 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
        try:
            pin = file_pin(root, spec)
            params = root, spec['path'], spec['sha256'], pin
            if args['action'] in ('character_thumbnail', 'character_preview'):
                require(row['use'] != 'voice', 'DIRECTOR_CHARACTER_VOICE_NO_THUMBNAIL')
                result = thumbnail(*params, small=args['action'] == 'character_thumbnail')
                require(self.director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
                return result
            if args['action'] == 'character_layer':
                require(row['use'] == 'accessory', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
                mime, data = accessory_layer(*params)
            else:
                mime, data = read_character_original(row, *params)
            require(self.director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
            offset = args['offset']
            require(0 <= offset < len(data), 'DIRECTOR_CHARACTER_OFFSET_INVALID')
            return {'mime_type': mime, 'sha256': spec['sha256'], 'total': len(data),
                    'offset': offset, 'data': b64encode(data[offset:offset + IMAGE_CHUNK]).decode('ascii')}
        except FileNotFoundError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_MISSING') from None
        except OSError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE') from None
