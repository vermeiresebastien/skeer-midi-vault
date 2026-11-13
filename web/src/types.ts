export const INSTRUMENT_CATEGORIES = [
  'Drums/percussion',
  'Bass',
  'Piano/keys',
  'Guitar/plucked',
  'Strings',
  'Brass/woodwinds',
  'Synth',
  'Mixed arrangement',
  'Unknown',
] as const;

export const TRACK_INSTRUMENT_CATEGORIES = INSTRUMENT_CATEGORIES.filter(
  (category) => category !== 'Mixed arrangement',
);

export const ROLE_CATEGORIES = [
  'Drum groove',
  'Drum fill',
  'Bassline',
  'Chord progression',
  'Lead/melody',
  'Arpeggio',
  'Pad/sustained harmony',
  'Complete song or multi-part arrangement',
  'Exercise or technical pattern',
  'Unknown',
] as const;

export const TRACK_ROLE_CATEGORIES = ROLE_CATEGORIES.filter(
  (role) => role !== 'Complete song or multi-part arrangement',
);

export type Instrument = (typeof INSTRUMENT_CATEGORIES)[number];
export type Role = (typeof ROLE_CATEGORIES)[number];

export interface Evidence {
  source: string;
  kind: 'embedded' | 'calculated' | 'filename' | 'conflict' | string;
  label: string;
  weight: number;
  category?: string | null;
}

export interface Alternative {
  category: string;
  share: number;
  score: number;
}

export interface ApiSource {
  id: number;
  path: string;
  label: string | null;
  kind: string;
  optional: boolean | number;
  enabled: boolean | number;
  available: boolean | number;
  last_seen_at?: string | null;
  created_at?: string | null;
  counts?: { files: number; indexed: number; failed: number };
  total_bytes?: number | null;
  free_bytes?: number | null;
  filesystem?: string;
}

export interface Drive extends ApiSource {
  drive_letter?: string | null;
}

export type StyleTag = 'straight' | 'swung' | 'sparse' | 'dense' | 'syncopated';

export interface LibraryItem {
  id: number;
  path: string;
  dirname: string;
  filename: string;
  extension: string;
  source_id: number | null;
  source_label: string | null;
  source_available: boolean | null;
  source_enabled: boolean | null;
  size: number | null;
  scan_state: 'indexed' | 'missing' | 'failed' | string;
  error: string | null;
  is_missing: number;
  parser_version: number | null;
  classifier_version: number | null;
  format: number | null;
  timing_type: string | null;
  sequence_count: number | null;
  duration_seconds: number | null;
  duration_beats: number | null;
  bars: number | null;
  tempo_bpm: number | null;
  tempo_source: string | null;
  tempo_min_bpm: number | null;
  tempo_max_bpm: number | null;
  tempo_change_count: number | null;
  time_sig: string | null;
  time_sig_source: string | null;
  key_name: string | null;
  key_source: string | null;
  key_confidence: number | null;
  note_count: number | null;
  track_count: number | null;
  pitch_min: number | null;
  pitch_max: number | null;
  velocity_min: number | null;
  velocity_max: number | null;
  note_density: number | null;
  polyphony_max: number | null;
  instrument: string;
  instrument_confidence: number | null;
  instrument_source: string;
  role: string;
  role_confidence: number | null;
  role_source: string;
  auto_instrument: string | null;
  auto_instrument_confidence: number | null;
  auto_role: string | null;
  auto_role_confidence: number | null;
  style_tags: string[];
  genre_hint: string | null;
  genre_confidence: number | null;
  uncertain: boolean;
  confidence: number | null;
  favorite: boolean;
  user_notes: string;
  exact_group_id: number | null;
  exact_copy_count: number;
  similar_group_id: number | null;
  similar_copy_count: number;
  embedded_text: string[];
  updated_at: string | null;
  indexed_at: string | null;
}

export interface LibraryFilters {
  q: string;
  instrument: string[];
  role: string[];
  style: string[];
  tempo_min: string;
  tempo_max: string;
  time_sig: string;
  key: string;
  key_source: string;
  duration_min: string;
  duration_max: string;
  bars_min: string;
  bars_max: string;
  pitch_min: string;
  pitch_max: string;
  density_min: string;
  density_max: string;
  confidence_min: string;
  folder: string;
  source_id: string;
  favorite: boolean;
  uncertain: boolean;
  duplicate: string;
  scan_state: string;
  collection_id: string;
  tag: string;
  include_failed: boolean;
  sort: string;
  page: number;
  page_size: number;
}

export const defaultFilters = (): LibraryFilters => ({
  q: '',
  instrument: [],
  role: [],
  style: [],
  tempo_min: '',
  tempo_max: '',
  time_sig: '',
  key: '',
  key_source: '',
  duration_min: '',
  duration_max: '',
  bars_min: '',
  bars_max: '',
  pitch_min: '',
  pitch_max: '',
  density_min: '',
  density_max: '',
  confidence_min: '',
  folder: '',
  source_id: '',
  favorite: false,
  uncertain: false,
  duplicate: '',
  scan_state: '',
  collection_id: '',
  tag: '',
  include_failed: false,
  sort: 'name',
  page: 1,
  page_size: 60,
});

export interface LibraryResponse {
  items: LibraryItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  fts: boolean;
}

export interface FacetItem {
  value: string;
  count: number;
}

export interface Facets {
  totals: {
    total: number;
    favorites: number;
    uncertain: number;
    missing: number;
    failed: number;
    exact_duplicates: number;
    similar_duplicates: number;
  };
  instruments: FacetItem[];
  roles: FacetItem[];
  styles: FacetItem[];
  sources: Array<{
    id: number;
    label: string;
    path: string;
    available: number;
    kind: string;
    enabled: number;
    count: number;
  }>;
  collections: Array<{ id: number; name: string; count: number }>;
  tags: Array<{ id: number; name: string; color: string | null; count: number }>;
}

export interface ScanStatus {
  active: boolean;
  state: string;
  scan_id: number | null;
  mode: string;
  message: string;
  discovered: number;
  indexed: number;
  skipped: number;
  failed: number;
  issues: number;
  directory_errors: number;
  current_path: string;
  completion: number;
  elapsed_seconds: number;
  files_per_second: number;
  started_at: string | null;
  ended_at: string | null;
  intensity: string;
  workers: number;
  queue_depth: number;
  skipped_cloud: number;
  skipped_links: number;
  sources_completed: number;
  total_sources: number;
  duplicates?: Record<string, number>;
  last_scan?: unknown;
  issues_detail?: ScanIssue[];
}

export interface ScanIssue {
  id: number;
  scan_run_id: number | null;
  kind: string;
  path: string;
  message: string;
  created_at: string;
}

export interface Collection {
  id: number;
  name: string;
  description?: string | null;
  created_at?: string;
  updated_at?: string;
  count?: number;
}

export interface Tag {
  id: number;
  name: string;
  color: string | null;
  count?: number;
}

export interface PreviewNote {
  b: number;
  d: number;
  t: number;
  l: number;
  p: number;
  v: number;
  a?: number;
  s?: number;
}

export interface PreviewTrack {
  sequence_index: number;
  track_index: number;
  chunk_index: number;
  channel: number;
  name: string | null;
  instrument_name: string | null;
  program: number | null;
  programs: number[];
  bank_msb: number | null;
  bank_lsb: number | null;
  notes: PreviewNote[];
  sustain_events: number;
  assumed_durations: number;
  sustained_notes: number;
  controller_counts: Record<string, number>;
  controller_values: Record<string, number>;
}

export interface PreviewTempo {
  tick: number;
  beat: number;
  seconds: number;
  bpm: number;
  microseconds: number;
  embedded: boolean;
}

export interface PreviewTimeSignature {
  tick: number;
  beat: number;
  numerator: number;
  denominator: number;
  label: string;
  embedded: boolean;
}

export interface PreviewKeySignature {
  tick: number;
  beat: number;
  sharps_flats: number;
  minor: number;
  label: string | null;
  embedded: boolean;
}

export interface PreviewSequence {
  index: number;
  name: string | null;
  duration_seconds: number;
  duration_beats: number;
  timing_type: string;
  ticks_per_quarter: number | null;
  bars: number | null;
  tempos: PreviewTempo[];
  time_signatures: PreviewTimeSignature[];
  key_signatures: PreviewKeySignature[];
  texts: Array<{ kind: string; text: string; tick: number; sequence: number }>;
  warnings: string[];
  tracks: PreviewTrack[];
}

export interface PreviewData {
  format: number;
  duration_seconds: number;
  duration_beats: number;
  note_count: number;
  timing_type: string;
  warnings: string[];
  sequences: PreviewSequence[];
}

export interface TrackRow {
  id: number;
  file_id: number;
  sequence_index: number;
  track_index: number;
  chunk_index: number;
  channel: number;
  name: string | null;
  program: number | null;
  programs: number[];
  note_count: number;
  pitch_min: number | null;
  pitch_max: number | null;
  sustained_notes: number;
  assumed_durations: number;
  auto_instrument: string;
  auto_instrument_confidence: number;
  auto_instrument_evidence: Evidence[];
  auto_instrument_alternatives: Alternative[];
  auto_role: string;
  auto_role_confidence: number;
  auto_role_evidence: Evidence[];
  auto_role_alternatives: Alternative[];
  instrument: string;
  instrument_confidence: number;
  instrument_source: 'auto' | 'user' | string;
  role: string;
  role_confidence: number;
  role_source: 'auto' | 'user' | string;
  label_source: string;
  style_tags: string[];
  uncertain: boolean;
  conflicts: Evidence[];
  analysis: {
    note_count?: number;
    pitch_min_name?: string | null;
    pitch_max_name?: string | null;
    monophonic_ratio?: number | null;
    polyphony_max?: number | null;
    note_density?: number | null;
    program_names?: string[];
    bar_span?: number | null;
  };
}

export interface FileRow {
  id: number;
  path: string;
  dirname: string;
  filename: string;
  parser_version: number | null;
  classifier_version: number | null;
  classifier_method: string | null;
  indexed_at: string | null;
  updated_at: string | null;
  source_id: number | null;
  source_label: string | null;
  source_available: boolean | null;
  source_kind: string | null;
  source_enabled: boolean | null;
  source_path?: string | null;
  scan_state: string;
  error: string | null;
  is_missing: number;
  size: number | null;
  format: number | null;
  timing_type: string | null;
  sequence_count: number | null;
  duration_seconds: number | null;
  duration_beats: number | null;
  bars: number | null;
  tempo_bpm: number | null;
  tempo_source: string | null;
  tempo_min_bpm: number | null;
  tempo_max_bpm: number | null;
  tempo_change_count: number | null;
  time_sig: string | null;
  time_sig_source: string | null;
  key_name: string | null;
  key_source: string | null;
  key_confidence: number | null;
  note_count: number | null;
  track_count: number | null;
  pitch_min: number | null;
  pitch_max: number | null;
  velocity_min: number | null;
  velocity_max: number | null;
  note_density: number | null;
  polyphony_max: number | null;
  instrument: string;
  instrument_confidence: number | null;
  instrument_source: string;
  role: string;
  role_confidence: number | null;
  role_source: string;
  auto_instrument: string;
  auto_instrument_confidence: number | null;
  auto_role: string;
  auto_role_confidence: number | null;
  label_source: string;
  style_tags: string[];
  genre_hint: string | null;
  genre_confidence: number | null;
  uncertain: boolean;
  confidence: number | null;
  conflicts_json: Evidence[];
  uncertainty_json: string[];
  warnings_json: string[];
  embedded_text_json: string[];
  favorite: boolean;
  user_notes: string;
  exact_group_id: number | null;
  exact_copy_count: number;
  similar_group_id: number | null;
  similar_copy_count: number;
}

export interface AnalysisTrack {
  sequence_index: number;
  track_index: number;
  chunk_index: number;
  channel: number;
  channel_display: number;
  drum_channel: boolean;
  name: string | null;
  instrument_name: string | null;
  programs: number[];
  program_names: string[];
  program_categories: string[];
  bank: { msb: number | null; lsb: number | null };
  note_count: number;
  pitch_min: number | null;
  pitch_max: number | null;
  pitch_min_name: string | null;
  pitch_max_name: string | null;
  pitch_median: number | null;
  monophonic_ratio: number;
  polyphony_max: number;
  polyphony_mean: number;
  note_density: number;
  avg_note_duration: number;
  short_note_ratio: number;
  long_note_ratio: number;
  syncopation_ratio: number;
  swing_ratio: number;
  regularity: number;
  pattern_repeat: number;
  scale_score: number;
  arpeggio_score: number;
  chord_tone_coverage: number;
  chord_hypothesis: string | null;
  low_register_ratio: number;
  high_register_ratio: number;
  stepwise_ratio: number;
  sustained_notes: number;
  assumed_durations: number;
  sustain_events: number;
  embedded_texts: string[];
  controller_summary: Record<string, number>;
  bar_span: number;
}

export interface AnalysisFile {
  format: number;
  format_2: boolean;
  sequence_count: number;
  primary_sequence_index: number;
  timing_type: string;
  duration_seconds: number;
  duration_beats: number;
  bars: number | null;
  note_count: number;
  track_count: number;
  channel_count: number;
  tempo: {
    initial_bpm: number;
    source: string;
    assumed: boolean;
    min_bpm: number;
    max_bpm: number;
    change_count: number;
    events: PreviewTempo[];
  };
  time_signature: {
    initial: string;
    source: string;
    assumed: boolean;
    change_count: number;
    events: PreviewTimeSignature[];
  };
  key: {
    label: string | null;
    embedded: string | null;
    estimated: string | null;
    source: string;
    confidence: number;
    uncertain: boolean;
    correlation: number;
    runner_up: string | null;
    conflict: string | null;
    events: PreviewKeySignature[];
  };
  pitch_min: number | null;
  pitch_max: number | null;
  pitch_min_name: string | null;
  pitch_max_name: string | null;
  velocity_min: number | null;
  velocity_max: number | null;
  velocity_mean: number | null;
  note_density: number;
  polyphony_max: number;
  polyphony_mean: number;
  programs: number[];
  program_names: string[];
  embedded_text: Array<{ kind: string; text: string; tick: number; sequence: number }>;
  controllers: {
    counts: Record<string, number>;
    values: Record<string, number>;
    named: Array<{ code: number; name: string; count: number }>;
    tracks_with_sustain: number;
  };
  warnings: string[];
  assumed_durations: number;
  unique_track_names: string[];
  unique_program_names: string[];
}

export interface ClassificationTrack {
  sequence_index: number;
  track_index: number;
  name: string | null;
  channel: number;
  instrument: string;
  instrument_confidence: number;
  instrument_evidence: Evidence[];
  instrument_alternatives: Alternative[];
  role: string;
  role_confidence: number;
  role_evidence: Evidence[];
  role_alternatives: Alternative[];
  feel_tags: string[];
  uncertain: boolean;
  conflicts: Evidence[];
}

export interface ClassificationFile {
  instrument: string;
  instrument_confidence: number;
  instrument_evidence: Evidence[];
  instrument_alternatives: Alternative[];
  role: string;
  role_confidence: number;
  role_evidence: Evidence[];
  role_alternatives: Alternative[];
  style_tags: string[];
  feel_tags: string[];
  genre_hint: string | null;
  genre_confidence: number;
  genre_evidence: string;
  genre_method: string;
  confidence: number;
  uncertain: boolean;
  conflicts: Evidence[];
  uncertainty_notes: string[];
  classifier_method: string;
  classifier_ruleset: string;
  classifier_version: number;
  primary_sequence_index: number;
  primary_track_count: number;
  primary_note_count: number;
  sequence_count: number;
  format_2_multi_sequence: boolean;
}

export interface CachePayload {
  preview: PreviewData;
  analysis: { file: AnalysisFile; tracks: AnalysisTrack[]; sequences: unknown[] };
  classification: { file: ClassificationFile; tracks: ClassificationTrack[]; method: unknown };
  parser_version?: number;
  classifier_version?: number;
}

export interface Correction {
  id: number;
  dimension: string;
  value: string;
  action: 'accepted' | 'corrected' | string;
  created_at: string;
}

export interface FileDetails {
  file: FileRow;
  tracks: TrackRow[];
  cache: CachePayload | null;
  tags: Tag[];
  collections: Collection[];
  corrections: {
    file: Correction[];
    tracks: Array<Correction & { sequence_index: number; track_index: number }>;
  };
  predictions: Array<Record<string, unknown>>;
  duplicates: {
    exact_members: Array<{
      id: number;
      path: string;
      filename: string;
      dirname: string;
      source_id: number;
      source_available: number | null;
    }>;
    similar_members: Array<{
      id: number;
      path: string;
      filename: string;
      dirname: string;
      instrument: string;
      role: string;
      tempo_bpm: number | null;
      duration_seconds: number | null;
    }>;
  };
}

export interface Bootstrap {
  app: { name: string; version: string; privacy: string };
  versions: {
    parser: number;
    classifier: number;
    schema: number;
    classifier_method: string;
    ruleset: string;
  };
  supported_extensions: string[];
  sources: ApiSource[];
  drives: Drive[];
  facets: Facets;
  stats: Record<string, number> & {
    db_path?: string;
    db_size_bytes?: number;
    fts_enabled?: boolean;
  };
  scan: ScanStatus;
  settings: Record<string, string>;
  excludes: Array<{ id: number; path: string; note?: string | null; created_at?: string }>;
  collections: Collection[];
  tags: Tag[];
  db: { path: string; fts_enabled: boolean; size_bytes: number };
  default_export_dir?: string;
  home_dir?: string;
  desktop?: { mode: boolean; can_quit: boolean };
}

export interface FolderRow {
  path: string;
  source_id: number;
  count: number;
}

export type SortKey = 'name' | 'recent' | 'tempo' | 'confidence' | 'duration' | 'bars' | 'relevance';
