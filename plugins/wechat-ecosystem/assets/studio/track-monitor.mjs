// These switches belong to the open Studio session. Project drafts and exports never read them.
export class TrackMonitor {
  constructor() {
    this.sessions = new Map();
    this.select(null, null, null);
  }

  select(project, song, version) {
    const key = JSON.stringify([project?.id, song?.id, version?.id]);
    this.ids = new Set((version?.mastered ? [] : version?.tracks ?? []).map(track => track.id));
    this.selection = this.sessions.get(key) ?? { solo: new Set(), mute: new Set() };
    this.key = key;
    for (const group of [this.selection.solo, this.selection.mute]) {
      for (const id of group) if (!this.ids.has(id)) group.delete(id);
    }
  }

  toggle(name, id) {
    if (!this.ids.has(id)) return false;
    const group = this.selection[name];
    if (!group.delete(id)) group.add(id);
    if (this.filtered()) this.sessions.set(this.key, this.selection);
    else this.sessions.delete(this.key);
    return true;
  }

  filtered(editorId) {
    return !!editorId || this.selection.solo.size > 0 || this.selection.mute.size > 0;
  }

  state(id, editorId) {
    const solo = this.selection.solo.has(id), mute = this.selection.mute.has(id);
    const editorSolo = id === editorId;
    const selected = editorId ? editorSolo : !this.selection.solo.size || solo;
    return { solo, mute, editorSolo, audible: !mute && selected };
  }
}

// Only one program route reaches the master at a time. Per-clip edit fades stay independent.
export class MonitorGains {
  constructor(context, master) {
    this.context = context;
    this.lanes = new Map();
    this.stems = context.createGain();
    this.native = context.createGain();
    this.stems.connect(master);
    this.native.connect(master);
    this.native.gain.value = 0;
    this.useNative = false;
  }

  lane(id, audible) {
    if (!this.lanes.has(id)) {
      const node = this.context.createGain();
      node.gain.value = Number(audible);
      node.connect(this.stems);
      this.lanes.set(id, { node, audible });
    }
    return this.lanes.get(id).node;
  }

  update(useNative, audible, immediate = false) {
    const now = this.context.currentTime, edge = now + .003;
    for (const [id, lane] of this.lanes) {
      const value = audible(id);
      if (!immediate && lane.audible === value) continue;
      lane.audible = value;
      const gain = lane.node.gain;
      if (immediate) {
        gain.cancelScheduledValues(now);
        gain.setValueAtTime(Number(value), now);
      } else {
        gain.cancelAndHoldAtTime(now);
        gain.linearRampToValueAtTime(Number(value), edge);
      }
    }
    if (!immediate && this.useNative === useNative) return;
    this.useNative = useNative;
    const off = (useNative ? this.stems : this.native).gain;
    const on = (useNative ? this.native : this.stems).gain;
    if (immediate) {
      for (const param of [off, on]) param.cancelScheduledValues(now);
      off.setValueAtTime(0, now);
      on.setValueAtTime(1, now);
    } else {
      // In a rapid reversal the new route may be the still-fading old route. Keep
      // it at its current value until that edge. The opposite route is already silent.
      off.cancelAndHoldAtTime(now);
      on.cancelAndHoldAtTime(now);
      off.linearRampToValueAtTime(0, edge);
      on.setValueAtTime(on.value, edge);
      on.linearRampToValueAtTime(1, edge + .003);
    }
  }

  clearLanes() {
    for (const { node } of this.lanes.values()) node.disconnect();
    this.lanes.clear();
  }

  close() {
    this.clearLanes();
    this.native.disconnect();
    this.stems.disconnect();
  }
}
