"""Account schedule preferences and host observations, not a scheduler.

Use the existing ProjectStore binding/operation namespace. Only Codex's official
automation tool manages the host tasks. This module never opens host task files,
starts timers, calls a model, or publishes a post.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .project_context import require, text
from .service import digest

TIME = re.compile(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]')
TASK_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
THREAD_ID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
URL = re.compile(r'https://x\.com/[A-Za-z0-9_]+/status/([0-9]+)')


def config(value):
    require(type(value) is dict and set(value) == {'mode', 'weekdays', 'times', 'timezone', 'once_at'})
    require(value['mode'] in ('daily', 'weekly', 'once'))
    require(type(value['weekdays']) is list and all(type(v) is int and 1 <= v <= 7 for v in value['weekdays']))
    require(len(set(value['weekdays'])) == len(value['weekdays']))
    require(type(value['times']) is list and all(type(v) is str and TIME.fullmatch(v) for v in value['times']))
    require(len(set(value['times'])) == len(value['times']))
    text(value['timezone']); text(value['once_at'])
    try:
        ZoneInfo(value['timezone'])
    except (ValueError, ZoneInfoNotFoundError):
        require(False, 'SCHEDULE_TIMEZONE_INVALID')
    if value['mode'] == 'once':
        require(not value['times'] and not value['weekdays'])
        try:
            moment = datetime.strptime(value['once_at'], '%Y-%m-%dT%H:%M')
            require(moment.strftime('%Y-%m-%dT%H:%M') == value['once_at'])
            zone = ZoneInfo(value['timezone'])
            aware = moment.replace(tzinfo=zone)
            require(aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == moment,
                    'SCHEDULE_TIME_NOT_EXIST')
            require(aware.utcoffset() == moment.replace(tzinfo=zone, fold=1).utcoffset(),
                    'SCHEDULE_TIME_AMBIGUOUS')
        except ValueError:
            require(False, 'SCHEDULE_TIME_INVALID')
    else:
        require(bool(value['times']) and value['once_at'] == '')
        require(bool(value['weekdays']) if value['mode'] == 'weekly' else not value['weekdays'])
    return dict(value, times=sorted(value['times']), weekdays=sorted(value['weekdays']))


def slots(value):
    return [value['once_at']] if value['mode'] == 'once' else value['times']


def default():
    return {'config': None, 'applied_config': None, 'pending': None, 'tasks': [],
            'observed': None, 'last_run': None, 'last_request_id': ''}


class Schedules:
    def __init__(self, projects, clock=None):
        self.projects = projects
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def key(self, cid):
        require(type(cid) is str and re.fullmatch(r'x-[0-9]+', cid), 'SCHEDULE_ACCOUNT_REQUIRED')
        return '["x","' + cid + '","schedule"]'

    def row(self, state, cid):
        value = state['bindings'].get(self.key(cid), default())
        require(type(value) is dict and set(value) == set(default())
                and type(value['tasks']) is list, 'SCHEDULE_STORE_UNAVAILABLE')
        return deepcopy(value)

    def read(self, connection_id):
        state = self.projects._load()
        return {'connection_id': connection_id, 'revision': state['revision'],
                **self.row(state, connection_id), 'authority': 'HOST_OBSERVATIONS_ONLY',
                'time_meaning': 'START_PRODUCTION_THEN_PUBLISH'}

    def request(self, connection_id, action, configuration, operation_id, expected_revision):
        require(action in ('save', 'enable', 'pause', 'resume', 'check'))
        cfg = config(configuration) if action in ('save', 'enable') else None
        payload = {'schedule_request': action, 'connection_id': connection_id, 'config': cfg}

        def mutate(state):
            row = self.row(state, connection_id)
            require(row['pending'] is None, 'SCHEDULE_PENDING_USE_ORIGINAL')
            if action == 'enable' and cfg['mode'] == 'once':
                moment = datetime.strptime(cfg['once_at'], '%Y-%m-%dT%H:%M').replace(tzinfo=ZoneInfo(cfg['timezone']))
                require(moment > datetime.now(timezone.utc), 'SCHEDULE_TIME_PAST')
            if action == 'save':
                row['config'] = cfg
            else:
                if action in ('pause', 'resume'):
                    require(bool(row['tasks']), 'SCHEDULE_TASK_NOT_BOUND')
                require(action != 'resume' or row['applied_config'] is not None, 'SCHEDULE_TASK_NOT_BOUND')
                row['pending'] = {'id': operation_id, 'action': action,
                                  'config': cfg if action == 'enable' else row['applied_config'],
                                  'tasks_before': deepcopy(row['tasks']), 'created_at': self.clock(),
                                  'delivery': 'NOT_SENT'}
                if cfg is not None:
                    row['config'] = cfg
                row['last_request_id'] = operation_id
            state['bindings'][self.key(connection_id)] = row
            return {'connection_id': connection_id, 'request_id': operation_id, 'action': action}
        return self.projects._change(operation_id, payload, expected_revision, mutate)

    def host_result(self, connection_id, request_id, outcome, tasks, note, expected_revision):
        require(outcome in ('PENDING', 'ACTIVE', 'PAUSED', 'UNKNOWN', 'FAILED'))
        text(note)
        require(type(tasks) is list)
        for task in tasks:
            require(type(task) is dict and set(task) == {'id', 'slot', 'status', 'thread_id', 'kind', 'next_run_at'})
            require(type(task['id']) is str and TASK_ID.fullmatch(task['id']))
            require(task['kind'] == 'heartbeat' and task['status'] in ('ACTIVE', 'PAUSED'))
            require(type(task['thread_id']) is str and THREAD_ID.fullmatch(task['thread_id']))
            text(task['slot']); text(task['next_run_at'])
            if task['next_run_at']:
                try:
                    require(datetime.fromisoformat(task['next_run_at']).tzinfo is not None)
                except ValueError:
                    require(False, 'SCHEDULE_HOST_RECEIPT_INVALID')
        require(len({t['id'] for t in tasks}) == len(tasks))
        payload = {'schedule_host': connection_id, 'request_id': request_id,
                   'outcome': outcome, 'tasks': tasks, 'note': note}

        def mutate(state):
            row = self.row(state, connection_id); pending = row['pending']
            require(pending is not None and pending['id'] == request_id, 'SCHEDULE_REQUEST_MISMATCH')
            old = {t['id']: t for t in row['tasks']}
            require(set(old) <= {t['id'] for t in tasks}, 'SCHEDULE_ORIGINAL_TASK_REQUIRED')
            for task in tasks:
                if task['id'] in old:
                    require(task['thread_id'] == old[task['id']]['thread_id'], 'SCHEDULE_THREAD_MISMATCH')
                require(task['slot'] in set(slots(pending['config'])) | {t['slot'] for t in old.values()}
                        if pending['config'] is not None else task['id'] in old,
                        'SCHEDULE_HOST_SLOTS_MISMATCH')
            require(len({t['thread_id'] for t in tasks}) <= 1, 'SCHEDULE_THREAD_MISMATCH')
            if outcome == 'ACTIVE':
                applied = pending['config']
                require(applied is not None)
                active = [t['slot'] for t in tasks if t['status'] == 'ACTIVE']
                require(sorted(active) == sorted(slots(applied)), 'SCHEDULE_HOST_SLOTS_MISMATCH')
                row['applied_config'] = deepcopy(applied)
            if outcome == 'PAUSED':
                require(bool(tasks) and all(t['status'] == 'PAUSED' for t in tasks), 'SCHEDULE_HOST_NOT_PAUSED')
            row['tasks'] = deepcopy(tasks)
            row['observed'] = {'status': outcome, 'checked_at': self.clock(),
                               'source': 'CODEX_OFFICIAL_AUTOMATION_OBSERVATION', 'note': note}
            if (outcome == 'ACTIVE' and pending['action'] in ('enable', 'resume', 'check')
                    or outcome == 'PAUSED' and pending['action'] in ('pause', 'check')):
                row['pending'] = None
            state['bindings'][self.key(connection_id)] = row
            return {'connection_id': connection_id, 'request_id': request_id, 'host_status': outcome}
        return self.projects._change('project-' + digest(payload)[:32], payload, expected_revision, mutate)

    def delivery(self, connection_id, request_id, delivery, operation_id, expected_revision):
        require(delivery in ('DISPATCHING', 'ACK', 'UNKNOWN', 'NOT_SENT'))
        payload = {'schedule_delivery': connection_id, 'request_id': request_id, 'delivery': delivery}
        def mutate(state):
            row = self.row(state, connection_id); pending = row['pending']
            require(pending is not None and pending['id'] == request_id, 'SCHEDULE_REQUEST_MISMATCH')
            old = pending['delivery']
            require(old == 'NOT_SENT' and delivery == 'DISPATCHING'
                    or old == 'DISPATCHING' and delivery in ('ACK', 'UNKNOWN', 'NOT_SENT'),
                    'SCHEDULE_DELIVERY_CONFLICT')
            pending['delivery'] = delivery
            state['bindings'][self.key(connection_id)] = row
            return {'connection_id': connection_id, 'request_id': request_id, 'delivery': delivery}
        return self.projects._change(operation_id, payload, expected_revision, mutate)

    def begin(self, connection_id, automation_id, occurrence_id, expected_revision):
        text(occurrence_id); require(bool(occurrence_id), 'SCHEDULE_OCCURRENCE_REQUIRED')
        run_id = 'x-scheduled-' + digest([connection_id, automation_id, occurrence_id])[:32]
        payload = {'schedule_run': run_id, 'connection_id': connection_id,
                   'automation_id': automation_id, 'occurrence_id': occurrence_id}

        def mutate(state):
            row = self.row(state, connection_id)
            require(any(t['id'] == automation_id and t['status'] == 'ACTIVE' for t in row['tasks']), 'SCHEDULE_TASK_NOT_ACTIVE')
            previous = row['last_run']
            require(not previous or previous['state'] not in ('RUNNING', 'UNKNOWN'), 'SCHEDULE_ORIGINAL_RUN_PENDING')
            row['last_run'] = dict(payload, run_id=run_id, state='RUNNING', started_at=self.clock(),
                                   upload_attempt_id=run_id + '-media', post_attempt_id=run_id + '-post', url='')
            state['bindings'][self.key(connection_id)] = row
            return deepcopy(row['last_run'])
        return self.projects._change('project-' + digest(payload)[:32], payload, expected_revision, mutate)

    def finish(self, connection_id, run_id, state, note, expected_revision, original_post, original_upload=None):
        require(state in ('MATCHED', 'UNKNOWN', 'FAILED')); text(note)
        if state == 'MATCHED':
            require(original_post.get('connection_id') == connection_id
                    and original_post.get('attempt_id') == run_id + '-post'
                    and original_post.get('state') == 'SUCCEEDED'
                    and original_post.get('readback_state') == 'MATCHED', 'SCHEDULE_ORIGINAL_READBACK_REQUIRED')
            match = URL.fullmatch(original_post.get('url', ''))
            require(match is not None and match[1] == original_post.get('result', {}).get('post_id'), 'SCHEDULE_ORIGINAL_READBACK_REQUIRED')
        if state == 'FAILED':
            require(original_post.get('connection_id') == connection_id
                    and original_post.get('attempt_id') == run_id + '-post'
                    and original_post.get('state') in ('NOT_FOUND', 'REJECTED')
                    and original_upload is not None
                    and original_upload.get('connection_id') == connection_id
                    and original_upload.get('attempt_id') == run_id + '-media'
                    and original_upload.get('state') in ('NOT_FOUND', 'REJECTED', 'SUCCEEDED', 'EXPIRED', 'SOURCE_UNAVAILABLE'),
                    'SCHEDULE_UNKNOWN_RUN_USE_ORIGINAL')
        payload = {'schedule_finish': connection_id, 'run_id': run_id, 'state': state, 'note': note}

        def mutate(store):
            row = self.row(store, connection_id)
            require(row['last_run'] is not None and row['last_run']['run_id'] == run_id, 'SCHEDULE_RUN_MISMATCH')
            require(row['last_run']['state'] != 'MATCHED' or state == 'MATCHED', 'SCHEDULE_RUN_ALREADY_MATCHED')
            row['last_run'].update(state=state, finished_at=self.clock(), note=note,
                                   url=original_post['url'] if state == 'MATCHED' else '')
            store['bindings'][self.key(connection_id)] = row
            return deepcopy(row['last_run'])
        return self.projects._change('project-' + digest(payload)[:32], payload, expected_revision, mutate)
