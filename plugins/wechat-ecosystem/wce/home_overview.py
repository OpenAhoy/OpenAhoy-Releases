"""The home overview uses registered workspace records and the existing tool routes."""

from datetime import datetime, timezone
from heapq import nlargest
from math import isfinite
import re

from .contracts import WCEError

CANVAS_FIELDS = ('project_id', 'work_id', 'scene_id', 'shot_id', 'revision_id')
CANVAS_ID = re.compile(r'[a-f0-9]{32}\Z')

FEATURES = (
    ('canvas', 'jiusera-canvas', '工作画布', '把作品、场景和镜头放在同一张画布上。', '打开画布'),
    ('assets', 'jiusera-assets', '资产库', '浏览工作区中的形象、图片、音视频和文章。', '打开资产库'),
    ('studio', 'l-unify', 'L-unify IMW', '在同一工程里剪辑画面、编辑分轨和制作母带。', '进入 IMW'),
)


def introductory_cards():
    slides = ''.join(f'''
     <div class="jho-hero-copy" data-feature="{feature}"{' hidden' if index else ''}>
      <h2>{title}</h2><p>{description}</p>
      <button type="button" data-wb-route="{route}">{action}<span aria-hidden="true">↗</span></button>
     </div>''' for index, (feature, route, title, description, action) in enumerate(FEATURES))
    return f'''
    <div class="jho-first">
     <section id="wbHomeFeature" class="jho-hero" data-feature="canvas" aria-label="功能推荐">
      <div class="jho-hero-art" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
      {slides}
      <div class="jho-hero-switch">
       <button id="wbHomeFeaturePrevious" type="button" aria-label="上一项功能">‹</button>
       <button id="wbHomeFeatureNext" type="button" aria-label="下一项功能">›</button>
      </div>
     </section>
     <section class="jho-panel jho-user" aria-labelledby="wbHomeUserTitle">
      <div class="jho-user-mark" aria-hidden="true"></div>
      <div class="jho-user-copy">
       <h2 id="wbHomeUserTitle">我的 Jiusera</h2>
       <p id="wbHomeIdentity">尚未登录 Jiusera</p>
       <p class="jho-rank">级别待同步</p>
       <p id="wbHomeConnections" class="jho-note">正在读取平台账号…</p>
      </div>
      <button type="button" data-wb-route="profile">个人资料 <span aria-hidden="true">›</span></button>
     </section>
    </div>
    '''


ACTIVITY = '''
<section class="jho-panel jho-activity" aria-labelledby="wbHomeActivityTitle">
 <header class="jho-section-head">
  <h2 id="wbHomeActivityTitle">最近活动</h2>
  <button id="wbHomeActivityRetry" type="button" hidden>重新读取</button>
 </header>
 <p id="wbHomeActivityState" class="jho-note" role="status">正在读取工作区记录…</p>
 <ol id="wbHomeActivityRows" class="jho-activity-list"></ol>
</section>
'''


def video_events(director, jobs, projects, now):
    """Use only original task receipts tied to a still-readable saved revision."""
    scopes = {}
    for row in jobs.receipts():
        binding = row.get('director_binding') or {}
        stamp = row.get('created_at')
        task = row.get('provider_task_id')
        if (binding.get('kind') != 'shot' or not isinstance(task, str) or not task
                or type(stamp) not in (int, float) or not isfinite(stamp) or not 0 < stamp <= now):
            continue
        target = {key: binding.get(key) for key in CANVAS_FIELDS}
        if not all(isinstance(value, str) and CANVAS_ID.fullmatch(value) for value in target.values()):
            continue
        project_id = target['project_id']
        project = projects.get(project_id)
        if not project or row.get('request', {}).get('project_id') != project_id:
            continue
        if project_id not in scopes:
            root, pin = director.project(project_id)
            scopes[project_id] = (pin, director.load(project_id, director.storage(root, pin)))
        pin, state = scopes[project_id]
        if row.get('project_video_root') != list(pin):
            continue
        work = state['works'].get(target['work_id'])
        if not work:
            continue
        tracked = work.get('generations', {}).get(row.get('generation_attempt_id'))
        if not tracked or any(tracked.get(key) != target[key] for key in CANVAS_FIELDS[2:]):
            continue
        scene = work.get('scenes', {}).get(target['scene_id'], {})
        shot = scene.get('shots', {}).get(target['shot_id'], {})
        revision = shot.get('revisions', {}).get(target['revision_id'])
        if not revision:
            continue
        title = revision.get('title') or work['title']
        yield {'type': 'video-request', 'time': stamp, 'project_name': project['name'],
               'title': title, 'work_name': work['title'], 'scope': target}


def recent_activity(studio, director, jobs):
    """Return a compact, time-ordered projection of trusted local records."""
    now = datetime.now(timezone.utc).timestamp()
    projects = {row['id']: row for row in studio.registered()}
    partial = False

    def events():
        nonlocal partial
        for row in projects.values():
            try:
                _, _, songs = studio.project(row, include_recent=True)
            except (WCEError, OSError, ValueError, TypeError, KeyError):
                partial = True
                continue
            for song in songs:
                for version in song['versions']:
                    dates = [(version[field], kind) for field, kind in (
                        ('generatedAt', 'generated'), ('archivedAt', 'archived'))
                        if 0 < version.get(field, 0) <= now]
                    if not dates:
                        continue
                    date, kind = max(dates, key=lambda event: (event[0], event[1] == 'archived'))
                    yield {'type': kind, 'time': date, 'project': row['id'],
                           'project_name': row['name'], 'song': song['id'], 'title': song['name'],
                           'version': version['id'], 'version_name': version['name']}
        try:
            yield from video_events(director, jobs, projects, now)
        except (WCEError, OSError, ValueError, TypeError, KeyError):
            partial = True

    items = nlargest(6, events(), key=lambda item: (item['time'], item['project_name'], item['title'], item['type']))
    return {'items': items, 'partial': partial}
