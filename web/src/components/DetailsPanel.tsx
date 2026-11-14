import { useEffect, useState } from 'react';
import type { Collection, Evidence, FileDetails } from '../types';
import { INSTRUMENT_CATEGORIES, ROLE_CATEGORIES } from '../types';
import type { PreviewEngine } from '../audio/engine';
import { SELECTABLE_SOUNDS, soundHint, soundLabel, type SoundId } from '../audio/sounds';
import { rawFileUrl } from '../api';
import { familyLabel, instrumentColor, roleLabel, trackColor } from '../lib/colors';
import {
  confidenceLabel,
  formatBpm,
  formatBytes,
  formatDuration,
  formatPercent,
  formatRelativeTime,
  formatTime,
  keyLabel,
  noteName,
} from '../lib/format';
import { Badge, Button, Confidence, InlineNotice, Select, Spinner } from './Common';
import { PianoRoll } from './PianoRoll';
import {
  CheckIcon,
  ChevronDown,
  ChevronRight,
  CloseIcon,
  CollectionIcon,
  ExportIcon,
  NoteIcon,
  PlusIcon,
  RevealIcon,
  StarIcon,
  TagIcon,
  WarningIcon,
} from './Icons';

export function DetailsPanel({
  details,
  loading,
  selectedSequence,
  onSelectSequence,
  engine,
  mutedTracks,
  soloTracks,
  onToggleMute,
  onToggleSolo,
  onSetFileLabel,
  onSetTrackLabel,
  trackSounds,
  trackSoundPicks,
  onSetTrackSound,
  onSetSequenceSound,
  onToggleFavorite,
  onReveal,
  onExport,
  onAddTag,
  onRemoveTag,
  onAddToCollection,
  onRemoveFromCollection,
  onSaveNotes,
  onOpenFile,
  collections,
  onNotify,
}: {
  details: FileDetails | null;
  loading: boolean;
  selectedSequence: number;
  onSelectSequence: (index: number) => void;
  engine: PreviewEngine;
  mutedTracks: Set<string>;
  soloTracks: Set<string>;
  onToggleMute: (trackKey: string) => void;
  onToggleSolo: (trackKey: string) => void;
  onSetFileLabel: (dimension: 'instrument' | 'role', value: string, clear?: boolean) => Promise<void>;
  onSetTrackLabel: (sequence: number, track: number, dimension: 'instrument' | 'role', value: string, clear?: boolean) => Promise<void>;
  /** Voice the engine plays per `${sequence}:${track}` key. */
  trackSounds: Record<string, SoundId>;
  /** The user's explicit picks, same keys; absent means "follow the analysis". */
  trackSoundPicks: Record<string, SoundId>;
  onSetTrackSound: (sequence: number, track: number, sound: SoundId) => void;
  onSetSequenceSound: (sound: SoundId | null) => void;
  onToggleFavorite: () => void;
  onReveal: () => void;
  onExport: () => void;
  onAddTag: (name: string) => Promise<void>;
  onRemoveTag: (tagId: number) => Promise<void>;
  onAddToCollection: (collectionId: number) => Promise<void>;
  onRemoveFromCollection: (collectionId: number) => Promise<void>;
  onSaveNotes: (notes: string) => Promise<void>;
  onOpenFile: (id: number) => void;
  collections: Collection[];
  onNotify: (message: string, tone?: 'info' | 'success' | 'error') => void;
}) {
  const file = details?.file;
  const cache = details?.cache;
  const preview = cache?.preview;
  const analysis = cache?.analysis.file;
  const classification = cache?.classification.file;
  const sequence = preview?.sequences.find((item) => item.index === selectedSequence) || preview?.sequences[0] || null;
  const selectedTracks = details?.tracks.filter((track) => track.sequence_index === selectedSequence) || [];
  const availableCollections = collections.filter(
    (collection) => !details?.collections.some((item) => item.id === collection.id),
  );
  const [tagText, setTagText] = useState('');
  const [notesDraft, setNotesDraft] = useState('');
  const [notesDirty, setNotesDirty] = useState(false);
  const [notesSaving, setNotesSaving] = useState(false);
  const [labelSaving, setLabelSaving] = useState<string | null>(null);
  const [expandedTracks, setExpandedTracks] = useState<Set<string>>(new Set());
  const [evidenceOpen, setEvidenceOpen] = useState<'instrument' | 'role' | null>(null);
  const [trackEditor, setTrackEditor] = useState<string | null>(null);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const [addCollection, setAddCollection] = useState('');

  useEffect(() => {
    setTagText('');
    setNotesDraft(details?.file.user_notes || '');
    setNotesDirty(false);
    setExpandedTracks(new Set());
    setEvidenceOpen(null);
    setTrackEditor(null);
    setShowAllWarnings(false);
    setAddCollection('');
  }, [details?.file.id]);

  useEffect(() => {
    setNotesDraft(details?.file.user_notes || '');
    setNotesDirty(false);
  }, [details?.file.user_notes]);

  const saveNotes = async () => {
    if (!file || !notesDirty) return;
    setNotesSaving(true);
    try {
      await onSaveNotes(notesDraft);
      setNotesDirty(false);
    } finally {
      setNotesSaving(false);
    }
  };

  if (loading && !details) {
    return (
      <aside className="details-panel">
        <div className="details-loading">
          <Spinner size={22} />
          <span>Reading MIDI details…</span>
        </div>
      </aside>
    );
  }

  if (!details || !file) {
    return (
      <aside className="details-panel details-empty">
        <div className="empty-detail-mark"><img src="/brand/skeer-mark.png" alt="" /></div>
        <h2>Select a MIDI file</h2>
        <p>
          Inspect the musical analysis, correct its classifications, audition the
          piano roll, and drag the original file into a DAW.
        </p>
        <div className="empty-detail-notes">
          <span><CheckIcon size={13} /> Read-only source files</span>
          <span><CheckIcon size={13} /> Private local analysis</span>
          <span><CheckIcon size={13} /> Automatic predictions stay separate</span>
        </div>
      </aside>
    );
  }

  const isFormat2 = (preview?.format ?? file.format) === 2;
  const sequenceCount = preview?.sequences.length ?? file.sequence_count ?? 1;
  const instrumentAuto = file.auto_instrument || file.instrument;
  const roleAuto = file.auto_role || file.role;
  const instrumentUser = file.instrument_source === 'user';
  const roleUser = file.role_source === 'user';
  const fileCorrections = details.corrections.file;
  const instrumentCorrection = fileCorrections.find((item) => item.dimension === 'instrument');
  const roleCorrection = fileCorrections.find((item) => item.dimension === 'role');
  const instrumentAccepted = instrumentCorrection?.action === 'accepted';
  const roleAccepted = roleCorrection?.action === 'accepted';
  const conflicts = [
    ...(classification?.conflicts || []),
    ...(file.conflicts_json || []),
  ];
  const warnings = uniqueStrings([
    ...(analysis?.warnings || []),
    ...(file.warnings_json || []),
    ...(sequence?.warnings || []),
  ]);
  const tempo = analysis?.tempo;
  const meter = analysis?.time_signature;
  const key = analysis?.key;
  const fileConfidence = Math.min(
    file.instrument_confidence ?? 0,
    file.role_confidence ?? 0,
  );
  const allTags = details.tags;
  const duplicateExact = details.duplicates.exact_members;
  const duplicateSimilar = details.duplicates.similar_members;

  const setLabel = async (dimension: 'instrument' | 'role', value: string, clear = false) => {
    setLabelSaving(dimension);
    try {
      await onSetFileLabel(dimension, value, clear);
    } finally {
      setLabelSaving(null);
    }
  };

  return (
    <aside className="details-panel">
      <div className="details-scroll">
        <header className="detail-header">
          <div className="detail-kicker">
            <span>{file.source_label || 'Local source'}</span>
            <span className="detail-kicker-sep">/</span>
            <span className="detail-folder" title={file.dirname}>{shortFolder(file.dirname)}</span>
          </div>
          <div className="detail-title-row">
            <h2 title={file.path}>{file.filename}</h2>
            <button
              type="button"
              className={`detail-star ${file.favorite ? 'is-favorite' : ''}`}
              onClick={onToggleFavorite}
              aria-label={file.favorite ? 'Remove from favorites' : 'Add to favorites'}
              title={file.favorite ? 'Remove from favorites' : 'Add to favorites'}
            >
              <StarIcon size={18} filled={file.favorite} />
            </button>
          </div>
          <div className="detail-badge-row">
            <Badge tone="neutral">SMF {file.format ?? '?'}</Badge>
            {file.timing_type === 'smpte' ? <Badge tone="neutral">SMPTE</Badge> : null}
            {isFormat2 ? <Badge tone="orange">{sequenceCount} sequences</Badge> : null}
            {file.uncertain ? <Badge tone="amber">Uncertain</Badge> : null}
            {file.exact_group_id ? <Badge tone="amber" title="Exact byte-for-byte duplicate">exact copy</Badge> : null}
            {!file.exact_group_id && file.similar_group_id ? <Badge tone="neutral">similar file</Badge> : null}
            {file.is_missing || file.source_available === false ? <Badge tone="red">source offline</Badge> : null}
            {file.scan_state === 'failed' ? <Badge tone="red">index issue</Badge> : null}
          </div>
          <div className="detail-actions">
            <Button variant="primary" size="sm" icon={<NoteIcon size={14} />} onClick={() => void engine.play()}>
              Audition
            </Button>
            <Button size="sm" icon={<RevealIcon size={14} />} onClick={onReveal}>Reveal</Button>
            <Button size="sm" icon={<ExportIcon size={14} />} onClick={onExport}>Copy / export</Button>
            <span
              className="drag-hint"
              title="Drag this file into a DAW that supports browser file drops"
              draggable
              onDragStart={(event) => {
                const url = new URL(rawFileUrl(file.id), window.location.href).toString();
                event.dataTransfer.effectAllowed = 'copy';
                event.dataTransfer.setData('DownloadURL', `audio/midi:${file.filename}:${url}`);
                event.dataTransfer.setData('text/plain', file.path);
              }}
            >
              <span className="drag-grip">⠿</span> drag to DAW
            </span>
          </div>
        </header>

        {file.scan_state === 'failed' && file.error ? (
          <InlineNotice tone="error">{file.error}</InlineNotice>
        ) : null}

        {isFormat2 && sequenceCount > 1 ? (
          <div className="sequence-tabs">
            <span className="sequence-tabs-label">Independent sequence</span>
            <div className="sequence-tabs-list">
              {preview?.sequences.map((item) => (
                <button
                  key={item.index}
                  type="button"
                  className={item.index === selectedSequence ? 'is-active' : ''}
                  onClick={() => onSelectSequence(item.index)}
                >
                  {item.index + 1}. {item.name || `Sequence ${item.index + 1}`}
                  <span>{item.tracks.length} parts</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <section className="panel-card preview-card">
          <div className="card-heading">
            <div>
              <span className="card-kicker">Musical preview</span>
              <h3>Piano roll</h3>
            </div>
            <span className="preview-tempo mono">{formatBpm(sequence ? sequence.tempos[0]?.bpm : tempo?.initial_bpm)} BPM</span>
          </div>
          <PianoRoll
            sequence={sequence}
            tracks={selectedTracks}
            engine={engine}
            mutedTracks={mutedTracks}
            soloTracks={soloTracks}
          />
        </section>

        <section className="panel-card classification-card">
          <div className="card-heading">
            <div>
              <span className="card-kicker">
                Classification {isFormat2 && sequenceCount > 1 ? '· primary sequence' : ''}
              </span>
              <h3>What this file is</h3>
            </div>
            <Confidence
              value={fileConfidence}
              source={instrumentUser || roleUser ? 'user' : undefined}
            />
          </div>
          <div className="classification-rows">
            <div className="classification-row">
              <span className="classification-label">Sound family</span>
              <div className="classification-control">
                <Select
                  value={file.instrument}
                  onChange={(event) => void setLabel('instrument', event.target.value)}
                  disabled={labelSaving === 'instrument'}
                  aria-label="Sound family classification"
                >
                  {INSTRUMENT_CATEGORIES.map((category) => (
                    <option key={category} value={category}>{familyLabel(category)}</option>
                  ))}
                </Select>
                {instrumentUser ? (
                  <div className="classification-meta">
                    <Badge tone="orange">{instrumentAccepted ? 'Accepted' : 'Your label'}</Badge>
                    <button type="button" className="text-action" onClick={() => void setLabel('instrument', '', true)}>
                      revert to auto
                    </button>
                  </div>
                ) : (
                  <div className="classification-meta">
                    <span>{confidenceLabel(file.instrument_confidence)} · {formatPercent(file.instrument_confidence)}</span>
                    <button
                      type="button"
                      className="text-action"
                      onClick={() => void setLabel('instrument', file.instrument)}
                      title="Record that you reviewed and accepted this automatic prediction"
                    >
                      {instrumentAccepted ? 'accepted' : 'accept auto'}
                    </button>
                  </div>
                )}
              </div>
              <span className="classification-dot" style={{ background: instrumentColor(file.instrument) }} />
            </div>
            <div className="classification-row">
              <span className="classification-label">Musical role</span>
              <div className="classification-control">
                <Select
                  value={file.role}
                  onChange={(event) => void setLabel('role', event.target.value)}
                  disabled={labelSaving === 'role'}
                  aria-label="Musical role classification"
                >
                  {ROLE_CATEGORIES.map((role) => (
                    <option key={role} value={role}>{roleLabel(role)}</option>
                  ))}
                </Select>
                {roleUser ? (
                  <div className="classification-meta">
                    <Badge tone="orange">{roleAccepted ? 'Accepted' : 'Your label'}</Badge>
                    <button type="button" className="text-action" onClick={() => void setLabel('role', '', true)}>
                      revert to auto
                    </button>
                  </div>
                ) : (
                  <div className="classification-meta">
                    <span>{confidenceLabel(file.role_confidence)} · {formatPercent(file.role_confidence)}</span>
                    <button
                      type="button"
                      className="text-action"
                      onClick={() => void setLabel('role', file.role)}
                      title="Record that you reviewed and accepted this automatic prediction"
                    >
                      {roleAccepted ? 'accepted' : 'accept auto'}
                    </button>
                  </div>
                )}
              </div>
              <span className="classification-dot role-dot" />
            </div>
          </div>
          <div className="classification-footer">
            <div className="tag-cloud">
              {(file.style_tags || []).map((tag) => (
                <span key={tag} className="style-tag">{tag}</span>
              ))}
              {file.genre_hint ? (
                <span className="genre-hint" title={classification?.genre_evidence || 'Low-confidence style hint'}>
                  style hint: {file.genre_hint}
                  {file.genre_confidence ? <span className="mono"> {Math.round(file.genre_confidence * 100)}%</span> : null}
                </span>
              ) : null}
            </div>
            {file.genre_hint ? (
              <span className="speculative-note">Genre is speculative, not a fact.</span>
            ) : null}
          </div>
          <div className="evidence-toggles">
            <button
              type="button"
              className={`evidence-toggle ${evidenceOpen === 'instrument' ? 'is-open' : ''}`}
              onClick={() => setEvidenceOpen(evidenceOpen === 'instrument' ? null : 'instrument')}
            >
              {evidenceOpen === 'instrument' ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              Why “{familyLabel(file.instrument)}”?
            </button>
            <button
              type="button"
              className={`evidence-toggle ${evidenceOpen === 'role' ? 'is-open' : ''}`}
              onClick={() => setEvidenceOpen(evidenceOpen === 'role' ? null : 'role')}
            >
              {evidenceOpen === 'role' ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              Why “{roleLabel(file.role)}”?
            </button>
          </div>
          {evidenceOpen ? (
            <EvidenceList
              evidence={evidenceOpen === 'instrument'
                ? classification?.instrument_evidence || []
                : classification?.role_evidence || []}
              alternatives={evidenceOpen === 'instrument'
                ? classification?.instrument_alternatives || []
                : classification?.role_alternatives || []}
              conflicts={conflicts}
            />
          ) : null}
          {classification?.uncertainty_notes?.length ? (
            <div className="uncertainty-list">
              <span className="uncertainty-title">Why it is uncertain</span>
              {classification.uncertainty_notes.slice(0, 4).map((note) => (
                <span key={note} className="uncertainty-item">{note}</span>
              ))}
            </div>
          ) : null}
          {conflicts.length > 0 ? (
            <div className="conflict-list">
              {conflicts.slice(0, 4).map((conflict, index) => (
                <div key={`${conflict.label}-${index}`} className="conflict-item">
                  <WarningIcon size={13} />
                  <span>{conflict.label}</span>
                </div>
              ))}
            </div>
          ) : null}
          {(file.instrument_source === 'user' || file.role_source === 'user')
            && (file.instrument !== instrumentAuto || file.role !== roleAuto) ? (
              <div className="auto-review">
                <span>Automatic prediction:</span>
                <span>{familyLabel(instrumentAuto)} / {roleLabel(roleAuto)}</span>
              </div>
            ) : null}
        </section>

        <section className="panel-card tracks-card">
          <div className="card-heading">
            <div>
              <span className="card-kicker">{selectedTracks.length} part{selectedTracks.length === 1 ? '' : 's'} in this sequence</span>
              <h3>Tracks</h3>
            </div>
            <span className="mute-solo-legend"><span>M</span> mute <span>S</span> solo</span>
          </div>
          <div className="sound-bulk">
            <span className="sound-bulk-label">Preview sound</span>
            <Select
              value=""
              aria-label="Set the preview sound for every track in this sequence"
              title="Apply one preview sound to all tracks in this sequence"
              onChange={(event) => onSetSequenceSound(event.target.value ? event.target.value as SoundId : null)}
            >
              <option value="">Apply to all…</option>
              {SELECTABLE_SOUNDS.filter((id) => id !== 'auto').map((id) => (
                <option key={id} value={id}>{soundLabel(id)}</option>
              ))}
            </Select>
            <button
              type="button"
              className="text-action"
              onClick={() => onSetSequenceSound(null)}
              title="Clear every pick so each track follows its own classification again"
            >
              follow analysis
            </button>
          </div>
          <div className="track-list">
            {selectedTracks.length === 0 ? (
              <p className="subtle-empty">No note-bearing tracks in this sequence.</p>
            ) : null}
            {selectedTracks.map((track) => {
              const key = `${track.sequence_index}:${track.track_index}`;
              const muted = mutedTracks.has(key);
              const soloed = soloTracks.has(key);
              const editing = trackEditor === key;
              const picked = trackSoundPicks[key];
              const resolvedSound = trackSounds[key] || 'default';
              const expanded = expandedTracks.has(key);
              const trackConflicts = track.conflicts || [];
              return (
                <div
                  key={track.id}
                  className={`track-entry ${editing ? 'is-editing' : ''} ${muted ? 'is-muted' : ''}`}
                >
                  <div className="track-main">
                    <span className="track-color" style={{ background: trackColor(track.track_index) }} />
                    <div className="track-name-block">
                      <div className="track-name-row">
                        <strong>{track.name || `Channel ${track.channel + 1}`}</strong>
                        <span className="track-channel mono">CH {track.channel + 1}</span>
                        {trackConflicts.length ? <WarningIcon size={12} /> : null}
                      </div>
                      <span className="track-subline">
                        {track.analysis.program_names?.length
                          ? track.analysis.program_names.slice(0, 2).join(' · ')
                          : track.program != null ? `Program ${track.program + 1}` : 'No program change'}
                        <span className="dot-sep">·</span>
                        <span className="mono">{track.note_count.toLocaleString()} notes</span>
                        {track.analysis.pitch_min_name ? (
                          <>
                            <span className="dot-sep">·</span>
                            <span className="mono">{track.analysis.pitch_min_name}–{track.analysis.pitch_max_name}</span>
                          </>
                        ) : null}
                      </span>
                    </div>
                    <div className="track-controls">
                      <button
                        type="button"
                        className={`ms-button ${muted ? 'is-on mute' : ''}`}
                        onClick={() => onToggleMute(key)}
                        title={muted ? 'Unmute track' : 'Mute track'}
                        aria-pressed={muted}
                      >M</button>
                      <button
                        type="button"
                        className={`ms-button ${soloed ? 'is-on solo' : ''}`}
                        onClick={() => onToggleSolo(key)}
                        title={soloed ? 'Unsolo track' : 'Solo track'}
                        aria-pressed={soloed}
                      >S</button>
                      <button
                        type="button"
                        className={`ms-button edit ${editing ? 'is-on' : ''}`}
                        onClick={() => setTrackEditor(editing ? null : key)}
                        title="Edit track classification"
                        aria-expanded={editing}
                      >
                        <span className="edit-glyph">✎</span>
                      </button>
                    </div>
                  </div>
                  <div className="track-labels">
                    <span className="track-label family">
                      <span className="track-label-dot" style={{ background: instrumentColor(track.instrument) }} />
                      {familyLabel(track.instrument)}
                      {track.instrument_source === 'user' ? <em>you</em> : null}
                    </span>
                    <span className="track-label role">{roleLabel(track.role)}</span>
                    <span
                      className={`track-label sound ${picked ? 'is-picked' : ''}`}
                      title={picked
                        ? `${soundHint(resolvedSound)} Your pick.`
                        : `${soundHint(resolvedSound)} Follows the classification.`}
                    >
                      {soundLabel(resolvedSound)}
                      {picked ? <em>you</em> : null}
                    </span>
                    <Confidence
                      value={Math.min(track.instrument_confidence, track.role_confidence)}
                      source={track.instrument_source === 'user' || track.role_source === 'user' ? 'user' : undefined}
                      compact
                    />
                    <button
                      type="button"
                      className="track-detail-toggle"
                      onClick={() => setExpandedTracks((current) => {
                        const next = new Set(current);
                        if (next.has(key)) next.delete(key);
                        else next.add(key);
                        return next;
                      })}
                    >
                      {expanded ? 'less' : 'details'}
                    </button>
                  </div>
                  {editing ? (
                    <div className="track-editor">
                      <label>
                        <span>Family</span>
                        <Select
                          value={track.instrument}
                          onChange={(event) => void onSetTrackLabel(track.sequence_index, track.track_index, 'instrument', event.target.value)}
                        >
                          {INSTRUMENT_CATEGORIES.filter((category) => category !== 'Mixed arrangement').map((category) => (
                            <option key={category} value={category}>{familyLabel(category)}</option>
                          ))}
                        </Select>
                      </label>
                      <label>
                        <span>Role</span>
                        <Select
                          value={track.role}
                          onChange={(event) => void onSetTrackLabel(track.sequence_index, track.track_index, 'role', event.target.value)}
                        >
                          {ROLE_CATEGORIES.filter((role) => role !== 'Complete song or multi-part arrangement').map((role) => (
                            <option key={role} value={role}>{roleLabel(role)}</option>
                          ))}
                        </Select>
                      </label>
                      <label>
                        <span>Sound</span>
                        <Select
                          value={picked || 'auto'}
                          onChange={(event) => onSetTrackSound(track.sequence_index, track.track_index, event.target.value as SoundId)}
                        >
                          {SELECTABLE_SOUNDS.map((id) => (
                            <option key={id} value={id}>{id === 'auto' ? 'Auto (follow analysis)' : soundLabel(id)}</option>
                          ))}
                        </Select>
                      </label>
                      <div className="track-editor-footer">
                        <span>
                          Auto: {familyLabel(track.auto_instrument)} / {roleLabel(track.auto_role)}
                        </span>
                        {track.label_source === 'user' ? (
                          <button
                            type="button"
                            className="text-action"
                            onClick={async () => {
                              await onSetTrackLabel(track.sequence_index, track.track_index, 'instrument', '', true);
                              await onSetTrackLabel(track.sequence_index, track.track_index, 'role', '', true);
                            }}
                          >
                            revert both
                          </button>
                        ) : null}
                      </div>
                      {trackConflicts.length ? (
                        <div className="track-conflicts">
                          {trackConflicts.map((conflict, index) => (
                            <span key={index}><WarningIcon size={11} /> {conflict.label}</span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {expanded ? (
                    <div className="track-details">
                      <div><span>Polyphony</span><strong className="mono">{track.analysis.polyphony_max ?? '—'} max</strong></div>
                      <div><span>Density</span><strong className="mono">{track.analysis.note_density?.toFixed(2) ?? '—'}/beat</strong></div>
                      <div><span>Monophonic</span><strong className="mono">{formatPercent(track.analysis.monophonic_ratio)}</strong></div>
                      <div><span>Bar span</span><strong className="mono">{track.analysis.bar_span?.toFixed(1) ?? '—'}</strong></div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel-card metadata-card">
          <div className="card-heading">
            <div>
              <span className="card-kicker">Embedded values and calculated estimates</span>
              <h3>Musical metadata</h3>
            </div>
          </div>
          <div className="metadata-grid">
            <Meta label="Tempo" value={`${formatBpm(tempo?.initial_bpm ?? file.tempo_bpm)} BPM`} source={tempo?.source ?? file.tempo_source} note={tempo?.change_count ? `${tempo.change_count} tempo change${tempo.change_count === 1 ? '' : 's'}` : undefined} />
            <Meta label="Meter" value={meter?.initial ?? file.time_sig ?? '—'} source={meter?.source ?? file.time_sig_source} note={meter?.change_count ? `${meter.change_count} meter change${meter.change_count === 1 ? '' : 's'}` : undefined} />
            <Meta label="Key" value={keyLabel(key?.label ?? file.key_name, key?.source ?? file.key_source)} source={key?.source ?? file.key_source} note={key?.source === 'estimated' && key ? `${Math.round(key.confidence * 100)}% confidence` : key?.embedded ? 'embedded signature' : undefined} />
            <Meta label="Duration" value={formatDuration(file.duration_seconds)} note={file.bars ? `${file.bars.toFixed(file.bars % 1 ? 1 : 0)} bars` : undefined} />
            <Meta label="Structure" value={`SMF ${file.format ?? '—'}`} note={`${file.track_count ?? 0} note tracks · ${file.sequence_count ?? 1} sequence${(file.sequence_count ?? 1) === 1 ? '' : 's'}`} />
            <Meta label="Timing" value={file.timing_type === 'smpte' ? 'SMPTE' : 'Metrical'} note={preview?.sequences[0]?.ticks_per_quarter ? `${preview.sequences[0].ticks_per_quarter} ticks / quarter` : undefined} />
            <Meta label="Notes" value={(file.note_count ?? 0).toLocaleString()} note={`${analysis?.channel_count ?? 0} channel${(analysis?.channel_count ?? 0) === 1 ? '' : 's'}`} />
            <Meta label="Pitch range" value={file.pitch_min != null ? `${noteName(file.pitch_min)} – ${noteName(file.pitch_max ?? file.pitch_min)}` : '—'} note={file.pitch_min != null ? `MIDI ${file.pitch_min}–${file.pitch_max}` : undefined} />
            <Meta label="Velocity" value={file.velocity_min != null ? `${file.velocity_min}–${file.velocity_max}` : '—'} note={analysis?.velocity_mean ? `mean ${analysis.velocity_mean}` : undefined} />
            <Meta label="Density" value={file.note_density != null ? `${file.note_density.toFixed(2)} / beat` : '—'} note={analysis?.polyphony_mean ? `avg polyphony ${analysis.polyphony_mean.toFixed(1)}` : undefined} />
            <Meta label="Key evidence" value={key?.source === 'embedded' ? 'Embedded' : key?.source === 'estimated' ? 'Estimated' : 'No key'} note={key?.runner_up ? `runner-up ${key.runner_up}` : undefined} />
            <Meta label="Classification" value={file.instrument_source === 'user' || file.role_source === 'user' ? 'Your labels' : 'SKEER rules'} note={`${classification?.classifier_ruleset || 'rules'} · v${file.classifier_version ?? '?'}`} />
          </div>
          {key?.conflict ? <InlineNotice tone="warning">{key.conflict}</InlineNotice> : null}
          {(file.tempo_change_count || 0) > 0 ? (
            <div className="tempo-map-strip">
              <span className="tempo-map-label">TEMPO MAP</span>
              {(tempo?.events || []).slice(0, 8).map((event, index) => (
                <span key={`${event.tick}-${index}`} className="tempo-map-event mono">
                  {formatBpm(event.bpm)} <em>BPM</em> <small>@ {formatTime(event.seconds)}</small>
                </span>
              ))}
              {(tempo?.events.length || 0) > 8 ? <span className="tempo-map-more">+{(tempo?.events.length || 0) - 8}</span> : null}
            </div>
          ) : null}
          <div className="controller-line">
            <span>Controllers:</span>
            {analysis?.controllers.named?.length ? (
              analysis.controllers.named.slice(0, 5).map((item) => (
                <span key={item.code} className="controller-chip" title={`${item.count} events`}>
                  {item.name} <em className="mono">{item.count}</em>
                </span>
              ))
            ) : (
              <span className="muted">none extracted</span>
            )}
            {(analysis?.controllers.tracks_with_sustain || 0) > 0 ? (
              <span className="controller-chip sustain">sustain present</span>
            ) : null}
          </div>
          {analysis?.embedded_text?.length ? (
            <div className="embedded-text-block">
              <span className="embedded-text-label">Embedded text</span>
              {analysis.embedded_text.slice(0, 5).map((item, index) => (
                <span key={index} className="embedded-text-chip" title={`${item.kind} · ${item.text}`}>
                  {item.text}
                </span>
              ))}
              {analysis.embedded_text.length > 5 ? <span className="muted">+{analysis.embedded_text.length - 5} more</span> : null}
            </div>
          ) : null}
        </section>

        {duplicateExact.length > 0 || duplicateSimilar.length > 0 ? (
          <section className="panel-card duplicates-card">
            <div className="card-heading">
              <div>
                <span className="card-kicker">Never removed automatically</span>
                <h3>Duplicate &amp; similarity</h3>
              </div>
            </div>
            {duplicateExact.length > 0 ? (
              <div className="duplicate-block">
                <div className="duplicate-heading">
                  <Badge tone="amber">{duplicateExact.length} exact copies</Badge>
                  <span>Same SHA-256 content. These are true duplicates.</span>
                </div>
                {duplicateExact.filter((member) => member.id !== file.id).map((member) => (
                  <button key={member.id} type="button" className="duplicate-file" onClick={() => onOpenFile(member.id)}>
                    <span className="cell-ellipsis">{member.filename}</span>
                    <span className="mono">{shortFolder(member.dirname)}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {duplicateSimilar.length > 0 ? (
              <div className="duplicate-block">
                <div className="duplicate-heading">
                  <Badge tone="neutral">{duplicateSimilar.length} similar</Badge>
                  <span>Musical fingerprint similarity, not byte duplication.</span>
                </div>
                {duplicateSimilar.filter((member) => member.id !== file.id).slice(0, 8).map((member) => (
                  <button key={member.id} type="button" className="duplicate-file" onClick={() => onOpenFile(member.id)}>
                    <span className="cell-ellipsis">{member.filename}</span>
                    <span className="mono">{member.tempo_bpm ? `${formatBpm(member.tempo_bpm)} BPM` : ''}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}

        <section className="panel-card organisation-card">
          <div className="card-heading">
            <div>
              <span className="card-kicker">Stored in the index, never in the MIDI file</span>
              <h3>Tags &amp; collections</h3>
            </div>
          </div>
          <div className="org-block">
            <div className="org-label"><TagIcon size={13} /> Tags</div>
            <div className="tag-input-row">
              {(allTags).map((tag) => (
                <span key={tag.id} className="user-tag">
                  {tag.name}
                  <button type="button" onClick={() => void onRemoveTag(tag.id)} aria-label={`Remove tag ${tag.name}`}>
                    <CloseIcon size={10} />
                  </button>
                </span>
              ))}
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  if (!tagText.trim()) return;
                  await onAddTag(tagText.trim());
                  setTagText('');
                }}
              >
                <input
                  className="tag-input"
                  value={tagText}
                  onChange={(event) => setTagText(event.target.value)}
                  placeholder="Add tag…"
                  aria-label="Add a tag"
                />
              </form>
            </div>
          </div>
          <div className="org-block">
            <div className="org-label"><CollectionIcon size={13} /> Collections</div>
            <div className="tag-input-row">
              {details.collections.map((collection) => (
                <span key={collection.id} className="collection-chip">
                  {collection.name}
                  <button type="button" onClick={() => void onRemoveFromCollection(collection.id)} aria-label={`Remove from ${collection.name}`}>
                    <CloseIcon size={10} />
                  </button>
                </span>
              ))}
              {availableCollections.length > 0 ? (
                <form
                  className="collection-add-form"
                  onSubmit={async (event) => {
                    event.preventDefault();
                    if (!addCollection) return;
                    await onAddToCollection(Number(addCollection));
                    setAddCollection('');
                  }}
                >
                  <Select
                    value={addCollection}
                    onChange={(event) => setAddCollection(event.target.value)}
                    aria-label="Add to collection"
                  >
                    <option value="">Add to collection…</option>
                    {availableCollections.map((collection) => (
                      <option key={collection.id} value={collection.id}>{collection.name}</option>
                    ))}
                  </Select>
                  <button className="mini-action" type="submit" aria-label="Add to selected collection"><PlusIcon size={12} /></button>
                </form>
              ) : null}
            </div>
          </div>
          <div className="org-block notes-block">
            <div className="org-label"><NoteIcon size={13} /> Notes</div>
            <textarea
              className="notes-input"
              value={notesDraft}
              placeholder="Add a private note about this file…"
              onChange={(event) => {
                setNotesDraft(event.target.value);
                setNotesDirty(true);
              }}
              onBlur={() => void saveNotes()}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                  event.preventDefault();
                  void saveNotes();
                }
              }}
              rows={3}
            />
            <div className="notes-footer">
              <span>{notesSaving ? 'Saving…' : notesDirty ? 'Unsaved note' : 'Saved locally'}</span>
              {notesDirty ? (
                <button type="button" className="text-action" onClick={() => void saveNotes()}>
                  Save note
                </button>
              ) : null}
            </div>
          </div>
        </section>

        {(warnings.length > 0 || (analysis?.assumed_durations || 0) > 0) ? (
          <section className="panel-card warnings-card">
            <div className="card-heading">
              <div>
                <span className="card-kicker">Parser observations</span>
                <h3>Warnings &amp; assumptions</h3>
              </div>
              <Badge tone="neutral">{warnings.length}</Badge>
            </div>
            {warnings.length === 0 ? <p className="subtle-empty">No parser warnings.</p> : null}
            <div className="warning-list">
              {(showAllWarnings ? warnings : warnings.slice(0, 4)).map((warning, index) => (
                <div key={index} className="warning-row"><WarningIcon size={12} /> <span>{warning}</span></div>
              ))}
            </div>
            {warnings.length > 4 ? (
              <button type="button" className="text-action" onClick={() => setShowAllWarnings((value) => !value)}>
                {showAllWarnings ? 'Show fewer' : `Show ${warnings.length - 4} more`}
              </button>
            ) : null}
            {(analysis?.assumed_durations || 0) > 0 ? (
              <p className="assumption-note">
                {analysis?.assumed_durations} note end{(analysis?.assumed_durations || 0) === 1 ? '' : 's'} were assumed
                because the MIDI omits matching note-off events.
              </p>
            ) : null}
          </section>
        ) : null}

        <div className="detail-footnote">
          <span>Analyzed locally by {file.classifier_method || 'SKEER transparent rules'}</span>
          <span>Parser v{file.parser_version ?? '—'} · classifier v{file.classifier_version ?? '—'}</span>
          <span>Indexed {formatRelativeTime(file.indexed_at)} · {formatBytes(file.size)}</span>
          {preview?.warnings?.length ? <span>{preview.warnings.length} parser note(s)</span> : null}
        </div>
      </div>
    </aside>
  );
}

function Meta({
  label,
  value,
  source,
  note,
}: {
  label: string;
  value: string;
  source?: string | null;
  note?: string;
}) {
  return (
    <div className="meta">
      <span className="meta-label">{label}</span>
      <span className="meta-value">{value}</span>
      <span className="meta-caption">
        {source ? <span className={`source-pill source-${source}`}>{sourceLabel(source)}</span> : null}
        {note ? <span>{note}</span> : null}
      </span>
    </div>
  );
}

function sourceLabel(source: string): string {
  switch (source) {
    case 'embedded':
      return 'embedded';
    case 'estimated':
      return 'estimated';
    case 'assumed':
      return 'assumed';
    case 'none':
      return 'none';
    case 'user':
      return 'your label';
    default:
      return source;
  }
}

function EvidenceList({
  evidence,
  alternatives,
  conflicts,
}: {
  evidence: Evidence[];
  alternatives: Array<{ category: string; share: number; score: number }>;
  conflicts: Evidence[];
}) {
  const seen = new Set<string>();
  const items = evidence.filter((item) => {
    const key = `${item.source}-${item.label}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return (
    <div className="evidence-box">
      <div className="evidence-list">
        {items.length === 0 ? <span className="muted">No supporting evidence recorded.</span> : null}
        {items.slice(0, 12).map((item, index) => (
          <div key={index} className={`evidence-item ${item.kind === 'conflict' ? 'is-conflict' : ''}`}>
            <span className={`evidence-kind kind-${item.kind}`}>{sourceName(item.source)}</span>
            <span className="evidence-label">{item.label}</span>
            <span className={`evidence-weight mono ${item.weight < 0 ? 'negative' : ''}`}>
              {item.weight > 0 ? '+' : ''}{item.weight.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
      {conflicts.length > 0 ? (
        <div className="evidence-note">
          Conflicting signals are kept visible; the chosen label is the strongest supported interpretation.
        </div>
      ) : null}
      {alternatives.length > 1 ? (
        <div className="alternatives-row">
          <span>Other possibilities:</span>
          {alternatives.slice(1, 4).map((alt) => (
            <span key={alt.category}>{alt.category} <span className="mono">{Math.round(alt.share * 100)}%</span></span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function sourceName(source: string): string {
  switch (source) {
    case 'midi_program':
      return 'program';
    case 'midi_channel':
      return 'channel';
    case 'track_text':
      return 'track name';
    case 'track_analysis':
      return 'track';
    case 'track_name':
      return 'track name';
    case 'filename_context':
      return 'filename';
    case 'register':
      return 'register';
    case 'texture':
      return 'texture';
    case 'rhythm':
      return 'rhythm';
    case 'arpeggio':
      return 'arp';
    case 'scale':
      return 'scale';
    case 'instrument':
      return 'instrument';
    case 'arrangement':
      return 'arrangement';
    case 'format':
      return 'format';
    case 'conflict':
      return 'conflict';
    default:
      return source;
  }
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function shortFolder(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  if (parts.length <= 2) return path;
  return `…\\${parts.slice(-2).join('\\')}`;
}
