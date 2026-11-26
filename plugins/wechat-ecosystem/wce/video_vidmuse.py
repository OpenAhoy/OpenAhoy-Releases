"""Official VidMuse CLI boundary. Authentication remains in its private home."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener
from zipfile import BadZipFile, ZipFile

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .video_relay import PublicHTTPSHandler, https_url
from .video_seedance import NoRedirect, download_mp4

PROVIDER = 'vidmuse'
MODEL = 'magi-2'
ORIGIN = 'https://vidmuse.ai'
DOC_URL = ORIGIN + '/en/cli'
PRICING_URL = ORIGIN + '/en/pricing'
VERSION = 'v0.9.17-45e8bc0'
ARCHIVES = {
    'arm64': '5231416c61fd07ecd4f76555f8e3c9539fa629a2540732c24f8090df09006ee9',
    'amd64': 'f4783057da218d8ed43c878158e882153a13f2272cffa8d46fc9631dd8ed9d90',
}
LIMIT = 32 * 1024 * 1024
MODES = {'text_to_video': 'text', 'reference_to_video': 'reference'}
RATIOS = ('16:9', '1:1', '4:3', '3:4', '9:16', '21:9')
DURATIONS = range(1, 31)
REFERENCE_LIMIT = 10
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,159}\Z')
TASK = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z')
STATES = {'pending': 'queued', 'queued': 'queued', 'submitted': 'queued',
          'running': 'running', 'processing': 'running', 'succeeded': 'succeeded',
          'success': 'succeeded', 'completed': 'succeeded', 'failed': 'failed',
          'cancelled': 'cancelled', 'canceled': 'cancelled', 'expired': 'expired'}


def require(condition, code):
    if not condition:
        raise WCEError(code)


def private_directory(path):
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    path_check(path, True)
    return path


def object_data(value):
    return value['data'] if isinstance(value, dict) and 'data' in value else value


def decimal_credit(value):
    if type(value) not in (int, float, str, Decimal) or len(str(value)) > 45:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and 0 <= amount <= 10**8 else None


def stable_account(value):
    value = object_data(value)
    if isinstance(value, dict):
        for name in ('profile', 'user', 'userInfo'):
            if isinstance(value.get(name), dict):
                value = value[name]
                break
        for name in ('user_id', 'userId', 'id', 'uid', 'sub'):
            identity = value.get(name)
            if type(identity) in (str, int) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', str(identity)):
                return sha256(('vidmuse-production:' + str(identity)).encode()).hexdigest()
    raise WCEError('VIDMUSE_ACCOUNT_UNAVAILABLE')


def model_name(row):
    return next((row[key] for key in ('model_name','modelName','name') if isinstance(row.get(key),str)), '')


def select_models(value):
    rows = object_data(value)
    if isinstance(rows, dict):
        rows = rows.get('models', rows.get('items', rows.get('videos')))
    require(isinstance(rows, list), 'VIDMUSE_CATALOG_UNAVAILABLE')
    matches = []
    for row in rows:
        if not isinstance(row, dict) or row.get('enabled', True) is False:
            continue
        name = model_name(row)
        labels = (row.get('displayName'), row.get('display_name'), name.rsplit('/', 1)[-1])
        if NAME.fullmatch(name) and any(isinstance(label, str) and re.fullmatch(r'magi[ _-]?2',label,re.I) for label in labels):
            matches.append(row)
    require(matches, 'VIDMUSE_NO_MODEL')
    return matches


def choices(value):
    if isinstance(value, dict):
        enum = next((value[key] for key in ('enum','options','values','choices') if key in value), None)
        if enum is None and 'value' in value:
            return [value['value']]
        value = enum
    if not isinstance(value, list):
        return []
    return [v.get('value') if isinstance(v, dict) else v for v in value]


def fields(value):
    if isinstance(value, dict):
        return value.get('properties', value)
    if isinstance(value, list):
        return {rule['name']: rule for rule in value if isinstance(rule, dict) and isinstance(rule.get('name'), str)}
    return {}


def catalog_schema(row):
    result = {}
    for key in ('required_params','optional_params','params','options','parameters','schema'):
        spec = fields(row.get(key))
        if isinstance(spec, dict):
            for name, rule in spec.items():
                if name not in result or isinstance(rule, (dict, list)):
                    result[name] = rule
    return result


def duration_choices(rule):
    if isinstance(rule, dict):
        lo = rule.get('minimum', rule.get('min'))
        hi = rule.get('maximum', rule.get('max'))
        step = rule.get('step', 1)
        if type(lo) is int and type(hi) is int and type(step) is int and 0 < step <= 30:
            return [n for n in DURATIONS if lo <= n <= hi and (n-lo) % step == 0]
    return [n for n in choices(rule) if type(n) is int and n in DURATIONS]


def filter_matches(actual, expected):
    if type(actual) is bool and expected in ('true','false'):
        return actual is (expected=='true')
    if type(actual) is int and isinstance(expected,str):
        return str(actual)==expected
    return type(actual) is type(expected) and actual==expected


@dataclass(frozen=True)
class Route:
    name: str
    generation: str
    mode: str
    durations: tuple
    resolutions: tuple
    ratios: tuple
    audio: tuple
    audio_key: str
    references: int
    prices: tuple

    def has(self, configuration):
        return (configuration['mode'] == self.mode and configuration['duration'] in self.durations
                and configuration['resolution'] in self.resolutions and configuration['ratio'] in self.ratios
                and configuration.get('audio', False) in self.audio)

    def body(self, configuration, prompt, images):
        request = {'model_name': self.name, 'generation_type': self.generation, 'prompt': prompt,
                   'duration': configuration['duration'], 'aspect_ratio': configuration['ratio'],
                   'resolution': configuration['resolution']}
        if self.audio_key:
            request[self.audio_key] = configuration.get('audio', False)
        if images:
            request['elements'] = [{'reference_image_urls': images}]
        return request

    def estimate(self, body):
        body = body | {'audio': body.get(self.audio_key, False)}
        items = []
        for item in self.prices:
            if not isinstance(item, dict):
                continue
            properties = item.get('properties') or {}
            if not isinstance(properties, dict):
                raise WCEError('VIDMUSE_PRICE_UNAVAILABLE')
            if any(key not in body for key in properties):
                # Cannot exclude a possible higher tier when its applicability is unknown.
                raise WCEError('VIDMUSE_PRICE_UNAVAILABLE')
            if any(not filter_matches(body[key], needed) for key, needed in properties.items()):
                continue
            price = item.get('price')
            unit = decimal_credit(price.get('output')) if isinstance(price, dict) else None
            cost = unit * body['duration'] if unit is not None and item.get('unit_type') == 'seconds' else None
            items.append((len(properties), cost))
        require(items, 'VIDMUSE_PRICE_UNAVAILABLE')
        specificity = max(weight for weight, _ in items)
        costs = {price for weight, price in items if weight == specificity}
        require(len(costs)==1 and None not in costs, 'VIDMUSE_PRICE_UNAVAILABLE')
        return costs.pop()


def catalog_routes(value):
    routes = []
    for row in select_models(value):
        schema = catalog_schema(row)
        modes = next((seq for seq in (row.get('generation_types'), row.get('generationTypes'),
                                      choices(schema.get('generation_type'))) if isinstance(seq,list) and seq), [])
        if isinstance(row.get('generation_type'),str) and not modes:
            modes = [row['generation_type']]
        duration = tuple(sorted(set(duration_choices(schema.get('duration')))))
        resolution = tuple(s for s in ('1080p',) if s in choices(schema.get('resolution')))
        ratios = tuple(r for r in RATIOS if r in choices(schema.get('aspect_ratio')))
        audio_key=next((key for key in ('audio','generate_audio') if key in schema),'')
        sound = schema.get(audio_key)
        audio = tuple(v for v in choices(sound) if type(v) is bool)
        if not audio:
            if isinstance(sound, dict) and sound.get('type') == 'boolean':
                audio=(False, True)
            elif audio_key:
                # An undeclared sound setting cannot be safely serialized or priced.
                continue
            else:
                audio=(False,)
        refs = schema.get('elements')
        reference_rule = refs.get('items', {}) if isinstance(refs,dict) else {}
        reference_props = fields(reference_rule)
        limits = reference_props.get('reference_image_urls') if isinstance(reference_props,dict) else None
        maximum = limits.get('maxItems', 1) if isinstance(limits,dict) else 1
        references = min(maximum, REFERENCE_LIMIT) if type(maximum) is int and maximum > 0 else 0
        if not (duration and resolution and ratios):
            continue
        prices = row.get('priceItems')
        prices = tuple(prices) if isinstance(prices,list) else ()
        for kind in MODES:
            if kind not in modes or kind=='reference_to_video' and ('elements' not in schema or not references):
                continue
            routes.append(Route(model_name(row),kind,MODES[kind],duration,resolution,ratios,audio,audio_key,
                                references if kind=='reference_to_video' else 0,prices))
    require(routes, 'VIDMUSE_PARAMETERS_UNAVAILABLE')
    return routes


def profile_projection(routes):
    # Show each live route separately if the provider supplies different requirements.
    return [{'model_name': route.name, 'mode': route.mode, 'duration': list(route.durations),
             'resolution': list(route.resolutions), 'ratio': list(route.ratios), 'audio': list(route.audio),
             'reference_count': route.references} for route in routes]


class VidMuse:
    def __init__(self, root, *, opener=None, public=None, clock=time.time):
        self.root = root / 'vidmuse'
        self.clock = clock
        self.opener = opener if opener is not None else build_opener(ProxyHandler({}),NoRedirect())
        self.public = public if public is not None else build_opener(ProxyHandler({}),NoRedirect(),PublicHTTPSHandler())

    def binary(self):
        candidate = self.root / 'vidmuse'
        if not os.path.lexists(candidate):
            raise WCEError('VIDMUSE_CLI_MISSING')
        path_check(self.root,True)
        info = candidate.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode)==0o700 and info.st_nlink==1,'VIDMUSE_CLI_UNSAFE')
        return candidate

    def install(self):
        if os.path.lexists(self.root / 'vidmuse'):
            self.binary()
            return
        machine = {'arm64':'arm64', 'x86_64':'amd64'}.get(platform.machine())
        require(platform.system()=='Darwin' and machine in ARCHIVES, 'VIDMUSE_CLI_PLATFORM_UNSUPPORTED')
        private_directory(self.root.parent)
        private_directory(self.root)
        stem='vidmuse-darwin-'+machine
        try:
            url=f'https://vidmuse.sandcdn.com/cli/releases/{VERSION}/{stem}.zip'
            with self.opener.open(url,timeout=25) as response:
                data=response.read(LIMIT+1)
            require(len(data)<=LIMIT and sha256(data).hexdigest()==ARCHIVES[machine], 'VIDMUSE_CLI_INTEGRITY')
            with ZipFile(BytesIO(data)) as archive:
                members=[entry for entry in archive.infolist()
                         if PurePosixPath(entry.filename).parts in ((stem,),('vidmuse-services',stem))]
                require(len(members)==1 and 0<members[0].file_size<=LIMIT, 'VIDMUSE_CLI_INTEGRITY')
                binary=archive.read(members[0])
            # Publish only the checked full binary. An interrupted install cannot publish a partial file.
            with tempfile.TemporaryDirectory(dir=self.root,prefix='.install-') as folder:
                stage=Path(folder)/stem
                stage.write_bytes(binary)
                stage.chmod(0o700)
                os.replace(stage,self.root/'vidmuse')
        except (OSError,BadZipFile):
            raise WCEError('VIDMUSE_CLI_INSTALL_FAILED') from None
        self.binary()

    def command(self, arguments, *, timeout=22, text=False):
        binary = self.binary()
        home = private_directory(self.root/'home')
        scratch = private_directory(self.root/'tmp')
        environment = {'HOME': str(home), 'TMPDIR':str(scratch), 'PATH':'/usr/bin:/bin',
                       'LANG':'en_US.UTF-8', 'VIDMUSE_BASE_URL':ORIGIN}
        argv = [str(binary), *arguments, '--output', 'json']
        try:
            subprocess_result = subprocess.run(argv,capture_output=True,timeout=timeout,env=environment,cwd=home)
        except (OSError, subprocess.TimeoutExpired):
            raise WCEError('VIDMUSE_CLI_UNAVAILABLE') from None
        if subprocess_result.returncode != 0:
            if subprocess_result.returncode == 3:
                raise WCEError('VIDMUSE_AUTH_REQUIRED')
            # Only recognize explicit first-party conditions, never forward CLI output.
            stderr = subprocess_result.stderr[:4096].decode(errors='replace').lower()
            if arguments[:2] == ['login','--device']:
                raise WCEError('VIDMUSE_AUTH_PENDING')
            if arguments[:2] == ['model','result'] and re.search(r'\b(?:http|status)\s*\(?429\b', stderr):
                raise WCEError('VIDEO_QUERY_RATE_LIMITED')
            raise WCEError('VIDMUSE_CLI_UNAVAILABLE')
        try:
            data = subprocess_result.stdout.decode()
            require(len(data)<=2*1024*1024,'VIDMUSE_RESPONSE_UNAVAILABLE')
            if text:
                return data
            return json.loads(data,parse_constant=lambda _: None)
        except (ValueError, UnicodeError, RecursionError):
            raise WCEError('VIDMUSE_RESPONSE_UNAVAILABLE') from None

    def device_start(self):
        value = self.command(['login','--device','--start'],text=True)
        url = re.search(r'https://[^\s"<>]+',value)
        code = re.search(r'Enter this code if prompted:\s*([A-Za-z0-9-]{4,24})',value,re.I)
        require(url and code, 'VIDMUSE_AUTH_UNAVAILABLE')
        parts = urlsplit(url.group())
        require(parts.scheme=='https' and parts.netloc=='vidmuse.ai' and
                parts.path=='/api/v1/cli/auth/verify' and not parts.fragment, 'VIDMUSE_AUTH_UNAVAILABLE')
        return {'url':url.group(),'code':code.group(1)}

    def device_finish(self):
        # The official CLI polls during --complete. A short unfinished poll is recoverable via the same device flow.
        try:
            self.command(['login','--device','--complete'],timeout=10,text=True)
        except WCEError as error:
            if error.code not in ('VIDMUSE_CLI_UNAVAILABLE','VIDMUSE_AUTH_PENDING','VIDMUSE_AUTH_REQUIRED'):
                raise
        return self.account()

    def account(self):
        return stable_account(self.command(['profile','get']))

    def credits(self):
        value = object_data(self.command(['credits','get']))
        amount = decimal_credit(value.get('availableCredits')) if isinstance(value,dict) else None
        if amount is None:
            value = object_data(self.command(['plan','get']))
            amount = decimal_credit(value.get('credits')) if isinstance(value,dict) else None
        require(amount is not None,'VIDMUSE_BALANCE_UNAVAILABLE')
        return amount

    def catalog(self):
        return catalog_routes(self.command(['model','list','--video','--search','MAGI-2']))

    def check_account(self, account):
        require(account == self.account(),'VIDMUSE_ACCOUNT_CHANGED')

    def submit(self, account, body):
        self.check_account(account)
        raw = self.command(['model','run','--async','--param',body.decode()],timeout=140)
        data = object_data(raw)
        task = (data.get('taskId',data.get('task_id')) if isinstance(data,dict) else data)
        if type(task) is int:
            task = str(task)
        require(isinstance(task,str) and TASK.fullmatch(task),'VIDEO_TASK_ID_UNKNOWN')
        return task

    def query(self, account, task, *, model):
        require(model==MODEL and TASK.fullmatch(task),'VIDEO_TASK_ID_UNKNOWN')
        try:
            self.check_account(account)
            value = object_data(self.command(['model','result',task]))
        except WCEError as error:
            if error.code=='VIDMUSE_AUTH_REQUIRED':
                raise WCEError('VIDEO_QUERY_AUTH_REQUIRED') from None
            raise
        if isinstance(value,dict):
            identity = value.get('taskId',value.get('task_id'))
            require(identity is None or str(identity)==task,'VIDEO_TASK_ID_MISMATCH')
            state = value.get('taskStatus',value.get('task_status',value.get('status')))
            status = STATES.get(state.lower()) if isinstance(state,str) else None
            if status and status!='succeeded':
                return {'status':status}
            videos = value.get('result', value.get('output', value))
            if isinstance(videos,dict):
                videos = videos.get('video_urls',videos.get('videos',videos.get('video_url')))
        else:
            videos = value
        if isinstance(videos,str):
            videos=[videos]
        if isinstance(videos,list) and len(videos)==1 and isinstance(videos[0],dict):
            videos=[videos[0].get('video_url',videos[0].get('url'))]
        require(isinstance(videos,list) and len(videos)==1 and isinstance(videos[0],str),
                'VIDEO_RESULT_URL_UNAVAILABLE')
        return {'status':'succeeded','content':{'video_url':videos[0]}}

    def download(self, url, output):
        require(isinstance(url,str),'VIDEO_RESULT_URL_UNAVAILABLE')
        parts = https_url(url,'VIDEO_RESULT_SOURCE_INVALID')
        require(parts.path not in ('','/'),'VIDEO_RESULT_SOURCE_INVALID')
        download_mp4(self.public,url,output)
