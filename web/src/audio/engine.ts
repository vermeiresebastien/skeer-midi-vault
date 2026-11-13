/**
 * Local audition engine.
 *
 * The lookahead scheduler owns note timing on the AudioContext clock. React
 * rendering only reads a snapshot; no piano-roll frame drives scheduling. The
 * same scheduler can route notes to a Web MIDI output. All notes are released
 * on stop, pause, file/sequence switch and output-device change.
 */
import type { PreviewNote, PreviewSequence } from '../types';

export interface EngineTrack {
  key: string;
  trackIndex: number;
  sequenceIndex: number;
  name: string | null;
  channel: number;
  instrument: string;
  role: string;
  program: number | null;
}

export interface EngineSequence {
  key: string;
  name: string;
  duration: number;
  originalBpm: number;
  timingType: string;
  tracks: EngineTrack[];
  notes: Array<PreviewNote & { trackKey: string }>;
}

export interface MidiOutputInfo {
  id: string;
  name: string;
  manufacturer: string;
}

export interface EngineDebugStats {
  scheduledNotes: number;
  lateNotes: number;
  skippedNotes: number;
  activeVoices: number;
  scheduledPasses: number;
  outputMode: string;
}

export interface EngineSnapshot {
  playing: boolean;
  paused: boolean;
  sourceTime: number;
  duration: number;
  loop: boolean;
  speed: number;
  originalBpm: number;
  auditionBpm: number;
  meter: number;
  activeVoices: number;
  outputMode: 'synth' | 'midi';
  outputId: string | null;
  midiOutputs: MidiOutputInfo[];
  midiSupported: boolean | null;
  midiError: string | null;
  volume: number;
  error: string | null;
  hasSequence: boolean;
  sequenceName: string;
  trackCount: number;
  noteCount: number;
}

interface MidiPortLike {
  id: string;
  name?: string;
  manufacturer?: string;
  send: (data: number[] | Uint8Array, timestamp?: number) => void;
}

interface MidiAccessLike {
  outputs: Map<string, MidiPortLike>;
  onstatechange: ((event: unknown) => void) | null;
}

interface Voice {
  trackKey: string;
  nodes: AudioScheduledSourceNode[];
  gain: GainNode;
  startedAt: number;
  cleanup: () => void;
}

const LOOKAHEAD = 0.28;
const SCHEDULER_INTERVAL_MS = 30;
const MAX_POLYPHONY = 72;

function noteFrequency(pitch: number): number {
  return 440 * 2 ** ((pitch - 69) / 12);
}

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

export class PreviewEngine {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private compressor: DynamicsCompressorNode | null = null;
  private analyser: AnalyserNode | null = null;
  private meterData: Uint8Array<ArrayBuffer> | null = null;
  private noiseBuffer: AudioBuffer | null = null;
  private sequence: EngineSequence | null = null;
  private listeners = new Set<() => void>();
  private snapshot: EngineSnapshot;
  private muted = new Set<string>();
  private solo = new Set<string>();
  private playing = false;
  private paused = false;
  private sourceTime = 0;
  private anchorCtx = 0;
  private anchorSource = 0;
  private speed = 1;
  private loop = false;
  private volume = 0.78;
  private outputMode: 'synth' | 'midi' = 'synth';
  private midiAccess: MidiAccessLike | null = null;
  private midiOutputId: string | null = null;
  private midiOutputs: MidiOutputInfo[] = [];
  private midiSupported: boolean | null = null;
  private midiError: string | null = null;
  private schedulerTimer: number | null = null;
  private clockTimer: number | null = null;
  private endTimer: number | null = null;
  private noteCursor = 0;
  private passStartSource = 0;
  private passStartCtx = 0;
  private passComplete = false;
  private scrubbing = false;
  private scrubWasPlaying = false;
  private tempoRestartTimer: number | null = null;
  private voices = new Set<Voice>();
  private midiTimers = new Set<number>();
  private midiActive = new Map<string, { channel: number; pitch: number; trackKey: string }>();
  private stats: EngineDebugStats = {
    scheduledNotes: 0,
    lateNotes: 0,
    skippedNotes: 0,
    activeVoices: 0,
    scheduledPasses: 0,
    outputMode: 'synth',
  };
  private lastEmit = 0;

  constructor() {
    this.snapshot = this.buildSnapshot();
  }

  // -------------------------------------------------------------- subscription
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): EngineSnapshot => this.snapshot;

  private buildSnapshot(): EngineSnapshot {
    const duration = Number.isFinite(this.sequence?.duration) ? this.sequence?.duration ?? 0 : 0;
    const originalBpm = Number.isFinite(this.sequence?.originalBpm)
      ? this.sequence?.originalBpm ?? 120
      : 120;
    return {
      playing: this.playing,
      paused: this.paused,
      sourceTime: Number.isFinite(this.sourceTime) ? this.sourceTime : 0,
      duration,
      loop: this.loop,
      speed: this.speed,
      originalBpm,
      auditionBpm: originalBpm * this.speed,
      meter: 0,
      activeVoices: this.voices.size,
      outputMode: this.outputMode,
      outputId: this.midiOutputId,
      midiOutputs: this.midiOutputs,
      midiSupported: this.midiSupported,
      midiError: this.midiError,
      volume: this.volume,
      error: this.lastError,
      hasSequence: !!this.sequence,
      sequenceName: this.sequence?.name ?? '',
      trackCount: this.sequence?.tracks.length ?? 0,
      noteCount: this.sequence?.notes.length ?? 0,
    };
  }

  private lastError: string | null = null;

  private emit(force = false): void {
    const now = performance.now();
    if (!force && now - this.lastEmit < 22) return;
    this.lastEmit = now;
    const meter = this.readMeter();
    const rawCurrent = this.currentSourceTime();
    const current = Number.isFinite(rawCurrent) ? rawCurrent : 0;
    this.snapshot = {
      ...this.buildSnapshot(),
      sourceTime: current,
      meter,
      activeVoices: this.voices.size,
      error: this.lastError,
    };
    for (const listener of this.listeners) {
      try {
        listener();
      } catch (error) {
        // Never let one observer take down the scheduler.
        console.error('SKEER MIDI VAULT engine listener failed', error);
      }
    }
  }

  // ----------------------------------------------------------------- loading
  setSequence(sequence: EngineSequence | null, options?: { keepTime?: boolean }): void {
    this.stopAllNotes();
    this.stopClock();
    this.cancelTempoRestart();
    this.scrubbing = false;
    this.scrubWasPlaying = false;
    this.playing = false;
    this.paused = false;
    this.sequence = sequence
      ? {
        ...sequence,
        duration: Number.isFinite(sequence.duration) && sequence.duration > 0
          ? sequence.duration
          : 0.05,
        originalBpm: Number.isFinite(sequence.originalBpm)
          ? clamp(sequence.originalBpm, 1, 1000)
          : 120,
      }
      : null;
    this.sourceTime = options?.keepTime
      ? clamp(this.sourceTime, 0, this.sequence?.duration ?? 0)
      : 0;
    this.speed = 1;
    this.cancelEndTimer();
    this.noteCursor = 0;
    this.passComplete = false;
    this.emit(true);
  }

  setVolume(volume: number): void {
    if (!Number.isFinite(volume)) return;
    this.volume = clamp(volume, 0, 1);
    if (this.master) this.master.gain.value = this.volume;
    this.emit(true);
  }

  setLoop(loop: boolean): void {
    if (this.loop === loop) return;
    this.loop = loop;
    if (this.playing) {
      const time = this.currentSourceTime();
      this.restartAt(time);
    }
    this.emit(true);
  }

  setAuditionBpm(bpm: number): void {
    if (!this.sequence || !Number.isFinite(bpm)) return;
    const nextSpeed = clamp(bpm / Math.max(1, this.sequence.originalBpm), 0.2, 3.5);
    if (!Number.isFinite(nextSpeed) || Math.abs(nextSpeed - this.speed) < 0.0001) return;
    this.speed = nextSpeed;
    if (this.playing) {
      // Dragging the tempo knob emits dozens of updates per second. Restarting
      // the audio graph on every pointermove can make the browser's Web Audio
      // renderer crash to a blank tab. Let the schedule settle, then restart
      // once from the current source time. The knob's pointer-up flushes it.
      this.scheduleTempoRestart();
    }
    this.emit(true);
  }

  flushTempoAdjustment(): void {
    if (!this.playing || !this.sequence) {
      this.cancelTempoRestart();
      return;
    }
    this.cancelTempoRestart();
    this.restartAt(this.currentSourceTime());
  }

  private scheduleTempoRestart(): void {
    this.cancelTempoRestart();
    this.tempoRestartTimer = window.setTimeout(() => {
      this.tempoRestartTimer = null;
      if (!this.playing || !this.sequence) return;
      this.restartAt(this.currentSourceTime());
      this.emit(true);
    }, 140);
  }

  private cancelTempoRestart(): void {
    if (this.tempoRestartTimer !== null) {
      window.clearTimeout(this.tempoRestartTimer);
      this.tempoRestartTimer = null;
    }
  }

  setTrackFilter(muted: Iterable<string>, solo: Iterable<string>): void {
    this.muted = new Set(muted);
    this.solo = new Set(solo);
    if (this.playing) {
      for (const voice of [...this.voices]) {
        if (!this.isAudible(voice.trackKey)) this.releaseVoice(voice);
      }
      for (const [key, active] of [...this.midiActive.entries()]) {
        if (!this.isAudible(active.trackKey)) {
          this.sendMidiNoteOff(active.channel, active.pitch);
          this.midiActive.delete(key);
        }
      }
    }
    this.emit(true);
  }

  // ----------------------------------------------------------------- transport
  async play(): Promise<void> {
    if (!this.sequence || this.sequence.notes.length === 0) return;
    if (!Number.isFinite(this.sequence.duration) || this.sequence.duration <= 0) return;
    this.lastError = null;
    try {
      await this.ensureAudio();
      if (!this.sequence) return;
      const duration = this.sequence.duration;
      let startAt = Number.isFinite(this.sourceTime) ? this.sourceTime : 0;
      if (startAt >= duration - 0.01) startAt = 0;
      this.beginPlayback(startAt);
    } catch (error) {
      this.lastError = error instanceof Error ? error.message : String(error);
      this.paused = false;
      this.playing = false;
      this.emit(true);
    }
  }

  pause(): void {
    if (!this.playing) return;
    this.cancelTempoRestart();
    this.scrubbing = false;
    this.scrubWasPlaying = false;
    this.sourceTime = this.currentSourceTime();
    this.playing = false;
    this.paused = this.sourceTime > 0;
    this.stopAllNotes();
    this.stopClock();
    this.cancelEndTimer();
    this.emit(true);
  }

  stop(): void {
    this.cancelTempoRestart();
    this.scrubbing = false;
    this.scrubWasPlaying = false;
    this.playing = false;
    this.paused = false;
    this.sourceTime = 0;
    this.stopAllNotes();
    this.stopClock();
    this.cancelEndTimer();
    this.emit(true);
  }

  seek(seconds: number): void {
    if (this.scrubbing) {
      this.scrubTo(seconds);
      return;
    }
    if (!this.sequence || !Number.isFinite(seconds)) return;
    const duration = Number.isFinite(this.sequence.duration) ? this.sequence.duration : 0;
    if (duration <= 0) return;
    const target = clamp(seconds, 0, duration);
    if (this.playing) {
      this.restartAt(target);
    } else {
      this.sourceTime = target;
      this.paused = target > 0;
      this.emit(true);
    }
  }

  /**
   * Interactive scrubbing: pause the audio scheduler once, move the playhead
   * cheaply, then resume once the pointer is released. This keeps a drag across
   * the piano roll or seek bar from restarting the whole audio graph on every
   * pointermove (which can stress the browser's Web Audio renderer).
   */
  beginScrub(): void {
    if (!this.sequence || this.scrubbing) return;
    this.scrubbing = true;
    this.scrubWasPlaying = this.playing;
    this.cancelTempoRestart();
    if (this.playing) {
      this.sourceTime = this.currentSourceTime();
      this.playing = false;
      this.paused = false;
      this.stopAllNotes();
      this.stopClock();
      this.cancelEndTimer();
      if (this.schedulerTimer !== null) {
        window.clearInterval(this.schedulerTimer);
        this.schedulerTimer = null;
      }
      this.emit(true);
    }
  }

  scrubTo(seconds: number): void {
    if (!this.scrubbing || !this.sequence || !Number.isFinite(seconds)) return;
    const duration = Number.isFinite(this.sequence.duration) ? this.sequence.duration : 0;
    if (duration <= 0) return;
    this.sourceTime = clamp(seconds, 0, duration);
    this.paused = false;
    this.emit(true);
  }

  endScrub(): void {
    if (!this.scrubbing) return;
    const resume = this.scrubWasPlaying;
    this.scrubbing = false;
    this.scrubWasPlaying = false;
    if (resume) {
      void this.play();
    } else {
      this.paused = this.sourceTime > 0;
      this.emit(true);
    }
  }

  isScrubbing(): boolean {
    return this.scrubbing;
  }

  seekFraction(fraction: number): void {
    if (!this.sequence) return;
    this.seek(clamp(fraction, 0, 1) * this.sequence.duration);
  }

  private beginPlayback(startAt: number): void {
    if (!this.context || !this.sequence) return;
    const context = this.context;
    this.cancelTempoRestart();
    this.scrubbing = false;
    this.scrubWasPlaying = false;
    if (!Number.isFinite(startAt)) startAt = 0;
    startAt = clamp(startAt, 0, this.sequence.duration);
    this.sourceTime = startAt;
    this.anchorSource = startAt;
    this.anchorCtx = context.currentTime + 0.06;
    this.passStartSource = startAt;
    this.passStartCtx = this.anchorCtx;
    this.passComplete = false;
    this.noteCursor = this.firstNoteAtOrAfter(startAt);
    this.playing = true;
    this.paused = false;
    this.cancelEndTimer();
    this.startClock();
    this.sendMidiProgramChanges();
    this.scheduleAhead();
    if (this.schedulerTimer !== null) window.clearInterval(this.schedulerTimer);
    this.schedulerTimer = window.setInterval(() => this.scheduleAhead(), SCHEDULER_INTERVAL_MS);
    this.emit(true);
  }

  private restartAt(time: number): void {
    if (!this.sequence) return;
    const duration = Number.isFinite(this.sequence.duration) ? this.sequence.duration : 0;
    if (duration <= 0) return;
    const safeTime = Number.isFinite(time) ? clamp(time, 0, duration) : 0;
    this.stopAllNotes();
    this.cancelEndTimer();
    if (this.schedulerTimer !== null) {
      window.clearInterval(this.schedulerTimer);
      this.schedulerTimer = null;
    }
    const context = this.context;
    if (!context) return;
    this.anchorSource = safeTime;
    this.anchorCtx = context.currentTime + 0.05;
    this.sourceTime = this.anchorSource;
    this.passStartSource = this.anchorSource;
    this.passStartCtx = this.anchorCtx;
    this.noteCursor = this.firstNoteAtOrAfter(this.anchorSource);
    this.passComplete = false;
    this.playing = true;
    this.paused = false;
    this.startClock();
    this.sendMidiProgramChanges();
    this.scheduleAhead();
    this.schedulerTimer = window.setInterval(() => this.scheduleAhead(), SCHEDULER_INTERVAL_MS);
    this.emit(true);
  }

  private firstNoteAtOrAfter(time: number): number {
    if (!this.sequence) return 0;
    const notes = this.sequence.notes;
    let low = 0;
    let high = notes.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (notes[mid].t < time - 0.001) low = mid + 1;
      else high = mid;
    }
    return low;
  }

  // ----------------------------------------------------------------- scheduling
  private scheduleAhead(): void {
    if (!this.playing || !this.context || !this.sequence) return;
    const context = this.context;
    if (!Number.isFinite(context.currentTime)) return;
    const speed = Number.isFinite(this.speed) && this.speed > 0.01 ? this.speed : 1;
    const horizon = context.currentTime + LOOKAHEAD;
    const notes = this.sequence.notes;
    let guard = 0;
    while (guard++ < 20000) {
      if (!this.playing) return;
      if (this.noteCursor < notes.length) {
        const note = notes[this.noteCursor];
        if (!Number.isFinite(note.t) || !Number.isFinite(note.l)) {
          this.stats.skippedNotes += 1;
          this.noteCursor += 1;
          continue;
        }
        const eventCtx = this.passStartCtx + (note.t - this.passStartSource) / speed;
        if (!Number.isFinite(eventCtx)) {
          this.stats.skippedNotes += 1;
          this.noteCursor += 1;
          continue;
        }
        if (eventCtx > horizon) break;
        const track = this.trackByKey(note.trackKey);
        if (track && this.isAudible(note.trackKey)) {
          const remainingPass = this.loop
            ? Math.max(0, (this.sequence.duration - note.t) / speed)
            : Number.POSITIVE_INFINITY;
          const duration = Math.min(note.l / speed, remainingPass);
          const late = eventCtx < context.currentTime - 0.02;
          if (late) {
            this.stats.lateNotes += 1;
          } else if (Number.isFinite(duration) && duration > 0.012) {
            const start = Math.max(eventCtx, context.currentTime + 0.008);
            if (Number.isFinite(start) && Number.isFinite(duration)) {
              this.scheduleNote(note, track, start, duration);
            } else {
              this.stats.skippedNotes += 1;
            }
          } else {
            this.stats.skippedNotes += 1;
          }
        }
        this.noteCursor += 1;
        continue;
      }
      // All notes in this pass have been scheduled.
      const passEndCtx = this.passStartCtx +
        (this.sequence.duration - this.passStartSource) / speed;
      if (!Number.isFinite(passEndCtx)) {
        this.playing = false;
        this.lastError = 'Playback timing became invalid. Press Play to restart.';
        this.stopAllNotes();
        this.stopClock();
        this.emit(true);
        return;
      }
      if (this.loop) {
        if (passEndCtx > horizon) {
          this.passComplete = true;
          break;
        }
        this.passStartCtx = passEndCtx;
        this.passStartSource = 0;
        this.noteCursor = 0;
        this.passComplete = false;
        this.stats.scheduledPasses += 1;
        continue;
      }
      this.passComplete = true;
      if (this.endTimer === null) {
        const delay = Math.max(0, (passEndCtx - context.currentTime) * 1000 + 35);
        this.endTimer = window.setTimeout(() => this.naturalEnd(), delay);
      }
      break;
    }
  }

  private naturalEnd(): void {
    this.endTimer = null;
    if (!this.playing) return;
    this.cancelTempoRestart();
    this.scrubbing = false;
    this.scrubWasPlaying = false;
    this.playing = false;
    this.paused = false;
    this.sourceTime = 0;
    this.stopAllNotes();
    this.stopClock();
    if (this.schedulerTimer !== null) {
      window.clearInterval(this.schedulerTimer);
      this.schedulerTimer = null;
    }
    this.emit(true);
  }

  private ensureAudibleTrack(trackKey: string): EngineTrack | null {
    const track = this.trackByKey(trackKey);
    if (!track || !this.isAudible(trackKey)) return null;
    return track;
  }

  private isAudible(trackKey: string): boolean {
    if (this.muted.has(trackKey)) return false;
    if (this.solo.size > 0 && !this.solo.has(trackKey)) return false;
    return true;
  }

  private trackByKey(trackKey: string): EngineTrack | null {
    return this.sequence?.tracks.find((track) => track.key === trackKey) ?? null;
  }

  private scheduleNote(note: PreviewNote, track: EngineTrack, start: number, duration: number): void {
    if (
      !Number.isFinite(start)
      || !Number.isFinite(duration)
      || !Number.isFinite(note.p)
      || !Number.isFinite(note.v)
    ) {
      this.stats.skippedNotes += 1;
      return;
    }
    if (this.outputMode === 'midi') {
      this.scheduleMidi(note, track, start, duration);
      return;
    }
    this.scheduleSynth(note, track, start, duration);
  }

  private scheduleSynth(note: PreviewNote, track: EngineTrack, start: number, duration: number): void {
    if (!this.context || !this.master) return;
    if (this.voices.size >= MAX_POLYPHONY) {
      this.stats.skippedNotes += 1;
      return;
    }
    const isDrum = track.channel === 9 || track.instrument === 'Drums/percussion' ||
      track.role.startsWith('Drum');
    const context = this.context;
    const gain = context.createGain();
    const pan = context.createStereoPanner();
    const trackHash = this.trackNumber(track.key) || 0;
    pan.pan.value = clamp(((trackHash % 5) - 2) * 0.08, -0.35, 0.35);
    gain.connect(pan);
    pan.connect(this.master);
    const nodes: AudioScheduledSourceNode[] = [];
    const velocity = clamp(note.v / 127, 0.12, 1);
    try {
      if (isDrum) {
        this.buildDrum(note.p, velocity, start, duration, gain, nodes);
      } else {
        this.buildMelodic(track, note.p, velocity, start, duration, gain, nodes);
      }
    } catch {
      gain.disconnect();
      pan.disconnect();
      return;
    }
    const voice: Voice = {
      trackKey: track.key,
      nodes,
      gain,
      startedAt: start,
      cleanup: () => {
        this.voices.delete(voice);
      },
    };
    if (nodes.length > 0) {
      const primary = nodes[0];
      primary.onended = () => voice.cleanup();
    }
    this.voices.add(voice);
    this.stats.scheduledNotes += 1;
  }

  private buildMelodic(
    track: EngineTrack,
    pitch: number,
    velocity: number,
    start: number,
    duration: number,
    gain: GainNode,
    nodes: AudioScheduledSourceNode[],
  ): void {
    if (!this.context) return;
    const context = this.context;
    const family = track.instrument;
    const frequency = noteFrequency(pitch);
    const pluck = family === 'Guitar/plucked';
    const pad = track.role === 'Pad/sustained harmony';
    const strings = family === 'Strings';
    const attack = pad || strings ? 0.12 : pluck ? 0.004 : 0.012;
    const release = pad || strings ? 0.32 : pluck ? 0.08 : 0.12;
    const peak = clamp(velocity, 0.1, 1) * (pad ? 0.035 : 0.07);
    const end = start + Math.max(0.02, duration);
    const sustainedEnd = Math.max(start + attack + 0.02, end - release);
    const filter = context.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = pluck ? 3200 : family === 'Bass' ? 900 : 4800;
    filter.Q.value = 0.4;
    filter.connect(gain);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.linearRampToValueAtTime(peak, start + attack);
    if (pluck) {
      gain.gain.exponentialRampToValueAtTime(peak * 0.25, start + Math.min(0.12, duration));
    }
    gain.gain.setValueAtTime(Math.max(0.0001, peak * 0.72), sustainedEnd);
    gain.gain.exponentialRampToValueAtTime(0.0001, end);

    const waveform: OscillatorType = family === 'Bass'
      ? 'sine'
      : family === 'Brass/woodwinds'
        ? 'square'
        : family === 'Synth'
          ? 'sawtooth'
          : family === 'Strings'
            ? 'sawtooth'
            : 'triangle';
    const main = context.createOscillator();
    main.type = waveform;
    main.frequency.setValueAtTime(frequency, start);
    if (family === 'Bass') {
      main.frequency.setValueAtTime(frequency * 0.5, start);
      main.frequency.exponentialRampToValueAtTime(frequency, start + 0.03);
    }
    main.connect(filter);
    main.start(start);
    main.stop(end + 0.06);
    nodes.push(main);

    if (family === 'Synth' || strings) {
      const detune = context.createOscillator();
      detune.type = family === 'Synth' ? 'square' : 'sawtooth';
      detune.frequency.setValueAtTime(frequency, start);
      detune.detune.setValueAtTime(strings ? -7 : 8, start);
      const detuneGain = context.createGain();
      detuneGain.gain.value = family === 'Synth' ? 0.28 : 0.4;
      detune.connect(detuneGain);
      detuneGain.connect(filter);
      detune.start(start);
      detune.stop(end + 0.04);
      nodes.push(detune);
    }
    if (family === 'Piano/keys' || family === 'Brass/woodwinds') {
      const harmonic = context.createOscillator();
      harmonic.type = 'sine';
      harmonic.frequency.setValueAtTime(frequency * 2, start);
      const harmonicGain = context.createGain();
      harmonicGain.gain.value = family === 'Piano/keys' ? 0.35 : 0.18;
      harmonic.connect(harmonicGain);
      harmonicGain.connect(filter);
      harmonic.start(start);
      harmonic.stop(end + 0.03);
      nodes.push(harmonic);
    }
  }

  private buildDrum(
    pitch: number,
    velocity: number,
    start: number,
    duration: number,
    gain: GainNode,
    nodes: AudioScheduledSourceNode[],
  ): void {
    if (!this.context) return;
    const context = this.context;
    const end = start + Math.max(0.06, Math.min(duration, 1.0));
    const noise = () => {
      if (!this.noiseBuffer) {
        const buffer = context.createBuffer(1, context.sampleRate, context.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
        this.noiseBuffer = buffer;
      }
      const source = context.createBufferSource();
      source.buffer = this.noiseBuffer;
      return source;
    };
    const env = (peak: number, attack: number, decay: number) => {
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.linearRampToValueAtTime(peak * velocity, start + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + Math.max(attack + 0.03, decay));
    };
    if ([35, 36, 41].includes(pitch)) {
      const osc = context.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(145, start);
      osc.frequency.exponentialRampToValueAtTime(44, start + 0.12);
      env(0.24, 0.002, 0.38);
      osc.connect(gain);
      osc.start(start);
      osc.stop(end + 0.02);
      nodes.push(osc);
      return;
    }
    if ([38, 40].includes(pitch)) {
      const source = noise();
      const filter = context.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.value = 950;
      source.connect(filter);
      filter.connect(gain);
      env(0.13, 0.002, 0.17);
      source.start(start);
      source.stop(end + 0.02);
      nodes.push(source);
      const body = context.createOscillator();
      body.type = 'triangle';
      body.frequency.setValueAtTime(190, start);
      env(0.08, 0.001, 0.12);
      body.connect(gain);
      body.start(start);
      body.stop(end + 0.02);
      nodes.push(body);
      return;
    }
    if ([39, 37].includes(pitch)) {
      const source = noise();
      const filter = context.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.value = 1600;
      filter.Q.value = 0.9;
      source.connect(filter);
      filter.connect(gain);
      env(0.16, 0.002, 0.18);
      source.start(start);
      source.stop(end + 0.02);
      nodes.push(source);
      return;
    }
    if ([42, 44, 46].includes(pitch)) {
      const source = noise();
      const filter = context.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.value = 7200;
      source.connect(filter);
      filter.connect(gain);
      env(0.065, 0.001, pitch === 46 ? 0.22 : 0.055);
      source.start(start);
      source.stop(end + 0.02);
      nodes.push(source);
      return;
    }
    if ([49, 52, 55, 57, 51].includes(pitch)) {
      const source = noise();
      const filter = context.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.value = 4800;
      source.connect(filter);
      filter.connect(gain);
      env(0.08, 0.003, 0.4);
      source.start(start);
      source.stop(end + 0.3);
      nodes.push(source);
      return;
    }
    if ([45, 47, 50].includes(pitch)) {
      const osc = context.createOscillator();
      const frequency = pitch === 45 ? 96 : pitch === 47 ? 128 : 174;
      osc.type = 'sine';
      osc.frequency.setValueAtTime(frequency, start);
      osc.frequency.exponentialRampToValueAtTime(frequency * 0.72, start + 0.2);
      env(0.15, 0.002, 0.24);
      osc.connect(gain);
      osc.start(start);
      osc.stop(end + 0.04);
      nodes.push(osc);
      return;
    }
    const osc = context.createOscillator();
    osc.type = 'square';
    osc.frequency.value = noteFrequency(pitch);
    env(0.05, 0.002, 0.09);
    osc.connect(gain);
    osc.start(start);
    osc.stop(end + 0.02);
    nodes.push(osc);
  }

  private trackNumber(key: string): number {
    const match = key.match(/:(\d+)$/);
    return match ? Number(match[1]) : 0;
  }

  private releaseVoice(voice: Voice): void {
    const now = this.context?.currentTime ?? 0;
    try {
      voice.gain.gain.cancelScheduledValues(now);
      voice.gain.gain.setTargetAtTime(0.0001, now, 0.008);
    } catch {
      // ignore
    }
    for (const node of voice.nodes) {
      try {
        node.stop(now + 0.025);
      } catch {
        // A scheduled source may already have ended.
      }
    }
    this.voices.delete(voice);
  }

  private stopAllNotes(): void {
    for (const voice of [...this.voices]) this.releaseVoice(voice);
    this.voices.clear();
    for (const timer of this.midiTimers) window.clearTimeout(timer);
    this.midiTimers.clear();
    for (const active of this.midiActive.values()) {
      this.sendMidiNoteOff(active.channel, active.pitch);
    }
    this.midiActive.clear();
    this.stats.activeVoices = 0;
  }

  // -------------------------------------------------------------------- clock
  private currentSourceTime(): number {
    if (!this.sequence) return 0;
    const duration = Number.isFinite(this.sequence.duration) ? this.sequence.duration : 0;
    if (duration <= 0) return 0;
    if (!this.playing || !this.context) {
      return Number.isFinite(this.sourceTime) ? clamp(this.sourceTime, 0, duration) : 0;
    }
    const speed = Number.isFinite(this.speed) && this.speed > 0.01 ? this.speed : 1;
    const elapsed = Math.max(0, this.context.currentTime - this.anchorCtx) * speed;
    const raw = this.anchorSource + elapsed;
    if (!Number.isFinite(raw)) return 0;
    if (this.loop) {
      return ((raw % duration) + duration) % duration;
    }
    return clamp(raw, 0, duration);
  }

  private startClock(): void {
    this.stopClock();
    this.clockTimer = window.setInterval(() => {
      if (!this.playing) return;
      const time = this.currentSourceTime();
      if (!Number.isFinite(time)) {
        this.failAudio('Playback timing became invalid. Press Play to restart the preview.');
        return;
      }
      this.sourceTime = time;
      if (!this.loop && this.sequence && time >= this.sequence.duration - 0.008) {
        this.naturalEnd();
        return;
      }
      this.emit();
    }, 33);
  }

  private failAudio(message: string): void {
    this.cancelTempoRestart();
    this.scrubbing = false;
    this.scrubWasPlaying = false;
    this.playing = false;
    this.paused = false;
    this.lastError = message;
    this.stopAllNotes();
    this.stopClock();
    this.cancelEndTimer();
    if (this.schedulerTimer !== null) {
      window.clearInterval(this.schedulerTimer);
      this.schedulerTimer = null;
    }
    this.emit(true);
  }

  private stopClock(): void {
    if (this.clockTimer !== null) {
      window.clearInterval(this.clockTimer);
      this.clockTimer = null;
    }
  }

  private cancelEndTimer(): void {
    if (this.endTimer !== null) {
      window.clearTimeout(this.endTimer);
      this.endTimer = null;
    }
  }

  // --------------------------------------------------------------- audio graph
  private async ensureAudio(): Promise<void> {
    if (this.context) {
      const state = this.context.state as string;
      if (state === 'closed') {
        this.context = null;
        this.master = null;
        this.compressor = null;
        this.analyser = null;
        this.meterData = null;
        this.noiseBuffer = null;
      } else {
        if (state === 'suspended') {
          try {
            await this.context.resume();
          } catch {
            throw new Error('The audio device is unavailable. Check the output device and press Play again.');
          }
        }
        if ((this.context.state as string) === 'closed') {
          this.context = null;
          this.master = null;
          throw new Error('The audio device stopped. Press Play to start a new audio session.');
        }
        return;
      }
    }
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) throw new Error('This browser does not provide the Web Audio API.');
    const context = new Ctor({ latencyHint: 'interactive' });
    const master = context.createGain();
    master.gain.value = this.volume;
    const compressor = context.createDynamicsCompressor();
    compressor.threshold.value = -14;
    compressor.knee.value = 18;
    compressor.ratio.value = 4;
    compressor.attack.value = 0.004;
    compressor.release.value = 0.18;
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.7;
    master.connect(compressor);
    compressor.connect(analyser);
    analyser.connect(context.destination);
    this.context = context;
    this.master = master;
    this.compressor = compressor;
    this.analyser = analyser;
    this.meterData = new Uint8Array(analyser.fftSize);
    context.onstatechange = () => {
      if (this.context !== context) return;
      const state = context.state as string;
      if (state === 'closed') {
        this.context = null;
        this.master = null;
        this.compressor = null;
        this.analyser = null;
        this.meterData = null;
        this.failAudio('The audio device stopped. Press Play to start a new preview session.');
      } else if (state === 'interrupted') {
        this.failAudio('The audio session was interrupted. Press Play to resume the preview.');
      }
    };
    if (context.state === 'suspended') {
      try {
        await context.resume();
      } catch {
        const message = 'The browser could not start the audio device. Check the output device and press Play again.';
        this.failAudio(message);
        throw new Error(message);
      }
    }
  }

  private readMeter(): number {
    if (!this.analyser || !this.meterData) return 0;
    try {
      this.analyser.getByteTimeDomainData(this.meterData);
      let sum = 0;
      for (let i = 0; i < this.meterData.length; i += 1) {
        const value = (this.meterData[i] - 128) / 128;
        sum += value * value;
      }
      return clamp(Math.sqrt(sum / this.meterData.length) * 3.6, 0, 1);
    } catch {
      return 0;
    }
  }

  // --------------------------------------------------------------------- Web MIDI
  async requestMidiAccess(): Promise<MidiOutputInfo[]> {
    const nav = navigator as Navigator & {
      requestMIDIAccess?: (options?: { sysex?: boolean }) => Promise<MidiAccessLike>;
    };
    if (!nav.requestMIDIAccess) {
      this.midiSupported = false;
      this.midiError = 'Web MIDI is not available in this browser. Preview synth remains available.';
      this.emit(true);
      throw new Error(this.midiError);
    }
    try {
      const access = await nav.requestMIDIAccess({ sysex: false });
      this.midiAccess = access as unknown as MidiAccessLike;
      this.midiSupported = true;
      this.midiError = null;
      this.refreshMidiOutputs();
      this.emit(true);
      return this.midiOutputs;
    } catch (error) {
      this.midiSupported = false;
      this.midiError = error instanceof Error ? error.message : 'MIDI access was not granted';
      this.emit(true);
      throw error;
    }
  }

  private refreshMidiOutputs(): void {
    if (!this.midiAccess) return;
    this.midiOutputs = [];
    for (const [id, output] of this.midiAccess.outputs) {
      this.midiOutputs.push({
        id,
        name: output.name || `MIDI ${id}`,
        manufacturer: output.manufacturer || '',
      });
    }
  }

  async setOutput(outputId: string | null): Promise<void> {
    if (this.outputMode === 'midi' || outputId) {
      this.pause();
      this.stopAllNotes();
    }
    if (outputId === null) {
      this.outputMode = 'synth';
      this.midiOutputId = null;
      this.stats.outputMode = 'synth';
      this.emit(true);
      return;
    }
    if (!this.midiAccess) await this.requestMidiAccess();
    if (!this.midiAccess?.outputs.has(outputId)) {
      throw new Error('The selected MIDI output is no longer available.');
    }
    this.outputMode = 'midi';
    this.midiOutputId = outputId;
    this.stats.outputMode = 'midi';
    this.emit(true);
  }

  private midiOutput(): MidiPortLike | null {
    if (!this.midiAccess || !this.midiOutputId) return null;
    return this.midiAccess.outputs.get(this.midiOutputId) ?? null;
  }

  private sendMidiProgramChanges(): void {
    if (this.outputMode !== 'midi' || !this.sequence) return;
    const output = this.midiOutput();
    if (!output) return;
    const sentChannels = new Set<number>();
    for (const track of this.sequence.tracks) {
      if (!this.isAudible(track.key)) continue;
      if (track.program === null || track.program === undefined) continue;
      const channel = clamp(track.channel, 0, 15);
      if (sentChannels.has(channel)) continue;
      sentChannels.add(channel);
      try {
        output.send([0xc0 | channel, clamp(Math.round(track.program), 0, 127)]);
      } catch {
        // A disconnected device is handled by the UI/output status.
      }
    }
  }

  private scheduleMidi(note: PreviewNote, track: EngineTrack, audioStart: number, duration: number): void {
    if (!this.context) return;
    const delay = Math.max(0, (audioStart - this.context.currentTime) * 1000);
    const output = this.midiOutput();
    if (!output) return;
    const channel = clamp(track.channel, 0, 15);
    const pitch = clamp(Math.round(note.p), 0, 127);
    const velocity = clamp(Math.round(note.v), 1, 127);
    const key = `${track.key}:${channel}:${pitch}`;
    const onTimer = window.setTimeout(() => {
      this.midiTimers.delete(onTimer);
      output.send([0x90 | channel, pitch, velocity]);
      this.midiActive.set(key, { channel, pitch, trackKey: track.key });
      const hold = Math.max(20, duration * 1000);
      const offTimer = window.setTimeout(() => {
        this.midiTimers.delete(offTimer);
        output.send([0x80 | channel, pitch, 0]);
        this.midiActive.delete(key);
      }, hold);
      this.midiTimers.add(offTimer);
    }, delay);
    this.midiTimers.add(onTimer);
    this.stats.scheduledNotes += 1;
  }

  private sendMidiNoteOff(channel: number, pitch: number): void {
    const output = this.midiOutput();
    if (!output) return;
    try {
      output.send([0x80 | channel, pitch, 0]);
    } catch {
      // Output disappeared; nothing left to release.
    }
  }

  getDebugStats(): EngineDebugStats {
    return { ...this.stats, activeVoices: this.voices.size, outputMode: this.outputMode };
  }

  resetDebugStats(): void {
    this.stats = {
      scheduledNotes: 0,
      lateNotes: 0,
      skippedNotes: 0,
      activeVoices: 0,
      scheduledPasses: 0,
      outputMode: this.outputMode,
    };
  }

  getSequenceTracks(): EngineTrack[] {
    return this.sequence?.tracks.slice() ?? [];
  }
}

export function sequenceFromPreview(
  sequence: PreviewSequence,
  labels: Array<{
    sequence_index: number;
    track_index: number;
    instrument: string;
    role: string;
  }>,
): EngineSequence {
  const labelMap = new Map(
    (Array.isArray(labels) ? labels : [])
      .filter((row) => row.sequence_index === sequence.index)
      .map((row) => [row.track_index, row]),
  );
  const duration = Number.isFinite(sequence.duration_seconds) && sequence.duration_seconds > 0
    ? sequence.duration_seconds
    : 0.05;
  const tracks: EngineTrack[] = (Array.isArray(sequence.tracks) ? sequence.tracks : [])
    .filter((track) => Number.isFinite(track.track_index))
    .map((track) => {
      const label = labelMap.get(track.track_index);
      const channel = Number.isFinite(track.channel) ? clamp(Math.round(track.channel), 0, 15) : 0;
      return {
        key: `${sequence.index}:${track.track_index}`,
        trackIndex: track.track_index,
        sequenceIndex: sequence.index,
        name: track.name || `Channel ${channel + 1}`,
        channel,
        instrument: label?.instrument || 'Unknown',
        role: label?.role || 'Unknown',
        program: Number.isFinite(track.program) ? clamp(Math.round(track.program as number), 0, 127) : null,
      };
    });
  const trackKeyByIndex = new Map(tracks.map((track) => [track.trackIndex, track.key]));
  const notes = (Array.isArray(sequence.tracks) ? sequence.tracks : []).flatMap((track) => {
    const key = trackKeyByIndex.get(track.track_index) ?? `${sequence.index}:${track.track_index}`;
    return (Array.isArray(track.notes) ? track.notes : [])
      .filter((note) => (
        Number.isFinite(note.t)
        && Number.isFinite(note.l)
        && Number.isFinite(note.p)
        && Number.isFinite(note.v)
        && note.t >= 0
        && note.l > 0
      ))
      .map((note) => ({
        ...note,
        t: clamp(note.t, 0, duration),
        l: clamp(note.l, 0.005, Math.max(0.005, duration)),
        p: clamp(Math.round(note.p), 0, 127),
        v: clamp(Math.round(note.v), 1, 127),
        trackKey: key,
      }));
  });
  notes.sort((a, b) => a.t - b.t || a.p - b.p);
  const tempos = Array.isArray(sequence.tempos) ? sequence.tempos : [];
  const firstTempo = tempos.find((tempo) => tempo.embedded) || tempos[0];
  const originalBpm = Number.isFinite(firstTempo?.bpm)
    ? clamp(firstTempo?.bpm as number, 1, 1000)
    : 120;
  return {
    key: `seq-${sequence.index}`,
    name: sequence.name || 'Full arrangement',
    duration,
    originalBpm,
    timingType: sequence.timing_type,
    tracks,
    notes,
  };
}
