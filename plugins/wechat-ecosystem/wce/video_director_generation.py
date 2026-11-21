"""Submit a saved shot through the original Jobs receipt and provider adapters."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from . import video_director_delivery as delivery
from . import video_autodl_catalog as autodl
from .video_director import require
from .video_director_media import compute_request

TARGET_KEYS = ('project_id', 'work_id', 'scene_id', 'shot_id', 'revision_id')


def submit(router, args):
    jobs, director = router.jobs, router.director
    target = {key: args[key] for key in TARGET_KEYS}
    project, attempt = target['project_id'], args['generation_attempt_id']
    root, pin = director.project(project)
    context = director.context(target)
    location = director.storage(root, pin)

    def matches(row):
        binding = row.get('director_binding', {})
        require(binding.get('kind') == 'shot' and all(binding.get(key) == value for key, value in target.items())
                and row.get('project_video_root') == list(pin), 'DIRECTOR_GENERATION_SCOPE_CHANGED')

    if previous := delivery.read_receipt(jobs, attempt, project):
        matches(previous)
        return jobs.status(attempt, project, poll=False)

    with TemporaryDirectory(prefix='openahoy-director-submit-') as folder:
        request = compute_request(jobs, context, root, Path(folder))

    config = request['configuration']
    route, model, mode, prompt, inputs = (request[key] for key in ('provider', 'model', 'mode', 'prompt', 'inputs'))
    witness = delivery.receipt_witness(context['revision'], project)
    spec = {'provider': route, 'model': model, 'mode': mode, 'witness': witness}
    track_args = dict(target, action='track_generation', attempt_id=attempt,
                      operation_id=sha256(('director-generation:' + attempt).encode()).hexdigest()[:32])

    def bind(row):
        require(director.project(project) == (root, pin) and row.get('project_video_root') == list(pin),
                'DIRECTOR_PROJECT_CHANGED')
        delivery.generation_scope(row, spec)
        from .character_library import verify_reference

        for item in inputs:
            if 'asset_version' in item:
                verify_reference(location, project, item, target['work_id'])
        receipt = director.edit(track_args, None, jobs=jobs)
        require(all(receipt.get(key) == value for key, value in target.items()) and
                receipt.get('attempt_id') == attempt, 'DIRECTOR_SAVE_NOT_VERIFIED')
        # Confirm the saved scope even if director.edit returned an idempotent historical receipt.
        state = director.load(project, location)
        stored = state['works'][target['work_id']].get('generations', {}).get(attempt)
        require(stored is not None and all(stored.get(key) == spec[key] for key in spec)
                and all(stored.get(key) == target[key] for key in TARGET_KEYS[2:]),
                'DIRECTOR_SAVE_NOT_VERIFIED')
        return dict(target, kind='shot', verification='URL_UNVERIFIED' if mode in ('subject', 'workflow') else 'LOCAL_INPUTS',
                    characters=[{'position': index, 'role': item['role'], 'version_id': item['asset_version'],
                                 'sha256': item['file']['sha256']}
                                | ({'character_reference': item['character_reference']}
                                   if 'character_reference' in item else {})
                                for index, item in enumerate(inputs, 1) if 'asset_version' in item])

    if mode == 'subject':
        row = jobs.submit_subject(attempt, project, route, prompt, config['subject_image_url'], director_bind=bind)
    elif mode == 'workflow':
        row = jobs.submit_relay(attempt, project, autodl.director_inputs(config, prompt), director_bind=bind)
    else:
        fields = ('duration', 'resolution', 'ratio', 'audio', 'direction')
        workspace = {'mode': mode, 'paths': [item['file']['path'] for item in inputs],
                     **{k: config[k] for k in fields if k in config}}
        if route in ('cn', 'global'):
            workspace['provider_site'] = route
            workspace.pop('audio', None)
        if route == 'tokenhex':
            workspace.pop('ratio', None)
        elif route == 'ark':
            workspace.setdefault('audio', False)
        if source := config.get('source'):
            workspace.update(source_attempt_id=source['attempt_id'], source_sha256=source['sha256'])
            if 'reference_asset' in source:
                workspace['reference_asset'] = source['reference_asset']
        row = jobs.submit(attempt, project, None, None, prompt, model=model, workspace=workspace, tokenhex=route == 'tokenhex',
                          director_bind=bind)
    matches(row)
    return row
