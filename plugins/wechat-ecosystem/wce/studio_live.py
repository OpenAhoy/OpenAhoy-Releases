"""Applied Stereo Out profiles and bounded, per-MCP-connection native monitoring."""
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import re
import secrets
import subprocess
from tempfile import NamedTemporaryFile
from threading import RLock, Timer

from . import studio_master_bus as master
from .bounded_file import file_state
from .project_context import exact_path
from .studio_draft import read_draft
from .studio_projects import digest, require, valid_id

KEY = ('project', 'song', 'version')
ACTIONS = {
    'monitor_open': (*KEY, 'analysis', 'frame', 'bypass'),
    'monitor_read': (*KEY, 'analysis', 'stream', 'frame', 'frames'),
    'monitor_close': (*KEY, 'stream'),
}
MAX_FRAMES = 32768
SCHEMA_FIELDS = {
    'stream': {'type': 'string', 'pattern': '^stream-[0-9a-f]{32}$', 'maxLength': 39},
    'frame': {'type': 'integer', 'minimum': 0},
    'frames': {'type': 'integer', 'minimum': 1, 'maximum': MAX_FRAMES},
    'bypass': {'type': 'boolean'},
}


def integer(value, lo, hi):
    return type(value) is int and lo <= value <= hi


@contextmanager
def deadline(process, seconds):
    # End a hung renderer even when it stops partway through a binary block.
    timer = Timer(seconds, process.kill)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


class Stream:
    def __init__(self, profile, frame, bypass):
        self.cursor = frame
        self.bypass = bypass
        args = [master.RENDERER, '--monitor', master.COMPONENT, profile['manifest'],
                '--load-preset', profile['preset']]
        if bypass:
            args.append('--bypass')
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL)
        try:
            with deadline(self.process, 25):
                msg = self.header()
                require(msg.get('ready') is True and msg.get('channels') == 2 and
                        msg.get('encoding') == 'f32le' and msg.get('frames') == profile['frames']
                        and msg.get('sampleRate') == profile['sampleRate'], 'studio_monitor_invalid')
                if frame:
                    self.send({'op': 'seek', 'frame': frame})
                    require(self.header().get('nextFrame') == frame, 'studio_monitor_invalid')
        except BaseException:
            self.close()
            raise

    def send(self, msg):
        self.process.stdin.write(json.dumps(msg).encode() + b'\n')
        self.process.stdin.flush()

    def header(self):
        line = self.process.stdout.readline(2049)
        require(0 < len(line) <= 2048 and line.endswith(b'\n'), 'studio_monitor_unavailable', 503)
        return json.loads(line)

    def read(self, amount, length, bypass):
        with deadline(self.process, 10):
            request = {'op': 'read', 'frames': amount}
            if bypass != self.bypass:
                request['bypass'] = bypass
            self.send(request)
            info = self.header()
            n = min(amount, length - self.cursor)
            require(info.get('start') == self.cursor and info.get('frames') == n and
                    info.get('eof') is (self.cursor + n == length), 'studio_monitor_invalid')
            pcm = self.process.stdout.read(n * 8)
            require(len(pcm) == n * 8, 'studio_monitor_invalid')
        self.cursor += n
        self.bypass = bypass
        return info | {'bytes': base64.b64encode(pcm).decode('ascii')}

    def close(self):
        try:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        finally:
            self.process.stdin.close()
            self.process.stdout.close()


class LiveBus:
    """Owned by one StudioRouter. Never requires a listening socket, daemon, or rendered track."""
    def __init__(self, router, idle_seconds=15):
        self.router = router
        self.streams = {}
        self.lock = RLock()
        self.idle_seconds = idle_seconds

    def profile(self, key, token):
        root, folder, _, version = self.router.bound(key)
        require(not version.get('mastered'), 'studio_original_required')
        receipt = self.router.analysis(folder, key, token)
        rate = receipt['sample_rate']
        master.choose(version['masterRate'], rate)
        manifest, pins = master.arrangement(root, version, read_draft(folder, key), rate)
        plan = master.arrangement_digest(manifest, version)
        renderer, unit = master.engine_identity()
        require((plan, renderer, unit, manifest['frames']) == (receipt['arrangement_sha256'],
                receipt['renderer_sha256'], receipt['engine_sha256'], receipt['frames']), 'analysis_changed', 409)
        require(token == 'analysis-' + digest([key, renderer, unit, plan, receipt['settings'],
                                               receipt['rate_basis']])[:32], 'analysis_changed', 409)
        preset = exact_path(str(folder / token / 'Output Master.aupreset'))
        require(preset.stat().st_size <= 1024 * 1024 and master.checksum(preset) == receipt['preset_sha256'],
                'analysis_changed', 409)
        return {'sampleRate': rate, 'frames': manifest['frames'], 'preset': preset, 'arrangement': manifest,
                'folder': folder, 'pins': pins}

    def remove(self, token):
        row = self.streams.pop(token, None)
        if row:
            if row.get('timer'):
                row['timer'].cancel()
            row['engine'].close()

    def arm(self, token, row):
        if row.get('timer'):
            row['timer'].cancel()

        def expire():
            with self.lock:
                if self.streams.get(token) is row and timer is row.get('timer'):
                    self.remove(token)

        timer = Timer(self.idle_seconds, expire)
        timer.daemon = True
        row['timer'] = timer
        timer.start()

    def close(self):
        with self.lock:
            for token in list(self.streams):
                self.remove(token)

    def dispatch(self, args):
        action = args.get('action')
        allowed = {'action', *ACTIONS[action]}
        if action == 'monitor_read' and 'bypass' in args:
            allowed.add('bypass')
        require(set(args) == allowed)
        key = tuple(args[k] for k in KEY)
        require(all(map(valid_id, key)))
        with self.lock:
            if action == 'monitor_open':
                require(type(args['bypass']) is bool)
                require(len(self.streams) < 4, 'studio_monitor_busy', 409)
                profile = self.profile(key, args['analysis'])
                require(integer(args['frame'], 0, profile['frames']))
                # Native reads this trusted arrangement during startup, before its ready reply.
                # Rebuilding from the bound catalog also supports previously saved R4 profiles.
                with NamedTemporaryFile(mode='w', dir=profile['folder'], prefix='.monitor-', suffix='.json') as tmp:
                    json.dump(profile['arrangement'], tmp, allow_nan=False)
                    tmp.flush()
                    player = Stream(profile | {'manifest': Path(tmp.name)}, args['frame'], args['bypass'])
                token = 'stream-' + secrets.token_hex(16)
                row = {'engine': player, 'key': key, 'analysis': args['analysis']}
                self.streams[token] = row
                self.arm(token, row)
                return {'stream': token, 'sampleRate': profile['sampleRate'], 'frames': profile['frames'],
                        'start': args['frame'], 'bypass': args['bypass']}
            token = args['stream']
            require(type(token) is str and re.fullmatch(r'stream-[0-9a-f]{32}', token))
            row = self.streams.get(token)
            if action == 'monitor_close' and row is None:
                return {'closed': True}
            require(row and row['key'] == key, 'studio_stream_unavailable', 404)
            if action == 'monitor_close':
                self.remove(token)
                return {'closed': True}
            require(args['analysis'] == row['analysis'], 'studio_stream_unavailable', 404)
            require(integer(args['frames'], 1, MAX_FRAMES) and integer(args['frame'], 0, 2**53-1)
                    and args['frame'] == row['engine'].cursor, 'studio_stream_position', 409)
            try:
                profile = self.profile(key, args['analysis'])
                bypass = args.get('bypass', row['engine'].bypass)
                require(type(bypass) is bool)
                data = row['engine'].read(args['frames'], profile['frames'], bypass)
                # Recheck the binding and bytes before returning data if the draft is edited concurrently.
                later = self.profile(key, args['analysis'])
                require(later['pins'] == profile['pins'] and all(
                    file_state(path.lstat()) == pin for path, pin in profile['pins']), 'studio_media_changed', 409)
                if data['eof']:
                    self.remove(token)
                else:
                    self.arm(token, row)
                return data | {'encoding': 'f32le', 'sampleRate': profile['sampleRate'], 'channels': 2, 'bypass': bypass}
            except BaseException:
                self.remove(token)
                raise
