// model.js — 简谱数据模型(中间表示)
// 一个音符/休止符的统一结构,渲染/键盘/XML导入导出共享
//
// note = {
//   id:        唯一id
//   type:      'note' | 'rest' | 'barline'
//   degree:    1..7  (音级, 休止符固定为0)
//   octave:    整数, 0=中音, +1=高八度(上点), -1=低八度(下点)
//   accidental:'' | 'sharp' | 'flat'
//   dur:       基础时值, 以"四分音符=4"为基准的分母: 1=全音符,2=二分,4=四分,8=八分,16=十六分
//   dots:      附点个数 0/1/2
// }

const Model = (() => {
  let _uid = 1;
  function uid() { return _uid++; }

  function makeNote(degree, octave = 0) {
    return {
      id: uid(),
      type: degree === 0 ? 'rest' : 'note',
      degree,
      octave,
      accidental: '',
      dur: 4,        // 默认四分音符
      dots: 0,
      lyric: ''      // 该音符下方对应的一个音节(空字符串=无词占位)
    };
  }

  // 小节线子类型:
  //   'normal'      普通小节线 |
  //   'final'       终止线 ‖(细+粗,乐曲结束)
  //   'repeatStart' 反复开始 𝄆(粗+细+两点,标在小节左侧)
  //   'repeatEnd'   反复结束 𝄇(两点+细+粗,标在小节右侧)
  function makeBarline(subtype) {
    return { id: uid(), type: 'barline', subtype: subtype || 'normal' };
  }

  // 谱中变拍号标记:插在音符流里,从它起后续小节改用新拍号切分。
  // 布局遇到它会先封口当前小节,切换生效拍号,并在其后第一个小节左侧显示新拍号。
  function makeTimeSig(timeSig) {
    return { id: uid(), type: 'timesig', time: timeSig || '4/4' };
  }

  // 时值 -> 下方减时线条数。四分=0条, 八分=1条, 十六分=2条, 三十二分=3条
  function underlines(dur) {
    if (dur <= 4) return 0;
    return Math.round(Math.log2(dur / 4)); // 8->1, 16->2, 32->3
  }
  // 时值 -> 二分/全音符的右侧增时线("—")条数。四分=0, 二分=1, 全=3
  function dashes(dur) {
    if (dur === 2) return 1;
    if (dur === 1) return 3;
    return 0;
  }

  // 音符占多少"四分音符拍"。dur=4 -> 1拍, dur=8 -> 0.5拍, dur=2 -> 2拍, dur=1 -> 4拍
  // 附点 +50%,双附点 +75%
  function beats(note) {
    if (!note || note.type === 'barline' || note.type === 'timesig') return 0;
    let b = 4 / note.dur;
    if (note.dots === 1) b *= 1.5;
    if (note.dots === 2) b *= 1.75;
    return b;
  }

  // 拍号字符串 "4/4" -> 每小节容纳多少"四分音符拍"
  // 4/4 -> 4, 3/4 -> 3, 6/8 -> 3(6个八分=3个四分拍), 2/2 -> 4
  function barCapacity(timeSig) {
    const m = /^(\d+)\s*\/\s*(\d+)$/.exec(timeSig || '4/4');
    if (!m) return 4;
    const numer = parseInt(m[1], 10), denom = parseInt(m[2], 10);
    return numer * (4 / denom);
  }

  // 应用一个符号动作到音符上(返回是否生效)
  function applyAction(note, act) {
    if (!note || note.type === 'barline') return false;
    switch (act) {
      case 'octaveUp':   note.octave = Math.min(2, note.octave + 1); return true;
      case 'octaveDown': note.octave = Math.max(-2, note.octave - 1); return true;
      case 'durHalf':      note.dur = 2; note.dots = 0; return true;
      case 'durQuarter':   note.dur = 4; note.dots = 0; return true;
      case 'durEighth':    note.dur = 8; note.dots = 0; return true;
      case 'durSixteenth': note.dur = 16; note.dots = 0; return true;
      case 'dot':        note.dots = note.dots ? 0 : 1; return true; // 切换附点
      case 'sharp':      note.accidental = note.accidental === 'sharp' ? '' : 'sharp'; return true;
      case 'flat':       note.accidental = note.accidental === 'flat' ? '' : 'flat'; return true;
      case 'natural':    note.accidental = note.accidental === 'natural' ? '' : 'natural'; return true;
      default: return false;
    }
  }

  // ===== 音高映射(发声 / 钢琴卷帘窗共用的纯函数)=====
  // 调号名 → 主音 do 的半音值(以 C=0)。与 index.html 的调号选项一一对应。
  const KEY_TONIC = {
    'C':0, 'G':7, 'D':2, 'A':9, 'E':4, 'B':11, 'F':5,
    'bC':11, 'bB':10, 'bE':3, 'bA':8, 'bD':1, 'bG':6,
    'F#':6, 'C#':1, 'G#':8, 'D#':3, 'A#':10
  };
  function formatKeyName(key) {
    return String(key || 'C').replace(/^b/, '♭').replace(/#$/, '♯');
  }
  // 大调音阶:音级 1-7 → 相对 do 的半音。
  const DEGREE_SEMI = {1:0, 2:2, 3:4, 4:5, 5:7, 6:9, 7:11};

  // 简谱音符 → MIDI 音高。中音区(octave=0)的 do 落在第 4 八度(≈C4=60)。
  //   midi = 60 + 主音半音 + 音级半音 + 升降修正 + 八度*12
  // 休止符 / 非音符返回 null。natural(还原)视作回到大调本级(无修正)。
  function pitchToMidi(note, key) {
    if (!note || note.type !== 'note') return null;
    const tonic = KEY_TONIC[key] != null ? KEY_TONIC[key] : 0;
    const deg = DEGREE_SEMI[note.degree];
    if (deg == null) return null;
    let acc = 0;
    if (note.accidental === 'sharp') acc = 1;
    else if (note.accidental === 'flat') acc = -1;
    return 60 + tonic + deg + acc + (note.octave || 0) * 12;
  }

  // 绝对 MIDI 音高 -> 指定首调 do 下的简谱音级。用于在不改变实际音高的
  // 前提下迁移旧谱面（例如 G 小调旧写法 1=G -> 标准首调 1=♭B）。
  function midiToNotation(midi, key, preferFlat = false) {
    const tonic = KEY_TONIC[key] != null ? KEY_TONIC[key] : 0;
    const diff = Math.round(Number(midi)) - (60 + tonic);
    const semi = ((diff % 12) + 12) % 12;
    const natural = Object.entries(DEGREE_SEMI).find(([, value]) => value === semi);
    let degree;
    let accidental = '';
    if (natural) {
      degree = Number(natural[0]);
    } else if (preferFlat) {
      const upper = Object.entries(DEGREE_SEMI).find(([, value]) => value === (semi + 1) % 12);
      degree = Number(upper[0]);
      accidental = 'flat';
    } else {
      const lower = Object.entries(DEGREE_SEMI).find(([, value]) => value === semi - 1);
      degree = Number(lower[0]);
      accidental = 'sharp';
    }
    return {
      degree,
      accidental,
      octave: Math.max(-2, Math.min(2, Math.floor(diff / 12))),
    };
  }

  // MIDI → 频率(A4=69=440Hz,十二平均律)。
  function midiToFreq(midi) {
    return 440 * Math.pow(2, (midi - 69) / 12);
  }

  // 音级(1-7)+ 八度 + 调号 → 频率。给发声/预览用(不构造完整 note)。
  function degreeToFreq(degree, octave, key) {
    const midi = pitchToMidi({ type: 'note', degree, octave: octave || 0, accidental: '' }, key);
    return midi == null ? null : midiToFreq(midi);
  }

  return { makeNote, makeBarline, makeTimeSig, underlines, dashes, beats, barCapacity, applyAction, uid,
           pitchToMidi, midiToNotation, midiToFreq, degreeToFreq, formatKeyName, KEY_TONIC, DEGREE_SEMI };
})();

export { Model };
