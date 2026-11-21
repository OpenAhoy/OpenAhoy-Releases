"""Non-secret X content configuration and its complete generated Skill.

Uses the existing ProjectStore transaction/lock; never schedules or publishes.
"""
from copy import deepcopy
from hashlib import sha256
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import WCEError
from .own_bootstrap_security import unique
from .project_context import require, text
from .service import digest
from .tools import schema

FORMAT = 'openahoy.x-operating'
QUALITY = ('先确定内容要传达的信息、主体关系、场景动作、具体细节和构图，再写生图提示。'
           '区分真实资料与概念图，不伪造截图或实测。生成后实际查看成图和发布裁切，核对主题、文字可读性、'
           '形体结构、细节、风格和内容关系；不符时在制作阶段修正，避免空白、装饰堆砌和泛化抽象。')
METHODS = ('专业知识', '实用教程', '作品展示', '行业资讯', '观点讨论', '产品使用', '社群交友')
TEXT = {'type': 'string'}
POSITION = ('topics', 'readers', 'language', 'background', 'allowed', 'excluded', 'voice', 'facts')
GROWTH = ('reason', 'custom', 'cta')
IMAGES = ('subject', 'characters', 'style', 'aspect_ratio', 'color', 'text_brand', 'method')
COLUMN = ('time', 'name', 'purpose', 'format', 'selection', 'missing', 'assets')
PROFILE_SPEC = schema({'positioning': schema({k: TEXT for k in POSITION}),
    'growth': schema({k: TEXT for k in GROWTH} | {'methods': {'type': 'array', 'items': TEXT}}),
    'timezone': TEXT, 'columns': {'type': 'array', 'items': schema({k: TEXT for k in COLUMN})},
    'images': schema({k: TEXT for k in IMAGES}), 'materials': TEXT, 'notes': TEXT})
SPEC = schema({'format': {'type': 'string', 'const': FORMAT},
    'schema_version': {'type': 'integer', 'const': 1}, 'platform': {'type': 'string', 'const': 'x'},
    'account_name': TEXT, 'profile': PROFILE_SPEC})


def blank(name=''):
    return {'format': FORMAT, 'schema_version': 1, 'platform': 'x', 'account_name': name,
        'profile': {'positioning': {k: '' for k in POSITION},
            'growth': {'methods': [], **{k: '' for k in GROWTH}}, 'timezone': 'UTC', 'columns': [],
            'images': {k: QUALITY if k == 'method' else '' for k in IMAGES}, 'materials': '', 'notes': ''}}


def configuration(raw):
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        # Same closed validator as project preferences, without content quotas.
        from .project_context_protocol import validate
        validate(value, SPEC)
        p = value['profile']
        require(len(set(p['growth']['methods'])) == len(p['growth']['methods']), 'X_CONFIG_DUPLICATE_METHOD')
        require(bool(p['timezone']), 'X_CONFIG_TIMEZONE_INVALID')
        try:
            ZoneInfo(p['timezone'])
        except (ValueError, ZoneInfoNotFoundError):
            raise WCEError('X_CONFIG_TIMEZONE_INVALID') from None
        for row in p['columns']:
            require(row['format'] in ('text', 'image', 'auto'), 'X_CONFIG_COLUMN_FORMAT')
            import re
            require(re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', row['time']) is not None,
                    'X_CONFIG_COLUMN_TIME')
        # A time may have multiple explicitly selected series; no artificial quota.
        return value, raw.encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WCEError('X_CONFIG_INVALID') from None


def skill(value, *, legacy=False):
    """Readable, lossless method derived from the exact saved configuration."""
    p = value['profile']
    brand = 'OpenAhoy' if legacy else 'Jiusera'
    lines = ['---', 'name: x-account-creation',
        'description: 依本号已保存运营配置创作 X 内容；不授予发布、互动或调度权限。', '---',
        '# X 本号创作方法', '适用显示名称：' + (value['account_name'] or '由加载时选定的账号决定'),
        f'来源：{brand} X 运营配置 v1；配置 SHA256 ' + digest(value),
        '这是内容方法，不是任务授权。与当前适用 AGENTS、选用 Skills 和补充偏好一起读取；'
        '本号具体内容选择优先于通用创作建议。真实权限及本人本次委托另行核对，冲突不得静默覆盖。',
        '## 定位与表达']
    def item(label, body):
        lines.extend([label + '：', body or '未设置，按当前任务和适用来源自主决定。'])
    for k, label in zip(POSITION, ('主题领域', '目标读者', '语言', '身份与品牌背景', '允许内容', '排除内容', '文风', '事实表述')):
        item(label, p['positioning'][k])
    lines.append('## 吸引关注的目标与方式')
    item('选择的方式', '、'.join(p['growth']['methods']))
    for k, label in zip(GROWTH, ('被关注的原因', '自定义方式', '行动号召')):
        item(label, p['growth'][k])
    lines.append('选题、开场、价值点和CTA结合以上选择，不承诺涨粉，不因此执行自动互动。')
    lines.extend(['## 栏目与节奏', '时区：' + p['timezone'],
        '下面是内容栏目参考，不是已启用的时间表。保存、导入和读取本Skill不创建任务。'
        '临时测试只沿该次明确委托，不把临时触发时刻硬套为同一整点栏目。'])
    for i, row in enumerate(p['columns'], 1):
        lines.append('### 栏目 ' + str(i))
        for k, label in zip(COLUMN, ('当地时刻', '栏目', '目的', '形式(text纯文字/image图文/auto自选)', '选材方法', '缺料处理', '素材来源')):
            item(label, row[k])
    lines.extend(['## 图片创作', '是否配图由本栏目和本次委托决定；画面选择属于本用户，不能推成所有用户默认。'])
    for k, label in zip(IMAGES, ('画面题材', '人物或物件', '风格', '比例', '色彩', '文字与品牌', '质量方法')):
        item(label, p['images'][k])
    lines.extend(['## 素材与特殊系列'])
    item('素材说明', p['materials'])
    lines.append('配置中的本机目录只是用户选择的参考，不证明文件存在或可跨机使用。'
                 '特殊栏目缺资料按该栏目处理，普通新帖不因此全部阻断；人物仅在选用时读取实际身份参考。')
    item('其他约定', p['notes'])
    lines.extend(['## 执行接缝', f'当前 Codex 负责内容与生成图片；使用已授权的本机原图和{brand}官方媒体/发帖/读回通路。'
        '不要求图床、额外模型API Key或角色签字，不复用历史稿冒新创作。'
        '制作阶段核对事实和成图，不另造发表许可。未知结果查询原请求，不补发。'])
    return '\n\n'.join(lines) + '\n'


class OperatingConfig:
    def __init__(self, projects):
        self.projects = projects

    @staticmethod
    def key(cid):
        require(type(cid) is str and cid and len(cid) <= 128, 'X_CONFIG_ACCOUNT_REQUIRED')
        text(cid)
        return json.dumps(['x', cid, 'operating'], separators=(',', ':'))

    def read(self, connection_id):
        state = self.projects._load()
        value = state['bindings'].get(self.key(connection_id))
        if value is not None:
            value, _ = configuration(json.dumps(value, ensure_ascii=False))
        body = skill(value) if value is not None else ''
        return {'revision': state['revision'], 'connection_id': connection_id,
            'state': 'CONFIGURED' if value is not None else 'NOT_CONFIGURED',
            'configuration': deepcopy(value), 'configuration_sha256': digest(value) if value is not None else '',
            'skill': {'name': 'X 本号运营创作 Skill', 'text': body,
                      'sha256': sha256(body.encode()).hexdigest(), 'complete': True},
            'authority': False, 'schedules_changed': False}

    def save(self, connection_id, configuration_text, expected_revision, operation_id):
        value, _ = configuration(configuration_text)
        key = self.key(connection_id)
        def mutate(state):
            state['bindings'][key] = deepcopy(value)
            return {'connection_id': connection_id, 'configuration_sha256': digest(value),
                    'skill_sha256': sha256(skill(value).encode()).hexdigest(), 'schedules_changed': False}
        return self.projects._change(operation_id, {'x_operating': key, 'configuration': value},
                                     expected_revision, mutate)
