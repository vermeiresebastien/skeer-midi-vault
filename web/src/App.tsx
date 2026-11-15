import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type {
  Bootstrap,
  Collection,
  Facets,
  FileDetails,
  FolderRow,
  LibraryFilters,
  LibraryItem,
  LibraryResponse,
  ScanStatus,
} from './types';
import { defaultFilters } from './types';
import { api, ApiRequestError } from './api';
import {
  AppearanceContext,
  applyAppearance,
  defaultAppearance,
  loadAppearance,
  saveAppearance,
  type Appearance,
} from './appearance';
import { PreviewEngine, sequenceFromPreview, soundLayerFromPreview } from './audio/engine';
import { soundSignature, type SoundId } from './audio/sounds';
import {
  loadSoundPreferences,
  saveSoundPreferences,
  sequenceOverrides,
  withSoundOverride,
  withSoundOverrides,
  type SoundPreferences,
} from './soundPreferences';
import { TopBar } from './components/TopBar';
import { Sidebar } from './components/Sidebar';
import { LibraryView } from './components/LibraryView';
import { DetailsPanel } from './components/DetailsPanel';
import { TransportBar } from './components/TransportBar';
import { ScanDialog } from './components/ScanDialog';
import { SettingsDialog } from './components/SettingsDialog';
import { FilterDialog } from './components/FilterDialog';
import { ExportDialog } from './components/ExportDialog';
import { Button } from './components/Common';
import { CloseIcon, InfoIcon } from './components/Icons';
import { basename } from './lib/format';

type ToastTone = 'info' | 'success' | 'error';

interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

const EMPTY_SCAN: ScanStatus = {
  active: false,
  state: 'idle',
  scan_id: null,
  mode: 'incremental',
  message: '',
  discovered: 0,
  indexed: 0,
  skipped: 0,
  failed: 0,
  issues: 0,
  directory_errors: 0,
  current_path: '',
  completion: 0,
  elapsed_seconds: 0,
  files_per_second: 0,
  started_at: null,
  ended_at: null,
  intensity: 'balanced',
  workers: 2,
  queue_depth: 0,
  skipped_cloud: 0,
  skipped_links: 0,
  sources_completed: 0,
  total_sources: 0,
};

function toLibraryItem(file: FileDetails['file']): LibraryItem {
  return {
    id: file.id,
    path: file.path,
    dirname: file.dirname,
    filename: file.filename,
    extension: file.path.split('.').pop() || 'mid',
    source_id: file.source_id,
    source_label: file.source_label,
    source_available: file.source_available,
    source_enabled: file.source_enabled,
    size: file.size,
    scan_state: file.scan_state,
    error: file.error,
    is_missing: file.is_missing,
    parser_version: file.parser_version,
    classifier_version: file.classifier_version,
    format: file.format,
    timing_type: file.timing_type,
    sequence_count: file.sequence_count,
    duration_seconds: file.duration_seconds,
    duration_beats: file.duration_beats,
    bars: file.bars,
    tempo_bpm: file.tempo_bpm,
    tempo_source: file.tempo_source,
    tempo_min_bpm: file.tempo_min_bpm,
    tempo_max_bpm: file.tempo_max_bpm,
    tempo_change_count: file.tempo_change_count,
    time_sig: file.time_sig,
    time_sig_source: file.time_sig_source,
    key_name: file.key_name,
    key_source: file.key_source,
    key_confidence: file.key_confidence,
    note_count: file.note_count,
    track_count: file.track_count,
    pitch_min: file.pitch_min,
    pitch_max: file.pitch_max,
    velocity_min: file.velocity_min,
    velocity_max: file.velocity_max,
    note_density: file.note_density,
    polyphony_max: file.polyphony_max,
    instrument: file.instrument,
    instrument_confidence: file.instrument_confidence,
    instrument_source: file.instrument_source,
    role: file.role,
    role_confidence: file.role_confidence,
    role_source: file.role_source,
    auto_instrument: file.auto_instrument,
    auto_instrument_confidence: file.auto_instrument_confidence,
    auto_role: file.auto_role,
    auto_role_confidence: file.auto_role_confidence,
    style_tags: file.style_tags,
    genre_hint: file.genre_hint,
    genre_confidence: file.genre_confidence,
    uncertain: file.uncertain,
    confidence: file.confidence,
    favorite: file.favorite,
    user_notes: file.user_notes,
    exact_group_id: file.exact_group_id,
    exact_copy_count: file.exact_copy_count,
    similar_group_id: file.similar_group_id,
    similar_copy_count: file.similar_copy_count,
    embedded_text: file.embedded_text_json,
    updated_at: file.updated_at || null,
    indexed_at: file.indexed_at || null,
  };
}

/**
 * The controls a browser activates on Space by itself. The global play/pause
 * shortcut has to leave them alone: preventDefault() on the keydown is exactly
 * what cancels the click a focused button would otherwise get on keyup, so a
 * keyboard user who had tabbed onto transport, filter or row controls got the
 * transport instead of the thing they were standing on. `summary` covers the
 * details/summary disclosure, and the ARIA roles are the ones the app gives its
 * own interactive rows and chips, which activate on Space by contract.
 */
const SPACE_ACTIVATES = [
  'button',
  'a[href]',
  'summary',
  'select',
  'input[type="checkbox"]',
  'input[type="radio"]',
  '[role="button"]',
  '[role="link"]',
  '[role="checkbox"]',
  '[role="radio"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="menuitem"]',
  '[role="option"]',
].join(',');

function activatesOnSpace(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  // An icon or label inside the control is the event target, so walk up to it.
  return target.closest(SPACE_ACTIVATES) !== null;
}

export default function App() {
  const engineRef = useRef<PreviewEngine | null>(null);
  if (!engineRef.current) engineRef.current = new PreviewEngine();
  const engine = engineRef.current;
  const [appearance, setAppearanceState] = useState<Appearance>(() => loadAppearance());
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [folders, setFolders] = useState<FolderRow[]>([]);
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryRefresh, setLibraryRefresh] = useState(0);
  const [filters, setFilters] = useState<LibraryFilters>(() => defaultFilters());
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);
  const [details, setDetails] = useState<FileDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [selectedSequence, setSelectedSequence] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [mutedTracks, setMutedTracks] = useState<Set<string>>(new Set());
  const [soloTracks, setSoloTracks] = useState<Set<string>>(new Set());
  const [soundPreferences, setSoundPreferences] = useState<SoundPreferences>(() => loadSoundPreferences());
  const [scan, setScan] = useState<ScanStatus>(EMPTY_SCAN);
  const [scanOpen, setScanOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoplayBusy, setAutoplayBusy] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportItems, setExportItems] = useState<LibraryItem[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const scanRef = useRef<ScanStatus>(EMPTY_SCAN);
  const libraryRequest = useRef(0);
  const autoSelected = useRef(false);
  // Records the file a user click asked to preview, so autoplay survives the
  // details reload and never fires on the row the library picks by itself.
  const autoplayFor = useRef<number | null>(null);
  const engineKeyRef = useRef('');
  const engineSoundRef = useRef('');
  // Mirror of soundPreferences for write paths. Reading state directly would
  // drop a second edit made in the same tick, and the ref is what makes
  // "apply to all tracks" atomic instead of last-one-wins.
  const soundPreferencesRef = useRef(soundPreferences);
  const lastLiveFacetRefresh = useRef(0);
  const lastEngineError = useRef<string | null>(null);

  const openFile = useCallback((id: number) => {
    // A click on a different file arms its preview; the sequence effect fires it
    // once that file's details have loaded, and only for that file.
    if (id !== selectedFileId) autoplayFor.current = id;
    setSelectedFileId(id);
  }, [selectedFileId]);

  const notify = useCallback((message: string, tone: ToastTone = 'info') => {
    const id = ++toastId.current;
    setToasts((current) => [...current.slice(-3), { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, tone === 'error' ? 6800 : 3800);
  }, []);

  const setAppearance = useCallback((updater: Partial<Appearance> | ((current: Appearance) => Appearance)) => {
    setAppearanceState((current) => {
      const next = typeof updater === 'function' ? updater(current) : { ...current, ...updater };
      saveAppearance(next);
      return next;
    });
  }, []);

  const autoplay = bootstrap?.settings?.preview_autoplay === '1';

  const toggleAutoplay = useCallback(async () => {
    const next = autoplay ? '0' : '1';
    setAutoplayBusy(true);
    try {
      const result = await api.updateSettings({ preview_autoplay: next });
      setBootstrap((current) => (current ? { ...current, settings: result.settings } : current));
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not change the autoplay setting.', 'error');
    } finally {
      setAutoplayBusy(false);
    }
  }, [autoplay, notify]);

  useEffect(() => {
    applyAppearance(appearance);
  }, [appearance]);

  useEffect(() => {
    const unsubscribe = engine.subscribe(() => {
      const error = engine.getSnapshot().error;
      if (error && error !== lastEngineError.current) {
        lastEngineError.current = error;
        notify(error, 'error');
      } else if (!error) {
        lastEngineError.current = null;
      }
    });
    return unsubscribe;
  }, [engine, notify]);

  const refreshFacets = useCallback(async () => {
    try {
      const [nextFacets, nextFolders] = await Promise.all([api.facets(), api.folders()]);
      setFacets(nextFacets);
      setFolders(nextFolders.folders);
    } catch {
      // Non-fatal: the current view still works.
    }
  }, []);

  const refreshBootstrap = useCallback(async () => {
    try {
      const payload = await api.bootstrap();
      setBootstrap(payload);
      setFacets(payload.facets);
      setScan(payload.scan);
      scanRef.current = payload.scan;
      const folderResult = await api.folders();
      setFolders(folderResult.folders);
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not refresh the library index.', 'error');
    }
  }, [notify]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const payload = await api.bootstrap();
        if (cancelled) return;
        setBootstrap(payload);
        setFacets(payload.facets);
        setScan(payload.scan);
        scanRef.current = payload.scan;
        const folderResult = await api.folders();
        if (cancelled) return;
        setFolders(folderResult.folders);
      } catch (error) {
        if (cancelled) return;
        setFatalError(
          error instanceof ApiRequestError && error.status === 0
            ? 'The local SKEER service is not running. Start it with start.bat or python -m midivault.server, then reload this page.'
            : error instanceof Error ? error.message : 'Could not open the local library.',
        );
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let timer = 0;
    let stopped = false;
    const poll = async () => {
      if (stopped) return;
      let nextDelay = 5000;
      try {
        const status = await api.scanStatus();
        if (stopped) return;
        const wasActive = scanRef.current.active;
        scanRef.current = status;
        setScan(status);
        if (wasActive && !status.active) {
          void refreshFacets();
          setLibraryRefresh((value) => value + 1);
          if (status.state === 'completed') {
            notify(
              `Index updated · ${status.indexed.toLocaleString()} files indexed${status.failed ? `, ${status.failed} issues` : ''}.`,
              status.failed ? 'info' : 'success',
            );
          }
        } else if (
          scanRef.current.state === 'running'
          && status.indexed > 0
          && status.indexed % 25 === 0
          && Date.now() - lastLiveFacetRefresh.current > 4000
        ) {
          // Keep the sidebar folder map useful during long scans without
          // refetching the whole bootstrap on every poll.
          lastLiveFacetRefresh.current = Date.now();
          void refreshFacets();
        }
        nextDelay = status.active ? 1000 : 5000;
      } catch {
        nextDelay = 8000;
      }
      if (!stopped) timer = window.setTimeout(poll, nextDelay);
    };
    timer = window.setTimeout(poll, 700);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [notify, refreshFacets]);

  useEffect(() => {
    const requestId = ++libraryRequest.current;
    setLibraryLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.library(filters);
        if (requestId !== libraryRequest.current) return;
        setLibrary(result);
        if (!autoSelected.current && result.items.length > 0 && selectedFileId === null) {
          autoSelected.current = true;
          setSelectedFileId(result.items[0].id);
        }
      } catch (error) {
        if (requestId === libraryRequest.current) {
          notify(error instanceof Error ? error.message : 'Could not query the library.', 'error');
        }
      } finally {
        if (requestId === libraryRequest.current) setLibraryLoading(false);
      }
    }, filters.q ? 180 : 60);
    return () => window.clearTimeout(timer);
    // selectedFileId is intentionally read only for first auto-selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, libraryRefresh, notify]);

  useEffect(() => {
    if (selectedFileId === null) {
      setDetails(null);
      setDetailsLoading(false);
      engine.setSequence(null);
      return;
    }
    let cancelled = false;
    setDetailsLoading(true);
    setDetails(null);
    setMutedTracks(new Set());
    setSoloTracks(new Set());
    engine.setSequence(null);
    setSelectedSequence(0);
    engineKeyRef.current = '';
    engineSoundRef.current = '';
    (async () => {
      try {
        const payload = await api.file(selectedFileId);
        if (cancelled) return;
        setDetails(payload);
        const primary = payload.cache?.analysis.file.primary_sequence_index ?? 0;
        setSelectedSequence(primary);
      } catch (error) {
        if (!cancelled) {
          notify(error instanceof Error ? error.message : 'Could not load the selected file.', 'error');
          setDetails(null);
        }
      } finally {
        if (!cancelled) setDetailsLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFileId]);

  // One source of truth for the voice layer. The rebuild guard and the details
  // panel read the same resolution, so a track chip can never advertise a sound
  // the engine is not actually playing. This only touches track-level data;
  // building the note array stays reserved for the moments a rebuild is due.
  const soundLayer = useMemo(() => {
    const sequence = details?.cache?.preview.sequences.find((item) => item.index === selectedSequence)
      || details?.cache?.preview.sequences[0];
    if (!details || !sequence) return null;
    // "Accepted" means the reviewer agreed with the machine; "corrected" means
    // they overrode it. Only an override should outrank a label at a narrower
    // scope, so accepting a file category cannot silently re-voice every part.
    const fileInstrumentAction = details.corrections.file
      .find((item) => item.dimension === 'instrument')?.action;
    const trackInstrumentActions = new Map(
      details.corrections.tracks
        .filter((item) => item.dimension === 'instrument')
        .map((item) => [`${item.sequence_index}:${item.track_index}`, item.action]),
    );
    const labels = details.tracks
      .filter((track) => track.sequence_index === sequence.index)
      .map((track) => ({
        sequence_index: track.sequence_index,
        track_index: track.track_index,
        instrument: track.instrument,
        role: track.role,
        instrument_source: trackInstrumentActions.get(`${track.sequence_index}:${track.track_index}`) === 'corrected'
          ? 'user'
          : 'auto',
      }));
    const options = {
      fileInstrument: details.file.instrument,
      fileInstrumentSource: fileInstrumentAction === 'corrected' ? 'user' : 'auto',
      overrides: sequenceOverrides(soundPreferences, details.file.path, sequence.index),
    };
    const tracks = soundLayerFromPreview(sequence, labels, options);
    const sounds: Record<string, SoundId> = {};
    for (const track of tracks) sounds[track.key] = track.sound;
    return {
      fileId: details.file.id,
      identity: `${details.file.id}:${sequence.index}`,
      signature: soundSignature(tracks),
      sounds,
      sequence,
      labels,
      options,
    };
  }, [details, selectedSequence, soundPreferences]);

  // ---------------------------------------------------------------- autoplay deck
  // The bounded list the transport walks when a preview ends by itself. It
  // rides the selection when the open file is part of a multi-selection — that
  // is the crate you asked to hear — and otherwise the rows the current filter
  // shows. It stops at the end instead of wrapping: an ear-scan that loops back
  // to the first file is a machine gun, not a review.
  const deckQueue = useMemo<number[]>(() => {
    const rows = (library?.items ?? []).map((item) => item.id);
    if (selectedIds.size > 1 && selectedFileId !== null && selectedIds.has(selectedFileId)) {
      const onList = rows.filter((id) => selectedIds.has(id));
      const offList = [...selectedIds]
        .filter((id) => !rows.includes(id))
        .sort((a, b) => a - b);
      return [...onList, ...offList];
    }
    return rows;
  }, [library, selectedIds, selectedFileId]);

  const deckIndex = selectedFileId === null ? -1 : deckQueue.indexOf(selectedFileId);

  const stepDeck = useCallback((delta: number) => {
    const target = deckIndex + delta;
    if (target < 0 || target >= deckQueue.length) return;
    openFile(deckQueue[target]);
  }, [deckIndex, deckQueue, openFile]);

  useEffect(() => {
    // The autoplay setting is the deck's switch: a clip the user stopped,
    // paused or seeked away from never reaches this, and a manual play with
    // autoplay off stays a one-off preview.
    if (!autoplay) return undefined;
    return engine.subscribeEnd(() => {
      const target = deckIndex + 1;
      if (target < deckQueue.length) openFile(deckQueue[target]);
      else if (deckQueue.length > 1) {
        notify(`End of the list · played through ${deckQueue.length} previews.`, 'info');
      }
    });
  }, [autoplay, engine, deckQueue, deckIndex, openFile, notify]);

  useEffect(() => {
    if (!soundLayer) {
      // No voice layer at all: the details call failed, or the file came back
      // with no preview sequence. That is the same "nothing to hear" case the
      // empty-notes branch below handles, so the arming is spent here too and
      // the deck gets past the row — otherwise one unreadable file stops an
      // ear-scan of the whole crate, and the arming survives to start the
      // transport the moment that row's layer does arrive.
      engine.setSequence(null);
      engineKeyRef.current = '';
      engineSoundRef.current = '';
      // Every file passes through this branch while its details are in flight,
      // and while nothing is selected at all. Spending the arming there would
      // throw away the click that started the deck.
      if (detailsLoading || selectedFileId === null) return;
      const armedRow = autoplayFor.current === selectedFileId;
      if (armedRow) autoplayFor.current = null;
      if (armedRow && autoplay) stepDeck(1);
      return;
    }
    const { fileId, identity, signature, sequence, labels, options } = soundLayer;
    // The arming is spent the first time this file's voice layer is reached,
    // whether or not it results in playback. Leaving it set would let a click
    // made with autoplay off start the transport later on, when autoplay gets
    // switched on or a correction forces a rebuild.
    const armed = autoplayFor.current === fileId;
    if (armed) autoplayFor.current = null;
    const autoplayNow = armed && autoplay;
    // Two independent reasons to rebuild. Identity covers "a different file or
    // sequence is on screen"; the signature covers "the same sequence is voiced
    // differently", which is what a correction or a manual pick does.
    const sameSequence = engineKeyRef.current === identity;
    if (sameSequence && engineSoundRef.current === signature) return;
    const engineSequence = sequenceFromPreview(sequence, labels, options);
    engineKeyRef.current = identity;
    engineSoundRef.current = signature;
    if (sameSequence) {
      // Re-voice in place: the playhead, the loop and the Audition tempo stay
      // put, so fixing a wrong label mid-preview does not throw you back to 0.
      engine.reloadSequence(engineSequence);
      return;
    }
    // setSequence releases every voice of the previous file before the new
    // one is installed, so autoplay cannot stack notes across two files.
    engine.setSequence(engineSequence);
    if (!autoplayNow) return;
    if (engineSequence.notes.length === 0 || !(engineSequence.duration > 0)) {
      // A clip with nothing to hear still has to be gotten past, or one empty
      // or unreadable file stalls the whole deck on the row that broke it.
      stepDeck(1);
      return;
    }
    void engine.play();
  }, [soundLayer, engine, autoplay, stepDeck, detailsLoading, selectedFileId]);

  useEffect(() => {
    engine.setTrackFilter(mutedTracks, soloTracks);
  }, [engine, mutedTracks, soloTracks]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = !!target && (
        ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) ||
        target.isContentEditable
      );
      if (typing) return;
      if (event.key === '/') {
        event.preventDefault();
        document.getElementById('library-search')?.focus();
        return;
      }
      if (event.code === 'Space') {
        // A focused control that Space belongs to keeps the key: the shortcut
        // owns it everywhere else, including on the body and the roll view.
        if (activatesOnSpace(event.target)) return;
        event.preventDefault();
        if (!engine.getSnapshot().hasSequence) return;
        if (engine.getSnapshot().playing) engine.pause();
        else void engine.play();
      }
      if (event.key === 'Escape') {
        setFiltersOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [engine]);

  useEffect(() => {
    window.__SKEER_MIDIVAULT_DEBUG__ = {
      engine,
      app: 'SKEER MIDI VAULT',
      // The service is the only place the version is written down, so the
      // debug handle reports what the running build really is.
      version: bootstrap?.app.version ?? 'unknown',
    };
    return () => {
      delete window.__SKEER_MIDIVAULT_DEBUG__;
    };
  }, [engine, bootstrap]);

  useEffect(() => () => {
    engine.stop();
  }, [engine]);

  const patchFilters = (patch: Partial<LibraryFilters>) => {
    // Selection deliberately survives a filter change: it is how you build a
    // crate across several passes, and the deck plays it. Clear it with the
    // explicit control in the library header.
    setFilters((current) => ({ ...current, ...patch }));
  };

  const refreshLibrary = () => setLibraryRefresh((value) => value + 1);

  const handleToggleFavorite = async (item: LibraryItem) => {
    const next = !item.favorite;
    setLibrary((current) => current ? {
      ...current,
      items: current.items.map((row) => row.id === item.id ? { ...row, favorite: next } : row),
    } : current);
    setDetails((current) => current && current.file.id === item.id
      ? { ...current, file: { ...current.file, favorite: next } }
      : current);
    try {
      await api.favorite(item.id, next);
      void refreshFacets();
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not update favorites.', 'error');
      refreshLibrary();
    }
  };

  const handleDetailsFavorite = async () => {
    if (!details) return;
    await handleToggleFavorite(toLibraryItem(details.file));
  };

  const setFileLabel = async (dimension: 'instrument' | 'role', value: string, clear = false) => {
    if (!details) return;
    const previous = details;
    // Optimistic update: a native select is controlled, so waiting for the
    // full details round-trip would visibly snap the choice back.
    const optimisticValue = clear
      ? (dimension === 'instrument' ? details.file.auto_instrument : details.file.auto_role)
      : value;
    setDetails({
      ...details,
      file: {
        ...details.file,
        ...(dimension === 'instrument'
          ? { instrument: optimisticValue, instrument_source: clear ? 'auto' : 'user' }
          : { role: optimisticValue, role_source: clear ? 'auto' : 'user' }),
      },
    });
    try {
      const updated = await api.setLabel(details.file.id, dimension, value, { clear });
      setDetails(updated);
      refreshLibrary();
      void refreshFacets();
    } catch (error) {
      setDetails(previous);
      notify(error instanceof Error ? error.message : 'Could not save the classification.', 'error');
      throw error;
    }
  };

  const setTrackLabel = async (
    sequence: number,
    track: number,
    dimension: 'instrument' | 'role',
    value: string,
    clear = false,
  ) => {
    if (!details) return;
    const previous = details;
    const targetTrack = details.tracks.find(
      (row) => row.sequence_index === sequence && row.track_index === track,
    );
    if (!targetTrack) return;
    const optimisticValue = clear
      ? (dimension === 'instrument' ? targetTrack.auto_instrument : targetTrack.auto_role)
      : value;
    setDetails({
      ...details,
      tracks: details.tracks.map((row) => (
        row.sequence_index === sequence && row.track_index === track
          ? {
            ...row,
            ...(dimension === 'instrument'
              ? { instrument: optimisticValue, instrument_source: clear ? 'auto' : 'user' }
              : { role: optimisticValue, role_source: clear ? 'auto' : 'user' }),
          }
          : row
      )),
    });
    try {
      const updated = await api.setTrackLabel(details.file.id, sequence, track, dimension, value, { clear });
      setDetails(updated);
      refreshLibrary();
    } catch (error) {
      setDetails(previous);
      notify(error instanceof Error ? error.message : 'Could not save the track classification.', 'error');
      throw error;
    }
  };

  const commitSoundPreferences = useCallback((next: SoundPreferences) => {
    // The ref is written before the state so a follow-up edit in the same tick
    // extends this map rather than overwriting it with the previous render's.
    soundPreferencesRef.current = next;
    setSoundPreferences(next);
    if (!saveSoundPreferences(next)) {
      notify('This browser is blocking local storage, so sound picks last only for this session.', 'info');
    }
  }, [notify]);

  /** Pick one track's preview voice. 'auto' hands the decision back to the analysis. */
  const setTrackSound = useCallback((sequenceIndex: number, trackIndex: number, sound: SoundId) => {
    if (!details) return;
    commitSoundPreferences(
      withSoundOverride(soundPreferencesRef.current, details.file.path, sequenceIndex, trackIndex, sound),
    );
  }, [commitSoundPreferences, details]);

  /**
   * One pick for every track in the sequence. Passing null clears them all,
   * which is what "reset to auto" means: the analysis decides per track again.
   */
  const setSequenceSound = useCallback((sound: SoundId | null) => {
    if (!details || !soundLayer) return;
    commitSoundPreferences(withSoundOverrides(
      soundPreferencesRef.current,
      details.file.path,
      soundLayer.sequence.index,
      soundLayer.sequence.tracks.map((track) => track.track_index),
      sound,
    ));
  }, [commitSoundPreferences, details, soundLayer]);

  const addTag = async (name: string) => {
    if (!details) return;
    try {
      await api.addTag(details.file.id, name);
      const updated = await api.file(details.file.id);
      setDetails(updated);
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not add the tag.', 'error');
    }
  };

  const removeTag = async (tagId: number) => {
    if (!details) return;
    try {
      await api.removeTag(details.file.id, tagId);
      const updated = await api.file(details.file.id);
      setDetails(updated);
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not remove the tag.', 'error');
    }
  };

  const addToCollection = async (collectionId: number) => {
    if (!details) return;
    try {
      await api.addToCollection(details.file.id, collectionId);
      const updated = await api.file(details.file.id);
      setDetails(updated);
      await refreshFacets();
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not add to the collection.', 'error');
    }
  };

  const removeFromCollection = async (collectionId: number) => {
    if (!details) return;
    try {
      await api.removeFromCollection(details.file.id, collectionId);
      const updated = await api.file(details.file.id);
      setDetails(updated);
      await refreshFacets();
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not remove from the collection.', 'error');
    }
  };

  const saveNotes = async (notes: string) => {
    if (!details) return;
    try {
      await api.updateFile(details.file.id, { notes });
      setDetails({ ...details, file: { ...details.file, user_notes: notes } });
      refreshLibrary();
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not save the note.', 'error');
      throw error;
    }
  };

  const createCollection = async (name: string) => {
    try {
      await api.createCollection(name);
      const updated = await api.collections();
      setFacets((current) => current ? {
        ...current,
        collections: updated.collections.map((collection) => ({
          id: collection.id,
          name: collection.name,
          count: collection.count || 0,
        })),
      } : current);
      notify('Collection created.', 'success');
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not create the collection.', 'error');
      throw error;
    }
  };

  const onBulkAction = async (
    action: 'favorite' | 'collection' | 'label',
    payload?: { dimension?: 'instrument' | 'role'; value?: string; collectionId?: number; favorite?: boolean },
  ) => {
    if (selectedIds.size === 0) return;
    const fileIds = [...selectedIds];
    try {
      if (action === 'favorite') {
        await api.bulk({ file_ids: fileIds, action: 'favorite', value: payload?.favorite ?? true });
        notify(`${fileIds.length} file${fileIds.length === 1 ? '' : 's'} updated.`, 'success');
      } else if (action === 'label') {
        await api.bulk({
          file_ids: fileIds,
          action: 'label',
          dimension: payload?.dimension,
          value: payload?.value,
        });
        notify(`${fileIds.length} file${fileIds.length === 1 ? '' : 's'} reclassified.`, 'success');
      } else if (action === 'collection' && payload?.collectionId) {
        await api.bulk({ file_ids: fileIds, action: 'collection', collection_id: payload.collectionId });
        notify(`Added ${fileIds.length} file${fileIds.length === 1 ? '' : 's'} to the collection.`, 'success');
      }
      setSelectedIds(new Set());
      setLibraryRefresh((value) => value + 1);
      await refreshFacets();
      if (details) {
        const updated = await api.file(details.file.id);
        setDetails(updated);
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not apply the bulk edit.', 'error');
    }
  };

  const openExport = (items: LibraryItem[]) => {
    if (items.length === 0) return;
    setExportItems(items);
    setExportOpen(true);
  };

  const toggleMute = (key: string) => {
    setMutedTracks((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleSolo = (key: string) => {
    setSoloTracks((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const startScan = async (payload: { source_ids: number[]; mode: string; intensity: string }) => {
    const response = await api.startScan({ ...payload });
    setScan(response.scan);
    scanRef.current = response.scan;
    notify('Scan started. Browsing remains available while it runs.', 'success');
  };

  const pauseScan = async () => {
    try {
      const status = await api.pauseScan();
      setScan(status);
      scanRef.current = status;
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not pause the scan.', 'error');
    }
  };

  const resumeScan = async () => {
    try {
      const status = await api.resumeScan();
      setScan(status);
      scanRef.current = status;
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not resume the scan.', 'error');
    }
  };

  const cancelScan = async () => {
    try {
      const status = await api.cancelScan();
      setScan(status);
      scanRef.current = status;
      notify('Scan cancelled. Already indexed files were kept.', 'info');
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not cancel the scan.', 'error');
    }
  };

  const rebuildIndex = async () => {
    const response = await api.rebuild();
    setScan(response.scan);
    scanRef.current = response.scan;
    setLibraryRefresh((value) => value + 1);
    await refreshFacets();
  };

  const revealFile = async () => {
    if (!details) return;
    try {
      await api.reveal(details.file.id);
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Could not reveal the original file.', 'error');
    }
  };

  const exportSelection = () => {
    if (selectedIds.size > 0 && library) {
      openExport(library.items.filter((item) => selectedIds.has(item.id)));
    } else if (details) {
      openExport([toLibraryItem(details.file)]);
    }
  };

  const title = useMemo(() => {
    if (filters.q) return `Search “${filters.q}”`;
    if (filters.favorite) return 'Favorites';
    if (filters.uncertain) return 'Uncertain';
    if (filters.duplicate === 'exact') return 'Exact duplicates';
    if (filters.duplicate === 'similar') return 'Similar files';
    if (filters.collection_id) {
      return facets?.collections.find((item) => String(item.id) === filters.collection_id)?.name || 'Collection';
    }
    if (filters.folder) return basename(filters.folder);
    if (filters.instrument.length === 1) return filters.instrument[0];
    if (filters.role.length === 1) return filters.role[0];
    return 'All MIDI';
  }, [filters, facets]);

  const subtitle = useMemo(() => {
    if (filters.folder) return filters.folder;
    if (filters.source_id) {
      const source = facets?.sources.find((item) => String(item.id) === filters.source_id);
      return source ? `Source: ${source.label || source.path}` : 'Filtered library';
    }
    if (filters.instrument.length || filters.role.length || filters.q) return 'Filtered library';
    if (filters.favorite) return 'Your selected files, kept locally';
    if (filters.uncertain) return 'Low-confidence predictions that may need review';
    if (filters.duplicate) return 'Content-identical and musically similar matches are kept separate';
    if (filters.collection_id) return 'A user collection — source files are untouched';
    return 'A private index of MIDI files on this computer';
  }, [filters, facets]);

  if (fatalError) {
    return (
      <div className="fatal-screen">
        <div className="fatal-card">
          <img src="/brand/skeer-wordmark.png" alt="SKEER" className="fatal-wordmark" />
          <span className="eyebrow">Connection</span>
          <h1>MIDI VAULT could not open</h1>
          <p>{fatalError}</p>
          <div className="fatal-commands">
            <code>start.bat</code>
            <span>or</span>
            <code>python -m midivault.server</code>
          </div>
          <Button variant="primary" onClick={() => window.location.reload()}>Retry</Button>
        </div>
      </div>
    );
  }

  if (!bootstrap) {
    return (
      <div className="splash-screen">
        <img src="/brand/skeer-wordmark.png" alt="SKEER" className="splash-wordmark" />
        <div className="splash-title">MIDI VAULT</div>
        <div className="splash-loader"><span /></div>
        <p>Opening your private MIDI index…</p>
      </div>
    );
  }

  const libraryCount = Math.max(0, (facets?.totals.total || 0) - (facets?.totals.failed || 0));

  return (
    <AppearanceContext.Provider
      value={{
        appearance,
        setAppearance,
        reset: () => setAppearance(defaultAppearance()),
      }}
    >
      <div className="app-shell">
        <TopBar
          scan={scan}
          onOpenScan={() => setScanOpen(true)}
          onOpenSettings={() => setSettingsOpen(true)}
          libraryCount={libraryCount}
        />
        <div className="app-main">
          <Sidebar
            facets={facets}
            filters={filters}
            onPatchFilters={patchFilters}
            folders={folders}
            collections={facets?.collections || []}
            onCreateCollection={createCollection}
            onOpenScan={() => setScanOpen(true)}
          />
          <LibraryView
            library={library}
            filters={filters}
            facets={facets}
            collections={facets?.collections || []}
            loading={libraryLoading}
            selectedId={selectedFileId}
            selectedIds={selectedIds}
            title={title}
            subtitle={subtitle}
            onPatchFilters={patchFilters}
            onSelect={(item) => openFile(item.id)}
            onToggleSelected={(id) => setSelectedIds((current) => {
              const next = new Set(current);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            })}
            onSelectAll={(ids) => setSelectedIds(new Set(ids))}
            onClearSelection={() => setSelectedIds(new Set())}
            onToggleFavorite={(item) => void handleToggleFavorite(item)}
            onOpenFilters={() => setFiltersOpen(true)}
            onOpenScan={() => setScanOpen(true)}
            onBulkAction={(action, payload) => void onBulkAction(action, payload)}
            onExportSelected={exportSelection}
            onRefresh={refreshLibrary}
          />
          <DetailsPanel
            details={details}
            loading={detailsLoading}
            selectedSequence={selectedSequence}
            onSelectSequence={setSelectedSequence}
            engine={engine}
            mutedTracks={mutedTracks}
            soloTracks={soloTracks}
            onToggleMute={toggleMute}
            onToggleSolo={toggleSolo}
            onSetFileLabel={setFileLabel}
            onSetTrackLabel={setTrackLabel}
            trackSounds={soundLayer?.sounds || {}}
            trackSoundPicks={(details && soundPreferences[details.file.path]) || {}}
            onSetTrackSound={setTrackSound}
            onSetSequenceSound={setSequenceSound}
            onToggleFavorite={() => void handleDetailsFavorite()}
            onReveal={() => void revealFile()}
            onExport={exportSelection}
            onAddTag={addTag}
            onRemoveTag={removeTag}
            onAddToCollection={addToCollection}
            onRemoveFromCollection={removeFromCollection}
            onSaveNotes={saveNotes}
            onOpenFile={(id) => {
              openFile(id);
              setSelectedIds(new Set());
            }}
            collections={facets?.collections || []}
            onNotify={notify}
          />
        </div>
        <TransportBar
          engine={engine}
          scan={scan}
          autoplay={autoplay}
          autoplayBusy={autoplayBusy}
          onToggleAutoplay={() => void toggleAutoplay()}
          deckIndex={deckIndex}
          deckCount={deckQueue.length}
          onStepDeck={stepDeck}
          onOpenScan={() => setScanOpen(true)}
          onPauseScan={() => void pauseScan()}
          onResumeScan={() => void resumeScan()}
          onCancelScan={() => void cancelScan()}
          onNotify={notify}
        />
        <ScanDialog
          open={scanOpen}
          scan={scan}
          onClose={() => setScanOpen(false)}
          onStart={startScan}
          onPause={() => void pauseScan()}
          onResume={() => void resumeScan()}
          onCancel={() => void cancelScan()}
          onNotify={notify}
          onRefreshApp={refreshBootstrap}
        />
        <SettingsDialog
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          bootstrap={bootstrap}
          onRefresh={refreshBootstrap}
          onRebuild={rebuildIndex}
          onNotify={notify}
        />
        <FilterDialog
          open={filtersOpen}
          filters={filters}
          facets={facets}
          onClose={() => setFiltersOpen(false)}
          onApply={patchFilters}
        />
        <ExportDialog
          open={exportOpen}
          onClose={() => setExportOpen(false)}
          items={exportItems}
          defaultDestination={bootstrap.default_export_dir || ''}
          onNotify={notify}
        />
        <ToastViewport toasts={toasts} onDismiss={(id) => setToasts((current) => current.filter((toast) => toast.id !== id))} />
      </div>
    </AppearanceContext.Provider>
  );
}

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div className="toast-viewport" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tone}`}>
          <span className="toast-icon">
            {toast.tone === 'success' ? '✓' : toast.tone === 'error' ? '!' : <InfoIcon size={14} />}
          </span>
          <span className="toast-message">{toast.message}</span>
          <button type="button" onClick={() => onDismiss(toast.id)} aria-label="Dismiss notification">
            <CloseIcon size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
