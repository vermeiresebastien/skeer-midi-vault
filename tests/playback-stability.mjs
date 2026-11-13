/**
 * Playback stability probe: play a real file while the indexer is scanning a
 * large duplicate corpus and the user is searching/filtering.
 *
 * Measures web-audio transport drift against wall time and inspects scheduler
 * telemetry (late/skipped notes) exposed for diagnostics.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import { findBrowser } from './browser-path.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'skeer-playback-'));
const dataDir = path.join(tempRoot, 'data');
const copiesDir = path.join(tempRoot, 'large-library');
const port = 9000 + Math.floor(Math.random() * 500);
const base = `http://127.0.0.1:${port}`;
fs.mkdirSync(dataDir, { recursive: true });
fs.mkdirSync(copiesDir, { recursive: true });

// Make the scan long enough to overlap a meaningful playback window.
const demoFiles = [
  'Synths/Analog Lead 118.mid',
  'Bass/Funk Bassline F.mid',
  'Keys/Rhodes Chords Cmaj7.mid',
  'Drums/Deep House Groove 124.mid',
];
for (let index = 0; index < 1500; index += 1) {
  const folder = path.join(copiesDir, `batch-${Math.floor(index / 50).toString().padStart(2, '0')}`);
  fs.mkdirSync(folder, { recursive: true });
  const source = path.join(root, 'fixtures', 'demo_library', demoFiles[index % demoFiles.length]);
  fs.copyFileSync(source, path.join(folder, `copy-${String(index).padStart(4, '0')}.mid`));
}

const logFd = fs.openSync(path.join(tempRoot, 'server.log'), 'a');
const errFd = fs.openSync(path.join(tempRoot, 'server.err.log'), 'a');
const server = spawn('python', ['-m', 'midivault.server', '--port', String(port)], {
  cwd: root,
  env: { ...process.env, SKEER_MIDIVAULT_DATA: dataDir, SKEER_SCAN_EXECUTOR: 'process' },
  stdio: ['ignore', logFd, errFd],
  windowsHide: true,
});
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function api(pathname, init = {}) {
  const response = await fetch(`${base}/api${pathname}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
  });
  if (!response.ok) throw new Error(`API ${pathname}: ${response.status} ${await response.text()}`);
  return response.json();
}

async function waitForHealth() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      const response = await fetch(`${base}/api/health`);
      if (response.ok) return;
    } catch {
      // waiting
    }
    await sleep(150);
  }
  throw new Error('Service did not become healthy');
}

async function waitForScanIdle(timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await api('/scan/status');
    if (!status.active) return status;
    await sleep(250);
  }
  throw new Error('Scan remained active');
}

let browser;
let page;
try {
  await waitForHealth();
  await api('/bootstrap');
  const demoSource = await api('/sources', {
    method: 'POST',
    body: JSON.stringify({ path: path.join(root, 'fixtures', 'demo_library'), label: 'Playback demo', enabled: true }),
  });
  const largeSource = await api('/sources', {
    method: 'POST',
    body: JSON.stringify({ path: copiesDir, label: 'Playback scan corpus', enabled: true }),
  });
  // Initial scan of the demo library only.
  await api('/scan/start', {
    method: 'POST',
    body: JSON.stringify({ source_ids: [demoSource.source.id], mode: 'incremental', intensity: 'balanced' }),
  });
  await waitForScanIdle();

  browser = await chromium.launch({
    executablePath: findBrowser(),
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--disable-gpu', '--mute-audio'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  page = await context.newPage();
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await page.locator('#library-search').fill('Analog Lead');
  await page.waitForTimeout(400);
  await page.locator('.file-row').first().click();
  await page.waitForTimeout(700);
  await page.locator('#library-search').fill('');
  await page.waitForTimeout(300);

  // Start a large background scan, then audition while it runs.
  await api('/scan/start', {
    method: 'POST',
    body: JSON.stringify({
      source_ids: [demoSource.source.id, largeSource.source.id],
      mode: 'incremental',
      intensity: 'balanced',
    }),
  });
  await page.waitForTimeout(600);
  await page.locator('.transport-play').click();
  const before = await page.evaluate(() => {
    const engine = window.__SKEER_MIDIVAULT_DEBUG__.engine;
    return { snapshot: engine.getSnapshot(), stats: engine.getDebugStats(), wall: performance.now() };
  });

  // Interact with the queue while playback continues.
  const searchStart = Date.now();
  await page.locator('#library-search').fill('bass');
  await page.waitForFunction(() => document.querySelectorAll('.file-row').length > 3, { timeout: 8000 });
  const searchResponseMs = Date.now() - searchStart;
  await page.locator('.category-row').filter({ hasText: 'Synth' }).first().click();
  await page.waitForTimeout(700);
  await page.getByRole('button', { name: 'Clear all' }).click();
  await page.waitForTimeout(250);
  await page.locator('#library-search').fill('');
  await page.waitForTimeout(6500);

  const after = await page.evaluate(() => {
    const engine = window.__SKEER_MIDIVAULT_DEBUG__.engine;
    return { snapshot: engine.getSnapshot(), stats: engine.getDebugStats(), wall: performance.now() };
  });
  const scanDuringPlayback = await api('/scan/status');
  const wallSeconds = (after.wall - before.wall) / 1000;
  const sourceAdvance = after.snapshot.sourceTime - before.snapshot.sourceTime;

  // Loop and seek sanity while the scan is still active.
  await page.evaluate(() => {
    const engine = window.__SKEER_MIDIVAULT_DEBUG__.engine;
    engine.setLoop(true);
    engine.seek(Math.max(0, engine.getSnapshot().duration - 0.9));
  });
  await page.waitForTimeout(1700);
  const loopSnapshot = await page.evaluate(() => window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot());
  await page.evaluate(() => window.__SKEER_MIDIVAULT_DEBUG__.engine.stop());
  await page.waitForTimeout(300);
  const stopped = await page.evaluate(() => window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot());

  const stillScanning = (await api('/scan/status')).active;
  if (stillScanning) await api('/scan/cancel', { method: 'POST' });
  await waitForScanIdle();

  const report = {
    timestamp: new Date().toISOString(),
    host: {
      platform: os.platform(),
      release: os.release(),
      cpu: os.cpus()[0]?.model,
      logical_cores: os.cpus().length,
      memory_gb: Math.round(os.totalmem() / (1024 ** 3) * 10) / 10,
      node: process.version,
    },
    test: {
      file: 'Analog Lead 118.mid',
      file_duration_seconds: before.snapshot.duration,
      wall_seconds: Number(wallSeconds.toFixed(3)),
      source_advance_seconds: Number(sourceAdvance.toFixed(3)),
      drift_ratio: Number((sourceAdvance / wallSeconds).toFixed(4)),
      scan_was_active_during_playback: Boolean(scanDuringPlayback.active),
      scan_indexed_at_sample: scanDuringPlayback.indexed,
      search_response_ms: searchResponseMs,
      scheduled_notes: after.stats.scheduledNotes - before.stats.scheduledNotes,
      late_notes: after.stats.lateNotes,
      skipped_notes: after.stats.skippedNotes,
      was_playing_after_interactions: after.snapshot.playing,
      loop_after_wrap_seconds: Number(loopSnapshot.sourceTime.toFixed(3)),
      loop_still_playing: loopSnapshot.playing,
      stopped_time_seconds: Number(stopped.sourceTime.toFixed(3)),
      stopped_playing: stopped.playing,
      active_voices_after_stop: stopped.activeVoices,
    },
    notes: [
      'The headless browser is muted; scheduling and transport telemetry are still exercised.',
      'Search/filter interactions ran while the scan and playback were active.',
      'Source-time drift is measured against wall time at the browser AudioContext tempo.',
    ],
  };
  const output = path.join(root, 'docs', 'playback-stability.json');
  fs.writeFileSync(output, JSON.stringify(report, null, 2), 'utf8');
  console.log(JSON.stringify(report, null, 2));
  console.log(`wrote ${path.relative(root, output)}`);
} finally {
  if (browser) await browser.close().catch(() => {});
  server.kill();
  await sleep(300);
  try {
    fs.closeSync(logFd);
    fs.closeSync(errFd);
  } catch {
    // ignore
  }
  try {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  } catch {
    // A transient Windows file handle should not fail the benchmark.
  }
}
