/**
 * Autoplay deck probe (next-steps step 10, plus the selection half of step 8).
 *
 * The claim under test is the one the product makes out loud: you can ear-scan
 * a pack without a click per file. So this drives the real interface in Chrome
 * and checks that a finished preview carries the transport to the next row on
 * its own, that it stops by itself at the end of the list, that a manual stop
 * or Autoplay off does not advance, and that a selection survives a filter
 * change — which is what lets a crate play as a deck.
 *
 * Every write here — adding the source, starting the scan, flipping Autoplay —
 * goes through the session-token client, so this is also the live proof that
 * the sealed loopback boundary (step 1) does not lock out the app's own writes.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import { findBrowser } from './browser-path.mjs';
import { createApiClient } from './api-client.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'skeer-deck-'));
const dataDir = path.join(tempRoot, 'data');
const port = 9200 + Math.floor(Math.random() * 400);
const base = `http://127.0.0.1:${port}`;
const demoLibrary = path.join(root, 'fixtures', 'demo_library');
fs.mkdirSync(dataDir, { recursive: true });

const logFd = fs.openSync(path.join(tempRoot, 'server.log'), 'a');
const errFd = fs.openSync(path.join(tempRoot, 'server.err.log'), 'a');
const server = spawn('python', ['-m', 'midivault.server', '--port', String(port)], {
  cwd: root,
  env: { ...process.env, SKEER_MIDIVAULT_DATA: dataDir, SKEER_SCAN_EXECUTOR: 'threads' },
  stdio: ['ignore', logFd, errFd],
  windowsHide: true,
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const api = createApiClient(base);
const results = [];
let browser;

async function waitForHealth() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      if ((await fetch(`${base}/api/health`)).ok) return;
    } catch {
      // Starting up.
    }
    await sleep(150);
  }
  throw new Error('The test service did not become healthy.');
}

async function waitForScanIdle(timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await api('/scan/status');
    if (!status.active) return status;
    await sleep(200);
  }
  throw new Error('The demo scan did not complete.');
}

async function checkpoint(name, action) {
  try {
    await action();
    results.push({ name, status: 'PASS' });
    console.log(`PASS ${name}`);
  } catch (error) {
    results.push({ name, status: 'FAIL', error: error instanceof Error ? error.message : String(error) });
    console.error(`FAIL ${name}:`, error);
    throw error;
  }
}

// Only rows the indexer is happy with: a fixture that failed to parse has
// nothing to hear, and stepping into it tests a different branch.
const rowNames = (page) => page.$$eval(
  '.file-row:not(.is-issue) .file-name',
  (nodes) => nodes.map((node) => node.textContent.trim()),
);
const openTitle = (page) => page.locator('.detail-title-row h2').first().innerText();
const deckReadout = async (page) => (await page.locator('.transport-deck').innerText()).trim();
const transportState = (page) => page.evaluate(() => {
  const snapshot = window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot();
  return { playing: snapshot.playing, duration: snapshot.duration };
});

const waitForPlaying = (page, timeout = 15000) => page.waitForFunction(
  () => window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot().playing, null, { timeout },
);
const waitForStopped = (page, timeout = 30000) => page.waitForFunction(
  () => !window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot().playing, null, { timeout },
);
const waitForTitle = (page, expected, timeout = 15000) => page.waitForFunction(
  (name) => (document.querySelector('.detail-title-row h2')?.innerText || '').includes(name),
  expected,
  { timeout },
);

/** Click a row by filename and wait until that file is the open one. */
async function openRow(page, name) {
  await page.locator('.file-row', { hasText: name }).first().click();
  await waitForTitle(page, name);
}

/**
 * Type into the library search and wait for the list to actually change.
 * `fill()` alone is not enough: the query is debounced, and reading the rows
 * before the filter lands silently tests the wrong list.
 */
async function searchFor(page, query) {
  const previous = await page.locator('.file-row').count();
  await page.locator('#library-search').fill(query);
  await page.waitForFunction(
    (count) => document.querySelectorAll('.file-row').length !== count,
    previous,
    { timeout: 15000 },
  );
  await page.waitForTimeout(150);
}

async function setAutoplay(page, on) {
  const button = page.getByRole('button', { name: /Autoplay/ });
  if ((await button.getAttribute('aria-pressed')) === String(on)) return;
  await button.click();
  await page.waitForTimeout(350);
  assert.equal((await api('/bootstrap')).settings.preview_autoplay, on ? '1' : '0');
}

try {
  await waitForHealth();

  const demoSource = await api('/sources', {
    method: 'POST',
    body: JSON.stringify({ path: demoLibrary, label: 'Deck Library', optional: false, enabled: true }),
  });
  const sources = await api('/sources');
  for (const source of sources.sources) {
    if (source.id !== demoSource.source.id && source.enabled) {
      await api(`/sources/${source.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: false }) });
    }
  }
  await api('/scan/start', {
    method: 'POST',
    body: JSON.stringify({ source_ids: [demoSource.source.id], mode: 'incremental', intensity: 'balanced' }),
  });
  const scanned = await waitForScanIdle();
  console.log(`indexed ${scanned.indexed} demo file(s), ${scanned.failed} issue(s)`);

  browser = await chromium.launch({
    executablePath: findBrowser(),
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--disable-gpu', '--mute-audio'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const consoleIssues = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleIssues.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => consoleIssues.push(`pageerror: ${error.message}`));
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);

  await checkpoint('the transport reports its position in the list on screen', async () => {
    const deck = await deckReadout(page);
    const [position, total] = deck.split('/').map((part) => Number(part.trim()));
    assert.ok(Number.isFinite(position) && Number.isFinite(total), `unreadable deck readout "${deck}"`);
    assert.equal(total, await page.locator('.file-row').count(), 'the deck must be the list on screen');
    assert.ok(total > 1, 'a one-row deck proves nothing');
  });

  await checkpoint('autoplay walks to the next file when a preview ends', async () => {
    await setAutoplay(page, true);
    // Two short loops, so the end arrives on its own and quickly.
    await searchFor(page, 'Fill');
    assert.equal(await page.locator('.file-row').count(), 2, 'the fixture needs exactly two short fills');
    const names = await rowNames(page);
    await openRow(page, names[0]);
    await waitForPlaying(page);
    const { duration } = await transportState(page);
    assert.ok(duration > 0 && duration < 25, `the first clip needs to be short, got ${duration}s`);
    await waitForTitle(page, names[1], duration * 1000 + 15000);
    assert.equal(await deckReadout(page), `2 / ${(await rowNames(page)).length}`);
  });

  await checkpoint('the deck is bounded and says so at the end of the list', async () => {
    await waitForPlaying(page);
    const { duration } = await transportState(page);
    await waitForStopped(page, duration * 1000 + 20000);
    await page.waitForFunction(
      () => Array.from(document.querySelectorAll('.toast-message'))
        .some((node) => /end of the list/i.test(node.textContent || '')),
      null,
      { timeout: 4000 },
    );
    const settled = await openTitle(page);
    await sleep(2500);
    assert.equal(await openTitle(page), settled, 'nothing may play past the last row of the list');
    assert.equal((await transportState(page)).playing, false);
  });

  await checkpoint('next and previous move the deck without waiting for an end', async () => {
    await searchFor(page, '');
    const total = await page.locator('.file-row').count();
    const names = await rowNames(page);
    await openRow(page, names[2]);
    await page.locator('.icon-btn[aria-label="Next file in the list"]').click();
    await waitForTitle(page, names[3]);
    assert.equal(await deckReadout(page), `4 / ${total}`);
    assert.equal((await transportState(page)).playing, true, 'stepping while playing must keep playing');
    await page.locator('.icon-btn[aria-label="Previous file in the list"]').click();
    await waitForTitle(page, names[2]);
    assert.equal(await deckReadout(page), `3 / ${total}`);
  });

  await checkpoint('a manual stop ends the deck instead of handing off', async () => {
    const names = await rowNames(page);
    const long = names.find((name) => /String Quartet|Warm Piano|Tempo Map/.test(name)) || names[0];
    await openRow(page, long);
    await waitForPlaying(page);
    const { duration } = await transportState(page);
    assert.ok(duration > 6, `this checkpoint needs a clip long enough to interrupt, got ${duration}s`);
    await page.locator('.icon-btn[aria-label="Stop"]').click();
    const stopped = await openTitle(page);
    await sleep(3000);
    assert.equal(await openTitle(page), stopped, 'Stop must end the deck, not start the next file');
    assert.equal((await transportState(page)).playing, false);
  });

  await checkpoint('autoplay off leaves a finished preview where it is', async () => {
    await setAutoplay(page, false);
    await searchFor(page, 'Fill');
    assert.equal(await page.locator('.file-row').count(), 2, 'the fixture needs exactly two short fills');
    const names = await rowNames(page);
    await openRow(page, names[0]);
    await page.locator('.transport-play').click();
    await waitForPlaying(page);
    const { duration } = await transportState(page);
    await waitForStopped(page, duration * 1000 + 20000);
    const settled = await openTitle(page);
    await sleep(2000);
    assert.equal(await openTitle(page), settled, 'with Autoplay off a preview must not start the next one');
  });

  await checkpoint('a selection survives a filter change', async () => {
    await searchFor(page, '');
    const names = await rowNames(page);
    await page.locator(`input[aria-label="Select ${names[0]}"]`).check();
    await page.locator(`input[aria-label="Select ${names[1]}"]`).check();
    await page.locator('.bulk-count').waitFor({ timeout: 5000 });
    assert.equal((await page.locator('.bulk-count').innerText()).trim(), '2');
    await page.locator('.category-row').filter({ hasText: 'Synth' }).first().click();
    await page.waitForTimeout(900);
    assert.equal(
      (await page.locator('.bulk-count').innerText()).trim(),
      '2',
      'filtering must not throw away the files the user selected',
    );
    await page.locator('.icon-btn[aria-label="Clear selection"]').click();
    await page.waitForFunction(() => !document.querySelector('.bulk-bar'), null, { timeout: 5000 });
  });

  await checkpoint('no browser console or page errors', async () => {
    assert.deepEqual(consoleIssues, []);
  });
} finally {
  if (browser) await browser.close().catch(() => {});
  server.kill();
  await sleep(400);
  try {
    fs.closeSync(logFd);
    fs.closeSync(errFd);
  } catch {
    // ignore
  }
  try {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  } catch {
    // A transient Windows handle on the temp index must not fail a passing run.
  }
}

const failed = results.filter((result) => result.status === 'FAIL');
console.log(JSON.stringify({ checks: results, failed: failed.length }, null, 2));
if (failed.length) {
  console.error(`${failed.length} autoplay-deck checkpoint(s) failed`);
  process.exitCode = 1;
} else {
  console.log(`autoplay-deck: ${results.length} checkpoints passed`);
}
