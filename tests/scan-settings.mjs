/**
 * Scan-settings harness — the incremental re-hash guard has to be a visible,
 * persisted control.
 *
 * An incremental scan skips a file whose size and mtime_ns still match the
 * index. An editor that rewrote the file in place while preserving both — and
 * an index whose clock was adjusted — therefore keeps its stale analysis forever.
 * The scan re-reads the bytes and compares the stored content hash by default,
 * and that default is a user's choice, not a silent policy: it has to appear in
 * Settings → Scanning, travel to the service on save, and come back from
 * `/api/bootstrap` on the next load.
 *
 * The real built UI is driven in headless Chrome against the stubbed service in
 * app-harness.mjs, which merges every PATCH into the settings it hands back, so
 * the reload check exercises the read path rather than a fixture. Nothing
 * reaches a Python service; the user's library and index are not touched.
 */
import assert from 'node:assert/strict';
import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import { findBrowser } from './browser-path.mjs';
import { sleep, stubAppRoutes } from './app-harness.mjs';

const ORIGIN = 'http://midi-vault.test';
const LABEL = 'Re-read files an incremental scan would skip';
const results = [];
let browser;

async function checkpoint(name, fn) {
  try {
    await fn();
    results.push(`PASS ${name}`);
    console.log(`PASS ${name}`);
  } catch (error) {
    const message = error instanceof Error ? error.message.split('\n').slice(0, 6).join('\n    ') : String(error);
    results.push(`FAIL ${name}: ${message}`);
    console.error(`FAIL ${name}: ${message}`);
  }
}

/** Open Settings → Scanning and return the switch for the re-hash guard. */
async function openScanning(page) {
  await page.locator('.settings-button').click();
  await page.locator('.settings-tabs button', { hasText: 'Scanning' }).first().click();
  const row = page.locator('.scanning-settings .toggle-row', { hasText: LABEL }).first();
  await row.waitFor({ timeout: 10000 });
  return row.locator('button[role="switch"]');
}

const isChecked = (switcher) => switcher.getAttribute('aria-checked');

try {
  browser = await chromium.launch({
    executablePath: findBrowser(),
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--disable-gpu', '--mute-audio'],
  });
  const context = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => consoleErrors.push(`pageerror: ${error.message}`));

  // The stub merges a PATCH into what it serves back, so the reload check below
  // can only pass if the value actually travelled through the service.
  const patches = [];
  page.on('request', (request) => {
    if (!request.url().includes('/api/settings')) return;
    try {
      patches.push({ method: request.method(), body: request.postDataJSON() });
    } catch {
      patches.push({ method: request.method(), body: null });
    }
  });

  await stubAppRoutes(page, { autoplay: false, settings: { verify_unchanged: '1' } });
  await page.goto(`${ORIGIN}/`, { waitUntil: 'domcontentloaded' });
  await sleep(1200);

  await checkpoint('the re-hash guard is offered as a control, on by default', async () => {
    const switcher = await openScanning(page);
    assert.equal(await isChecked(switcher), 'true', 'a default index reports the guard as off');
    await page.locator('.settings-modal button', { hasText: 'Cancel' }).first().click();
  });

  await checkpoint('switching it off and saving sends verify_unchanged=0', async () => {
    const switcher = await openScanning(page);
    await switcher.click();
    assert.equal(await isChecked(switcher), 'false', 'the switch did not move on click');
    const before = patches.length;
    await page.locator('.settings-modal button', { hasText: 'Save scan settings' }).first().click();
    await sleep(900);
    const sent = patches.slice(before).find((call) => call.method !== 'GET');
    assert.ok(sent, 'saving the scanning tab sent no settings request at all');
    assert.equal(sent.body?.verify_unchanged, '0', `saved ${JSON.stringify(sent.body?.verify_unchanged)}, expected "0"`);
    // The neighbours ride along: one save must not blank the other scan settings.
    for (const key of ['scan_intensity', 'scan_mode', 'parse_workers']) {
      assert.ok(sent.body && key in sent.body, `the save dropped ${key} (${Object.keys(sent.body || {}).join(', ')})`);
    }
  });

  await checkpoint('the saved value comes back from the service on reload', async () => {
    await page.reload({ waitUntil: 'domcontentloaded' });
    await sleep(1200);
    const switcher = await openScanning(page);
    assert.equal(await isChecked(switcher), 'false', [
      'the switch re-opened on, so the interface shows its own default rather than',
      'what the index holds — a scan started now would use the other policy than',
      'the one on screen',
    ].join(' '));
    await page.locator('.settings-modal button', { hasText: 'Cancel' }).first().click();
    await sleep(300);
  });

  await checkpoint('switching it back on sends verify_unchanged=1', async () => {
    const switcher = await openScanning(page);
    await switcher.click();
    assert.equal(await isChecked(switcher), 'true', 'the switch did not return to on');
    const before = patches.length;
    await page.locator('.settings-modal button', { hasText: 'Save scan settings' }).first().click();
    await sleep(900);
    const sent = patches.slice(before).find((call) => call.method !== 'GET');
    assert.ok(sent, 'the second save sent nothing');
    assert.equal(sent.body?.verify_unchanged, '1', 'the guard could not be re-armed');
  });

  await checkpoint('no console errors from the settings path', async () => {
    assert.equal(consoleErrors.length, 0, `console errors: ${consoleErrors.slice(0, 3).join(' | ')}`);
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
