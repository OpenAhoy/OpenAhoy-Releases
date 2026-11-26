import { Model } from "./model.mjs";
// xml.js — MusicXML 解析为简谱模型
// 支持 .xml / .musicxml(未压缩的 MusicXML)。
//
// 设计要点(为避免丢音符/错拍/留空白/丢延音):
//   ① 只取第一个含 measure 的 <part>(主旋律),不再把多 part 串接。
//   ② 只取主声部(第一个出现的 voice),跳过 backup 出来的伴奏声部,避免重叠错位。
//   ③ 时值以权威的 divisions + <duration> 为准(divisions=每四分音符的 tick 数),
//      再反推成简谱的 dur(分母)+ dots(附点);<type> 仅作兜底。
//   ④ 长时值封顶:单个音符最长到"附点二分音符"(增时线);更长(全音符及以上)
//      拆成多个音符并用延音线(slur)相连 —— 与《GB 46845-2025》简谱规范一致
//      (四分音符为基本符号,增时线延长;休止符用多个 0 而不加增时线)。
//   ⑤ 延音线:解析 <tie>/<tied> 并入 slurs(与显式 <slur>、一字多音统一为弧线)。
//   ⑥ 三连音等 time-modification:模型无三连音记号,退化为"最接近的单一时值"(近似,不拆分)。
//   ⑦ grace 装饰音无 duration → 跳过。
//   ⑧ 有时值但无音高(unpitched 等)→ 转休止符占位,不丢弃。
//   ⑨ 整小节休止(rest measure=yes 或整小节空)→ 按拍号补足,拆成多个 0。
//   ⑩ 调号/拍号/速度都从主 part 读取;首小节拍号直接作为初始拍号。
//   ⑪ 一字多音自动连线:仅当歌词带 <extend/>(延音记号)时才判定持续,避免把
//      纯器乐无词音符误连。

const XmlImport = (() => {

  // 音名 -> 半音(以 C=0)
  const STEP_SEMI = { C:0, D:2, E:4, F:5, G:7, A:9, B:11 };
  const MAJOR_KEYS = {
    '-7':'bC','-6':'bG','-5':'bD','-4':'bA','-3':'bE','-2':'bB','-1':'F',
    '0':'C','1':'G','2':'D','3':'A','4':'E','5':'B','6':'F#','7':'C#'
  };
  const MINOR_KEYS = {
    '-7':'bA','-6':'bE','-5':'bB','-4':'F','-3':'C','-2':'G','-1':'D',
    '0':'A','1':'E','2':'B','3':'F#','4':'C#','5':'G#','6':'D#','7':'A#'
  };

  function keyInfoFromFifths(fifths, mode) {
    const normalizedMode = String(mode || 'major').trim().toLowerCase() === 'minor'
      ? 'minor' : 'major';
    const tonalName = (normalizedMode === 'minor' ? MINOR_KEYS : MAJOR_KEYS)[String(fifths)]
      || (normalizedMode === 'minor' ? 'A' : 'C');
    // 标准首调简谱以 do 为 1，小调主音是 6。五线谱 G minor（两个降号）
    // 因而显示 1=♭B，而不是把 G 强行当成 1。
    const name = MAJOR_KEYS[String(fifths)] || 'C';
    const tonic = Model.KEY_TONIC[name] != null ? Model.KEY_TONIC[name] : 0;
    return { name, tonic, mode: normalizedMode, tonalName };
  }

  // 半音差(相对do) -> 简谱音级 + 升降。返回 {degree, accidental}
  const SEMI_TO_DEGREE = {0:1, 2:2, 4:3, 5:4, 7:5, 9:6, 11:7};
  // 黑键拼写:升号调(fifths>=0)用 sharp+下方音级;降号调用 flat+上方音级。
  function semiToDegree(semi, preferFlat) {
    semi = ((semi % 12) + 12) % 12;
    if (SEMI_TO_DEGREE[semi] != null) return { degree: SEMI_TO_DEGREE[semi], accidental: '' };
    if (preferFlat) return { degree: SEMI_TO_DEGREE[(semi + 1) % 12], accidental: 'flat' };
    return { degree: SEMI_TO_DEGREE[semi - 1], accidental: 'sharp' };
  }

  // 备用:<type> -> 四分音符数(quarterLength)。divisions 缺失时才用。
  const TYPE_QL = {
    'breve':8, 'whole':4, 'half':2, 'quarter':1,
    'eighth':0.5, '16th':0.25, '32nd':0.125, '64th':0.0625
  };

  // 简谱可表示的单一时值(含附点)。max = 附点二分音符(3 拍),即"封顶二分"。
  const SINGLE_TABLE = [
    { ql: 3,      dur: 2,  dots: 1 },   // 附点二分(number — ·)
    { ql: 2,      dur: 2,  dots: 0 },   // 二分(number —)
    { ql: 1.5,    dur: 4,  dots: 1 },   // 附点四分
    { ql: 1,      dur: 4,  dots: 0 },   // 四分
    { ql: 0.75,   dur: 8,  dots: 1 },   // 附点八分
    { ql: 0.5,    dur: 8,  dots: 0 },   // 八分
    { ql: 0.375,  dur: 16, dots: 1 },   // 附点十六
    { ql: 0.25,   dur: 16, dots: 0 },   // 十六
    { ql: 0.1875, dur: 32, dots: 1 },   // 附点三十二
    { ql: 0.125,  dur: 32, dots: 0 },   // 三十二
  ];
  // 拆分用的"整"时值(无附点),便于把长音拆成整齐的连音片段。
  const BINARY_TABLE = [
    { ql: 2,     dur: 2,  dots: 0 },
    { ql: 1,     dur: 4,  dots: 0 },
    { ql: 0.5,   dur: 8,  dots: 0 },
    { ql: 0.25,  dur: 16, dots: 0 },
    { ql: 0.125, dur: 32, dots: 0 },
  ];
  const TOL = 0.02;

  // ql -> 最接近的单一时值(用于三连音等无法精确表示的近似)。
  function nearestSingle(ql) {
    let best = SINGLE_TABLE[SINGLE_TABLE.length - 1], bestErr = Infinity;
    for (const t of SINGLE_TABLE) {
      const e = Math.abs(t.ql - ql);
      if (e < bestErr) { bestErr = e; best = t; }
    }
    return { dur: best.dur, dots: best.dots };
  }

  // ql -> 一组时值片段 [{dur,dots}...]。
  //   能用单一时值精确表示 → 返回 1 个;否则贪心用"整"时值拆分(长音靠连音线相连)。
  function splitDuration(ql) {
    if (ql <= 0) return [{ dur: 4, dots: 0 }];
    // 先看能否单符号精确表示(含附点,封顶 3 拍)
    for (const t of SINGLE_TABLE) {
      if (Math.abs(t.ql - ql) < TOL) return [{ dur: t.dur, dots: t.dots }];
    }
    // 贪心拆:每次取不超过剩余的最大"整"时值
    const pieces = [];
    let rem = ql;
    let guard = 0;
    while (rem > TOL && guard++ < 64) {
      let pick = null;
      for (const t of BINARY_TABLE) {
        if (t.ql <= rem + TOL) { pick = t; break; }
      }
      if (!pick) { pick = BINARY_TABLE[BINARY_TABLE.length - 1]; } // 比最小还小 → 用最小兜底
      pieces.push({ dur: pick.dur, dots: pick.dots });
      rem -= pick.ql;
    }
    return pieces.length ? pieces : [{ dur: 4, dots: 0 }];
  }

  // 休止符专用拆分:封顶四分休止符(dur=4),整拍用多个 0 逐个写,不用增时线,
  // 符合《GB 46845-2025》6.3.7.2(二分/全休止符用增加四分休止符个数的办法构成)。
  const REST_TABLE = [
    { ql: 1,     dur: 4,  dots: 0 },
    { ql: 0.5,   dur: 8,  dots: 0 },
    { ql: 0.25,  dur: 16, dots: 0 },
    { ql: 0.125, dur: 32, dots: 0 },
  ];
  function splitRest(ql) {
    if (ql <= 0) return [{ dur: 4, dots: 0 }];
    const pieces = [];
    let rem = ql, guard = 0;
    while (rem > TOL && guard++ < 128) {
      let pick = null;
      for (const t of REST_TABLE) { if (t.ql <= rem + TOL) { pick = t; break; } }
      if (!pick) pick = REST_TABLE[REST_TABLE.length - 1];
      pieces.push({ dur: pick.dur, dots: pick.dots });
      rem -= pick.ql;
    }
    return pieces.length ? pieces : [{ dur: 4, dots: 0 }];
  }

  function firstChildText(el, tag) {
    const c = el && el.querySelector(tag);
    return c ? c.textContent.trim() : null;
  }

  function parse(xmlText) {
    const doc = new DOMParser().parseFromString(xmlText, 'application/xml');
    if (doc.querySelector('parsererror')) throw new Error('XML 解析失败,文件可能损坏');

    const out = { title: '', key: 'C', mode: 'major', time: '4/4', tempo: '', notes: [], slurs: [] };

    // 标题(全曲级,取文档级)
    const workTitle = doc.querySelector('work-title, movement-title');
    if (workTitle) out.title = workTitle.textContent.trim();

    // ① 先定位主 part(第一个含 measure 的 part),后续元数据都从它内部读
    const parts = Array.from(doc.querySelectorAll('part'));
    let mainPart = null;
    for (const p of parts) { if (p.querySelector('measure')) { mainPart = p; break; } }
    if (!mainPart) throw new Error('未在文件中找到乐谱声部(part)');

    // ⑩ 调号 fifths(优先主 part 内,退回文档)
    let fifths = 0;
    const fifthsEl = mainPart.querySelector('key fifths') || doc.querySelector('key fifths');
    if (fifthsEl) fifths = parseInt(fifthsEl.textContent, 10) || 0;
    const modeEl = mainPart.querySelector('key mode') || doc.querySelector('key mode');
    const keyInfo = keyInfoFromFifths(fifths, modeEl ? modeEl.textContent : 'major');
    out.key = keyInfo.name;
    out.mode = keyInfo.mode;
    const tonic = keyInfo.tonic;
    const preferFlat = fifths < 0;

    // ⑩ 初始拍号(主 part 第一处 time)
    const beats0 = mainPart.querySelector('time beats');
    const beatType0 = mainPart.querySelector('time beat-type');
    if (beats0 && beatType0) out.time = `${beats0.textContent.trim()}/${beatType0.textContent.trim()}`;

    // ⑩ 速度:优先主 part 内 <sound tempo>,否则 <metronome per-minute>;退回文档级
    let bpm = null;
    const soundTempo = mainPart.querySelector('sound[tempo]') || doc.querySelector('sound[tempo]');
    if (soundTempo) {
      const t = parseFloat(soundTempo.getAttribute('tempo'));
      if (t > 0) bpm = Math.round(t);
    }
    if (bpm == null) {
      const perMin = mainPart.querySelector('metronome per-minute') || doc.querySelector('metronome per-minute');
      if (perMin) { const t = parseInt(perMin.textContent, 10); if (t > 0) bpm = t; }
    }
    if (bpm != null) out.tempo = `♩=${bpm}`;

    const measures = Array.from(mainPart.querySelectorAll('measure'));
    let divisions = 0;              // 每四分音符的 tick 数
    let curTimeStr = out.time;      // 当前生效拍号
    let mainVoice = null;           // 主声部编号
    let nextBeamGroup = 1;
    let currentBeamGroup = null;

    // —— 弧线检测状态(一字多音 / 显式 slur / 延音 tie 统一进 out.slurs)——
    let melismaStart = null, melismaEnd = null;   // 一字多音:音节起止音符下标
    const openSlurs = {};                          // 显式 <slur> number → 起始下标
    let openTieFrom = null;                        // 延音 <tie>/<tied> 起始下标
    function closeMelisma() {
      if (melismaStart != null && melismaEnd != null && melismaEnd > melismaStart) {
        out.slurs.push({ from: melismaStart, to: melismaEnd });
      }
      melismaStart = null; melismaEnd = null;
    }

    // 追加一个音高音符(必要时拆成多片并用延音线相连)。返回 {first,last} 下标。
    function emitPitched(degree, oct, accidental, ql, lyric, hasTimeMod, beamGroup) {
      const pieces = hasTimeMod ? [nearestSingle(ql)] : splitDuration(ql);
      const idxs = [];
      pieces.forEach((p, i) => {
        const nt = Model.makeNote(degree, oct);
        nt.accidental = accidental;
        nt.dur = p.dur; nt.dots = p.dots;
        if (i === 0 && beamGroup != null) nt.beamGroup = beamGroup;
        if (i === 0 && lyric) nt.lyric = lyric;
        out.notes.push(nt);
        idxs.push(out.notes.length - 1);
      });
      if (idxs.length > 1) out.slurs.push({ from: idxs[0], to: idxs[idxs.length - 1] });  // 拆分片段=延音线
      return { first: idxs[0], last: idxs[idxs.length - 1], count: idxs.length };
    }
    // 追加休止(按 ql 拆成多个 0;封顶四分,休止符不加增时线,符合规范)。
    function emitRest(ql, beamGroup) {
      const pieces = splitRest(ql);
      pieces.forEach((p, index) => {
        const r = Model.makeNote(0, 0);
        r.dur = p.dur; r.dots = p.dots;
        if (index === 0 && beamGroup != null) r.beamGroup = beamGroup;
        out.notes.push(r);
      });
      return pieces.length;
    }
    function durationQl(el) {
      const durText = firstChildText(el, 'duration');
      const durTicks = durText ? parseInt(durText, 10) : NaN;
      if (divisions > 0 && durTicks > 0) return durTicks / divisions;
      const typeEl = el.querySelector('type');
      const durName = typeEl ? typeEl.textContent.trim() : 'quarter';
      let ql = TYPE_QL[durName] != null ? TYPE_QL[durName] : 1;
      const dots = el.querySelectorAll('dot').length;
      if (dots === 1) ql *= 1.5; else if (dots === 2) ql *= 1.75;
      return ql;
    }

    function beamGroupForEvent(noteEl) {
      const beam = Array.from(noteEl.querySelectorAll('beam')).find(el =>
        !el.getAttribute('number') || el.getAttribute('number') === '1');
      if (!beam) return null;
      const marker = beam.textContent.trim().toLowerCase();
      if (marker === 'begin' || currentBeamGroup == null) currentBeamGroup = nextBeamGroup++;
      const group = currentBeamGroup;
      if (marker === 'end') currentBeamGroup = null;
      return group;
    }

    measures.forEach((measure, mi) => {
      currentBeamGroup = null;       // 连梁不得跨越 MusicXML 小节边界
      // divisions 随 attributes 更新
      const divText = firstChildText(measure, 'attributes divisions');
      if (divText) { const d = parseInt(divText, 10); if (d > 0) divisions = d; }

      // 拍号:首小节写入初始拍号;之后变化插入 timesig 标记
      const mb = measure.querySelector('time beats');
      const mbt = measure.querySelector('time beat-type');
      if (mb && mbt) {
        const ts = `${mb.textContent.trim()}/${mbt.textContent.trim()}`;
        if (mi === 0) {
          out.time = ts; curTimeStr = ts;
        } else if (ts !== curTimeStr) {
          out.notes.push(Model.makeTimeSig(ts));
          curTimeStr = ts;
        }
      }

      const cap = Model.barCapacity(curTimeStr) || 4;   // 本小节容量(四分拍)
      const musicEvents = Array.from(measure.children).filter(el => {
        const tag = (el.localName || el.tagName || '').toLowerCase();
        return tag === 'note' || tag === 'forward' || tag === 'backup';
      });
      let addedInThisMeasure = 0;

      for (const ev of musicEvents) {
        const tag = (ev.localName || ev.tagName || '').toLowerCase();
        if (tag === 'backup') {
          closeMelisma();
          continue;
        }
        if (tag === 'forward') {
          const voice = firstChildText(ev, 'voice');
          if (mainVoice != null && voice && voice !== mainVoice) continue;
          closeMelisma();
          addedInThisMeasure += emitRest(durationQl(ev));
          continue;
        }
        const n = ev;
        // ⑦ grace 装饰音:无 duration,跳过(其上的 slur 端点一并忽略)
        if (n.querySelector('grace')) continue;
        // 和弦附加音:只保留和弦第一个音
        if (n.querySelector('chord')) continue;

        // ② 主声部过滤
        const voiceEl = n.querySelector('voice');
        const voice = voiceEl ? voiceEl.textContent.trim() : '1';
        if (mainVoice == null) mainVoice = voice;
        if (voice !== mainVoice) continue;

        const restEl = n.querySelector('rest');
        const isRest = !!restEl;
        const beamGroup = beamGroupForEvent(n);

        // ⑨ 整小节休止:rest measure="yes" → 直接按拍号补满,拆成多个 0
        if (isRest && (restEl.getAttribute('measure') === 'yes')) {
          closeMelisma();
          addedInThisMeasure += emitRest(cap);
          continue;
        }

        // ③ 时值:优先 divisions + <duration>;缺失退回 <type>;再缺按四分
        const ql = durationQl(n);
        // ⑥ time-modification(三连音等):标记后按最接近单一时值近似
        const hasTimeMod = !!n.querySelector('time-modification');

        if (isRest) {
          closeMelisma();                     // 休止打断一字多音
          addedInThisMeasure += emitRest(ql, beamGroup);
          continue;
        }

        // ⑧ 无音高但有时值 → 休止占位
        const stepEl = n.querySelector('pitch step');
        const octEl = n.querySelector('pitch octave');
        if (!stepEl || !octEl) {
          closeMelisma();
          addedInThisMeasure += emitRest(ql, beamGroup);
          continue;
        }

        const step = stepEl.textContent.trim();
        const octave = parseInt(octEl.textContent, 10);
        const alterEl = n.querySelector('pitch alter');
        const alter = alterEl ? parseInt(alterEl.textContent, 10) : 0;

        const absSemi = STEP_SEMI[step] + alter + (octave + 1) * 12;
        const tonicAbs = tonic + (4 + 1) * 12;                 // 第4八度 do 为中音参考
        const diff = absSemi - tonicAbs;

        // ⑭ 畸形音高兜底:算不出合法半音 → 转休止占位,不产坏音符
        if (!isFinite(diff)) {
          closeMelisma();
          addedInThisMeasure += emitRest(ql, beamGroup);
          continue;
        }

        const { degree, accidental } = semiToDegree(((diff % 12) + 12) % 12, preferFlat);
        let oct = Math.floor(diff / 12);
        oct = Math.max(-2, Math.min(2, oct));                  // 钳到模型支持范围

        // 歌词音节(number=1 或第一个 <lyric>);<extend/> 标记该音节要延音
        const lyricEl = n.querySelector('lyric');
        const lyricTextEl = lyricEl ? lyricEl.querySelector('text') : null;
        const syllable = lyricTextEl ? lyricTextEl.textContent.trim() : '';
        const hasExtend = !!(lyricEl && lyricEl.querySelector('extend'));

        const { first, last } = emitPitched(
          degree, oct, accidental, ql, syllable, hasTimeMod, beamGroup,
        );
        addedInThisMeasure++;

        // ⑪ 一字多音:仅在音节明确带 <extend/> 时开启持续;否则不自动连,避免误连器乐音
        if (syllable) {
          closeMelisma();
          if (hasExtend) { melismaStart = first; melismaEnd = last; }
        } else if (melismaStart != null) {
          melismaEnd = last;                  // 处在延音中的无词音符 → 扩展
        }

        // 显式 <slur>
        n.querySelectorAll('slur').forEach(sl => {
          const type = sl.getAttribute('type');
          const num = sl.getAttribute('number') || '1';
          if (type === 'start') openSlurs[num] = first;
          else if (type === 'stop') {
            const f = openSlurs[num];
            if (f != null && last > f) out.slurs.push({ from: f, to: last });
            delete openSlurs[num];
          }
        });

        // ⑤ 延音线 <tie>/<tied>(同音相连)。start 记起点,stop 配对。
        const tieEls = [
          ...Array.from(n.querySelectorAll('tie')),
          ...Array.from(n.querySelectorAll('tied')),
        ];
        let tieStart = false, tieStop = false;
        tieEls.forEach(t => {
          const ty = t.getAttribute('type');
          if (ty === 'start') tieStart = true;
          else if (ty === 'stop') tieStop = true;
        });
        if (tieStop && openTieFrom != null && first > openTieFrom) {
          out.slurs.push({ from: openTieFrom, to: first });
          openTieFrom = null;
        }
        if (tieStart) openTieFrom = last;
      }

      // ⑨ 整小节空 → 按拍号补足,拆成多个 0
      if (addedInThisMeasure === 0) {
        closeMelisma();
        emitRest(cap);
      }

      // 小节线(最后一个小节不加)
      if (mi < measures.length - 1) out.notes.push(Model.makeBarline());
    });

    closeMelisma();   // 结算最后一个未收尾的一字多音

    // 弧线去重:一字多音 / 显式 slur / 延音 tie / 拆分片段 可能指向同一对音符
    const seen = new Set();
    out.slurs = out.slurs.filter(s => {
      if (s.from == null || s.to == null || s.to <= s.from) return false;
      const k = s.from + '-' + s.to;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });

    if (out.notes.filter(n => n.type !== 'barline' && n.type !== 'timesig').length === 0) {
      throw new Error('未在文件中找到音符');
    }
    return out;
  }

  return { parse, keyInfoFromFifths };
})();

export { XmlImport };
