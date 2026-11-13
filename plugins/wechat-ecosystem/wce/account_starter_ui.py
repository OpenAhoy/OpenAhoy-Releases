"""Shared account starter suggestions for the existing WeChat and X editors."""
import json

from .management_locale import FALLBACK


TOPICS = {
    'AI 与科技': ('AI 工具、实际应用、重要技术进展', 'AI 爱好者、入门用户、使用 AI 的创作者', '工具教程、新闻解读、产品体验'),
    '知识与教学': ('基础概念、实用方法、常见问题', '初学者、自学者、希望解决实际问题的读者', '分步教程、案例拆解、常见问答'),
    '行业观察': ('行业变化、公开数据、代表性案例', '业内从业者、决策者、关注行业的读者', '趋势解读、案例分析、有依据的观点'),
    '音乐与艺术': ('创作过程、作品赏析、工具与技法', '创作者、音乐与艺术爱好者、学习者', '作品展示、过程记录、技巧分享'),
    '生活观察': ('日常体验、城市生活、兴趣与发现', '对生活方式感兴趣的读者、同好', '真实体验、生活随笔、实用建议'),
    '个人创作': ('正在做的项目、创作笔记、阶段性发现', '同行创作者、同好、对项目感兴趣的读者', '作品进展、经验复盘、交流讨论'),
    '品牌与产品': ('产品用途、使用场景、常见问题', '潜在用户、现有用户、合作伙伴', '场景演示、功能说明、产品动态'),
}
VOICES = ('通俗清楚', '耐心具体', '专业克制', '具象有画面', '自然口语', '真诚直接', '清晰务实')
PURPOSES = ('分享知识', '帮助读者上手', '解释变化与影响', '展示作品', '交流生活体验', '与同行交流', '帮助用户了解产品')
IMAGES = ('真实资料', '步骤截图或示意图', '图表与信息图', '作品原图或原创插画', '摄影或原创插画', '创作过程图', '真实产品图或场景示意图')
FACTS = '核对关键事实与出处，区分转述、观点和真实体验。'
IMAGE_QUALITY = '按内容选择图片，核对图文一致性；概念图不冒充实拍或实测。'

GROUPS = {
    '主题': ('AI 工具', '科技趋势', '行业动态', '实用知识', '音乐与艺术', '生活观察', '个人项目', '品牌与产品'),
    '读者': ('入门用户', '兴趣爱好者', '创作者', '专业从业者', '决策者', '潜在用户', '现有用户'),
    '内容形式': ('教程', '资讯解读', '测评', '观点', '案例', '作品展示', '问答', '创作笔记'),
    '表达': (*VOICES, '故事叙述'),
    '目标': PURPOSES,
    '配图': (*IMAGES, '按内容决定', '纯文字优先'),
    '版式': ('简洁清晰', '留白舒展', '清晰的小标题', '优先手机阅读'),
    '语言': ('简体中文', '繁體中文', 'English'),
}


def suggestion_lines(label, text):
    return '\n'.join(f'{label}：{part}' for part in text.split('、'))


def starter_options():
    options = []
    for i, (name, (topics, readers, forms)) in enumerate(TOPICS.items()):
        voice, purpose, image = VOICES[i], PURPOSES[i], IMAGES[i]
        options.append({
            'name': name, 'description': forms, 'readers': readers,
            'wechat': {
                'audience_topics': '\n'.join((suggestion_lines('主题', topics), suggestion_lines('读者', readers),
                                               suggestion_lines('内容形式', forms), f'目标：{purpose}')),
                'voice': f'表达：{voice}\n按读者熟悉程度解释术语，用具体例子说明重点。',
                'image_preferences': f'配图：{image}\n{IMAGE_QUALITY}',
                'visual_layout': '版式：简洁清晰\n用小标题分段，优先照顾手机阅读。',
                'content_qa': FACTS + ' 检查图文一致性。',
                'delivery_publication': '交付完整含图 HTML，发表按本次委托处理。',
            },
            'x': {
                'positioning.topics': suggestion_lines('主题', topics),
                'positioning.readers': suggestion_lines('读者', readers),
                'positioning.allowed': suggestion_lines('内容形式', forms), 'positioning.voice': f'表达：{voice}',
                'positioning.language': '简体中文', 'positioning.facts': FACTS,
                'growth.reason': f'目标：{purpose}',
                'growth.cta': '合适时邀请读者分享实际体验或提出问题。',
                'images.subject': f'配图：{image}', 'images.style': IMAGE_QUALITY,
            },
        })
    return options


def entry(prefix):
    return f'<section id="{prefix}Starter" class="oa-starter" aria-label="账号起步方案" hidden></section>'


STYLE = """
.oa-starter{margin:0 0 16px;padding:2px 3px 12px;border-bottom:1px solid var(--line)}
.oa-starter details,.oa-choice-editor details{margin:0}
.oa-starter summary,.oa-choice-editor summary{font-weight:600;color:var(--ink)}
.oa-starter-options{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,155px),1fr));gap:8px;margin:9px 0}
.oa-management .oa-starter-options button{display:grid;text-align:left;justify-content:stretch;white-space:normal;padding:8px 10px;gap:2px}
.oa-starter-options button span,.oa-choice-current{font-size:12px;color:var(--muted)}
.oa-management .oa-starter-options button[aria-pressed=true],.oa-management .oa-choice-picks button[aria-pressed=true]{border-color:var(--accent);background:var(--tint)}
.oa-starter-controls,.oa-choice-picks{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:6px 0}
.oa-management .oa-starter-controls label{display:flex;align-items:center;gap:4px;margin:0}
.oa-management .oa-choice-picks button{min-height:30px;padding:4px 8px;font-size:12px;white-space:normal}
.oa-choice-editor{display:grid;gap:7px;margin-top:8px}
.oa-choice-group{font-size:12px;color:var(--muted);margin:0}
.oa-choice-current{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;max-height:9em;overflow:auto}
.oa-choice-custom-value{min-width:0;padding:8px 10px;border-radius:8px;background:var(--oa-fill,var(--soft));color:var(--ink)}
.oa-choice-custom-value strong{display:block;font-size:12px;margin-bottom:3px}
"""


SCRIPT = FALLBACK + r'''
globalThis.OAAccountStarter = (() => {
  const ui = globalThis.OAUI || globalThis.OAPlainUI;
  const options = __OPTIONS__;
  const groups = __GROUPS__;
  const choiceTones = {'读者':'violet', '表达':'violet', '配图':'teal', '版式':'teal', '目标':'amber'};
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  function mount(root, platform, {read, write, empty, onChange}) {
    const picker = document.createElement('details');
    const heading = document.createElement('summary');
    ui.set(heading, '选择账号方案');
    const cards = document.createElement('div');
    cards.className = 'oa-starter-options';
    const controls = document.createElement('div');
    controls.className = 'oa-starter-controls';
    const replaceLabel = document.createElement('label');
    const replace = document.createElement('input');
    replace.type = 'checkbox';
    replaceLabel.append(replace, ui.label('替换方案涉及的内容偏好'));
    const undo = document.createElement('button');
    undo.type = 'button';
    ui.set(undo, '撤销方案填写');
    const status = document.createElement('p');
    status.className = 'help';
    status.setAttribute('role', 'status');
    const feedback = document.createElement('div');
    feedback.className = 'oa-starter-controls';
    controls.append(replaceLabel);
    feedback.append(status, undo);
    picker.append(heading, cards, controls);
    root.append(picker, feedback);

    // Only the fields changed by the last scheme are kept for undo.
    // The existing editor remains the sole owner of the complete draft.
    const history = new Map();
    let account = '';
    let locked = true;
    let announcement = '';
    const keys = Object.keys(options[0][platform]);
    function restore() {
      const previous = history.get(account);
      if (!previous) return false;
      let restored = false;
      for (const [key, {before, after}] of previous.changes) {
        const current = read(key);
        if (same(current, after)) {
          write(key, before);
          restored = true;
          continue;
        }
        const currentText = typeof current === 'string' ? current : current.text;
        const afterText = typeof after === 'string' ? after : after.text;
        // Remove only exact generated lines, retaining any later edits or additions.
        if (current.inherit !== after.inherit) continue;
        const generated = new Set(afterText.split('\n'));
        const lines = currentText.split('\n');
        const additions = lines.filter(line => !generated.has(line));
        if (additions.length === lines.length) continue;
        if (!additions.some(line => line.trim())) {
          write(key, before);
          restored = true;
          continue;
        }
        const beforeText = typeof before === 'string' ? before : before.text;
        const text = [beforeText, additions.join('\n')].filter(Boolean).join('\n');
        write(key, typeof current === 'string' ? text : {...current, text});
        restored = true;
      }
      history.delete(account);
      return restored;
    }

    const buttons = options.map(option => {
      const button = document.createElement('button');
      button.type = 'button';
      const name = document.createElement('strong');
      ui.set(name, option.name);
      const description = document.createElement('span');
      ui.set(description, option.description);
      const readers = document.createElement('span');
      ui.set(readers, option.readers);
      button.append(name, description, readers);
      button.onclick = () => {
        if (locked || !account) return;
        const restored = restore();
        announcement = '';
        const changes = new Map();
        for (const [key, suggestion] of Object.entries(option[platform])) {
          const before = read(key);
          if (!replace.checked && !empty(key, before)) continue;
          const after = typeof before === 'string' ? suggestion : {text: suggestion, inherit: false};
          if (same(before, after)) continue;
          write(key, after);
          changes.set(key, {before, after});
        }
        if (changes.size) history.set(account, {name: option.name, changes});
        replace.checked = false;
        announcement = changes.size ? '方案已填入当前账号草稿，保存后生效。' :
          '已有内容已保留。可在各分类里点选细化。';
        if (restored || changes.size) onChange();
        update(account, locked);
        if (changes.size) picker.open = false;
      };
      cards.append(button);
      return button;
    });
    undo.onclick = () => {
      if (locked || !account) return;
      const restored = restore();
      announcement = '已撤销方案填写。之后单独修改过的内容已保留。';
      if (restored) onChange();
      update(account, locked);
      if (keys.every(key => empty(key, read(key)))) picker.open = true;
    };

    function update(id, disabled) {
      const switched = account !== id;
      account = id;
      locked = disabled;
      root.hidden = !id;
      if (!id) return;
      const previous = history.get(id);
      const allEmpty = keys.every(key => empty(key, read(key)));
      if (switched) {
        replace.checked = false;
        announcement = '';
        picker.open = allEmpty;
      }
      ui.set(heading, previous ? '已填写 · {0}' : '选择账号方案', ui.message(previous?.name || ''));
      replaceLabel.hidden = allEmpty;
      replace.disabled = locked;
      undo.hidden = !previous;
      undo.disabled = locked;
      ui.set(status, announcement || (previous ? '方案已填入当前账号草稿，保存后生效。' : '默认补齐空项。'));
      status.hidden = !announcement && !previous && !picker.open;
      buttons.forEach((button, i) => {
        button.disabled = locked;
        button.setAttribute('aria-pressed', String(previous?.name === options[i].name));
      });
    }
    picker.addEventListener('toggle', () => update(account, locked));
    return {update, forget(id) {
      history.delete(id);
      if (account === id) announcement = '';
    }};
  }

  function choices(input, labels, {canEdit, beforeEdit, commit, read = () => input.value}) {
    const root = document.createElement('div');
    root.className = 'oa-choice-editor';
    const current = document.createElement('p');
    current.className = 'oa-choice-current';
    const customValue = document.createElement('div');
    customValue.className = 'oa-choice-custom-value';
    const customLabel = document.createElement('strong');
    ui.set(customLabel, '当前自定义文字');
    customValue.append(customLabel, current);
    const custom = document.createElement('details');
    const heading = document.createElement('summary');
    ui.set(heading, '自定义文字');
    custom.append(heading, input);
    const buttons = [];
    for (const label of labels) {
      const group = document.createElement('div');
      group.setAttribute('role', 'group');
      group.dataset.choiceTone = choiceTones[label] || 'blue';
      ui.attr(group, 'aria-label', label);
      const caption = document.createElement('p');
      caption.className = 'oa-choice-group';
      ui.set(caption, label);
      const picks = document.createElement('div');
      picks.className = 'oa-choice-picks';
      const prefix = label + '：';
      const recommended = options.flatMap(option => Object.values(option.wechat))
        .flatMap(text => text.split('\n')).filter(line => line.startsWith(prefix))
        .map(line => line.slice(prefix.length));
      const extra = document.createElement('details');
      const more = document.createElement('summary');
      ui.set(more, '更多{0}', ui.message(label));
      const morePicks = document.createElement('div');
      morePicks.className = 'oa-choice-picks';
      extra.append(more, morePicks);
      const values = [...new Set([...groups[label], ...recommended])];
      for (const value of values) {
        const text = label + '：' + value;
        const button = document.createElement('button');
        button.type = 'button';
        ui.set(button, value);
        const uncommon = !groups[label].includes(value);
        const option = {button, label, value, single: label === '语言', uncommon, picks, morePicks};
        button.onclick = () => {
          if (!canEdit()) return;
          beforeEdit?.();
          const rows = selection(input.value);
          const active = rows.some(row => row.options.includes(option));
          if (option.single) input.value = active ? '' : value;
          else if (active) {
            input.value = rows.flatMap(row => {
              if (!row.options.includes(option)) return [row.raw];
              const remaining = row.options.filter(item => item !== option);
              return remaining.length ? [row.prefix + remaining.map(item => item.value).join(row.separator)] : [];
            }).join('\n');
          } else input.value += (input.value && !input.value.endsWith('\n') ? '\n' : '') + text;
          commit();
          refresh();
        };
        buttons.push(option);
        (uncommon ? morePicks : picks).append(button);
      }
      group.append(caption, picks);
      if (morePicks.children.length) group.append(extra);
      root.append(group);
    }
    root.append(customValue, custom);
    function selection(text) {
      // Resolve only exact values. A bare value shared by multiple groups, or
      // a list with an unknown entry, remains custom instead of guessing.
      return text.split('\n').map(raw => {
        const line = raw.trim();
        const tagged = line.match(/^([^:：]+?)\s*[:：]\s*(.*)$/);
        const body = tagged ? tagged[2] : line;
        const candidates = tagged ? buttons.filter(item => item.label === tagged[1].trim()) : buttons;
        const exact = value => candidates.filter(item => item.value === value);
        const matches = exact(body);
        const separator = body.match(/[、,，]/)?.[0];
        let options = matches.length === 1 ? matches : [];
        if (options[0]?.single && text.trim() !== line) options = [];
        if (!matches.length && separator && !candidates.some(item => item.single)) {
          const parts = body.split(/[、,，]/).map(part => exact(part.trim()));
          if (parts.every(part => part.length === 1) && new Set(parts.flat().map(item => item.label)).size === 1) options = parts.flat();
        }
        return {raw, options, prefix: tagged ? line.slice(0, line.length - body.length) : '', separator};
      });
    }
    function refresh() {
      const value = read();
      const rows = selection(value);
      const selected = new Set(rows.flatMap(row => row.options));
      for (const option of buttons) {
        const {button, uncommon, picks, morePicks} = option;
        const active = selected.has(option);
        button.disabled = !canEdit();
        button.setAttribute('aria-pressed', String(active));
        if (uncommon) {
          const target = active ? picks : morePicks;
          if (button.parentNode !== target && document.activeElement !== button) target.append(button);
        }
      }
      const customText = rows.filter(row => !row.options.length).map(row => row.raw).join('\n');
      customValue.hidden = !customText.trim();
      current.textContent = customText;
    }
    input.addEventListener('input', refresh);
    refresh();
    return {root, refresh};
  }

  return {mount, choices};
})();
'''.replace('__OPTIONS__', json.dumps(starter_options(), ensure_ascii=False)).replace(
    '__GROUPS__', json.dumps(GROUPS, ensure_ascii=False))
