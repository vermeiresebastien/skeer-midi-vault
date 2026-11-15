/**
 * End-to-end browser test for SKEER MIDI VAULT.
 *
 * Launches an isolated local service, scans only the generated demo folder,
 * then drives the real interface in Chrome. It also writes the documentation
 * screenshots for both skins.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import { findBrowser } from './browser-path.mjs';
import { createApiClient } from './api-client.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runId = new Date().toISOString().replace(/[:.]/g, '-');
const tempRoot = path.join(root, 'tests', 'e2e-tmp', `run-${runId}`);
const dataDir = path.join(tempRoot, 'data');
const exportDir = path.join(tempRoot, 'exports');
const shotsDir = path.join(root, 'docs', 'screenshots');
const port = 8755 + Math.floor(Math.random() * 200);
const base = `http://127.0.0.1:${port}`;
const demoLibrary = path.join(root, 'fixtures', 'demo_library');
fs.mkdirSync(dataDir, { recursive: true });
fs.mkdirSync(exportDir, { recursive: true });
fs.mkdirSync(shotsDir, { recursive: true });

const logFd = fs.openSync(path.join(tempRoot, 'server.log'), 'a');
const errFd = fs.openSync(path.join(tempRoot, 'server.err.log'), 'a');
const server = spawn('python', ['-m', 'midivault.server', '--port', String(port)], {
  cwd: root,
  env: {
    ...process.env,
    SKEER_MIDIVAULT_DATA: dataDir,
    SKEER_SCAN_EXECUTOR: 'process',
  },
  stdio: ['ignore', logFd, errFd],
  windowsHide: true,
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const results = [];
let browser;
let context;

const api = createApiClient(base);

async function waitForHealth() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(`${base}/api/health`);
      if (response.ok) return;
    } catch {
      // Starting up.
    }
    await sleep(150);
  }
  throw new Error('The test service did not become healthy.');
}

async function waitForScan() {
  for (let attempt = 0; attempt < 300; attempt += 1) {
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

async function chooseMidnight(page) {
  const search = page.locator('#library-search');
  await search.fill('Midnight Drive');
  await page.waitForTimeout(500);
  const row = page.locator('.file-row', { hasText: 'Midnight Drive 118.mid' }).first();
  await row.waitFor({ state: 'visible', timeout: 10000 });
  await row.click();
  await page.locator('.detail-title-row h2', { hasText: 'Midnight Drive 118.mid' }).waitFor({ timeout: 10000 });
  await page.waitForTimeout(500);
  await search.fill('');
  await page.waitForTimeout(500);
  await page.locator('.library-kicker').click();
  await page.waitForTimeout(250);
}

try {
  await waitForHealth();
  console.log(`Test service ${base} (data: ${path.relative(root, dataDir)})`);

  await api('/bootstrap');
  const demoSource = await api('/sources', {
    method: 'POST',
    body: JSON.stringify({ path: demoLibrary, label: 'Demo Library', optional: false, enabled: true }),
  });
  const demoSourceId = demoSource.source.id;
  const sources = await api('/sources');
  for (const source of sources.sources) {
    if (source.id !== demoSourceId && source.enabled) {
      await api(`/sources/${source.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: false }) });
    }
  }

  browser = await chromium.launch({
    executablePath: findBrowser(),
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--disable-gpu', '--mute-audio'],
  });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const consoleIssues = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleIssues.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => consoleIssues.push(`pageerror: ${error.message}`));
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);

  await checkpoint('initial empty state is usable', async () => {
    assert.equal(await page.locator('.empty-library').count(), 1);
    assert.equal(await page.locator('.transport-play').isDisabled(), true);
  });

  await checkpoint('scan dialog lists drives and starts an explicit scan', async () => {
    await page.locator('.scan-button').click();
    await page.locator('.scan-config').waitFor({ timeout: 15000 });
    await page.locator('.source-row').first().waitFor({ timeout: 15000 });
    assert.ok(await page.locator('.source-row').count() > 0);
    await page.getByRole('button', { name: 'Start scan' }).click();
    await page.locator('.scan-live').waitFor({ timeout: 15000 });
  });

  const finishedScan = await waitForScan();
  await checkpoint('scan completes and the demo library is indexed', async () => {
    assert.equal(finishedScan.state, 'completed');
    assert.equal(finishedScan.indexed, 36);
    assert.ok(finishedScan.failed >= 1);
  });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await checkpoint('library and details render after scanning', async () => {
    assert.equal(await page.locator('.file-row').count(), 36);
    assert.match(await page.locator('.topbar-stat').innerText(), /36 files indexed/);
    assert.equal(await page.locator('.detail-title-row h2').count(), 1);
  });

  await chooseMidnight(page);
  await page.screenshot({ path: path.join(shotsDir, 'studio-clean.png') });

  await checkpoint('appearance panel switches to Studio Tactile', async () => {
    await page.locator('.settings-button').click();
    await page.locator('.settings-tabs button', { hasText: 'Appearance' }).click();
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(shotsDir, 'appearance-panel.png') });
    await page.locator('.skin-card').nth(1).click();
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => document.documentElement.dataset.skin), 'tactile');
    await page.getByRole('button', { name: 'Done' }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: path.join(shotsDir, 'studio-tactile.png') });
    await page.locator('.settings-button').click();
    await page.locator('.settings-tabs button', { hasText: 'Appearance' }).click();
    await page.waitForTimeout(200);
    // Interface scale, finish and motion controls are real preferences.
    const scaleInput = page.locator('.range-field', { hasText: 'Interface scale' }).locator('input');
    await scaleInput.focus();
    await scaleInput.press('ArrowRight');
    await page.waitForTimeout(200);
    assert.equal(
      await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--ui-scale').trim()),
      '1.05',
    );
    await scaleInput.press('ArrowLeft');
    await page.locator('.settings-field .segmented button', { hasText: 'Plastic' }).click();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.tileFinish), 'plastic');
    await page.locator('.switch').click();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.reduceMotion), 'true');
    await page.getByRole('button', { name: 'Reset appearance' }).click();
    await page.waitForTimeout(250);
    assert.equal(await page.evaluate(() => document.documentElement.dataset.skin), 'clean');
    assert.equal(await page.evaluate(() => document.documentElement.dataset.reduceMotion), 'false');
    await page.getByRole('button', { name: 'Done' }).click();
    await page.waitForTimeout(250);
  });

  await checkpoint('classification can be corrected and reverted', async () => {
    const select = page.locator('.classification-row').first().locator('select');
    const original = await select.inputValue();
    await select.selectOption('Strings');
    await page.waitForFunction(
      () => document.querySelector('.classification-row select')?.value === 'Strings',
      null,
      { timeout: 8000 },
    );
    assert.equal(await page.locator('.classification-row').first().locator('select').inputValue(), 'Strings');
    assert.match(await page.locator('.classification-row').first().innerText(), /your label/i);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    await page.locator('#library-search').fill('Midnight Drive');
    await page.waitForTimeout(500);
    await page.locator('.file-row', { hasText: 'Midnight Drive' }).first().click();
    await page.waitForTimeout(500);
    assert.equal(await page.locator('.classification-row').first().locator('select').inputValue(), 'Strings');
    await page.getByRole('button', { name: 'revert to auto' }).first().click();
    await page.waitForFunction(
      (value) => document.querySelector('.classification-row select')?.value === value,
      original,
      { timeout: 8000 },
    );
    assert.equal(await page.locator('.classification-row').first().locator('select').inputValue(), original);
    await page.locator('#library-search').fill('');
    await page.waitForTimeout(500);
  });

  await checkpoint('text search covers names, paths and track names', async () => {
    await page.locator('#library-search').fill('bass');
    await page.waitForTimeout(500);
    assert.ok(await page.locator('.file-row').count() >= 5);
    await page.locator('#library-search').fill('Rhodes Chords');
    await page.waitForTimeout(500);
    assert.ok(await page.locator('.file-row').count() >= 1);
    await page.locator('#library-search').fill('');
    await page.waitForTimeout(500);
  });

  await checkpoint('advanced filters combine and clear', async () => {
    await page.locator('.library-heading-actions .btn').click();
    await page.locator('.filter-dialog').waitFor({ timeout: 5000 });
    await page.locator('.filter-dialog').locator('input[type=number]').nth(0).fill('100');
    await page.locator('.filter-dialog').locator('input[type=number]').nth(1).fill('130');
    await page.waitForTimeout(450);
    await page.locator('.filter-dialog').locator('h3').first().click();
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(shotsDir, 'filters.png') });
    await page.getByRole('button', { name: 'Apply filters' }).click();
    await page.waitForTimeout(600);
    assert.ok(await page.locator('.filter-chip', { hasText: 'BPM' }).count() >= 1);
    await page.getByRole('button', { name: 'Clear all' }).click();
    await page.waitForTimeout(500);
    assert.equal(await page.locator('.filter-chip').count(), 0);
  });

  await checkpoint('favorite, tag and note persist locally', async () => {
    await chooseMidnight(page);
    await page.locator('.detail-star').click();
    await page.locator('.detail-star.is-favorite').waitFor({ timeout: 5000 });
    const tagInput = page.locator('.tag-input');
    await tagInput.fill('e2e-tag');
    await tagInput.press('Enter');
    await page.locator('.user-tag', { hasText: 'e2e-tag' }).first().waitFor({ timeout: 8000 });
    const notes = page.locator('.notes-input');
    await notes.fill('Verified in the browser test.');
    await notes.blur();
    await page.waitForTimeout(700);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    await page.locator('#library-search').fill('Midnight Drive');
    await page.waitForTimeout(500);
    await page.locator('.file-row', { hasText: 'Midnight Drive' }).first().click();
    await page.waitForTimeout(700);
    assert.ok(await page.locator('.detail-star.is-favorite').count() === 1);
    await page.locator('.user-tag', { hasText: 'e2e-tag' }).first().waitFor({ timeout: 5000 });
    assert.equal(await page.locator('.notes-input').inputValue(), 'Verified in the browser test.');
    await page.locator('#library-search').fill('');
    await page.waitForTimeout(500);
  });

  await checkpoint('playback advances and stops on file switch', async () => {
    await chooseMidnight(page);
    const parseClock = (text) => {
      const match = text.match(/(\d+):(\d+(?:\.\d+)?)/);
      return match ? Number(match[1]) * 60 + Number(match[2]) : 0;
    };
    const initial = await page.locator('.transport-time').innerText();
    await page.locator('.transport-play').click();
    await page.waitForTimeout(1100);
    const playing = await page.locator('.transport-time').innerText();
    assert.ok(parseClock(playing) > 0.3);
    await page.locator('.file-row', { hasText: 'Analog Lead 118.mid' }).first().click();
    await page.waitForTimeout(600);
    const stopped = await page.locator('.transport-time').innerText();
    assert.ok(parseClock(stopped) < 0.2);
    await page.locator('.transport-play').click();
    await page.waitForTimeout(500);
    await page.locator('.transport-play').click();
    await page.waitForTimeout(250);
    assert.ok(parseClock(await page.locator('.transport-time').innerText()) > 0.1);
    await page.locator('.icon-btn[aria-label="Stop"]').click();
    await page.waitForTimeout(250);
  });

  await checkpoint('piano-roll drag and scrub stay stable', async () => {
    await chooseMidnight(page);
    const canvas = page.locator('.piano-roll-canvas');
    const box = await canvas.boundingBox();
    assert.ok(box, 'piano roll should be visible');
    // Paused drag across the map.
    await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.35);
    await page.mouse.down();
    for (let step = 1; step <= 24; step += 1) {
      await page.mouse.move(
        box.x + box.width * (0.2 + (0.6 * step) / 24),
        box.y + box.height * 0.35,
      );
      await page.waitForTimeout(8);
    }
    await page.mouse.up();
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => document.querySelector('#root')?.childElementCount), 1);

    // Dragging while auditioning must pause/resume cleanly, not restart the whole
    // audio graph on each pointermove.
    await page.locator('.transport-play').click();
    await page.waitForTimeout(350);
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.6);
    await page.mouse.down();
    for (let step = 1; step <= 20; step += 1) {
      await page.mouse.move(
        box.x + box.width * (0.7 - (0.45 * step) / 20),
        box.y + box.height * 0.6,
      );
      await page.waitForTimeout(8);
    }
    await page.mouse.up();
    await page.waitForTimeout(500);
    const afterDrag = await page.evaluate(() => window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot());
    assert.equal(afterDrag.playing, true);
    assert.ok(Number.isFinite(afterDrag.sourceTime));
    await page.locator('.transport-play').click();

    // Seek slider drag.
    const seek = page.locator('.transport-seek input');
    const seekBox = await seek.boundingBox();
    assert.ok(seekBox);
    await page.mouse.move(seekBox.x + seekBox.width * 0.15, seekBox.y + seekBox.height / 2);
    await page.mouse.down();
    for (let step = 1; step <= 16; step += 1) {
      await page.mouse.move(
        seekBox.x + seekBox.width * (0.15 + (0.7 * step) / 16),
        seekBox.y + seekBox.height / 2,
      );
      await page.waitForTimeout(8);
    }
    await page.mouse.up();
    await page.waitForTimeout(250);

    // Tempo knob drag.
    const knob = page.locator('.transport-tempo .knob');
    const knobBox = await knob.boundingBox();
    assert.ok(knobBox);
    const beforeBpm = await page.evaluate(() => window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot().auditionBpm);
    await page.mouse.move(knobBox.x + knobBox.width / 2, knobBox.y + knobBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(knobBox.x + knobBox.width / 2, knobBox.y - 24);
    await page.mouse.up();
    await page.waitForTimeout(250);
    const afterBpm = await page.evaluate(() => window.__SKEER_MIDIVAULT_DEBUG__.engine.getSnapshot().auditionBpm);
    assert.notEqual(Math.round(afterBpm), Math.round(beforeBpm));
    assert.equal(await page.evaluate(() => document.querySelector('#root')?.childElementCount), 1);
  });

  await checkpoint('track mute and solo update the audition routing', async () => {
    await chooseMidnight(page);
    const firstTrack = page.locator('.track-entry').first();
    await firstTrack.locator('.ms-button').nth(0).click();
    await page.waitForTimeout(200);
    assert.ok(await firstTrack.locator('.ms-button').nth(0).evaluate((el) => el.classList.contains('is-on')));
    await firstTrack.locator('.ms-button').nth(1).click();
    await page.waitForTimeout(200);
    assert.ok(await firstTrack.locator('.ms-button').nth(1).evaluate((el) => el.classList.contains('is-on')));
    await firstTrack.locator('.ms-button').nth(0).click();
    await firstTrack.locator('.ms-button').nth(1).click();
  });

  await checkpoint('format 2 independent sequences are shown separately', async () => {
    await page.locator('#library-search').fill('Format 2');
    await page.waitForTimeout(500);
    await page.locator('.file-row').first().click();
    await page.waitForTimeout(600);
    assert.equal(await page.locator('.sequence-tabs-list button').count(), 2);
    await page.locator('.sequence-tabs-list button').nth(1).click();
    await page.waitForTimeout(500);
    assert.match(await page.locator('.detail-title-row h2').innerText(), /Format 2/);
    await page.screenshot({ path: path.join(shotsDir, 'format-2-sequences.png') });
    await page.locator('#library-search').fill('');
    await page.waitForTimeout(500);
  });

  await checkpoint('export copies original files to a chosen folder', async () => {
    await chooseMidnight(page);
    await page.getByRole('button', { name: 'Copy / export' }).click();
    await page.locator('.export-dialog').waitFor({ timeout: 5000 });
    const destinationInput = page.locator('.destination-input-wrap input');
    await destinationInput.fill(exportDir);
    await page.getByRole('button', { name: 'Copy files' }).click();
    await page.locator('.export-results').waitFor({ timeout: 10000 });
    assert.ok(fs.existsSync(path.join(exportDir, 'Midnight Drive 118.mid')));
    await page.getByRole('button', { name: 'Close' }).last().click();
  });

  await checkpoint('scan dialog reports source controls and recent issues', async () => {
    await page.locator('.scan-button').click();
    await page.locator('.scan-config').waitFor({ timeout: 10000 });
    await page.locator('.source-row').first().waitFor({ timeout: 10000 });
    await page.waitForTimeout(450);
    await page.waitForFunction(
      () => document.querySelectorAll('.toast').length === 0,
      null,
      { timeout: 8000 },
    ).catch(() => {});
    assert.ok(await page.locator('.source-row').count() > 0);
    assert.ok(await page.locator('.scan-section').count() >= 3);
    await page.screenshot({ path: path.join(shotsDir, 'scan-computer.png') });
    await page.getByRole('button', { name: 'Not now' }).click();
  });

  await checkpoint('no browser console or page errors', async () => {
    assert.deepEqual(consoleIssues, []);
  });

  const failed = results.filter((item) => item.status === 'FAIL');
  console.log(`\nE2E RESULT: ${results.length - failed.length}/${results.length} checks passed`);
  fs.writeFileSync(
    path.join(root, 'docs', 'e2e-results.json'),
    JSON.stringify({ run_id: runId, results, console_issues: consoleIssues }, null, 2),
    'utf8',
  );
  if (failed.length) process.exitCode = 1;
} catch (error) {
  console.error('E2E ABORTED:', error);
  fs.writeFileSync(
    path.join(root, 'docs', 'e2e-results.json'),
    JSON.stringify({ run_id: runId, results, error: error instanceof Error ? error.stack : String(error) }, null, 2),
    'utf8',
  );
  process.exitCode = 1;
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
}
