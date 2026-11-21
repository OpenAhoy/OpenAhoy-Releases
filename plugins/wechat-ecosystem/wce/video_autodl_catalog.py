"""Public AutoDL video workflow parameters and their original field names.

The snapshot comes from the details linked in the official workflow catalogue.
https://www.autodl.art/large-model/comfyui
"""
import json
from pathlib import Path

from .contracts import WCEError
from .prepared_contracts import strict_validate

LEGACY_WORKFLOW = 'minimax_h3_zm_nono'
CATALOG = Path(__file__).resolve().parent.parent / 'assets' / 'video' / 'autodl-workflows.json'
WORKFLOWS = {row['id']: row for row in json.loads(CATALOG.read_bytes())}
WORKFLOW_ID = {'type': 'string', 'enum': list(WORKFLOWS)}
URL = {'type': 'string', 'minLength': 1, 'maxLength': 8192}
FIELDS = ('workflow_id', 'reference_images', 'reference_audio', 'first_frame', 'last_frame',
          'reference_video', 'duration', 'audio_duration', 'resolution', 'seed', 'quality_mode',
          'style_preset', 'video_subject_to_replace')
CONFIG_OPTIONS = {
    'workflow_id': WORKFLOW_ID,
    'reference_images': {'type': 'array', 'items': URL, 'minItems': 1, 'maxItems': 9},
    'reference_audio': {'type': 'array', 'items': URL, 'maxItems': 3},
    'first_frame': URL, 'last_frame': URL, 'reference_video': URL,
    'audio_duration': {'type': 'integer', 'minimum': 1, 'maximum': 15},
    'seed': {'type': 'integer', 'minimum': 0, 'maximum': 100_000_000_000_000_000},
    'quality_mode': {'type': 'string', 'minLength': 1, 'maxLength': 40},
    'style_preset': {'type': 'string', 'minLength': 1, 'maxLength': 80},
    'video_subject_to_replace': {'type': 'string', 'minLength': 1, 'maxLength': 100, 'x-wce-maxUtf8Bytes': 400},
}


def profile(workflow_id):
    if not isinstance(workflow_id, str) or workflow_id not in WORKFLOWS:
        raise WCEError('VIDEO_RELAY_WORKFLOW_UNSUPPORTED')
    return WORKFLOWS[workflow_id]


def options():
    return [{'id': row['id'], 'name': row['name'] + ('（736p）' if row['id'] in
                ('minimax_h3_b99_001', 'minimax_h3_b99_002') else ''), 'fields': {
                name: {key: value for key, value in field.items() if key != 'wire'}
                for name, field in row['fields'].items()}}
            for row in WORKFLOWS.values()]


def director_inputs(config, prompt):
    inputs = {key: config[key] for key in FIELDS if key in config}
    workflow_id = config.get('workflow_id', LEGACY_WORKFLOW)
    rule = profile(workflow_id)['fields'].get('prompt')
    if rule and (prompt.strip() or rule['required']):
        inputs['prompt'] = prompt
    return inputs


def media(inputs):
    for name in ('first_frame', 'last_frame', 'reference_images', 'reference_audio', 'reference_video'):
        if name not in inputs:
            continue
        role = {'reference_images': 'reference_image'}.get(name, name)
        values = inputs[name] if name in ('reference_images', 'reference_audio') else [inputs[name]]
        yield from ((role, value) for value in values)


def validate(inputs, *, partial=False):
    fields = profile(inputs.get('workflow_id', LEGACY_WORKFLOW))['fields']
    values = {key: value for key, value in inputs.items() if key != 'workflow_id'}
    missing = set() if partial else {key for key, rule in fields.items() if rule['required']} - values.keys()
    if values.keys() - fields.keys() or missing:
        raise WCEError('VIDEO_RELAY_WORKFLOW_INPUTS_INVALID')
    wire = {}
    for key, value in values.items():
        rule = fields[key]
        try:
            strict_validate(value, rule)
        except WCEError:
            raise WCEError('VIDEO_RELAY_WORKFLOW_INPUTS_INVALID') from None
        if rule['type'] == 'array':
            wire.update(zip(rule['wire'], value))
        else:
            wire[rule['wire']] = value
    return wire
