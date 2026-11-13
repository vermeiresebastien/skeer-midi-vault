import { useEffect, useRef, useState, type CSSProperties } from 'react';
import type { PreviewEngine } from '../audio/engine';
import { useEngineSnapshot } from '../audio/useEngine';
import type { ScanStatus } from '../types';
import { formatBpm, formatTime } from '../lib/format';
import { IconButton, Knob, Select } from './Common';
import {
  LoopIcon,
  PauseIcon,
  PlayIcon,
  ScanIcon,
  StopIcon,
} from './Icons';

export function TransportBar({
  engine,
  scan,
  onOpenScan,
  onPauseScan,
  onResumeScan,
  onCancelScan,
  onNotify,
}: {
  engine: PreviewEngine;
  scan: ScanStatus;
  onOpenScan: () => void;
  onPauseScan: () => void;
  onResumeScan: () => void;
  onCancelScan: () => void;
  onNotify: (message: string, tone?: 'info' | 'success' | 'error') => void;
}) {
  const snapshot = useEngineSnapshot(engine);
  const [seeking, setSeeking] = useState(false);
  const seekingRef = useRef(false);
  const [midiBusy, setMidiBusy] = useState(false);
  const duration = snapshot.duration || 0;
  const progress = duration > 0 ? Math.min(1, snapshot.sourceTime / duration) : 0;
  const scanning = scan.active || scan.state === 'cancelling';
  const paused = snapshot.paused && !snapshot.playing;
  const scanFailures = scan.failed || 0;

  const togglePlay = async () => {
    if (snapshot.playing) engine.pause();
    else await engine.play();
  };

  const finishSeekDrag = () => {
    if (!seekingRef.current) return;
    seekingRef.current = false;
    setSeeking(false);
    engine.endScrub();
  };

  useEffect(() => {
    if (!seeking) return undefined;
    const onRelease = () => finishSeekDrag();
    window.addEventListener('pointerup', onRelease, { once: true });
    window.addEventListener('pointercancel', onRelease, { once: true });
    return () => {
      window.removeEventListener('pointerup', onRelease);
      window.removeEventListener('pointercancel', onRelease);
    };
  }, [seeking]);

  const chooseOutput = async (value: string) => {
    try {
      setMidiBusy(true);
      if (value === '') {
        await engine.setOutput(null);
        return;
      }
      if (value === '__enable') {
        const outputs = await engine.requestMidiAccess();
        if (outputs.length === 0) {
          onNotify('Web MIDI is available, but no MIDI output was found.', 'info');
        } else {
          onNotify('MIDI output enabled. Choose a port from the output menu.', 'success');
        }
        return;
      }
      await engine.setOutput(value);
      onNotify('MIDI output selected. Playback is paused with all notes released.', 'info');
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not change the MIDI output.', 'error');
    } finally {
      setMidiBusy(false);
    }
  };

  return (
    <footer className="transport-bar">
      <div className="transport-left">
        <button
          type="button"
          className={`transport-play ${snapshot.playing ? 'is-playing' : ''}`}
          onClick={() => void togglePlay()}
          aria-label={snapshot.playing ? 'Pause' : 'Play'}
          title={snapshot.playing ? 'Pause (Space)' : 'Play (Space)'}
          disabled={!snapshot.hasSequence}
        >
          {snapshot.playing ? <PauseIcon size={18} /> : <PlayIcon size={18} />}
        </button>
        <IconButton
          label="Stop"
          onClick={() => engine.stop()}
          disabled={!snapshot.hasSequence}
          className="transport-secondary"
        >
          <StopIcon size={15} />
        </IconButton>
        <IconButton
          label={snapshot.loop ? 'Loop on' : 'Loop off'}
          onClick={() => engine.setLoop(!snapshot.loop)}
          active={snapshot.loop}
          disabled={!snapshot.hasSequence}
          className="transport-secondary"
        >
          <LoopIcon size={16} />
        </IconButton>
        <div className="transport-time mono">
          <span>{formatTime(snapshot.sourceTime)}</span>
          <span className="time-divider">/</span>
          <span className="muted">{formatTime(duration)}</span>
        </div>
      </div>

      <div className="transport-tempo">
        <Knob
          value={Math.round(snapshot.auditionBpm)}
          min={30}
          max={300}
          step={1}
          label="Audition"
          size={36}
          disabled={!snapshot.hasSequence}
          valueLabel={`${Math.round(snapshot.auditionBpm)} BPM`}
          onChange={(value) => engine.setAuditionBpm(value)}
          onDragEnd={() => engine.flushTempoAdjustment()}
          onReset={() => engine.setAuditionBpm(Math.round(snapshot.originalBpm))}
        />
        <div className="tempo-copy">
          <span className="mono tempo-value">{formatBpm(snapshot.auditionBpm)} <em>BPM</em></span>
          <button
            type="button"
            className="tempo-original"
            onClick={() => engine.setAuditionBpm(Math.round(snapshot.originalBpm))}
            title="Reset audition tempo to the file's original tempo"
          >
            original {formatBpm(snapshot.originalBpm)}
          </button>
        </div>
      </div>

      <div className="transport-seek">
        <input
          type="range"
          min={0}
          max={Math.max(0.001, duration)}
          step={0.01}
          value={Math.min(snapshot.sourceTime, duration)}
          disabled={!snapshot.hasSequence}
          aria-label="Seek"
          onChange={(event) => {
            const value = Number(event.target.value);
            if (!Number.isFinite(value)) return;
            if (seekingRef.current) engine.scrubTo(value);
            else engine.seek(value);
          }}
          onPointerDown={() => {
            seekingRef.current = true;
            setSeeking(true);
            engine.beginScrub();
          }}
          onPointerUp={finishSeekDrag}
          onPointerCancel={finishSeekDrag}
          onLostPointerCapture={finishSeekDrag}
          style={{ '--progress': `${progress * 100}%` } as CSSProperties}
        />
        {scanning ? (
          <div className="scan-progress-track" title={scan.current_path}>
            <span style={{ width: `${Math.max(2, scan.completion)}%` }} />
          </div>
        ) : null}
      </div>

      <div className="transport-output">
        <span className="transport-label">Output</span>
        <Select
          value={snapshot.outputMode === 'midi' ? snapshot.outputId || '' : ''}
          onChange={(event) => void chooseOutput(event.target.value)}
          disabled={midiBusy}
          aria-label="Playback output device"
        >
          <option value="">Preview synth</option>
          {snapshot.midiOutputs.map((output) => (
            <option key={output.id} value={output.id}>{output.name}</option>
          ))}
          {snapshot.midiSupported !== false ? <option value="__enable">Enable MIDI output…</option> : null}
          {snapshot.midiSupported === false ? <option value="__unsupported" disabled>MIDI unavailable</option> : null}
        </Select>
        {snapshot.outputMode === 'midi' ? <span className="midi-output-badge">MIDI</span> : null}
      </div>

      <div className="transport-meter" aria-label={`Audio level ${Math.round(snapshot.meter * 100)} percent`}>
        <div className="meter-track">
          <span style={{ width: `${Math.round(snapshot.meter * 100)}%` }} />
        </div>
        <span className="transport-label">Level</span>
      </div>

      <button
        type="button"
        className={`scan-status ${scanning ? 'is-scanning' : ''}`}
        onClick={onOpenScan}
        title={scan.current_path || scan.message}
      >
        <span className="scan-status-main">
          {scanning ? <span className="scan-live-dot" /> : <ScanIcon size={14} />}
          <span className="scan-status-copy">
            <span className="scan-status-title">
              {scanning
                ? scan.state === 'paused' ? 'Scan paused' : 'Scanning computer'
                : scan.state === 'completed' ? 'Index ready' : scan.state === 'error' ? 'Last scan failed' : 'Ready to scan'}
            </span>
            <span className="scan-status-detail">
              {scanning ? (
                <>
                  <span className="mono">{scan.indexed.toLocaleString()}</span> indexed
                  {scanFailures ? <> · <span className="scan-fail-count">{scanFailures} failed</span></> : null}
                  {' · '}
                  <span className="scan-path">{scan.state === 'paused' ? scan.current_path : scan.current_path || 'discovering…'}</span>
                </>
              ) : (
                <>
                  {scan.indexed.toLocaleString()} indexed
                  {scanFailures ? ` · ${scanFailures} failed` : ''}
                  {scan.ended_at ? ` · ${shortStamp(scan.ended_at)}` : ''}
                </>
              )}
            </span>
          </span>
        </span>
        {scanning ? (
          <span className="scan-status-actions" onClick={(event) => event.stopPropagation()}>
            {scan.state === 'paused' ? (
              <button type="button" onClick={onResumeScan} title="Resume scan">Resume</button>
            ) : (
              <button type="button" onClick={onPauseScan} title="Pause scan" disabled={scan.state === 'cancelling'}>Pause</button>
            )}
            <button type="button" className="danger" onClick={onCancelScan} title="Cancel scan" disabled={scan.state === 'cancelling'}>Cancel</button>
          </span>
        ) : (
          <span className="scan-status-chevron">›</span>
        )}
      </button>
    </footer>
  );
}

function shortStamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
