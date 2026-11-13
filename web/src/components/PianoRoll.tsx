import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { PreviewNote, PreviewSequence, TrackRow } from '../types';
import type { PreviewEngine } from '../audio/engine';
import { useEngineSnapshot } from '../audio/useEngine';
import { trackColor } from '../lib/colors';
import { formatTime } from '../lib/format';
import { Button, IconButton } from './Common';
import { ChevronLeft, ChevronRight, DragIcon } from './Icons';

const GUTTER = 34;
const RIGHT_PAD = 12;
const TOP_PAD = 16;
const BOTTOM_PAD = 8;
const VELOCITY_HEIGHT = 34;
const MIN_HEIGHT = 232;
const MAX_CANVAS_WIDTH = 6000;
const MAX_DRAW_NOTES = 12000;

interface GridLine {
  seconds: number;
  major: boolean;
  label?: string;
}

function safeTempos(sequence: PreviewSequence): Array<{ beat: number; seconds: number; bpm: number }> {
  const raw = Array.isArray(sequence.tempos) ? sequence.tempos : [];
  const tempos = raw.filter((tempo) => (
    Number.isFinite(tempo.beat) && Number.isFinite(tempo.seconds) && Number.isFinite(tempo.bpm)
  ));
  return tempos.length ? tempos : [{ beat: 0, seconds: 0, bpm: 120 }];
}

function beatToSeconds(sequence: PreviewSequence, beat: number): number {
  const tempos = safeTempos(sequence);
  let entry = tempos[0];
  for (const tempo of tempos) {
    if (tempo.beat <= beat + 1e-8) entry = tempo;
    else break;
  }
  return entry.seconds + (beat - entry.beat) * (60 / Math.max(1, entry.bpm));
}

function buildGrid(sequence: PreviewSequence): GridLine[] {
  const duration = Number.isFinite(sequence.duration_seconds) && sequence.duration_seconds > 0
    ? sequence.duration_seconds
    : 0.1;
  if (sequence.timing_type === 'smpte') {
    const step = duration > 120 ? 30 : duration > 40 ? 10 : duration > 12 ? 5 : duration > 6 ? 2 : 1;
    const lines: GridLine[] = [];
    for (let second = 0; second <= duration + 0.001 && lines.length < 2048; second += step) {
      lines.push({
        seconds: second,
        major: Math.abs(second % (step * 2)) < 0.001,
        label: `${second}s`,
      });
    }
    return lines;
  }
  const rawTimeSignatures = Array.isArray(sequence.time_signatures) ? sequence.time_signatures : [];
  const timeSignatures = rawTimeSignatures.filter((signature) => (
    Number.isFinite(signature.beat)
    && Number.isFinite(signature.numerator)
    && Number.isFinite(signature.denominator)
    && signature.numerator > 0
    && signature.denominator > 0
  ));
  const safeSignatures = timeSignatures.length
    ? timeSignatures
    : [{ beat: 0, numerator: 4, denominator: 4, label: '4/4', tick: 0 } as PreviewSequence['time_signatures'][number]];
  const rawBeats = Number.isFinite(sequence.duration_beats) && (sequence.duration_beats as number) > 0
    ? sequence.duration_beats
    : duration * 2;
  const durationBeats = Math.max(0.1, rawBeats);
  const lines: GridLine[] = [];
  let beatCursor = 0;
  let tsIndex = 0;
  let current = safeSignatures[0];
  let bar = 1;
  while (beatCursor < durationBeats + 0.001 && lines.length < 1024) {
    while (tsIndex < safeSignatures.length && safeSignatures[tsIndex].beat <= beatCursor + 1e-6) {
      current = safeSignatures[tsIndex];
      tsIndex += 1;
    }
    const seconds = beatToSeconds(sequence, beatCursor);
    if (!Number.isFinite(seconds) || seconds > duration + 0.001) break;
    lines.push({ seconds, major: true, label: String(bar) });
    const beatsPerBar = current.numerator * 4 / current.denominator;
    const beatsPerBeat = 4 / current.denominator;
    if (!Number.isFinite(beatsPerBar) || beatsPerBar <= 0) break;
    if (beatsPerBar >= 2 && durationBeats / beatsPerBar < 42) {
      for (let inner = beatsPerBeat; inner < beatsPerBar - 1e-6; inner += beatsPerBeat) {
        const secondsInner = beatToSeconds(sequence, beatCursor + inner);
        if (!Number.isFinite(secondsInner)) break;
        lines.push({ seconds: secondsInner, major: false });
        if (lines.length >= 2048) break;
      }
    }
    beatCursor += beatsPerBar;
    bar += 1;
  }
  return lines;
}

function noteLabelHeight(rowHeight: number): boolean {
  return rowHeight >= 8;
}

export function PianoRoll({
  sequence,
  tracks,
  engine,
  mutedTracks,
  soloTracks,
}: {
  sequence: PreviewSequence | null;
  tracks: TrackRow[];
  engine: PreviewEngine;
  mutedTracks: Set<string>;
  soloTracks: Set<string>;
}) {
  const snapshot = useEngineSnapshot(engine);
  const playing = snapshot.playing;
  const scrollRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [canvasWidth, setCanvasWidth] = useState(480);
  const [zoom, setZoom] = useState(1);
  const [showVelocity, setShowVelocity] = useState(true);
  const [focusedTrack, setFocusedTrack] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [canvasProblem, setCanvasProblem] = useState(false);
  const dragRef = useRef(false);
  const grid = useMemo(() => {
    if (!sequence) return [];
    try {
      return buildGrid(sequence);
    } catch (error) {
      console.error('SKEER MIDI VAULT could not build the piano-roll grid', error);
      return [];
    }
  }, [sequence]);
  const trackColorMap = useMemo(
    () => new Map(tracks.map((track) => [`${track.sequence_index}:${track.track_index}`, trackColor(track.track_index)])),
    [tracks],
  );
  const trackLabelMap = useMemo(
    () => new Map(tracks.map((track) => [`${track.sequence_index}:${track.track_index}`, track.name || `Channel ${track.channel + 1}`])),
    [tracks],
  );
  const rollData = useMemo(() => {
    const all: Array<PreviewNote & { trackKey: string }> = [];
    if (sequence && Array.isArray(sequence.tracks)) {
      for (const track of sequence.tracks) {
        if (!Number.isFinite(track.track_index) || !Array.isArray(track.notes)) continue;
        const trackKey = `${sequence.index}:${track.track_index}`;
        for (const note of track.notes) {
          if (
            Number.isFinite(note.t) && Number.isFinite(note.l)
            && Number.isFinite(note.p) && Number.isFinite(note.v)
          ) {
            all.push({ ...note, trackKey });
          }
        }
      }
    }
    const total = all.length;
    let drawn = all;
    if (all.length > MAX_DRAW_NOTES) {
      // Keep the shape of very dense files without trying to draw every note on
      // every animation frame. Playback still receives the complete sequence.
      const stride = all.length / MAX_DRAW_NOTES;
      drawn = Array.from({ length: MAX_DRAW_NOTES }, (_, index) => all[Math.floor(index * stride)]);
    }
    const pitches = drawn.map((note) => note.p);
    return {
      notes: drawn,
      total,
      sampled: drawn.length < total,
      pitchMin: pitches.length ? Math.min(72, ...pitches) - 2 : 50,
      pitchMax: pitches.length ? Math.max(72, ...pitches) + 2 : 74,
    };
  }, [sequence]);
  const duration = Math.max(0.1, sequence?.duration_seconds || 0.1);
  const playheadLimit = Number.isFinite(duration) ? duration : 0.1;
  const rawPlayhead = Number.isFinite(snapshot.sourceTime) ? snapshot.sourceTime : 0;
  const playhead = Math.min(playheadLimit, Math.max(0, rawPlayhead));
  const velocityVisible = showVelocity;
  const height = MIN_HEIGHT;
  const canvasCssWidth = Math.min(
    MAX_CANVAS_WIDTH,
    Math.max(280, Number.isFinite(canvasWidth) ? canvasWidth : 480) * Math.max(1, zoom),
  );
  const playheadFraction = playheadLimit > 0 ? clampFraction(playhead / playheadLimit) : 0;
  const playheadX = GUTTER + playheadFraction * (canvasCssWidth - GUTTER - RIGHT_PAD);

  useEffect(() => {
    setCanvasProblem(false);
    setDragging(false);
    dragRef.current = false;
  }, [sequence?.index]);

  useEffect(() => {
    const element = wrapRef.current;
    if (!element) return undefined;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width || 480;
      setCanvasWidth(Math.max(280, Number.isFinite(width) ? width : 480));
    });
    observer.observe(element);
    setCanvasWidth(Math.max(280, Number.isFinite(element.clientWidth) ? element.clientWidth : 480));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const onLost = (event: Event) => {
      event.preventDefault();
      setCanvasProblem(true);
    };
    const onRestored = () => {
      setCanvasProblem(false);
    };
    canvas.addEventListener('contextlost', onLost);
    canvas.addEventListener('contextrestored', onRestored);
    return () => {
      canvas.removeEventListener('contextlost', onLost);
      canvas.removeEventListener('contextrestored', onRestored);
    };
  }, []);

  useEffect(() => {
    setFocusedTrack(null);
    setZoom(1);
  }, [sequence?.index]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !sequence || canvasProblem) return;
    try {
      const dpr = Math.max(1, Number.isFinite(window.devicePixelRatio) ? window.devicePixelRatio : 1);
      const cssWidth = canvasCssWidth;
      const cssHeight = height;
      canvas.width = Math.max(1, Math.round(cssWidth * dpr));
      canvas.height = Math.max(1, Math.round(cssHeight * dpr));
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${cssHeight}px`;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawPianoRoll(ctx, {
        sequence,
        grid,
        width: cssWidth,
        height: cssHeight,
        zoom,
        showVelocity: velocityVisible,
        focusedTrack,
        mutedTracks,
        soloTracks,
        trackColorMap,
        notes: rollData.notes,
        pitchMin: rollData.pitchMin,
        pitchMax: rollData.pitchMax,
      });
    } catch (error) {
      // A drawing failure must never take down the whole application. Playback,
      // metadata and the rest of the library remain usable.
      console.error('SKEER MIDI VAULT piano-roll draw failed', error);
      setCanvasProblem(true);
    }
  }, [
    canvasCssWidth, height, sequence, grid, velocityVisible,
    focusedTrack, mutedTracks, soloTracks, trackColorMap, canvasProblem, rollData,
  ]);

  useEffect(() => {
    if (!playing || zoom <= 1) return;
    const scroller = scrollRef.current;
    if (!scroller) return;
    const plotWidth = scroller.scrollWidth - GUTTER - RIGHT_PAD;
    const x = GUTTER + (playhead / duration) * plotWidth;
    const left = scroller.scrollLeft;
    const right = left + scroller.clientWidth;
    if (x < left + GUTTER + 20) {
      scroller.scrollLeft = Math.max(0, x - GUTTER - 30);
    } else if (x > right - 36) {
      scroller.scrollLeft = x - scroller.clientWidth + 60;
    }
  }, [playhead, playing, zoom, duration]);

  const seekFromEvent = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!sequence) return;
    const canvas = canvasRef.current;
    const scroller = scrollRef.current;
    if (!canvas || !scroller) return;
    const rect = canvas.getBoundingClientRect();
    const usable = rect.width - GUTTER - RIGHT_PAD;
    const duration = Number.isFinite(sequence.duration_seconds) ? sequence.duration_seconds : 0.1;
    if (!Number.isFinite(rect.width) || !Number.isFinite(event.clientX) || usable <= 1 || duration <= 0) return;
    const localX = event.clientX - rect.left;
    const fraction = Math.max(0, Math.min(1, (localX - GUTTER) / usable));
    engine.scrubTo(fraction * Math.max(0.1, duration));
  };

  const finishScrub = (event?: ReactPointerEvent<HTMLCanvasElement>) => {
    dragRef.current = false;
    setDragging(false);
    engine.endScrub();
    if (event) {
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // ignore
      }
    }
  };

  const availableTracks = Array.isArray(sequence?.tracks) ? sequence.tracks : [];
  if (!sequence) {
    return (
      <div className="piano-roll piano-roll-empty">
        <div className="piano-roll-empty-mark">
          <img src="/brand/skeer-mark.png" alt="" />
        </div>
        <p>Select a file to see its musical shape.</p>
      </div>
    );
  }

  return (
    <div className="piano-roll">
      <div className="piano-roll-topline">
        <div className="track-legend">
          <button
            type="button"
            className={`legend-chip ${focusedTrack === null ? 'is-active' : ''}`}
            onClick={() => setFocusedTrack(null)}
          >
            All parts
          </button>
          {availableTracks.map((track) => {
            const key = `${sequence.index}:${track.track_index}`;
            return (
              <button
                key={key}
                type="button"
                className={`legend-chip ${focusedTrack === key ? 'is-active' : ''}`}
                onClick={() => setFocusedTrack(focusedTrack === key ? null : key)}
                title={trackLabelMap.get(key)}
              >
                <span className="legend-dot" style={{ background: trackColorMap.get(key) }} />
                <span>{track.name || `Ch ${track.channel + 1}`}</span>
              </button>
            );
          })}
        </div>
        <div className="piano-roll-controls">
          <button
            type="button"
            className={`mini-toggle ${showVelocity ? 'is-active' : ''}`}
            onClick={() => setShowVelocity((value) => !value)}
            title="Show velocity lane"
          >
            VEL
          </button>
          <IconButton
            label="Zoom out"
            disabled={zoom <= 1}
            onClick={() => setZoom((value) => Math.max(1, value / 1.5))}
          >
            <ChevronLeft size={13} />
          </IconButton>
          <span className="mono zoom-value">{zoom.toFixed(1)}×</span>
          <IconButton
            label="Zoom in"
            disabled={zoom >= 8}
            onClick={() => setZoom((value) => Math.min(8, value * 1.5))}
          >
            <ChevronRight size={13} />
          </IconButton>
        </div>
      </div>
      <div className={`piano-roll-scroll ${dragging ? 'is-dragging' : ''}`} ref={scrollRef}>
        <canvas
          ref={canvasRef}
          className="piano-roll-canvas"
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.currentTarget.setPointerCapture(event.pointerId);
            dragRef.current = true;
            setDragging(true);
            engine.beginScrub();
            seekFromEvent(event);
          }}
          onPointerMove={(event) => {
            if (dragRef.current) seekFromEvent(event);
          }}
          onPointerUp={(event) => finishScrub(event)}
          onPointerCancel={() => finishScrub()}
          onLostPointerCapture={() => {
            if (dragRef.current) finishScrub();
          }}
          aria-label="Piano roll preview. Click or drag to seek."
          role="img"
        />
        {!canvasProblem ? (
          <div
            className="piano-roll-playhead"
            style={{ left: `${playheadX}px` }}
            aria-hidden="true"
          />
        ) : null}
        {canvasProblem ? (
          <div className="piano-roll-canvas-error" role="status">
            The preview map could not be drawn for this file. Playback and all other library tools are still available.
          </div>
        ) : null}
      </div>
      <div className="piano-roll-footer">
        <span className="mono">{formatTime(playhead)} / {formatTime(sequence.duration_seconds)}</span>
        <span className="roll-meta">
          {sequence.timing_type === 'smpte'
            ? 'SMPTE timing'
            : `${sequence.bars ? `${sequence.bars.toFixed(sequence.bars % 1 ? 1 : 0)} bars` : 'bar length unknown'} · ${sequence.time_signatures[0]?.label || '4/4'}`}
        </span>
        <span className="roll-note-count"><DragIcon size={12} /> {formatNotes(sequence)}</span>
      </div>
      <div className="piano-roll-hint">
        Click or drag inside the roll to seek. Audition sounds are preview instruments, not the original devices.
        {rollData.sampled ? ` Showing a simplified map of a dense file (${MAX_DRAW_NOTES.toLocaleString()} of ${rollData.total.toLocaleString()} notes); playback uses the full sequence.` : ''}
      </div>
    </div>
  );
}

function formatNotes(sequence: PreviewSequence): string {
  const tracks = Array.isArray(sequence.tracks) ? sequence.tracks : [];
  const count = tracks.reduce(
    (total, track) => total + (Array.isArray(track.notes) ? track.notes.length : 0),
    0,
  );
  return `${count.toLocaleString()} notes · ${tracks.length} part${tracks.length === 1 ? '' : 's'}`;
}

function drawPianoRoll(
  ctx: CanvasRenderingContext2D,
  options: {
    sequence: PreviewSequence;
    grid: GridLine[];
    width: number;
    height: number;
    zoom: number;
    showVelocity: boolean;
    focusedTrack: string | null;
    mutedTracks: Set<string>;
    soloTracks: Set<string>;
    trackColorMap: Map<string, string>;
    notes: Array<PreviewNote & { trackKey: string }>;
    pitchMin: number;
    pitchMax: number;
  },
): void {
  const {
    sequence, grid, width, height, showVelocity, focusedTrack,
    mutedTracks, soloTracks, trackColorMap, notes,
  } = options;
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= GUTTER + RIGHT_PAD || height <= 0) return;
  const styles = getComputedStyle(document.documentElement);
  const paper = styles.getPropertyValue('--board').trim() || '#FCFAF6';
  const stone = styles.getPropertyValue('--stone').trim() || '#E7E2D8';
  const muted = styles.getPropertyValue('--ink-muted').trim() || '#716C63';
  const lineColor = styles.getPropertyValue('--line').trim() || 'rgba(41,40,33,.12)';
  const accent = styles.getPropertyValue('--accent').trim() || '#FF6500';
  let pitchMin = Number.isFinite(options.pitchMin) ? Math.floor(options.pitchMin) : 48;
  let pitchMax = Number.isFinite(options.pitchMax) ? Math.ceil(options.pitchMax) : 72;
  if (pitchMax - pitchMin < 18) {
    const center = (pitchMax + pitchMin) / 2;
    pitchMin = Math.floor(center - 9);
    pitchMax = Math.ceil(center + 9);
  }
  pitchMin = Math.max(0, pitchMin);
  pitchMax = Math.min(127, Math.max(pitchMin + 11, pitchMax));
  const velocityHeight = showVelocity ? VELOCITY_HEIGHT : 0;
  const plotLeft = GUTTER;
  const plotRight = width - RIGHT_PAD;
  const plotTop = TOP_PAD;
  const plotBottom = height - BOTTOM_PAD - velocityHeight;
  const plotWidth = Math.max(10, plotRight - plotLeft);
  const plotHeight = Math.max(10, plotBottom - plotTop);
  const rows = Math.max(1, pitchMax - pitchMin + 1);
  const rowHeight = plotHeight / rows;
  const duration = Number.isFinite(sequence.duration_seconds) && sequence.duration_seconds > 0
    ? sequence.duration_seconds
    : 0.1;
  const xFor = (seconds: number) => plotLeft + (Number.isFinite(seconds) ? (seconds / duration) * plotWidth : 0);
  const yFor = (pitch: number) => plotBottom - (pitch - pitchMin + 1) * rowHeight;
  const anySolo = soloTracks.size > 0;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = paper;
  ctx.fillRect(0, 0, width, height);

  // Horizontal key lanes.
  for (let pitch = pitchMin; pitch <= pitchMax; pitch += 1) {
    const y = yFor(pitch);
    const black = [1, 3, 6, 8, 10].includes(pitch % 12);
    if (black) {
      ctx.fillStyle = 'rgba(41,40,33,0.028)';
      ctx.fillRect(plotLeft, y, plotWidth, rowHeight);
    }
    ctx.strokeStyle = rowHeight > 5 ? lineColor : 'rgba(41,40,33,0.045)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(plotLeft, Math.round(y) + 0.5);
    ctx.lineTo(plotRight, Math.round(y) + 0.5);
    ctx.stroke();
  }

  // Keyboard gutter.
  ctx.fillStyle = stone;
  ctx.fillRect(0, 0, GUTTER, height);
  ctx.strokeStyle = lineColor;
  ctx.beginPath();
  ctx.moveTo(GUTTER + 0.5, 0);
  ctx.lineTo(GUTTER + 0.5, height);
  ctx.stroke();
  ctx.font = '9px "IBM Plex Mono", monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let pitch = pitchMin; pitch <= pitchMax; pitch += 1) {
    if (pitch % 12 === 0 && noteLabelHeight(rowHeight)) {
      ctx.fillStyle = muted;
      ctx.fillText(noteNameShort(pitch), GUTTER - 4, yFor(pitch) + rowHeight / 2);
    }
  }

  // Time grid.
  const bars = grid.filter((line) => line.major);
  const showEvery = bars.length > 64 ? Math.ceil(bars.length / 64) : 1;
  ctx.textBaseline = 'top';
  ctx.textAlign = 'left';
  for (const line of grid) {
    if (!line.major && bars.length > 28) continue;
    const x = Math.round(xFor(line.seconds)) + 0.5;
    if (x < plotLeft || x > plotRight + 1) continue;
    ctx.strokeStyle = line.major ? 'rgba(41,40,33,0.19)' : 'rgba(41,40,33,0.075)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, plotTop - 2);
    ctx.lineTo(x, plotBottom);
    ctx.stroke();
    if (line.major && line.label) {
      const index = bars.indexOf(line);
      if (index % showEvery === 0) {
        ctx.fillStyle = muted;
        ctx.font = '9px "IBM Plex Mono", monospace';
        ctx.fillText(line.label, x + 3, 3);
      }
    }
  }

  // Notes.
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  const sorted = [...notes].sort((a, b) => a.t - b.t);
  for (const note of sorted) {
    const isMuted = mutedTracks.has(note.trackKey);
    const isSoloDimmed = anySolo && !soloTracks.has(note.trackKey);
    const isFocused = focusedTrack === null || focusedTrack === note.trackKey;
    if (!isFocused) {
      ctx.globalAlpha = 0.18;
    } else if (isMuted || isSoloDimmed) {
      ctx.globalAlpha = 0.16;
    } else {
      ctx.globalAlpha = 0.82 + (note.v / 127) * 0.18;
    }
    const x = xFor(note.t);
    const w = Math.max(2.2, xFor(note.t + note.l) - x);
    const y = yFor(note.p);
    const h = Math.max(2.2, rowHeight - 1.2);
    const color = trackColorMap.get(note.trackKey) || accent;
    ctx.fillStyle = color;
    roundedRect(ctx, x, y + 0.5, w, h, Math.min(2, h / 2));
    ctx.fill();
    if (note.a && h > 4) {
      ctx.fillStyle = 'rgba(255,255,255,0.4)';
      ctx.fillRect(x + w - Math.min(3, w / 3), y + 1, Math.min(3, w / 3), h - 2);
    }
    ctx.globalAlpha = 1;
  }

  // The playhead is a DOM overlay so transport/scrub updates do not repaint the
  // full canvas (and cannot accumulate GPU damage on long drag sessions).

  // Velocity lane.
  if (showVelocity) {
    const laneTop = height - BOTTOM_PAD - VELOCITY_HEIGHT + 6;
    ctx.strokeStyle = lineColor;
    ctx.beginPath();
    ctx.moveTo(plotLeft, laneTop - 5.5);
    ctx.lineTo(plotRight, laneTop - 5.5);
    ctx.stroke();
    ctx.fillStyle = muted;
    ctx.font = '8px "IBM Plex Mono", monospace';
    ctx.textAlign = 'left';
    ctx.fillText('VEL', 5, laneTop + 1);
    for (const note of notes) {
      const isMutedTrack = mutedTracks.has(note.trackKey);
      const isSoloDimmed = anySolo && !soloTracks.has(note.trackKey);
      const isFocused = focusedTrack === null || focusedTrack === note.trackKey;
      ctx.globalAlpha = !isFocused || isMutedTrack || isSoloDimmed ? 0.16 : 0.8;
      const x = xFor(note.t);
      const value = (note.v / 127) * (VELOCITY_HEIGHT - 10);
      ctx.fillStyle = trackColorMap.get(note.trackKey) || accent;
      ctx.fillRect(x, laneTop + VELOCITY_HEIGHT - 10 - value, 2.2, value);
      ctx.globalAlpha = 1;
    }
  }
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number): void {
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return;
  const safeWidth = Math.max(0, width);
  const safeHeight = Math.max(0, height);
  const safeRadius = Number.isFinite(radius) ? Math.max(0, radius) : 0;
  const r = Math.max(0, Math.min(safeRadius, safeWidth / 2, safeHeight / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + safeWidth, y, x + safeWidth, y + safeHeight, r);
  ctx.arcTo(x + safeWidth, y + safeHeight, x, y + safeHeight, r);
  ctx.arcTo(x, y + safeHeight, x, y, r);
  ctx.arcTo(x, y, x + safeWidth, y, r);
  ctx.closePath();
}

function noteNameShort(pitch: number): string {
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  return `${names[Math.abs(pitch) % 12]}${Math.floor(pitch / 12) - 1}`;
}

function clampFraction(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}
