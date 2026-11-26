import { Model } from "./model.mjs";
// layout.js — 坐标布局引擎(地基) · 两层定位
// 职责:输入 notes + state,输出一份"坐标清单"。渲染层只照坐标摆,不算位置。
//
// 【两层定位】(正规打谱排版法)
//   外层:A4 可用宽度 = PAGE_W − 左右相等边距,平均切成 BARS_PER_ROW 个"等宽小节格"。
//        每格 x 坐标定死 → 左右边距天生相等、每行右边永远对齐。
//   内层:每个小节格里,按本小节音符数量,把音符在格内均匀铺开(并为格内小节线留位)。
//
// 四套坐标轨道(每个元素都带自己的 {x,y}):
//   ① 音符 x 由"格内分布"决定; y = 基线 BASE_Y。
//   ② 小节线 与音符共享 Y(同一行); x = 格右边界。
//   ③ 歌词   与所属音符共享 X; y 在下层 LYRIC_Y。
//   ④ 符号(八度点/升降/附点) 与音符共享 X; y 各自纵向堆叠(点锚定点)。

const Layout = (() => {

  // ===== 基准尺寸常量(微调按钮 / 单元素 offset 都落到这里)=====
  const CFG = {
    PAGE_W:        740,  // A4 谱面可用总宽(对应 .score 内容宽,随排版收窄字号)
    MARGIN_X:      28,   // 左右边距(强制相等)
    BASE_Y:        40,   // 音符数字中心所在的基线 y
    ROW_H:         96,   // 行高(下一行整体下移多少)
    BARS_PER_ROW:  4,    // 每行固定小节数 → 也是每行的等分格数

    NOTE_FS:       16,   // 音符数字字号(←19→16,整体缩小)
    NOTE_W:        17,   // 一个音符"数字框"的标称宽度(←20)
    CELL_PAD:      8,    // 小节格内左右内缩
    MIN_NOTE_GAP:  15,   // 格内相邻音符中心的最小间距(←18)
    FIRST_LAST_DX: 16,   // 铁律:首/末"单元"离小节线的固定距离(左右相等、恒定不变)
    TIMESIG_W:     20,   // 小节显示拍号时,左侧为拍号预留的额外宽度
    NEED_PER_NOTE: 14,   // 每个音符大致需要的"身体宽度"(←17)
    CELL_W_MIN:    44,   // 单格最小宽度(←52)
    CELL_W_MAX:    240,  // 单格最大宽度(←260)

    OCT_DOT_R:     1.3,  // 八度点半径(←1.6)
    OCT_GAP_1:      9,   // 第一个八度点离数字中心的距离(←11)
    OCT_GAP_N:      5,   // 后续八度点之间的距离(←6)
    ACC_DX:        -9,   // 升降号相对数字中心的 x 偏移(←-11)
    ACC_DY:        -7,   // 升降号相对数字中心的 y 偏移(←-8)

    DASH_GAP:      5,    // 增时线之间的水平间距(←7)
    DASH_DX:      28,    // 第一条增时线离音符中心的偏移(≈NOTE_W*1.65,让增时线居中于音符间的空间中)

    UL_GAP:        3,    // 减时线之间的垂直间距(保持)
    UL_FIRST_DY:   12,   // 第一条减时线离基线的垂直距离(←14)
    BEAM_INSET:    3,    // 连梁端点向内收(保持)
    BEAM_GAP_MIN:  5,    // 相邻梁段最小空隙(←6)
    DOT_AUG_DX:    10,   // 附点离数字中心的 x 偏移(←12)

    LYRIC_FS:      11,   // 歌词字号(←13)
    LYRIC_DY:      28,   // 歌词中心相对音符基线向下的距离(←34)

    SLUR_DY:      -16,   // 弧线顶点相对音符基线向上的距离(负=在上方)
    SLUR_END_DY:  -11,   // 弧线两端离音符基线的向上距离(端点比顶点低,形成拱形)
    SLUR_PAD_X:     4,   // 弧线端点相对首/末音符中心向内(外)的水平微调
    SLUR_ROW_EXT:  30,   // 跨行弧线:前半段延伸到行右、后半段从行左起的水平长度

    // 挂件字符半宽估算(用于防溢出小节线):
    DASH_CHAR_HW:   5,   // "—" 字宽≈10px → 半宽≈5
    AUG_CHAR_HW:    4,   // "·" 字宽≈8px  → 半宽≈4
    ACC_CHAR_HW:    6,   // "♯" 字宽≈12px → 半宽≈6(←ACC_FS=12)
  };

  // 计算一个音符所有"挂件"(八度点/升降/附点)的相对坐标
  function decorations(note) {
    const decos = [];
    if (note.octave > 0) {
      for (let i = 0; i < note.octave; i++)
        decos.push({ kind: 'octdot', dx: 0, dy: -(CFG.OCT_GAP_1 + i * CFG.OCT_GAP_N) });
    } else if (note.octave < 0) {
      for (let i = 0; i < -note.octave; i++)
        decos.push({ kind: 'octdot', dx: 0, dy: (CFG.OCT_GAP_1 + i * CFG.OCT_GAP_N) });
    }
    if (note.accidental === 'sharp')   decos.push({ kind: 'acc', text: '♯', dx: CFG.ACC_DX, dy: CFG.ACC_DY });
    if (note.accidental === 'flat')    decos.push({ kind: 'acc', text: '♭', dx: CFG.ACC_DX, dy: CFG.ACC_DY });
    if (note.accidental === 'natural') decos.push({ kind: 'acc', text: '♮', dx: CFG.ACC_DX, dy: CFG.ACC_DY });
    if (note.dots >= 1) decos.push({ kind: 'augdot', dx: CFG.DOT_AUG_DX, dy: 2 });
    if (note.dots >= 2) decos.push({ kind: 'augdot', dx: CFG.DOT_AUG_DX + 6, dy: 2 });
    return decos;
  }

  // ===== 第一步:把音符流切成"小节"数组 =====
  // 每个小节 = { notes:[{note,index,filler?}], manualBar:bool }
  // 满拍自动断 / 遇到手动 barline 也断。不足拍 → 自动补休止符(只读占位)。
  //
  // 用标准时值休止符填补一个小节剩余的拍数(贪心:从大到小)
  function fillRests(bar, remBeats, insertAt) {
    if (remBeats <= 1e-6) return;
    // 简谱习惯:休止符以"拍"为单位逐个写 0(半拍=带减时线的 0)。
    // 因此补拍单位最大只到 1 拍(四分休=纯"0"),不用二分/全休的"0—"写法。
    const STD = [[1, 4], [0.5, 8], [0.25, 16], [0.125, 32]];  // [拍数, dur]
    let rem = remBeats;
    let guard = 0;
    while (rem > 1e-6 && guard++ < 64) {
      const pick = STD.find(([b]) => b <= rem + 1e-6);
      if (!pick) break;
      bar.notes.push({
        note: { type: 'rest', degree: 0, octave: 0, accidental: '', dur: pick[1], dots: 0, lyric: '' },
        index: null,
        filler: true,            // 合成占位休止符:淡色、不可选、用户输入会自动顶掉
        insertAt: insertAt,      // 点击该 0 时,光标定位到 state.notes 的这个数组位置(在此输入即顶替)
      });
      rem -= pick[0];
    }
  }

  function splitBars(notes, cap0) {
    const bars = [];
    let cap = cap0;                  // 当前生效拍号容量(可被谱中 timesig 标记切换)
    // 下一个新起小节要显示的拍号(谱首 or 变拍号处):初始为谱首拍号。
    let pendingTimeSig = null;
    let cur = { notes: [], manualBar: false, rightBar: 'normal', leftBar: null, cap, showTimeSig: null };
    let acc = 0;
    // 本小节末尾"下一个音符该插入 state.notes 的位置":= 本小节最后一个真实音符 index+1,
    // 若本小节尚无真实音符,则沿用上次记录的位置(点空节的 0 时光标落这里)。
    let barInsertAt = 0;
    function closeBar(manual, rightSub) {
      // MusicXML 会在每个 measure 后给出显式小节线。如果前一个音符
      // 已经恰好填满小节，自动断句已经将它推入 bars，此时的显式线
      // 只是确认边界，不能再生成一个全休止空小节。
      if (cur.notes.length === 0 && acc <= 1e-6) {
        const previous = bars[bars.length - 1];
        if (previous) {
          previous.manualBar = previous.manualBar || !!manual;
          if (rightSub && rightSub !== 'normal') previous.rightBar = rightSub;
        }
        return false;
      }
      fillRests(cur, cap - acc, barInsertAt);   // 自动适配:忘了几拍就补几拍(按本小节生效的 cap)
      cur.manualBar = manual;
      if (rightSub) cur.rightBar = rightSub;
      bars.push(cur);
      cur = { notes: [], manualBar: false, rightBar: 'normal', leftBar: null, cap, showTimeSig: null };
      acc = 0;
      return true;
    }
    notes.forEach((note, index) => {
      if (note.type === 'timesig') {
        // 谱中变拍号:先把当前小节封口(补足残拍),再切换 cap,
        // 并让紧随其后的新起小节显示新拍号。
        if (cur.notes.length > 0) closeBar(false);
        cap = Model.barCapacity(note.time);
        cur.cap = cap;
        cur.showTimeSig = note.time;   // 新起小节标注该拍号
        return;
      }
      if (note.type === 'barline') {
        const sub = note.subtype || 'normal';
        if (sub === 'repeatStart') {
          // 反复开始记号标在"下一小节"的左侧:若当前小节已有内容,先以普通线封口,
          // 再把 repeatStart 挂到新起小节的左边界。
          if (cur.notes.length > 0) closeBar(true, 'normal');
          cur.leftBar = 'repeatStart';
        } else {
          // 普通线 / 终止线 / 反复结束:都作用于当前小节的右边界。
          closeBar(true, sub);
        }
        return;
      }
      const nb = Model.beats(note);
      // 自动适配·防超拍:若把该音符放进本小节会超过容量,且本小节已有内容,
      // 先把本小节"封口"(补足它欠缺的残拍),让这个音符落到下一小节的开头。
      // 这样任何一个封口的小节都恰好 = cap 拍,绝不超拍。
      // (单个音符自身就超过 cap 的极端情形——如 3/4 里写全音符——无法在不引入
      //  连音线的前提下拆分,只能让它独占一个略微超宽的小节,属可接受的罕见边界。)
      if (acc > 1e-6 && acc + nb > cap + 1e-6) {
        closeBar(false);
      }
      cur.notes.push({ note, index });
      barInsertAt = index + 1;         // 该真实音符之后 → 下个音符插到这里
      acc += nb;
      if (acc >= cap - 1e-6) closeBar(false);
    });
    if (cur.notes.length > 0) closeBar(false);
    return bars;
  }

  // 一个小节占多少"单元":每个音符1个单元,其后每条增时线各占1个单元。
  function barUnitCount(bar) {
    let u = 0;
    bar.notes.forEach(bn => { u += 1 + Model.dashes(bn.note.dur); });
    return Math.max(1, u);
  }

  // ===== 第二步:在一个"小节格"内,给音符 + 增时线分配 x(单元均分模型)=====
  // 铁律:首单元贴左固定距离 FIRST_LAST_DX,末单元贴右固定距离(左右相等);
  //       中间所有单元在两者之间严格平均分。
  // 增时线是音符右侧的独立单元 → 天生排在音符右边,不会跑到左侧。
  function distributeInCell(barNotes, cellLeft, cellRight, leftInset) {
    const n = barNotes.length;
    if (n === 0) return { noteX: [], dashX: [] };

    // 构建单元序列:[音符, (该音符的增时线…), 音符, …]
    const units = [];
    barNotes.forEach((bn, k) => {
      units.push({ k, isDash: false });
      const d = Model.dashes(bn.note.dur);
      for (let j = 0; j < d; j++) units.push({ k, isDash: true });
    });
    const U = units.length;

    // 首/末单元中心到小节线的距离恒定;FIRST_LAST_DX 已覆盖升降号/附点的横向延伸。
    // leftInset:小节左侧需为拍号等预留的额外宽度(把首单元再往右推)。
    const innerL = cellLeft + CFG.FIRST_LAST_DX + (leftInset || 0);
    const innerR = cellRight - CFG.FIRST_LAST_DX;

    const centers = [];
    if (U === 1) {
      centers.push((innerL + cellRight - CFG.FIRST_LAST_DX) / 2);   // 单元独占 → 在可用区居中(含左预留)
    } else {
      const step = (innerR - innerL) / (U - 1);
      for (let i = 0; i < U; i++) centers.push(innerL + i * step);
    }

    const noteX = new Array(n).fill(0);
    const dashX = barNotes.map(() => []);
    units.forEach((u, i) => {
      if (u.isDash) dashX[u.k].push(centers[i]);
      else noteX[u.k] = centers[i];
    });
    return { noteX, dashX };
  }

  // 主函数:返回 { items, width, height, cfg }
  function compute(notes, state) {
    const items = [];
    const cap = Model.barCapacity(state.time);
    const bars = splitBars(notes, cap);
    // 首小节始终标注谱首拍号(除非它自身已被谱中变拍号覆盖)。
    if (bars.length > 0 && !bars[0].showTimeSig) bars[0].showTimeSig = state.time;

    const usableW = CFG.PAGE_W - CFG.MARGIN_X * 2;
    const FULL = CFG.BARS_PER_ROW;

    // ===== 弹性格宽(两条铁律)=====
    //  铁律A:每个"满行"(恰好 FULL 个小节)的内容总宽 ≡ usableW。
    //         → 左边距 = MARGIN_X(定值),右边距 = PAGE_W − MARGIN_X − usableW = MARGIN_X。
    //         → 所有满行的左右边距完全相等、行行统一。这点与"行内各格不等宽"互不矛盾:
    //           格宽按音符数自适配,但一行四格之和被强制缩放到 usableW。
    //  铁律B:行内永远最多 FULL 个小节,但四格宽度按音符多少自动分配(本函数职责)。
    //  残行(最后一行不足 FULL 个小节):不拉满,沿用"满行的单格平均基准",左对齐、右留白。
    function rowCellWidths(rowBars, isFullRow) {
      const need = rowBars.map(b => {
        // 需求宽按"单元数"(音符 + 增时线)算 → 增时线多的小节自动更宽。
        const u = barUnitCount(b);
        // 至少容纳 u 个单元、每单元 MIN_NOTE_GAP,再加首末固定边距与内缩。
        const minByGap = (u - 1) * CFG.MIN_NOTE_GAP + CFG.FIRST_LAST_DX * 2;
        const raw = Math.max(u * CFG.NEED_PER_NOTE + CFG.CELL_PAD * 2, minByGap);
        return Math.min(CFG.CELL_W_MAX, Math.max(CFG.CELL_W_MIN, raw));
      });
      const sum = need.reduce((a, b) => a + b, 0);
      if (isFullRow) {
        // 满行:等比缩放到正好填满 usableW(右缘严格对齐)
        const scale = usableW / sum;
        return need.map(w => w * scale);
      }
      // 残行:用"满行平均单格宽"为基准等比缩放,使残行的密度感与满行一致,
      //       但总宽 < usableW → 右边留白,左边距仍 = MARGIN_X(与满行统一)。
      const avgCell = usableW / FULL;                 // 满行下每格的平均宽
      const targetSum = avgCell * rowBars.length;      // 残行该占的总宽(按格数缩放)
      const scale = targetSum / sum;
      return need.map(w => w * scale);
    }

    // 先把 bars 按行分组,算出每行各格的左右边界(x 坐标定死)
    const rowsArr = [];
    for (let i = 0; i < bars.length; i += FULL) {
      rowsArr.push(bars.slice(i, i + FULL));
    }
    // barIdx → { row, col, cellLeft, cellRight }
    const cellGeom = [];
    rowsArr.forEach((rowBars, row) => {
      const isFullRow = rowBars.length === FULL;
      const widths = rowCellWidths(rowBars, isFullRow);
      let x = CFG.MARGIN_X;                            // 每行左边距恒为 MARGIN_X
      rowBars.forEach((_, col) => {
        const cellLeft = x;
        const cellRight = x + widths[col];
        cellGeom.push({ row, col, cellLeft, cellRight,
          isRowEnd: col === rowBars.length - 1, isFullRow });
        x = cellRight;
      });
    });

    // 全谱统一的左右"行边线":每行首尾各画一根真实小节线。
    //  左线 = MARGIN_X, 右线 = PAGE_W − MARGIN_X(满行)。
    //  残行右线 = 残行最后一格的右边界(留白,但仍画出该行的收尾竖线)。
    const HARD_LEFT  = CFG.MARGIN_X;
    const HARD_RIGHT = CFG.PAGE_W - CFG.MARGIN_X;

    // 先按行收集:每行 y、左线 x、右线 x(右线=该行最后一格的 cellRight)
    const rowMeta = [];   // [{ y, leftX, rightX }]

    let rows = 0;
    bars.forEach((bar, barIdx) => {
      const g = cellGeom[barIdx];
      const row = g.row, col = g.col;
      rows = Math.max(rows, row + 1);

      const cellLeft  = g.cellLeft;
      const cellRight = g.cellRight;
      const yy = CFG.BASE_Y + row * CFG.ROW_H;

      // 记录每行的首/末竖线 x:行首格的左缘 = 左线;行末格的右缘 = 右线。
      // 同时把子类型带上:行首左线取本小节 leftBar(反复开始),行末右线取本小节 rightBar(终止/反复结束)。
      if (col === 0) rowMeta[row] = { y: yy, leftX: cellLeft, rightX: cellRight,
        leftSub: bar.leftBar || 'normal', rightSub: 'normal', barNo: barIdx + 1 };
      if (g.isRowEnd && rowMeta[row]) { rowMeta[row].rightX = cellRight; rowMeta[row].rightSub = bar.rightBar || 'normal'; }

      // 单元均分:返回每个音符的 x(noteX)和每个音符右侧增时线的 x(dashX)。
      // 若本小节要显示拍号,给格内左侧预留 TIMESIG_W,音符整体右移,避免与拍号重叠。
      const leftInset = bar.showTimeSig ? CFG.TIMESIG_W : 0;
      const { noteX, dashX } = distributeInCell(bar.notes, cellLeft, cellRight, leftInset);

      // —— 谱中拍号标记:该小节需要显示拍号(谱首 or 变拍号处)——
      // 画在小节格左内侧预留区的中间,与音符共享基线 y。渲染层画成分数形式(如 3/4)。
      if (bar.showTimeSig) {
        items.push({
          type: 'timesig',
          index: null,
          x: cellLeft + CFG.FIRST_LAST_DX / 2 + CFG.TIMESIG_W / 2,
          y: yy,
          time: bar.showTimeSig,
        });
      }

      // —— 减时线"连梁"分组:同一拍内、相邻且都有减时线(八分及以下)的音符连成一组 ——
      // 用拍位累加判断"同一拍"。组内逐条线(第k条)按"减时级≥k"决定该音符这条线连不连。
      const beats = bar.notes.map(bn => Model.beats(bn.note));
      let accBeat = 0;
      const beatIdxOf = bar.notes.map((bn, k) => {
        const idx = Math.floor(accBeat + 1e-6);
        accBeat += beats[k];
        return idx;
      });
      // 给每个节奏事件标注 beam 组。MusicXML 带有 beam begin/continue/end
      // 时优先尊重它的真实分组；没有显式分组时才按拍内连续事件分组。
      // 简谱的 0 是有时值的休止事件，只要仍在同一节奏组就必须参与连梁。
      function canBeam(bn) {
        return !bn.filler
          && (bn.note.type === 'note' || bn.note.type === 'rest')
          && Model.underlines(bn.note.dur) > 0;
      }
      const beamGroupId = new Array(bar.notes.length).fill(-1);
      let gid = 0;
      for (let k = 0; k < bar.notes.length; k++) {
        if (!canBeam(bar.notes[k])) { continue; }
        const prevK = k - 1;
        const explicit = bar.notes[k].note.beamGroup;
        const previousExplicit = prevK >= 0 ? bar.notes[prevK].note.beamGroup : null;
        const joinsPrevious = prevK >= 0 && canBeam(bar.notes[prevK])
          && beamGroupId[prevK] >= 0
          && (explicit != null
            ? previousExplicit != null && String(previousExplicit) === String(explicit)
            : previousExplicit == null && beatIdxOf[prevK] === beatIdxOf[k]);
        if (joinsPrevious) {
          beamGroupId[k] = beamGroupId[prevK];
        } else {
          beamGroupId[k] = gid++;
        }
      }

      bar.notes.forEach((bn, k) => {
        const note = bn.note;
        const d = Model.dashes(note.dur);
        // 增时线 x 坐标直接来自单元均分(dashX[k]):天生排在音符右侧的独立单元。
        const dashXs = dashX[k] || [];
        items.push({
          type: note.type,
          index: bn.index,
          x: noteX[k],
          y: yy,
          w: CFG.NOTE_W,
          note,
          filler: !!bn.filler,   // 自动补拍的占位休止符:淡色、不可选
          insertAt: bn.insertAt, // filler 专用:点击它时光标应定位到的 state.notes 位置
          underlines: Model.underlines(note.dur),
          dashes: d,
          dashXs,   // 增时线的精确 x 坐标数组
          decos: decorations(note),
          lyric: note.lyric || '',
          lyricY: yy + CFG.LYRIC_DY,
          beamId: beamGroupId[k] >= 0 ? (row * 1000 + barIdx * 100 + beamGroupId[k]) : null,
        });
      });

      // 小节内分隔线:画在每个非行末格的右边界。
      // 行末竖线交给下面统一的"行边线"绘制(首尾各一根),这里不重复画。
      const isRowEnd = g.isRowEnd;
      if (!isRowEnd) {
        // 边界子类型:优先本小节右侧记号(终止/反复结束);若为普通线但下一小节
        // 是反复开始,则该分隔线显示反复开始(左侧两点)。
        let sub = bar.rightBar || 'normal';
        const nextBar = bars[barIdx + 1];
        if (sub === 'normal' && nextBar && nextBar.leftBar === 'repeatStart') sub = 'repeatStart';
        items.push({
          type: 'barline',
          index: null,
          x: cellRight,
          y: yy,
          w: 0,
          manual: bar.manualBar,
          subtype: sub,
        });
      }
    });

    // —— 行边线:每行首尾各画一根真实小节线(左线 + 右线)——
    rowMeta.forEach(rm => {
      if (!rm) return;
      // 行首小节号:显示在行首左线左侧上方(每行只显示该行第一小节的编号)。
      if (rm.barNo != null) {
        items.push({ type: 'rownum', index: null, x: rm.leftX, y: rm.y, barNo: rm.barNo });
      }
      // 行首左线:普通行边线,但若首小节带反复开始记号,则画反复开始。
      items.push({ type: 'barline', index: null, x: rm.leftX,  y: rm.y, w: 0, edge: true,
        subtype: rm.leftSub === 'repeatStart' ? 'repeatStart' : 'normal' });
      // 行末右线:普通行边线,但若末小节带终止线/反复结束,则如实画出。
      items.push({ type: 'barline', index: null, x: rm.rightX, y: rm.y, w: 0, edge: true,
        subtype: rm.rightSub || 'normal' });
    });

    const width = CFG.PAGE_W;
    const height = rows * CFG.ROW_H + 20;

    // ===== 第三步:把同 beamId 的音符,逐条减时线算成"连通横梁"几何 =====
    // 第 k 条线连通条件:组内相邻两音符的减时级都 >= k。
    // 关键:梁只在"同一拍"内连(分组已保证)。段端点向内收 BEAM_INSET,
    //       并裁掉与右邻音符的重叠,确保相邻拍的梁之间留出肉眼可见的空隙。
    const beams = [];
    const groups = {};
    items.forEach(it => {
      if (it.beamId == null) return;
      (groups[it.beamId] = groups[it.beamId] || []).push(it);
    });
    const half = CFG.NOTE_W / 2;
    Object.values(groups).forEach(grp => {
      grp.sort((a, b) => a.x - b.x);
      const maxUl = Math.max(...grp.map(g => g.underlines));
      const y0 = grp[0].y;
      const solo = grp.length === 1;   // 单音符组:画一条贴住它的短线
      for (let k = 1; k <= maxUl; k++) {
        let i = 0;
        while (i < grp.length) {
          if (grp[i].underlines < k) { i++; continue; }
          let j = i;
          while (j + 1 < grp.length && grp[j + 1].underlines >= k) j++;
          let x1, x2;
          if (solo) {
            // 孤立音符:短线居中,宽度约 NOTE_W-6
            x1 = grp[i].x - half + 3;
            x2 = grp[i].x + half - 3;
          } else {
            // 连梁:端点从首/末音符中心向内收,绝不越过音符外缘的中点,
            //       从而两段相邻梁之间天然留白。
            x1 = grp[i].x - half + CFG.BEAM_INSET;
            x2 = grp[j].x + half - CFG.BEAM_INSET;
          }
          if (x2 > x1) beams.push({ y: y0 + CFG.UL_FIRST_DY + (k - 1) * CFG.UL_GAP, x1, x2 });
          i = j + 1;
        }
      }
    });
    // 兜底:逐条线(同 y)按 x 排序,若相邻两段重叠/贴太近,把右段左端推开,强制留空隙。
    const byRow = {};
    beams.forEach(b => { (byRow[Math.round(b.y)] = byRow[Math.round(b.y)] || []).push(b); });
    Object.values(byRow).forEach(arr => {
      arr.sort((a, b) => a.x1 - b.x1);
      for (let i = 1; i < arr.length; i++) {
        const minLeft = arr[i - 1].x2 + CFG.BEAM_GAP_MIN;
        if (arr[i].x1 < minLeft) arr[i].x1 = Math.min(minLeft, arr[i].x2 - 1);
      }
    });

    // ===== 第四步:连音线 / 延音线(弧线)几何 =====
    // slurs: [{from, to}](音符 index 对)。弧线画在音符上方,跨越 from..to 的水平范围。
    // 同一行:一条弧;跨行:在首行从起点画到行右边线、在末行从行左边线画到终点(拆两段)。
    // 弧顶要避开该范围内最高的挂件(高八度点),因此按范围内音符的 y 及八度决定起拱高度。
    const slurArcs = [];
    // index → 音符本体 item(排除 filler / barline)
    const noteItemByIndex = {};
    items.forEach(it => {
      if (it.type === 'barline') return;
      if (it.index == null) return;
      noteItemByIndex[it.index] = it;
    });
    (state.slurs || []).forEach(s => {
      const a = noteItemByIndex[s.from];
      const b = noteItemByIndex[s.to];
      if (!a || !b) return;                       // 端点被删除 → 跳过
      // 规范化:让 a 在左、b 在右(按 index 或坐标)
      let lft = a, rgt = b;
      if (a.index > b.index) { lft = b; rgt = a; }

      const sameRow = Math.abs(lft.y - rgt.y) < 1e-6;
      if (sameRow) {
        slurArcs.push(makeArc(lft.x, rgt.x, lft.y, rgt.y, lft, rgt));
      } else {
        // 跨行:首行段(起点→本行右边线),末行段(本行左边线→终点)。
        // 中间若还跨了整行,这里从简只画首末两段(简谱里连音线极少跨 3 行)。
        const rightEdgeOfLft = CFG.PAGE_W - CFG.MARGIN_X;
        const leftEdgeOfRgt  = CFG.MARGIN_X;
        slurArcs.push(makeArc(lft.x, rightEdgeOfLft, lft.y, lft.y, lft, null));
        slurArcs.push(makeArc(leftEdgeOfRgt, rgt.x, rgt.y, rgt.y, null, rgt));
      }
    });

    return { items, beams, slurArcs, width, height, cfg: CFG };
  }

  // 生成一条弧线的几何:二次贝塞尔的三点(起点 P0、控制点 PC、终点 P1)。
  // 弧线在音符上方,拱高随跨度增大,并抬到高八度点之上。
  // endL/endR:左右端点对应的音符 item(用于判断是否有高八度点需要额外抬高);可为 null(跨行断点)。
  function makeArc(x0, x1, y0, y1, endL, endR) {
    const span = Math.abs(x1 - x0);
    // 基础离顶:弧线两端稍高于数字顶(数字半高≈NOTE_FS/2)。
    const topGap = CFG.NOTE_FS / 2 + 4;
    // 若端点有高八度点,把弧端再抬高,免得压住八度点。
    const octLift = (it) => {
      if (!it || !it.note) return 0;
      const o = it.note.octave;
      return o > 0 ? (CFG.OCT_GAP_1 + (o - 1) * CFG.OCT_GAP_N + 3) : 0;
    };
    const lift0 = topGap + octLift(endL);
    const lift1 = topGap + octLift(endR);
    const p0y = y0 - lift0;
    const p1y = y1 - lift1;
    // 拱高:跨度越大越高,夹在 8~26。
    const arch = Math.max(8, Math.min(26, span * 0.12 + 8));
    const cx = (x0 + x1) / 2;
    const cy = Math.min(p0y, p1y) - arch;
    return { x0, y0: p0y, cx, cy, x1, y1: p1y };
  }

  return { compute, partitionBars: splitBars, CFG };
})();

export { Layout };
