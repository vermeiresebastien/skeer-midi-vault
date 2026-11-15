/**
 * Shared plumbing for the browser harnesses that drive the built interface.
 *
 * Everything here serves the REAL built interface out of `web/dist` and answers
 * its `/api` calls from fixtures, so a harness can drive the actual React app in
 * headless Chrome without a Python service and — critically — without ever
 * touching the user's library or index. Nothing is written anywhere.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const repoRoot = path.resolve(here, '..');
// SKEER_DIST lets a harness point at a pre-fix build to prove the checks fail
// on the old interface; the default is the real one the app ships.
export const distDir = process.env.SKEER_DIST
  ? path.resolve(process.env.SKEER_DIST)
  : path.join(repoRoot, 'web', 'dist');
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** The rows the fake index reports. 102 and 103 are the rows that yield no sound. */
export const FILES = [
  { id: 101, name: 'Alpha Groove.mid', kind: 'ok' },
  { id: 102, name: 'Broken Take.mid', kind: 'fetch-fails' },
  { id: 103, name: 'Empty Sequences.mid', kind: 'no-sequence' },
  { id: 104, name: 'Gamma Take.mid', kind: 'ok' },
  { id: 105, name: 'Delta Take.mid', kind: 'ok' },
];

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.map': 'application/json',
};

function json(route, payload, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  });
}

/** A MIDI file as the preview endpoint reports it: one short, audible sequence. */
function previewSequence(id) {
  const note = (t, p) => ({ b: Math.round(t * 2), d: 240, t, l: 0.22, p, v: 92 });
  return {
    index: 0,
    name: 'Full arrangement',
    duration_seconds: 0.9,
    duration_beats: 2,
    timing_type: 'ppqn',
    ticks_per_quarter: 480,
    bars: 2,
    tempos: [{ tick: 0, beat: 0, seconds: 0, bpm: 120, microseconds: 500000, embedded: true }],
    time_signatures: [],
    key_signatures: [],
    texts: [],
    warnings: [],
    tracks: [
      {
        sequence_index: 0,
        track_index: 0,
        chunk_index: 0,
        channel: 0,
        name: `Part ${id}`,
        instrument_name: null,
        program: 0,
        programs: [0],
        bank_msb: null,
        bank_lsb: null,
        notes: [note(0.05, 60 + (id % 5)), note(0.5, 64 + (id % 5))],
        sustain_events: 0,
        assumed_durations: 0,
        sustained_notes: 0,
        controller_counts: {},
        controller_values: {},
      },
    ],
  };
}

function libraryItem(meta) {
  return {
    id: meta.id,
    path: `D:/Midi/Test/${meta.name}`,
    dirname: 'D:/Midi/Test',
    filename: meta.name,
    extension: '.mid',
    source_id: 1,
    source_label: 'Test Source',
    source_available: true,
    source_enabled: true,
    size: 1024,
    scan_state: 'indexed',
    error: null,
    is_missing: 0,
    parser_version: 1,
    classifier_version: 1,
    format: 1,
    timing_type: 'ppqn',
    sequence_count: 1,
    duration_seconds: 0.9,
    duration_beats: 2,
    bars: 2,
    tempo_bpm: 120,
    tempo_source: 'embedded',
    tempo_min_bpm: 120,
    tempo_max_bpm: 120,
    tempo_change_count: 1,
    time_sig: '4/4',
    time_sig_source: 'assumed',
    key_name: 'C',
    key_source: 'estimated',
    key_confidence: 0.5,
    note_count: 2,
    track_count: 1,
    pitch_min: 60,
    pitch_max: 66,
    velocity_min: 92,
    velocity_max: 92,
    note_density: 2.2,
    polyphony_max: 1,
    instrument: 'Piano/keys',
    instrument_confidence: 0.6,
    instrument_source: 'auto',
    role: 'Lead/melody',
    role_confidence: 0.6,
    role_source: 'auto',
    auto_instrument: 'Piano/keys',
    auto_instrument_confidence: 0.6,
    auto_role: 'Lead/melody',
    auto_role_confidence: 0.6,
    style_tags: ['straight'],
    genre_hint: null,
    genre_confidence: 0,
    uncertain: false,
    confidence: 0.6,
    favorite: false,
    user_notes: '',
    exact_group_id: null,
    exact_copy_count: 1,
    similar_group_id: null,
    similar_copy_count: 1,
    embedded_text: [],
    updated_at: '2026-01-01T00:00:00',
    indexed_at: '2026-01-01T00:00:00',
  };
}

function trackRow(meta) {
  return {
    id: meta.id * 10,
    file_id: meta.id,
    sequence_index: 0,
    track_index: 0,
    chunk_index: 0,
    channel: 0,
    name: `Part ${meta.id}`,
    program: 0,
    programs: [0],
    note_count: 2,
    pitch_min: 60,
    pitch_max: 66,
    sustained_notes: 0,
    assumed_durations: 0,
    auto_instrument: 'Piano/keys',
    auto_instrument_confidence: 0.6,
    auto_instrument_evidence: [],
    auto_instrument_alternatives: [],
    auto_role: 'Lead/melody',
    auto_role_confidence: 0.6,
    auto_role_evidence: [],
    auto_role_alternatives: [],
    instrument: 'Piano/keys',
    instrument_confidence: 0.6,
    instrument_source: 'auto',
    role: 'Lead/melody',
    role_confidence: 0.6,
    role_source: 'auto',
    label_source: 'auto',
    style_tags: ['straight'],
    uncertain: false,
    conflicts: [],
    analysis: { note_count: 2, pitch_min_name: 'C4', pitch_max_name: 'F#4', monophonic_ratio: 1, polyphony_max: 1, note_density: 2.2 },
  };
}

function analysisFile(meta) {
  return {
    format: 1,
    format_2: false,
    sequence_count: 1,
    primary_sequence_index: 0,
    timing_type: 'ppqn',
    duration_seconds: 0.9,
    duration_beats: 2,
    bars: 2,
    note_count: 2,
    track_count: 1,
    channel_count: 1,
    tempo: { initial_bpm: 120, source: 'embedded', assumed: false, min_bpm: 120, max_bpm: 120, change_count: 1, events: [] },
    time_signature: { initial: '4/4', source: 'assumed', assumed: true, change_count: 0, events: [] },
    key: {
      label: 'C major', embedded: null, estimated: 'C major', source: 'estimated',
      confidence: 0.5, uncertain: false, correlation: 0.5, runner_up: null, conflict: null, events: [],
    },
    pitch_min: 60,
    pitch_max: 66,
    pitch_min_name: 'C4',
    pitch_max_name: 'F#4',
    velocity_min: 92,
    velocity_max: 92,
    velocity_mean: 92,
    note_density: 2.2,
    polyphony_max: 1,
    polyphony_mean: 1,
    programs: [0],
    program_names: ['Acoustic Grand Piano'],
    embedded_text: [],
    controllers: { counts: {}, values: {}, named: [], tracks_with_sustain: 0 },
    warnings: [],
    assumed_durations: 0,
    unique_track_names: [`Part ${meta.id}`],
    unique_program_names: ['Acoustic Grand Piano'],
  };
}

function classificationFile() {
  return {
    instrument: 'Piano/keys',
    instrument_confidence: 0.6,
    instrument_evidence: [],
    instrument_alternatives: [],
    role: 'Lead/melody',
    role_confidence: 0.6,
    role_evidence: [],
    role_alternatives: [],
    style_tags: ['straight'],
    feel_tags: [],
    genre_hint: null,
    genre_confidence: 0,
    genre_evidence: '',
    genre_method: 'rules',
    confidence: 0.6,
    uncertain: false,
    conflicts: [],
    uncertainty_notes: [],
    classifier_method: 'rules',
    classifier_ruleset: 'v1',
    classifier_version: 1,
    primary_sequence_index: 0,
    primary_track_count: 1,
    primary_note_count: 2,
    sequence_count: 1,
    format_2_multi_sequence: false,
  };
}

function fileDetails(meta) {
  const base = libraryItem(meta);
  return {
    file: {
      ...base,
      classifier_method: 'rules',
      label_source: 'auto',
      conflicts_json: [],
      uncertainty_json: [],
      warnings_json: [],
      embedded_text_json: [],
    },
    tracks: meta.kind === 'no-sequence' ? [] : [trackRow(meta)],
    cache: {
      parser_version: 1,
      classifier_version: 1,
      preview: {
        format: 1,
        duration_seconds: 0.9,
        duration_beats: 2,
        note_count: 2,
        timing_type: 'ppqn',
        warnings: [],
        sequences: meta.kind === 'no-sequence' ? [] : [previewSequence(meta.id)],
      },
      analysis: { file: analysisFile(meta), tracks: [], sequences: [] },
      classification: { file: classificationFile(), tracks: [], method: null },
    },
    tags: [],
    collections: [],
    corrections: { file: [], tracks: [] },
    predictions: [],
    duplicates: { exact_members: [], similar_members: [] },
  };
}

function facetsFixture() {
  return {
    totals: { total: FILES.length, favorites: 0, uncertain: 0, missing: 0, failed: 0, exact_duplicates: 0, similar_duplicates: 0 },
    instruments: [{ value: 'Piano/keys', count: FILES.length }],
    roles: [{ value: 'Lead/melody', count: FILES.length }],
    styles: [{ value: 'straight', count: FILES.length }],
    sources: [{ id: 1, label: 'Test Source', path: 'D:/Midi/Test', available: 1, kind: 'folder', enabled: 1, count: FILES.length }],
    collections: [],
    tags: [],
  };
}

function scanFixture() {
  return {
    active: false, state: 'idle', scan_id: null, mode: 'full', message: '', discovered: FILES.length,
    indexed: FILES.length, skipped: 0, failed: 0, issues: 0, directory_errors: 0, current_path: '',
    completion: 1, elapsed_seconds: 0, files_per_second: 0, started_at: null, ended_at: null,
    intensity: 'eco', workers: 1, queue_depth: 0, skipped_cloud: 0, skipped_links: 0,
    sources_completed: 1, total_sources: 1,
  };
}

function sourceFixture() {
  return {
    id: 1, path: 'D:/Midi/Test', label: 'Test Source', kind: 'folder', optional: false,
    enabled: true, available: true, counts: { files: FILES.length, indexed: FILES.length, failed: 0 },
  };
}

function bootstrapFixture(settings) {
  return {
    app: { name: 'SKEER MIDI VAULT', version: '0.0.0-harness', privacy: 'local' },
    versions: {
      parser: 1, classifier: 1, schema: 1, schema_supported: 1, fingerprint: 1,
      classifier_method: 'rules', ruleset: 'v1',
    },
    supported_extensions: ['.mid', '.midi'],
    sources: [sourceFixture()],
    drives: [{ ...sourceFixture(), drive_letter: 'D' }],
    facets: facetsFixture(),
    stats: { files: FILES.length, db_path: 'D:/tmp/harness.db', db_size_bytes: 1, fts_enabled: false },
    scan: scanFixture(),
    settings,
    excludes: [],
    collections: [],
    tags: [],
    db: { path: 'D:/tmp/harness.db', fts_enabled: false, size_bytes: 1, schema_version: 1, fingerprint_version: 1, last_migration: null },
    default_export_dir: 'D:/Midi/Export',
    home_dir: 'D:/tmp',
    desktop: { mode: false, can_quit: false },
  };
}

/**
 * Installs the whole fake service on a page. `options.autoplay` seeds the
 * persisted setting the deck reads; `options.apiDelay` lets a details call
 * settle so a harness cannot pass on a lucky race.
 */
export async function stubAppRoutes(page, options = {}) {
  const settings = { preview_autoplay: options.autoplay ? '1' : '0', ...(options.settings || {}) };
  const delay = options.apiDelay ?? 40;
  page.on('requestfailed', () => { /* assets we do not serve are not interesting */ });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/')) {
      const pathname = url.pathname.slice('/api'.length);
      if (pathname === '/bootstrap') return json(route, bootstrapFixture(settings));
      if (pathname === '/session') return json(route, { token: 'harness-token' });
      if (pathname === '/folders') {
        return json(route, { folders: [{ path: 'D:/Midi/Test', source_id: 1, count: FILES.length }], sources: [sourceFixture()], truncated: false });
      }
      if (pathname === '/facets') return json(route, facetsFixture());
      if (pathname === '/health') return json(route, { ok: true });
      if (pathname === '/scan/status') return json(route, scanFixture());
      if (pathname === '/scan/issues') return json(route, { issues: [] });
      if (pathname === '/settings') {
        const body = route.request().postDataJSON?.() || {};
        Object.assign(settings, body);
        return json(route, { settings });
      }
      if (pathname === '/library') {
        return json(route, {
          items: FILES.filter((meta) => (options.items || FILES).includes(meta)).map(libraryItem),
          total: FILES.length, page: 1, page_size: 60, pages: 1, fts: false,
        });
      }
      if (pathname.startsWith('/sources') || pathname.startsWith('/collections') || pathname.startsWith('/tags')) {
        return json(route, { sources: [sourceFixture()], collections: [], tags: [] });
      }
      const details = pathname.match(/^\/library\/(\d+)$/);
      if (details) {
        const meta = FILES.find((item) => item.id === Number(details[1]));
        if (!meta) return json(route, { error: 'unknown file' }, 404);
        if (options.failIds?.includes(meta.id)) return json(route, { error: 'could not read the file' }, 500);
        if (meta.kind === 'fetch-fails') return json(route, { error: 'could not read the file' }, 500);
        await sleep(delay);
        return json(route, fileDetails(meta));
      }
      const nested = pathname.match(/^\/library\/(\d+)\//);
      if (nested) return json(route, fileDetails(FILES.find((i) => i.id === Number(nested[1])) || FILES[0]));
      return json(route, { ok: true });
    }
    const rel = url.pathname === '/' ? 'index.html' : url.pathname.replace(/^\/+/, '');
    const target = path.join(distDir, ...rel.split('/'));
    if (!target.startsWith(distDir) || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
      if (url.pathname.endsWith('.html') || url.pathname === '/') {
        return route.fulfill({ status: 404, contentType: 'text/plain', body: 'not in dist' });
      }
      return route.fulfill({ status: 404, contentType: 'text/plain', body: 'missing' });
    }
    return route.fulfill({
      status: 200,
      headers: { 'content-type': CONTENT_TYPES[path.extname(target)] || 'application/octet-stream' },
      body: fs.readFileSync(target),
    });
  });
}

export const FIRST_ROW = 'Alpha Groove.mid';
export const BROKEN_ROW = 'Broken Take.mid';
export const EMPTY_ROW = 'Empty Sequences.mid';
export const THIRD_ROW = 'Gamma Take.mid';
