import { Model } from "./model.mjs";
import { Layout } from "./layout.mjs";
// render.js — 坐标驱动渲染层(绝对定位) · 多页 A4 自动分页
// 不再自己算位置。从 Layout.compute() 拿到坐标清单,逐个绝对定位摆上去。
//
// 【多页 A4】内容超过一页高度时,自动分成多张 A4 纸:
//   · 第一页含完整谱头(标题 / 调号拍号 / 速度 / 作词作曲制谱 / 表情)。
//   · 第二页起只有谱面(无谱头),行坐标整体上移到本页顶部。
//   · 分页以"行"为单位(不切断任何一行);首页因谱头占位可容纳行数略少。
//
// 元素分层(每页各自的 .canvas 容器内,全部 position:absolute):
//   .el-num     数字本体(框只框它) —— x 居中于 item.x, y 居中于 item.y
//   .el-deco    挂件:八度点/升降/附点(共享音符 x,各自 y)
//   .el-ul      减时线(贴在音符下方,逐条按"减时级≥k")
//   .el-dash    增时线 "—"(音符右侧)
//   .el-bar     小节线/终止线(与音符共享基线 y)
//   .el-lyric   歌词字框(共享音符 x,y 在下层)
//   .el-cursor  光标

const Render = (() => {

  // 每页可容纳的行数:首页要留出谱头,故比后续页少。
  const FIRST_PAGE_ROWS = 9;   // 第一页(含谱头;谱头压缩后可多容一行)
  const OTHER_PAGE_ROWS = 10;  // 第二页起(纯谱面)
  const BAR_H = 36;

  function centerEl(cls, cx, cy) {
    const d = document.createElement('div');
    d.className = cls;
    d.style.left = cx + 'px';
    d.style.top  = cy + 'px';
    d.style.transform = 'translate(-50%, -50%)';
    return d;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  // 构建首页谱头(标题 / 调号拍号+速度 / 作词作曲制谱 / 表情)。
  function buildMeta(state) {
    const meta = document.createElement('div');
    meta.className = 'score-meta';
    const credits = [
      state.lyricist ? `作词:${escapeHtml(state.lyricist)}` : '',
      state.composer ? `作曲:${escapeHtml(state.composer)}` : '',
      state.arranger ? `制谱:${escapeHtml(state.arranger)}` : '',
    ].filter(Boolean).map(t => `<div>${t}</div>`).join('');
    meta.innerHTML = `
      <div class="score-title">${escapeHtml(state.title || '')}</div>
      <div class="score-head">
        <div class="score-head-left">
          <span class="meta-key-time">1=${escapeHtml(Model.formatKeyName(state.key))}&nbsp;&nbsp;${escapeHtml(state.time)}</span>
          ${state.tempo ? `<span class="meta-tempo">${escapeHtml(state.tempo)}</span>` : ''}
          ${state.expression ? `<span class="score-expr">${escapeHtml(state.expression)}</span>` : ''}
        </div>
        <div class="score-head-right">${credits}</div>
      </div>`;
    return meta;
  }

  // 主入口:计算坐标 → 按行分页 → 逐页渲染。
  function draw(container, notes, state) {
    container.innerHTML = '';

    const L = Layout.compute(notes, state);
    const CFG = Layout.CFG;
    const BASE_Y = CFG.BASE_Y, ROW_H = CFG.ROW_H;

    // 从 y 反推所属行号(所有主坐标都是 BASE_Y + row*ROW_H;挂件/梁/弧的偏移远小于半行,故四舍五入稳定)。
    const rowOf = (y) => Math.max(0, Math.round((y - BASE_Y) / ROW_H));

    let maxRow = 0;
    L.items.forEach(it => { if (it.y != null) maxRow = Math.max(maxRow, rowOf(it.y)); });
    const totalRows = maxRow + 1;

    // 分页计划:每页 [startRow, endRow)。
    const pages = [];
    let r = 0;
    while (r < totalRows) {
      const capRows = pages.length === 0 ? FIRST_PAGE_ROWS : OTHER_PAGE_ROWS;
      pages.push({ startRow: r, endRow: Math.min(totalRows, r + capRows) });
      r += capRows;
    }
    if (pages.length === 0) pages.push({ startRow: 0, endRow: 1 });  // 空谱也出一页

    // 预备:光标目标坐标(全局坐标,后面按页平移)。
    const cur = cursorTarget(L, notes, state);

    pages.forEach((pg, pi) => {
      const yOff = pg.startRow * ROW_H;
      const rowsOnPage = pg.endRow - pg.startRow;
      const inPage = (y) => { const rr = rowOf(y); return rr >= pg.startRow && rr < pg.endRow; };

      const page = document.createElement('div');
      page.className = 'score' + (pi > 0 ? ' score-cont' : '');
      if (pi === 0) page.appendChild(buildMeta(state));

      const canvas = document.createElement('div');
      canvas.className = 'canvas';
      canvas.style.width  = L.width + 'px';
      canvas.style.height = (rowsOnPage * ROW_H + 20) + 'px';

      // —— 音符 / 小节线 / 拍号 ——
      L.items.forEach(item => {
        if (item.y == null || !inPage(item.y)) return;
        drawItem(canvas, shiftItem(item, yOff), state);
      });

      // —— 连梁减时线 ——
      if (L.beams) {
        L.beams.forEach(b => {
          if (!inPage(b.y)) return;
          const line = document.createElement('div');
          line.className = 'el-ul';
          line.style.left  = b.x1 + 'px';
          line.style.top   = (b.y - yOff) + 'px';
          line.style.width = (b.x2 - b.x1) + 'px';
          canvas.appendChild(line);
        });
      }

      // —— 连音线 / 延音线(SVG 弧)——
      if (L.slurArcs && L.slurArcs.length) {
        const svgNS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(svgNS, 'svg');
        svg.setAttribute('class', 'slur-layer');
        svg.setAttribute('width', L.width);
        svg.setAttribute('height', rowsOnPage * ROW_H + 20);
        let any = false;
        L.slurArcs.forEach(arc => {
          if (!inPage(arc.y0) && !inPage(arc.y1)) return;   // 弧两端都不在本页则跳过
          any = true;
          const path = document.createElementNS(svgNS, 'path');
          path.setAttribute('d',
            `M ${arc.x0} ${arc.y0 - yOff} Q ${arc.cx} ${arc.cy - yOff} ${arc.x1} ${arc.y1 - yOff}`);
          path.setAttribute('class', 'slur-path');
          svg.appendChild(path);
        });
        if (any) canvas.appendChild(svg);
      }

      // —— 光标:只画在包含它的那一页 ——
      if (cur && inPage(cur.cy)) {
        const c = document.createElement('div');
        c.className = 'el-cursor';
        c.style.left = cur.cx + 'px';
        c.style.top  = (cur.cy - yOff - 16) + 'px';
        canvas.appendChild(c);
      }

      page.appendChild(canvas);

      // —— 页号:每页底部居中 ——
      const foot = document.createElement('div');
      foot.className = 'score-pageno';
      foot.textContent = (pi + 1) + ' / ' + pages.length;
      page.appendChild(foot);

      container.appendChild(page);
    });
  }

  // 把 item 的纵向坐标整体上移 dy(用于分页:本页第一行移到页顶)。
  // 挂件 decos 的 dy 是相对偏移、dashXs 只含 x,均不受影响。
  function shiftItem(item, dy) {
    if (!dy) return item;
    const out = Object.assign({}, item);
    if (out.y != null) out.y -= dy;
    if (out.lyricY != null) out.lyricY -= dy;
    return out;
  }

  // 渲染单个 item(音符 / 休止 / 小节线 / 拍号)。
  function drawItem(canvas, item, state) {
    if (item.type === 'barline') { drawBarline(canvas, item); return; }

    // —— 行首小节号:标在行首左线左侧上方(每行只显示该行第一小节的编号)——
    if (item.type === 'rownum') {
      const rn = document.createElement('div');
      rn.className = 'el-rownum';
      rn.textContent = String(item.barNo);
      rn.style.left = (item.x - 4) + 'px';           // 贴左线左侧
      rn.style.top  = (item.y - Layout.CFG.ROW_H / 2) + 'px';  // 抬到该行上方
      canvas.appendChild(rn);
      return;
    }

    // —— 谱中拍号标记:分子/分母竖排的分数形式(如 3/4)——
    if (item.type === 'timesig') {
      const m = /^(\d+)\s*\/\s*(\d+)$/.exec(item.time || '4/4');
      const numer = m ? m[1] : '4';
      const denom = m ? m[2] : '4';
      const ts = centerEl('el-timesig', item.x, item.y);
      ts.innerHTML = `<span class="ts-num">${numer}</span><span class="ts-den">${denom}</span>`;
      canvas.appendChild(ts);
      return;
    }

    // —— 数字本体 ——
    const isSel = !item.filler && state.selected === item.index;
    const num = centerEl('el-num' + (isSel ? ' selected' : '') + (item.filler ? ' filler' : ''), item.x, item.y);
    if (!item.filler) num.dataset.index = item.index;
    if (item.filler && item.insertAt != null) num.dataset.insertAt = item.insertAt;
    num.style.fontSize = Layout.CFG.NOTE_FS + 'px';
    num.style.width  = Layout.CFG.NOTE_W + 'px';
    num.style.height = (Layout.CFG.NOTE_FS + 6) + 'px';
    num.textContent = item.type === 'rest' ? '0' : String(item.note.degree);
    canvas.appendChild(num);

    // —— 挂件(共享 item.x)——
    item.decos.forEach(dc => {
      if (dc.kind === 'octdot') {
        const dot = centerEl('el-octdot', item.x + dc.dx, item.y + dc.dy);
        const d = Layout.CFG.OCT_DOT_R * 2;
        dot.style.width  = d + 'px';
        dot.style.height = d + 'px';
        canvas.appendChild(dot);
      } else if (dc.kind === 'acc') {
        const a = centerEl('el-acc', item.x + dc.dx, item.y + dc.dy);
        a.textContent = dc.text;
        canvas.appendChild(a);
      } else if (dc.kind === 'augdot') {
        const a = centerEl('el-augdot', item.x + dc.dx, item.y + dc.dy);
        a.textContent = '·';
        canvas.appendChild(a);
      }
    });

    // —— 减时线(未分组的孤立音符自己画;分组的由 L.beams 统一画)——
    if (item.underlines > 0 && item.beamId == null) {
      for (let k = 1; k <= item.underlines; k++) {
        const ulY = item.y + Layout.CFG.UL_FIRST_DY + (k - 1) * Layout.CFG.UL_GAP;
        const line = document.createElement('div');
        line.className = 'el-ul';
        line.style.left = (item.x - Layout.CFG.NOTE_W / 2 + 3) + 'px';
        line.style.top  = ulY + 'px';
        line.style.width = (Layout.CFG.NOTE_W - 6) + 'px';
        canvas.appendChild(line);
      }
    }

    // —— 增时线 "—"(音符右侧,共享基线 y)——
    if (item.dashes > 0 && item.dashXs) {
      for (const dx of item.dashXs) {
        const dash = centerEl('el-dash', dx, item.y);
        dash.textContent = '—';
        canvas.appendChild(dash);
      }
    }

    // —— 歌词(共享 item.x,y 在下层;编辑态换成真实 input)——
    if (!item.filler) {
      if (state.lyricEdit === item.index) {
        const inp = document.createElement('input');
        inp.className = 'el-lyric-input';
        inp.dataset.lyricIndex = item.index;
        inp.value = item.lyric || '';
        inp.style.left = item.x + 'px';
        inp.style.top  = item.lyricY + 'px';
        inp.style.fontSize = Layout.CFG.LYRIC_FS + 'px';
        inp.style.height = (Layout.CFG.LYRIC_FS + 8) + 'px';
        canvas.appendChild(inp);
      } else {
        const ly = centerEl('el-lyric' + (item.lyric ? '' : ' empty'), item.x, item.lyricY);
        ly.dataset.lyricIndex = item.index;
        ly.style.fontSize = Layout.CFG.LYRIC_FS + 'px';
        ly.style.width  = (Layout.CFG.LYRIC_FS + 6) + 'px';
        ly.style.height = (Layout.CFG.LYRIC_FS + 8) + 'px';
        ly.textContent = item.lyric || '词';
        canvas.appendChild(ly);
      }
    }
  }

  // —— 小节线:按子类型画普通线 / 终止线 / 反复开始 / 反复结束 ——
  function drawBarline(canvas, item) {
    const sub = item.subtype || 'normal';
    const baseCls = item.edge ? 'el-bar edge' : ('el-bar' + (item.manual ? '' : ' auto'));

    function stroke(kind, dx) {
      const bar = centerEl(baseCls + (kind === 'thick' ? ' thick' : ''), item.x + dx, item.y);
      bar.style.height = BAR_H + 'px';
      if (item.index != null) bar.dataset.index = item.index;
      canvas.appendChild(bar);
    }
    function dots(dx) {
      [-5, 5].forEach(dy => {
        const d = centerEl('el-repeat-dot', item.x + dx, item.y + dy);
        canvas.appendChild(d);
      });
    }

    if (sub === 'final') {
      stroke('thin', -3);
      stroke('thick', 1);
    } else if (sub === 'repeatStart') {
      stroke('thick', -3);
      stroke('thin', 1);
      dots(6);
    } else if (sub === 'repeatEnd') {
      dots(-6);
      stroke('thin', -1);
      stroke('thick', 3);
    } else {
      stroke('thin', 0);
    }
  }

  // 计算光标目标(全局坐标 cx, cy);draw() 再按页平移。cursor 指"第几个元素之前"。
  function cursorTarget(L, notes, state) {
    let cx, cy;
    if (state.cursor >= notes.length) {
      const last = [...L.items].reverse().find(it => it.x != null);
      if (last) {
        cx = last.x + (last.w || 24);
        cy = last.y;
        const rightEdge = Layout.CFG.PAGE_W - Layout.CFG.MARGIN_X;
        if (cx > rightEdge - 4) {
          cx = Layout.CFG.MARGIN_X + Layout.CFG.FIRST_LAST_DX;
          cy = last.y + Layout.CFG.ROW_H;
        }
      }
    } else {
      const target = L.items.find(it => it.index === state.cursor);
      if (target) { cx = target.x - (target.w || 24) / 2 - 4; cy = target.y; }
    }
    if (cx == null) { cx = Layout.CFG.MARGIN_X; cy = Layout.CFG.BASE_Y; }
    return { cx, cy };
  }

  return { draw };
})();

export { Render };
