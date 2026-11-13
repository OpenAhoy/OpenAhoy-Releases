"""Initialize only the explicitly selected project; never account preferences.

The bridge stays small and resolves the currently installed plugin's authority.
User files are never replaced: AGENTS is append-only, the Skill is create-only.
"""
import fcntl
from hashlib import sha256
import os
import re
import stat

from .contracts import WCEError
from .project_context import catalog, exact_path, require
from .service import digest

BEGIN = '<!-- OpenAhoy production bridge:begin -->'
END = '<!-- OpenAhoy production bridge:end -->'
BLOCK = f'''{BEGIN}
## OpenAhoy 内容生产

涉及 OpenAhoy 的平台内容任务，先完整读取本项目 `.agents/skills/openahoy-production/SKILL.md`，再读取当前已安装插件的通用 Skill、平台技术标准与目标账号完整有效规则。遵守当前用户委托和适用的项目指令；个人账号、风格、配图比例与署名不作为通用默认。
公众号最终产物必须是真实存在、可读取的完整含图 HTML 文件，不能用纯文字或完成声明代替；X 按 X 平台格式交付。本段与初始化本身不授权发表、绑定账号或启用调度。
{END}'''
SKILL = '''---
name: openahoy-production
description: Use for OpenAhoy content research, illustrated production and platform delivery in this project; resolve the installed plugin rules and account preferences first.
---

# OpenAhoy 内容生产

这是当前项目的桥接 Skill，不复制或冻结插件的整套生产规则。用户当前要求、适用 AGENTS 与平台权限继续有效；初始化不授权绑定、上传、发表、互动或调度。

1. 先用当前已安装 OpenAhoy 的原生 `own.projects.read {view:"catalog"}` 获取 `builtin`，以 `source_id:"builtin-openahoy"`、实际 SHA256、空 project_id 读取全部 source chunks，核对完整原文、字节数和 SHA。再按其引用完整读取当前安装包中的 CONTENT_PRODUCTION、PROJECT_CONTEXT、目标平台规范及相关 HTML 技术标准；不猜插件路径，不从本项目复制的旧版本规范取代当前包。若工具或来源不可读，如实说明具体缺口，不声称已经采用。
2. 核对实际目标账号，读取本号完整 effective 规则、已关联的项目/Skills、所选模板与用户补充要求。公众号使用 `own.production.rules.read` 全部字段分块；X 使用 `own.projects.read effective` 的完整运营配置与 skill.text。个人主题、受众、署名、文风、图片内容/风格/比例和排版来自用户与本号配置，不写入所有用户的默认。
3. 由当前 Codex 完成研究、文字、真实配图及排版。公众号最终交付必须包含真实落盘、可读取且图片可解析的完整含图 HTML 文件；保存实际路径并读取核对，纯文字、图片占位符或“已完成”声明不算 HTML 产物。图片兼容要求与 HTML 结构按当前随包同源标准处理，不另加自建配额或发表许可。X 按 X 的图文/线程与媒体规范交付，不要求先生成公众号 HTML。小红书使用标题、正文、有序图片与可选话题，不传公众号HTML；按本号有效偏好与正常创作页面约束生产。
4. 只有当前有效委托覆盖上传/入稿/发表时，才走插件现有正式通路，保留原请求/分组与未知结果；普通发表和群发区分，成功后按平台实际句柄/URL读回。不得把初始化变成已有账号发文的新门槛。
5. 新建本 Skill 不代表旧聊天自动加载。初始化后当前 Codex 应显式完整读取本文件、AGENTS维护段与当前随包规范，并报告实际读取来源/版本、HTML产物要求及尚未读取的来源。软件更新时继续解析已安装插件，不自动重写个人偏好或在途稿件。
'''.encode('utf-8')
PARTS = ('.agents', 'skills', 'openahoy-production')


def _walk(root, parts, create=False):
    fd = os.dup(root)
    try:
        for part in parts:
            if create:
                try: os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError: pass
            try:
                require(not stat.S_ISLNK(os.stat(part, dir_fd=fd, follow_symlinks=False).st_mode),
                        'PROJECT_SYMLINK_NOT_ALLOWED')
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                os.close(fd)
                return None
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(directory, name):
    if directory is None: return None
    try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError: return None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
                'PROJECT_INIT_FILE_CONFLICT')
        raw = stream.read()
        raw.decode('utf-8')
        return raw


def fingerprint(raw):
    return 'MISSING' if raw is None else sha256(raw).hexdigest()


def _root_current(root, fd):
    exact_path(str(root))
    actual, pinned = root.stat(), os.fstat(fd)
    require((actual.st_dev, actual.st_ino) == (pinned.st_dev, pinned.st_ino),
            'PROJECT_INIT_ROOT_CHANGED')


def initialize(store, project_root, expected_agents_sha256, expected_skill_sha256,
               operation_id, expected_revision):
    root = exact_path(project_root)
    require(root.is_dir() and root != root.parent, 'PROJECT_ROOT_UNAVAILABLE')
    for value in (expected_agents_sha256, expected_skill_sha256):
        require(value == 'MISSING' or re.fullmatch('[0-9a-f]{64}', value or ''), 'PROJECT_INVALID_REQUEST')
    # Check discovery conflicts and registry revision before any project write.
    state = store.view()
    pid = digest({'root': str(root)})[:32]
    existing = next((p for p in state['projects'] if p['id'] == pid), None)
    extras = existing['extra_skill_paths'] if existing else []
    entries = catalog(str(root), extras)
    target = root.joinpath(*PARTS, 'SKILL.md')
    require(not any(row['kind'] == 'skill' and row['name'] == 'openahoy-production'
                    and row['path'] != str(target) for row in entries), 'PROJECT_INIT_SKILL_CONFLICT')
    prior = store.operation(operation_id)
    if prior['state'] == 'SAVED':
        require(prior.get('project_id') == pid, 'PROJECT_OPERATION_CONFLICT')
        require(existing and existing['source_digest'] == prior.get('source_digest'),
                'PROJECT_INIT_ORIGINAL_SOURCE_CHANGED')
    else:
        require(state['revision'] == expected_revision, 'PROJECT_REVISION_CONFLICT')
    anchor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try: rootfd = _walk(anchor, root.parts[1:])
    finally: os.close(anchor)
    require(rootfd is not None, 'PROJECT_ROOT_UNAVAILABLE')
    skillfd = None
    wrote = False
    try:
        fcntl.flock(rootfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _root_current(root, rootfd)
        require(_read(rootfd, 'AGENTS.override.md') is None, 'PROJECT_INIT_OVERRIDE_CONFLICT')
        skillfd = _walk(rootfd, PARTS)
        agents, skill = _read(rootfd, 'AGENTS.md'), _read(skillfd, 'SKILL.md')
        if prior['state'] == 'SAVED':
            registered = {row['path']: row['sha256'] for row in existing['sources']}
            require(registered.get(str(root/'AGENTS.md')) == fingerprint(agents) and
                    registered.get(str(target)) == fingerprint(skill), 'PROJECT_INIT_ORIGINAL_SOURCE_CHANGED')
        else:
            require(fingerprint(agents) == expected_agents_sha256 and fingerprint(skill) == expected_skill_sha256,
                    'PROJECT_INIT_SOURCE_CHANGED')
        require(skill is None or skill == SKILL, 'PROJECT_INIT_SKILL_CONFLICT')
        body = (agents or b'').decode('utf-8')
        if BEGIN in body or END in body:
            require(body.count(BEGIN) == body.count(END) == 1 and BLOCK in body,
                    'PROJECT_INIT_MANAGED_SECTION_CONFLICT')
            addition = b''
        else:
            addition = (('\n\n' if agents else '') + BLOCK + '\n').encode('utf-8')
        if prior['state'] != 'SAVED':
            if skill is None:
                if skillfd is not None: os.close(skillfd)
                skillfd = _walk(rootfd, PARTS, create=True)
                fd = os.open('SKILL.md', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=skillfd)
                with os.fdopen(fd, 'wb') as stream:
                    wrote = True
                    stream.write(SKILL)
                    stream.flush()
                    os.fsync(stream.fileno())
            if addition:
                flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
                if agents is None: flags |= os.O_CREAT | os.O_EXCL
                fd = os.open('AGENTS.md', flags, 0o644, dir_fd=rootfd)
                try:
                    # O_APPEND preserves concurrent user additions; never truncate.
                    require(fingerprint(_read(rootfd, 'AGENTS.md')) ==
                            (fingerprint(agents) if agents is not None else fingerprint(b'')),
                            'PROJECT_INIT_SOURCE_CHANGED')
                    wrote = True
                    require(os.write(fd, addition) == len(addition), 'PROJECT_INIT_RESULT_UNKNOWN')
                    os.fsync(fd)
                finally: os.close(fd)
        agents_after, skill_after = _read(rootfd, 'AGENTS.md'), _read(skillfd, 'SKILL.md')
        require(agents_after is not None and BLOCK.encode() in agents_after and skill_after == SKILL,
                'PROJECT_INIT_RESULT_UNKNOWN')
        files = [{'path': str(root/'AGENTS.md'), 'sha256': fingerprint(agents_after)},
                 {'path': str(target), 'sha256': fingerprint(skill_after)}]
        try:
            _root_current(root, rootfd)
            result = prior if prior['state'] == 'SAVED' else store.sync(str(root), extras, operation_id, expected_revision)
            _root_current(root, rootfd)
            current = next(p for p in store.view()['projects'] if p['id'] == pid)
            registered = {row['path']: row['sha256'] for row in current['sources']}
            require(all(registered.get(row['path']) == row['sha256'] for row in files) and
                    fingerprint(_read(rootfd, 'AGENTS.md')) == files[0]['sha256'] and
                    fingerprint(_read(skillfd, 'SKILL.md')) == files[1]['sha256'],
                    'PROJECT_INIT_SOURCE_CHANGED')
        except WCEError as error:
            return {'state': 'FILES_WRITTEN_REGISTRATION_PENDING', 'error': error.code,
                    'operation_id': operation_id, 'project_root': str(root), 'files': files,
                    'current_chat_consumed': False}
        return result | {'state': 'INITIALIZED', 'project_root': str(root), 'files': files,
                         'files_changed': wrote, 'current_chat_consumed': False,
                         'personal_preferences_changed': False}
    except (OSError, UnicodeError):
        raise WCEError('PROJECT_INIT_RESULT_UNKNOWN' if wrote else 'PROJECT_INIT_FILES_UNAVAILABLE') from None
    finally:
        if skillfd is not None: os.close(skillfd)
        os.close(rootfd)
