"""One persistent local render per work/version. The worker inherits the lease across MCP restarts."""
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from threading import Thread

from .contracts import WCEError
from .bounded_file import identity
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional
from .service import digest
from .video_director import Director, ROOT_NAME, lookup, require
from . import video_director_timeline as timeline
from .video_jobs import Jobs


def paths(root, work_id, version):
    stem = root / ROOT_NAME / f'cut-{work_id}-{version}'
    return stem.with_suffix('.json'), stem.with_suffix('.lock')


def load_work(director, args):
    project = args['project_id']
    root, pin = director.project(project)
    storage = director.storage(root, pin)
    require((storage / 'storyboards.json').exists(), 'DIRECTOR_WORK_NOT_FOUND')
    with locked(storage / 'writer.lock', shared=True, existing=True, readonly=True):
        state = director.load(project, storage)
    work = lookup(state['works'], args['work_id'], 'DIRECTOR_WORK_NOT_FOUND')
    require(work.get('kind') != 'article', 'ARTICLE_WORK_USE_ARTICLE_TOOLS')
    return root, state, work


def write_record(path, row):
    with locked(path.with_suffix('.state-lock')):
        atomic_write(path, row)


def read_record(path):
    if not os.path.lexists(path):
        return None
    with locked(path.with_suffix('.state-lock'), shared=True, existing=True, readonly=True):
        return read_optional(path)


def project_job(row):
    return row.get('receipt', {}) | {key: row[key] for key in ('state', 'completed_clips', 'total_clips', 'error') if key in row} | {
        'operation_id': row['request']['operation_id']}


def from_state(root, state, work, version, mix=None):
    base = {'project_id': state['project_id'], 'work_id': work['id'], 'timeline_version': version}
    key = timeline.export_key(version, mix)
    record, lease = paths(root, work['id'], key)
    archive = work.get('timeline_exports', {}).get(key)
    if archive:
        row = state['operations'].get(archive.get('operation_id'), {})
        film = work['films'][archive['delivery_id']]
        count = len(archive['cut']['clips'])
        return {**base, 'state': 'SAVED', 'completed_clips': count, 'total_clips': count,
                'delivery_id': archive['delivery_id'], 'asset': film['asset'],
                'chat_path': str(root / film['file']['path']), **row.get('receipt', {}),
                'operation_id': archive.get('operation_id')}
    row = read_record(record)
    if not row:
        return {**base, 'state': 'NOT_FOUND'}
    result = base | project_job(row)
    if row['state'] == 'RUNNING':
        try:
            with locked(lease, nonblocking=True, shared=True, existing=True, readonly=True):
                # The worker released its lease. Its last checkpoint may have raced the first read.
                latest = read_record(record)
                result.update(project_job(latest))
                if latest['state'] == 'RUNNING':
                    result.update(state='INTERRUPTED', error='DIRECTOR_RENDER_INTERRUPTED')
        except WCEError as error:
            if error.code != 'CONNECTION_BUSY':
                raise
    return result


def status(director, args):
    root, state, work = load_work(director, args)
    return from_state(root, state, work, args['expected_timeline_version'], args.get('studio_mix'))


def clear_interrupted_render(storage, previous):
    scratch = previous.get('scratch')
    if not scratch:
        return
    name = scratch['name']
    prefix = 'render-' + previous['request']['operation_id'] + '-'
    if not re.fullmatch(re.escape(prefix) + r'[A-Za-z0-9_-]+', name):
        return
    path = storage / name
    if not os.path.lexists(path):
        return
    # Only remove our own one-level, inode-pinned staging directory. Unknown contents are retained.
    try:
        parent = os.open(storage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                if identity(os.fstat(fd)) != tuple(scratch['pin']):
                    return
                entries = os.listdir(fd)
                for entry in entries:
                    info = os.stat(entry, dir_fd=fd, follow_symlinks=False)
                    if not (re.fullmatch(r'source-[0-9]+[.]mp4|clip-[0-9]+[.]mov|stem-[0-9]+[.]audio|studio-score[.]wav|song|sequence[.]ffconcat|sequence[.]mp4', entry)
                            and stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1):
                        return
                for entry in entries:
                    os.unlink(entry, dir_fd=fd)
                if identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == identity(os.fstat(fd)):
                    os.rmdir(name, dir_fd=parent)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
    except OSError:
        # A recovered export gets its own new scratch directory regardless.
        return


def start(director, args):
    root, state, work = load_work(director, args)
    version = args['expected_timeline_version']
    mix = args.get('studio_mix')
    key = timeline.export_key(version, mix)
    request = {key: value for key, value in args.items() if key != 'retry'}
    prior = state['operations'].get(args['operation_id'])
    if prior:
        require(prior['fingerprint'] == digest(request), 'DIRECTOR_OPERATION_CONFLICT')
    result = from_state(root, state, work, version, mix)
    if result['state'] in ('RUNNING', 'SAVED'):
        record, _ = paths(root, work['id'], key)
        previous = read_record(record)
        if previous and previous['request']['operation_id'] == args['operation_id']:
            require(previous['request'] == request, 'DIRECTOR_OPERATION_CONFLICT')
        return result
    require(timeline.saved(work)['timeline_version'] == version, 'DIRECTOR_TIMELINE_CHANGED')
    require(timeline.saved(work)['clips'], 'DIRECTOR_TIMELINE_EMPTY')
    record, lease = paths(root, work['id'], key)
    try:
        with locked(lease, nonblocking=True) as fd:
            # Recheck after acquiring the exclusive lease. Other callers may have started or finished.
            root, state, work = load_work(director, args)
            if key in work.get('timeline_exports', {}):
                return from_state(root, state, work, version, mix)
            require(timeline.saved(work)['timeline_version'] == version, 'DIRECTOR_TIMELINE_CHANGED')
            previous = read_record(record)
            if previous:
                if previous['request']['operation_id'] == args['operation_id']:
                    require(previous['request'] == request, 'DIRECTOR_OPERATION_CONFLICT')
                if not args.get('retry') or previous['request']['operation_id'] == args['operation_id']:
                    projected = project_job(previous)
                    if projected['state'] == 'RUNNING':
                        projected.update(state='INTERRUPTED', error='DIRECTOR_RENDER_INTERRUPTED')
                    return {'project_id': args['project_id'], 'work_id': work['id'], 'timeline_version': version,
                            **projected}
                clear_interrupted_render(root / ROOT_NAME, previous)
            row = {'request': request, 'state': 'RUNNING', 'completed_clips': 0,
                   'total_clips': len(timeline.saved(work)['clips'])}
            write_record(record, row)
            entry = Path(__file__).resolve().parents[1] / 'scripts' / 'wce_timeline_export.py'
            try:
                process = subprocess.Popen([sys.executable, '-I', '-B', str(entry), str(director.projects.registry),
                                  args['project_id'], work['id'], key, str(fd)],
                                 pass_fds=(fd,), start_new_session=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                Thread(target=process.wait, name='director-render-reaper', daemon=True).start()
            except OSError:
                row.update(state='FAILED', error='DIRECTOR_RENDER_WORKER_UNAVAILABLE')
                write_record(record, row)
            return {'project_id': args['project_id'], 'work_id': work['id'], 'timeline_version': version,
                    **project_job(row)}
    except WCEError as error:
        if error.code != 'CONNECTION_BUSY':
            raise
        current = status(director, args)
        # A concurrent caller is still writing the first job receipt.
        if current['state'] == 'NOT_FOUND':
            current.update(state='RUNNING', operation_id=args['operation_id'], completed_clips=0,
                           total_clips=len(timeline.saved(work)['clips']))
        return current


def worker(registry, project, work_id, key, fd):
    jobs = Jobs(registry)
    director = Director(jobs.projects)
    root, _ = director.project(project)
    require(re.fullmatch(r'[0-9]+(?:-mix-[0-9a-f]{64})?', str(key)), 'DIRECTOR_RENDER_LEASE_CHANGED')
    record, lease = paths(root, work_id, key)
    require(os.path.samestat(lease.lstat(), os.fstat(fd)), 'DIRECTOR_RENDER_LEASE_CHANGED')
    row = read_record(record)
    args = row['request']
    require(args['project_id'] == project and args['work_id'] == work_id
            and timeline.export_key(args['expected_timeline_version'], args.get('studio_mix')) == str(key), 'DIRECTOR_RENDER_LEASE_CHANGED')

    row['worker_pid'] = os.getpid()
    write_record(record, row)

    def progress(count):
        row['completed_clips'] = count
        write_record(record, row)

    def record_scratch(folder):
        row['scratch'] = {'name': folder.name, 'pin': list(path_check(folder, True))}
        write_record(record, row)

    try:
        row['receipt'] = timeline.export(director, jobs, args, progress, record_scratch)
        row['state'] = 'SAVED'
    except WCEError as error:
        row.update(state='FAILED', error=error.code)
    except Exception:
        row.update(state='FAILED', error='DIRECTOR_RENDER_FAILED')
    write_record(record, row)
