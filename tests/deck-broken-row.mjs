/**
 * Autoplay deck harness — a row with no sound must not stall the deck.
 *
 * App.tsx's soundLayer effect early-returns while `soundLayer === null`, which
 * is what a row whose details call failed, or whose preview has no sequence,
 * produces. That return happens BEFORE the autoplay arming is spent and BEFORE
 * the "nothing to hear, get past it" step that the block a few lines below
 * already does for an empty note array. So one broken row stops an ear-scan of
 * the whole crate, and the leftover arming can fire on a later click.
 *
 * The deck is walked for real, in the built UI, with the /api details call
 * failing (500) for one row and an empty `preview.sequences` for another. The
 * last check is the anti-lazy-fix guard: with Autoplay OFF a broken row must be
 * spent but NOT stepped past.
 *
 * Nothing reaches a Python service, so the user's library and index are not
 * read or written.
 */
import assert from 'node:assert/strict';
import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import { findBrowser } from './browser-path.mjs';
import { FILES, sleep, stubAppRoutes } from './app-harness.mjs';

const ORIGIN = 'http://midi-vault.test';
const results = [];
let browser;

const firstFileName = (meta) => meta.name;

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

const deck = (page) => page.evaluate(() => {
  const engine = window.__SKEER_MIDIVAULT_DEBUG__?.engine;
  const s = engine?.getSnapshot();
  const text = (selector) => document.querySelector(selector)?.textContent?.trim() ?? null;
  return {
    transportDeck: text('.transport-deck'),
    detailTitle: text('.detail-title-row h2'),
    activeRow: document.querySelector('.file-row.is-active .file-name')?.textContent?.trim() ?? null,
    playing: s?.playing ?? null,
    paused: s?.paused ?? null,
    hasSequence: s?.hasSequence ?? null,
    emptyState: /no file|select a|nothing/i.test(text('.details-panel') ?? ''),
  };
});

/**
 * Waits until the deck is audibly on a healthy row past both broken ones.
 * Reports where it stopped, so a failure names the row it stalled on.
 */
async function waitForRow(page, fileName, timeoutMs = 25000) {
  const deadline = Date.now() + timeoutMs;
  let seen = null;
  while (Date.now() < deadline) {
    seen = await deck(page);
    if (seen.activeRow === fileName && seen.playing) return seen;
    await sleep(200);
  }
  throw new Error(
    `the deck never played ${fileName} within ${timeoutMs}ms — parked at `
    + `activeRow=${seen.activeRow} deck=${seen.transportDeck} detail=${seen.detailTitle} `
    + `playing=${seen.playing} hasSequence=${seen.hasSequence}`,
  );
}

async function freshPage(context, consoleErrors, options) {
  const page = await context.newPage();
  page.on('console', (message) => {
    // The harness itself answers one details call with a 500, which Chrome logs
    // as a failed resource. That is the fixture talking, not the app.
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => consoleErrors.push(`pageerror: ${error.message}`));
  await stubAppRoutes(page, options);
  await page.goto(`${ORIGIN}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  return page;
}

const rowOf = (page, fileName) => page.locator('.file-row', { hasText: fileName }).first();

try {
  browser = await chromium.launch({
    executablePath: findBrowser(),
    headless: true,
    // A short per-file scan only needs the transport to run; the audio is muted.
    args: ['--autoplay-policy=no-user-gesture-required', '--disable-gpu', '--mute-audio'],
  });
  const context = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const consoleErrors = [];
  const broken = FILES.find((meta) => meta.kind === 'fetch-fails');
  const empty = FILES.find((meta) => meta.kind === 'no-sequence');
  const afterBoth = FILES.filter((meta) => meta.kind === 'ok' && meta.id > empty.id)[0];
  console.log(`   broken rows: ${broken.name} (details 500), ${empty.name} (no preview sequence)`);

  await checkpoint('deck stepped onto a broken row still plays through to the next audible row', async () => {
    const page = await freshPage(context, consoleErrors, { autoplay: true });
    // The library auto-selects row 1 on load without arming it, so land on the
    // last row first and then click row 1: that click is what arms the deck.
    await rowOf(page, firstFileName(FILES[4])).click();
    await sleep(600);
    await rowOf(page, firstFileName(FILES[0])).click();
    // 101 plays (0.9s) -> naturalEnd -> openFile(102, broken) -> must not stop.
    const seen = await waitForRow(page, afterBoth.name);
    assert.ok(seen.playing, `reached ${afterBoth.name} but it is not playing`);
    console.log(`   ${FILES[0].name} -> ${broken.name} -> ${empty.name} -> ${afterBoth.name} playing, deck ${seen.transportDeck}`);
    await page.close();
  });

  await checkpoint('a click straight onto a broken row is spent and gotten past', async () => {
    const page = await freshPage(context, consoleErrors, { autoplay: true });
    await rowOf(page, firstFileName(broken)).click();
    const seen = await waitForRow(page, afterBoth.name, 20000);
    assert.ok(seen.playing, `reached ${afterBoth.name} but it is not playing`);
    await page.close();
  });

  await checkpoint('the walk visits the rows in order and stops at the end of the crate', async () => {
    const page = await freshPage(context, consoleErrors, { autoplay: true });
    await rowOf(page, firstFileName(FILES[4])).click();
    await sleep(600);
    await rowOf(page, firstFileName(FILES[0])).click();
    const order = FILES.map((meta) => meta.name);
    const visited = [];
    const toasts = new Set();
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      const state = await page.evaluate(() => ({
        row: document.querySelector('.file-row.is-active .file-name')?.textContent?.trim() ?? null,
        deck: document.querySelector('.transport-deck')?.textContent?.trim() ?? null,
        playing: window.__SKEER_MIDIVAULT_DEBUG__?.engine?.getSnapshot().playing ?? false,
        toast: [...document.querySelectorAll('.toast')].map((node) => node.textContent?.trim() ?? ''),
      }));
      for (const text of state.toast) toasts.add(text);
      if (state.row && visited[visited.length - 1] !== state.row) visited.push(state.row);
      if (!state.playing && state.deck === `5 / ${FILES.length}` && [...toasts].some((t) => t.includes('End of the list'))) break;
      await sleep(120);
    }
    const indices = visited.map((name) => order.indexOf(name));
    assert.deepEqual(visited, order.filter((name) => visited.includes(name)), `the deck visited rows out of order: ${visited.join(' -> ')}`);
    assert.ok(indices.every((value, i) => i === 0 || value >= indices[i - 1]), `the deck went backwards or re-played a row: ${visited.join(' -> ')}`);
    assert.ok(!visited.includes(order[0]) || indices[0] === 0, 'the deck wrapped back to the first row');
    assert.ok([...toasts].some((text) => text.includes('End of the list')), `no end-of-list notice; visited ${visited.join(' -> ')}`);
    console.log(`   visited ${visited.join(' -> ')}`);
    await page.close();
  });

  await checkpoint('guard: with Autoplay off a broken row is NOT stepped past', async () => {
    const page = await freshPage(context, consoleErrors, { autoplay: false });
    await rowOf(page, firstFileName(broken)).click();
    await page.waitForTimeout(2500);
    const parked = await deck(page);
    assert.equal(parked.activeRow, broken.name, `the deck moved on its own to ${parked.activeRow} with Autoplay off`);
    assert.equal(parked.playing, false, 'a broken row with Autoplay off must not start the transport');
    await page.close();
  });

  await checkpoint('guard: a healthy row keeps playing to its own end, broken or not', async () => {
    const page = await freshPage(context, consoleErrors, { autoplay: true });
    await rowOf(page, firstFileName(FILES[3])).click();
    const seen = await waitForRow(page, firstFileName(FILES[4]), 20000);
    assert.ok(seen.playing, `FILES[4] never played: ${JSON.stringify(seen)}`);
    await page.close();
  });

  await checkpoint('guard: the deck path logged no console errors', async () => {
    assert.deepEqual(consoleErrors, [], consoleErrors.slice(0, 4).join(' | '));
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
