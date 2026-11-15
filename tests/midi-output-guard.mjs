/**
 * Web MIDI output harness — a dead port must be visible to the transport.
 *
 * engine.ts scheduled `output.send()` bare inside setTimeout callbacks while the
 * only guarded call site was sendMidiNoteOff. Unplug a MIDI port mid preview
 * and every pending note-on/note-off throws InvalidStateError: the console fills
 * with unhandled errors, `playing` stays true, and `midiActive` keeps entries
 * whose note-off never landed — a note held on the hardware synth until it is
 * power-cycled. Nothing assigned `onstatechange` on the output, so the engine
 * never learned the port was gone, and no unload handler released notes when the
 * page reloaded.
 *
 * The engine is bundled from web/src with esbuild and run in headless Chrome
 * against a fake `navigator.requestMIDIAccess` whose single output starts
 * throwing partway through playback. The fake records every byte it accepted in
 * localStorage, so a REAL navigation can be inspected afterwards.
 *
 * No service, no audio hardware, nothing written outside tests/e2e-tmp.
 */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import esbuild from '../web/node_modules/esbuild/lib/main.js';
import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import { findBrowser } from './browser-path.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..');
const outdir = path.join(here, 'e2e-tmp', 'midi-dist');
// SKEER_ENGINE_TS lets a run bundle a pre-fix engine to prove these checks fail
// on the old code; the default is the engine the app actually ships.
const engineEntry = process.env.SKEER_ENGINE_TS
  ? path.resolve(process.env.SKEER_ENGINE_TS)
  : path.join(repoRoot, 'web', 'src', 'audio', 'engine.ts');
const ORIGIN = 'http://midi-fake.test';
const results = [];
let browser;

async function checkpoint(name, fn) {
  try {
    await fn();
    results.push(`PASS ${name}`);
    console.log(`PASS ${name}`);
  } catch (error) {
    const message = error instanceof Error ? error.message.split('\n').slice(0, 8).join('\n    ') : String(error);
    results.push(`FAIL ${name}: ${message}`);
    console.error(`FAIL ${name}: ${message}`);
  }
}

// ---------------------------------------------------------------- the fake port
const FAKE_MIDI = `
(() => {
  const LOG_KEY = 'fake-midi-sends-v1';
  const read = () => { try { return JSON.parse(localStorage.getItem(LOG_KEY) || '[]'); } catch { return []; } };
  const write = (rows) => { try { localStorage.setItem(LOG_KEY, JSON.stringify(rows)); } catch {} };
  const control = {
    throws: false,
    failAfter: null,
    port: null,
    access: null,
    stateChanges: 0,
    sends(rows) {
      const all = read();
      for (const bytes of rows) all.push(bytes);
      write(all);
    },
    log() { return read(); },
    reset() { write([]); this.throws = false; this.failAfter = null; this.stateChanges = 0; },
    unplug() {
      // A pulled device reports itself and stops taking writes; the engine has
      // to act on the report. Note-offs attempted after this point are logged
      // as refusals, so the release path is still measurable.
      this.port.connection = 'disconnected';
      this.stateChanges += 1;
      const event = { type: 'statechange', port: this.port };
      if (typeof this.port.onstatechange === 'function') this.port.onstatechange(event);
      if (typeof this.access.onstatechange === 'function') this.access.onstatechange(event);
    },
  };
  class FakeOutput {
    constructor() {
      this.id = 'out-1';
      this.name = 'Fake Hardware Synth';
      this.manufacturer = 'Harness';
      this.connection = 'open';
      this.onstatechange = null;
    }
    send(data) {
      const bytes = Array.from(data);
      const accepted = control.log().filter((row) => !row.error);
      const doomed = control.throws || (control.failAfter !== null && accepted.length >= control.failAfter);
      if (doomed) {
        control.sends([{ error: 'InvalidStateError', bytes }]);
        throw new DOMException('The port is disconnected.', 'InvalidStateError');
      }
      control.sends([bytes]);
    }
  }
  const port = new FakeOutput();
  control.port = port;
  const outputs = new Map([[port.id, port]]);
  const access = { outputs, inputs: new Map(), onstatechange: null, onerror: null, attributes: {} };
  control.access = access;
  window.__FAKE_MIDI__ = control;
  Object.defineProperty(Navigator.prototype, 'requestMIDIAccess', {
    configurable: true, writable: true,
    value: async () => access,
  });
})();
`;

// An exception thrown inside a bare setTimeout surfaces as an uncaught window
// error, which Playwright reports as an evaluate rejection rather than pageerror.
// This sink is the measurement, so it has to be installed before the module runs.
const ERROR_SINK = `
(() => {
  window.__PAGE_ERRORS__ = [];
  window.addEventListener('error', (event) => {
    window.__PAGE_ERRORS__.push(String(event.message || event.error || 'unknown'));
  });
  window.addEventListener('unhandledrejection', (event) => {
    window.__PAGE_ERRORS__.push('rejection: ' + String((event.reason && event.reason.message) || event.reason));
  });
})();
`;

const PROBE_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>engine midi probe</title></head>
<body>
<script type="module">
  import { PreviewEngine, sequenceFromPreview } from './engine.mjs';

  const sequenceData = (noteCount, noteLength, spacing) => ({
    index: 0,
    name: 'MIDI probe',
    duration_seconds: Math.max(0.2, noteCount * spacing + noteLength),
    duration_beats: 8,
    timing_type: 'ppqn',
    ticks_per_quarter: 480,
    bars: 4,
    tempos: [{ tick: 0, beat: 0, seconds: 0, bpm: 120, microseconds: 500000, embedded: true }],
    time_signatures: [],
    key_signatures: [],
    texts: [],
    warnings: [],
    tracks: [{
      sequence_index: 0, track_index: 0, chunk_index: 0, channel: 0,
      name: 'Probe', instrument_name: null, program: 0, programs: [0],
      bank_msb: null, bank_lsb: null, sustain_events: 0, assumed_durations: 0,
      sustained_notes: 0, controller_counts: {}, controller_values: {},
      notes: Array.from({ length: noteCount }, (_, i) => ({
        b: i * 48, d: Math.round(noteLength * 240), t: i * spacing, l: noteLength,
        p: 48 + (i % 24), v: 90 + (i % 30),
      })),
    }],
  });

  let engine = null;
  window.__PROBE__ = {
    async start(options) {
      engine = new PreviewEngine();
      window.__ENGINE__ = engine;
      const built = sequenceFromPreview(
        sequenceData(options.noteCount, options.noteLength, options.spacing),
        [{ sequence_index: 0, track_index: 0, instrument: 'Piano/keys', role: 'Lead/melody' }],
        {},
      );
      await engine.requestMidiAccess();
      await engine.setOutput('out-1');
      engine.setSequence(built);
      engine.subscribeEnd(() => { window.__ENDED__ = true; });
      await engine.play();
      return true;
    },
    state() {
      if (!engine) return null;
      const s = engine.getSnapshot();
      return {
        snapshot: {
          playing: s.playing, paused: s.paused, outputMode: s.outputMode,
          outputId: s.outputId, midiSupported: s.midiSupported, midiError: s.midiError,
          error: s.error, hasSequence: s.hasSequence,
        },
        midiOutputId: engine.midiOutputId,
        outputMode: engine.outputMode,
        midiActiveSize: engine.midiActive.size,
        midiActive: [...engine.midiActive.values()].map((row) => ({ channel: row.channel, pitch: row.pitch })),
        midiTimersSize: engine.midiTimers.size,
        portConnection: window.__FAKE_MIDI__.port.connection,
        portHandler: String(window.__FAKE_MIDI__.port.onstatechange),
        accessHandler: String(window.__FAKE_MIDI__.access.onstatechange),
        ended: window.__ENDED__ === true,
      };
    },
  };
  window.__READY__ = true;
</script>
</body></html>`;

const AFTER_HTML = '<!doctype html><html><head><meta charset="utf-8"><title>after</title></head><body>unloaded</body></html>';

async function bundleEngine() {
  fs.mkdirSync(outdir, { recursive: true });
  await esbuild.build({
    entryPoints: [engineEntry],
    bundle: true,
    format: 'esm',
    target: 'es2022',
    outfile: path.join(outdir, 'engine.mjs'),
    logLevel: 'silent',
  });
  return fs.readFileSync(path.join(outdir, 'engine.mjs'), 'utf8');
}

async function newProbePage(context, bundle, errors) {
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) {
      errors.push(`console: ${message.text()}`);
    }
  });
  await page.addInitScript(ERROR_SINK);
  await page.addInitScript(FAKE_MIDI);
  await page.route(`${ORIGIN}/**/*`, (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/engine.mjs') {
      return route.fulfill({ status: 200, contentType: 'text/javascript; charset=utf-8', body: bundle });
    }
    if (url.pathname === '/after.html') {
      return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: AFTER_HTML });
    }
    return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: PROBE_HTML });
  });
  await page.goto(`${ORIGIN}/probe.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__READY__ === true, null, { timeout: 15000 });
  assert.equal(
    await page.evaluate(() => typeof navigator.requestMIDIAccess === 'function'),
    true,
    'the fake MIDI was not installed — every check below would be vacuous',
  );
  return page;
}

const stateOf = (page) => page.evaluate(() => window.__PROBE__.state());

/** Both sinks: Playwright's pageerror/console plus the in-page event sink. */
async function allErrors(page, errors) {
  const rows = await page.evaluate(() => window.__PAGE_ERRORS__ || []).catch(() => []);
  return [...errors, ...rows];
}

async function waitFor(predicate, timeoutMs, describe) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await predicate();
    if (last.done) return last.value;
    await new Promise((resolve) => setTimeout(resolve, 60));
  }
  throw new Error(`timed out after ${timeoutMs}ms — ${describe(last.value)}`);
}

const acceptedSends = (rows) => rows.filter((row) => !row.error);
const pitchesOf = (rows, status) => acceptedSends(rows)
  .filter((row) => (row[0] & 0xf0) === status)
  .map((row) => row[1]);

try {
  const bundle = await bundleEngine();
  console.log(`   bundled web/src/audio/engine.ts -> ${bundle.length} bytes (rebuilt every run)`);
  browser = await chromium.launch({
    executablePath: findBrowser(),
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--disable-gpu', '--mute-audio'],
  });
  const context = await browser.newContext();

  // ---------------------------------------------------------------- sends throw
  const failErrors = [];
  const failPage = await newProbePage(context, bundle, failErrors);
  // Four sends land, so the hardware really has notes under it, then the very
  // next one throws the way an unplugged port throws.
  await failPage.evaluate(() => {
    window.__FAKE_MIDI__.reset();
    window.__FAKE_MIDI__.failAfter = 4;
  });
  await failPage.evaluate(() => window.__PROBE__.start({ noteCount: 14, noteLength: 0.25, spacing: 0.04 }));

  await checkpoint('the first refused send drops the output, stops the transport and empties midiActive', async () => {
    const seen = await waitFor(
      async () => {
        const rows = await failPage.evaluate(() => window.__FAKE_MIDI__.log());
        const state = await stateOf(failPage);
        return { done: rows.some((row) => row.error), value: { ...state, throws: rows.filter((row) => row.error).length } };
      },
      6000,
      (value) => `the fake port never refused a send, so nothing was exercised (${JSON.stringify(value)})`,
    );
    assert.equal(seen.midiActiveSize, 0, `${seen.midiActiveSize} note(s) stayed in midiActive with no note-off landing: ${JSON.stringify(seen.midiActive)}`);
    assert.equal(seen.midiOutputId, null, `the engine still holds the dead output ${seen.midiOutputId}`);
    assert.equal(seen.snapshot.playing, false, 'the transport still claimed it was playing after the port died');
    assert.equal(seen.midiTimersSize, 0, 'pending note-on/note-off timers were not cancelled');
  });

  await checkpoint('no send failure escapes as an unhandled error', async () => {
    await failPage.waitForTimeout(900);
    const settled = await stateOf(failPage);
    const uncaught = await allErrors(failPage, failErrors);
    assert.equal(uncaught.length, 0, `${uncaught.length} unhandled error(s): ${uncaught.slice(0, 4).join(' | ')}`);
    assert.equal(settled.snapshot.playing, false, 'the transport still claims it is playing');
    assert.notEqual(settled.snapshot.error, null, 'the snapshot carries no reason for the stop');
    assert.equal(settled.snapshot.outputMode, 'synth', 'the engine stayed in midi mode with no port');
    console.log(`   dropped after ${await failPage.evaluate(() => window.__FAKE_MIDI__.log().filter((r) => !r.error).length)} accepted sends — "${settled.snapshot.error}"`);
    await failPage.close();
  });

  // ------------------------------------------------------- onstatechange + release
  const plugErrors = [];
  const plugPage = await newProbePage(context, bundle, plugErrors);
  await plugPage.evaluate(() => window.__FAKE_MIDI__.reset());
  await plugPage.evaluate(() => window.__PROBE__.start({ noteCount: 3, noteLength: 4, spacing: 0.05 }));
  const held = await waitFor(
    async () => {
      const state = await stateOf(plugPage);
      return { done: state.midiActiveSize === 3, value: state };
    },
    6000,
    (value) => `midiActive=${value?.midiActiveSize}, the three long notes were never all held`,
  );

  await checkpoint('the engine listens for a port state change', async () => {
    const handlers = await plugPage.evaluate(() => ({
      isFunction: typeof window.__FAKE_MIDI__.port.onstatechange === 'function'
        || typeof window.__FAKE_MIDI__.access.onstatechange === 'function',
      port: String(window.__FAKE_MIDI__.port.onstatechange).slice(0, 20),
      access: String(window.__FAKE_MIDI__.access.onstatechange).slice(0, 20),
    }));
    assert.ok(
      handlers.isFunction,
      `nothing is assigned to onstatechange (port=${handlers.port}, access=${handlers.access})`,
    );
    console.log(`   handlers: port=${handlers.port === 'null' ? 'null' : 'assigned'}, access=${handlers.access === 'null' ? 'null' : 'assigned'}`);
  });

  await checkpoint('a reported disconnect drops the output and releases the held notes', async () => {
    const pitchesHeld = held.midiActive.map((row) => row.pitch);
    // The fake still accepts sends here, so the note-offs are provably delivered.
    await plugPage.evaluate(() => {
      window.__FAKE_MIDI__.throws = false;
      window.__FAKE_MIDI__.unplug();
    });
    const dropped = await waitFor(
      async () => {
        const state = await stateOf(plugPage);
        return { done: state.midiOutputId === null && state.midiActiveSize === 0, value: state };
      },
      6000,
      (value) => `outputId=${value?.midiOutputId} midiActive=${value?.midiActiveSize} playing=${value?.snapshot.playing}`,
    );
    const offs = pitchesOf(await plugPage.evaluate(() => window.__FAKE_MIDI__.log()), 0x80);
    assert.deepEqual(
      offs.slice().sort((a, b) => a - b),
      pitchesHeld.slice().sort((a, b) => a - b),
      `note-offs delivered ${JSON.stringify(offs)} but ${JSON.stringify(pitchesHeld)} were held`,
    );
    assert.equal(dropped.snapshot.playing, false, 'the transport kept running through a dead port');
    const uncaught = await allErrors(plugPage, plugErrors);
    assert.equal(uncaught.length, 0, `unhandled errors during the disconnect: ${uncaught.slice(0, 3).join(' | ')}`);
    console.log(`   released ${offs.length} held note(s) on disconnect`);
  });

  // ------------------------------------------------- pulled device: no writes land
  await checkpoint('a disconnect that also refuses writes still clears the bookkeeping', async () => {
    const hardErrors = [];
    const hardPage = await newProbePage(context, bundle, hardErrors);
    await hardPage.evaluate(() => {
      window.__FAKE_MIDI__.reset();
      window.__FAKE_MIDI__.throws = true;
    });
    await hardPage.evaluate(() => window.__PROBE__.start({ noteCount: 2, noteLength: 6, spacing: 0.05 }));
    // The port throws from the first note-on, so nothing is ever held; the
    // engine must still end up out of midi mode with an empty active map.
    const settled = await waitFor(
      async () => {
        const state = await stateOf(hardPage);
        return { done: state.midiOutputId === null && state.snapshot.playing === false, value: state };
      },
      6000,
      (value) => `outputId=${value?.midiOutputId} playing=${value?.snapshot?.playing} midiActive=${value?.midiActiveSize}`,
    );
    assert.equal(settled.midiActiveSize, 0, `${settled.midiActiveSize} note(s) were left tracked against a dead port`);
    assert.equal(settled.snapshot.outputMode, 'synth', 'a port that never took a write stayed selected');
    const uncaught = await allErrors(hardPage, hardErrors);
    assert.equal(uncaught.length, 0, `unhandled errors from a port that throws on everything: ${uncaught.slice(0, 3).join(' | ')}`);
    await hardPage.close();
  });

  // ------------------------------------------------------------------- real unload
  await checkpoint('a real page unload releases the notes held on the hardware', async () => {
    const unloadErrors = [];
    const page = await newProbePage(context, bundle, unloadErrors);
    await page.evaluate(() => window.__FAKE_MIDI__.reset());
    await page.evaluate(() => window.__PROBE__.start({ noteCount: 2, noteLength: 8, spacing: 0.05 }));
    const before = await waitFor(
      async () => {
        const state = await stateOf(page);
        return { done: state.midiActiveSize === 2, value: state };
      },
      6000,
      (value) => `midiActive=${value?.midiActiveSize}, no long note was held on the hardware`,
    );
    const pitchesHeld = before.midiActive.map((row) => row.pitch);
    const onsBefore = pitchesOf(await page.evaluate(() => window.__FAKE_MIDI__.log()), 0x90);
    assert.deepEqual(onsBefore, pitchesHeld, `the setup did not put those notes on the wire: ${JSON.stringify(onsBefore)}`);
    // Navigating away is the only honest way to exercise the unload path.
    await page.goto(`${ORIGIN}/after.html`, { waitUntil: 'domcontentloaded' });
    const rows = await page.evaluate(() => JSON.parse(localStorage.getItem('fake-midi-sends-v1') || '[]'));
    const offs = pitchesOf(rows, 0x80);
    assert.equal(
      offs.length,
      pitchesHeld.length,
      `${pitchesHeld.length} note(s) were still held when the page went away; log had ${rows.length} accepted sends, offs ${JSON.stringify(offs)}`,
    );
    await page.close();
  });

  // ----------------------------------------------------------------- happy path
  await checkpoint('guard: a healthy MIDI output still gets every note-on and note-off', async () => {
    const errors = [];
    const page = await newProbePage(context, bundle, errors);
    await page.evaluate(() => window.__FAKE_MIDI__.reset());
    await page.evaluate(() => window.__PROBE__.start({ noteCount: 6, noteLength: 0.2, spacing: 0.05 }));
    const finished = await waitFor(
      async () => {
        const state = await stateOf(page);
        return { done: state.ended === true && state.midiActiveSize === 0, value: state };
      },
      12000,
      (value) => `ended=${value?.ended} playing=${value?.snapshot.playing} midiActive=${value?.midiActiveSize}`,
    );
    const rows = await page.evaluate(() => window.__FAKE_MIDI__.log());
    const ons = pitchesOf(rows, 0x90);
    const offs = pitchesOf(rows, 0x80);
    assert.equal(ons.length, 6, `only ${ons.length} of 6 note-ons reached the port`);
    assert.ok(offs.length >= 6, `only ${offs.length} note-offs reached the port`);
    assert.equal(finished.midiOutputId, 'out-1', 'a working port must not be dropped');
    assert.equal(finished.snapshot.outputMode, 'midi', 'midi mode must survive a clean run');
    assert.equal(finished.snapshot.error, null, `a clean run reported an error: ${finished.snapshot.error}`);
    const uncaught = await allErrors(page, errors);
    assert.equal(uncaught.length, 0, `console errors on the happy path: ${uncaught.slice(0, 3).join(' | ')}`);
    console.log(`   ${ons.length} ons / ${offs.length} offs through a healthy port`);
    await page.close();
  });
} catch (error) {
  results.push(`FAIL harness: ${error instanceof Error ? error.message : error}`);
  console.error(`FAIL harness: ${error instanceof Error ? error.message : error}`);
} finally {
  if (browser) await browser.close();
}

const failed = results.filter((line) => line.startsWith('FAIL'));
console.log(failed.length === 0
  ? `\nALL ${results.length} CHECKS PASS`
  : `\n${failed.length} of ${results.length} CHECKS FAILED`);
process.exitCode = failed.length === 0 ? 0 : 1;
