"""Exact native body text with opaque local-image wrappers; no image I/O.

Only the control reader opts into this profile. Attachment bytes and pixels
are never interpreted as instructions, and paths are never opened or fetched.
"""
from hashlib import sha256
import re

from .draft_revision_native_source import canonical, require
from .draft_revision_native_lookup import valid_thread

PROFILE = 'NATIVE_USER_BODY_WITH_OPAQUE_LOCAL_IMAGES_V1'
_OPEN = re.compile(r'<image name=\[Image #([1-9][0-9]*)\] path="([^"\r\n]+)">\Z')
_HASH = re.compile(r'[a-f0-9]{64}\Z')
_ERROR = 'SLOT_HUMAN_IMAGE_PROFILE_INVALID'


def validate_descriptor(value):
    require(type(value) is dict and set(value) == {
        'profile', 'count', 'paths_sha256', 'raw_attachments_sha256'}
        and value['profile'] == PROFILE and type(value['count']) is int and value['count'] > 0
        and all(type(value[key]) is str and _HASH.fullmatch(value[key])
            for key in ('paths_sha256', 'raw_attachments_sha256')), _ERROR)
    return value


def raw_response(record, *, allow_incomplete_control=False):
    require(type(allow_incomplete_control) is bool, _ERROR)
    row = record.value
    value = row['payload']
    content = value.get('content')
    if (type(content) is not list or not any(type(item) is dict
            and item.get('type') == 'input_image' for item in content)):
        return None
    metadata = row.get('metadata')
    passthrough = value.get('internal_chat_message_metadata_passthrough')
    require(type(metadata) is dict and type(passthrough) is dict, _ERROR)
    turn = passthrough.get('turn_id')
    valid_thread(turn)
    retained = metadata.get('retained_source')
    # Only an explicitly selected post-grant control reader can project an
    # opaque attachment whose retention is incomplete. Its exact body still
    # requires the typed pair; this projection can never supply a grant pin.
    incomplete = (allow_incomplete_control and type(retained) is dict
        and retained.get('complete') is False and 'revision' in retained
        and retained['revision'] is not None)
    require(type(retained) is dict and (retained.get('complete') is True or incomplete)
        and retained.get('id') == {'message_id': value.get('id'), 'turn_id': turn, 'role': 'user'}
        and (metadata.get('client_authored') is None or type(metadata['client_authored']) is bool)
        and len(content) >= 4 and (len(content) - 1) % 3 == 0, _ERROR)
    entries = passthrough.get('content_item_metadata')
    count = (len(content) - 1) // 3
    require(type(entries) is list and len(entries) == len(content)
        and all(type(entry) is dict and entry == {'provenance': {'type': 'user'}} for entry in entries)
        and passthrough.get('content_item_kinds') == ['user.text']
            + ['user.text', 'user.image', 'user.text'] * count, _ERROR)
    body = content[0]
    require(type(body) is dict and set(body) == {'type', 'text'}
        and body['type'] == 'input_text' and type(body['text']) is str, _ERROR)
    paths, images = [], []
    for index in range(count):
        opening, image, closing = content[1 + index * 3:4 + index * 3]
        require(type(opening) is dict and set(opening) == {'type', 'text'}
            and opening['type'] == 'input_text' and type(opening['text']) is str
            and type(closing) is dict and closing == {'type': 'input_text', 'text': '</image>'}
            and type(image) is dict and set(image) == {'type', 'detail', 'image_url'}
            and image['type'] == 'input_image' and image['detail'] == 'original'
            and type(image['image_url']) is str and bool(image['image_url']), _ERROR)
        match = _OPEN.fullmatch(opening['text'])
        require(match is not None and match.group(1) == str(index + 1), _ERROR)
        path = match.group(2)
        require(path.startswith('/') and path.isprintable(), _ERROR)
        paths.append(path)
        images.append([opening, image, closing])
    descriptor = {'profile': PROFILE, 'count': count,
        'paths_sha256': sha256(canonical(paths)).hexdigest(),
        'raw_attachments_sha256': sha256(canonical(images)).hexdigest()}
    return {'turn_id': turn, 'response_id': value['id'],
        'text_sha256': sha256(body['text'].encode('utf8')).hexdigest(),
        'record': record.reference(), 'client_authored': metadata.get('client_authored'),
        'opaque_images': descriptor, **({'control_only': True} if incomplete else {})}


def typed_body(content, descriptor):
    validate_descriptor(descriptor)
    require(type(content) is list and len(content) == descriptor['count'] + 1, _ERROR)
    body = content[0]
    require(type(body) is dict and set(body) == {'type', 'text', 'text_elements'}
        and body['type'] == 'text' and type(body['text']) is str and body['text_elements'] == [], _ERROR)
    paths = []
    for image in content[1:]:
        require(type(image) is dict and set(image) == {'type', 'path'}
            and image['type'] == 'local_image' and type(image['path']) is str
            and image['path'].startswith('/') and image['path'].isprintable(), _ERROR)
        paths.append(image['path'])
    require(sha256(canonical(paths)).hexdigest() == descriptor['paths_sha256'], _ERROR)
    return body['text']


def completion_identity(fact):
    descriptor = None
    if 'opaque_images' in fact:
        descriptor = validate_descriptor(fact['opaque_images'])
    return fact['root_turn_id'], fact['text_sha256'], descriptor
