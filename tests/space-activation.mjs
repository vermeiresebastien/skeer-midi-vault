/**
 * Keyboard harness — Space belongs to the focused control, not the transport.
 *
 * App.tsx's global keydown handler treats every target that is not an
 * INPUT/TEXTAREA/SELECT/contentEditable as "not typing", so it calls
 * preventDefault() on Space even when the keyboard user has tabbed onto a real
 * <button>. Cancelling the keydown is exactly what stops the browser from
 * synthesizing that button's click, so Enter-and-Tab users get play/pause
 * instead of the control they are standing on.
 *
 * The engine is instrumented in-page (play/pause call counters) so a check can
 * say directly "the global shortcut did not run", instead of inferring it from
 * transport state that the row click rewrites anyway. Each check requires both
 * halves: the control activated itself AND zero play/pause calls. The body check
 * is the anti-vacuity guard: it must show a play/pause call either way, or the
 * counter patch is not wired and every other result is meaningless.
 *
 * No service, no writes: the built UI is served from web/dist and its /api
 * calls are answered from fixtures.
 */
import assert from 'node:assert/strict';
import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import { findBrowser } from './browser-path.mjs';
import { FILES, sleep, stubAppRoutes } from './app-harness.mjs';

const ORIGIN = 'http://midi-vault.test';
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

const snapshot = (page) => page.evaluate(() => {
  const engine = window.__SKEER_MIDIVAULT_DEBUG__?.engine;
  if (!engine) return null;
  const s = engine.getSnapshot();
  return {
    playing: s.playing,
    paused: s.paused,
    loop: s.loop,
    hasSequence: s.hasSequence,
    sourceTime: s.sourceTime,
    calls: { ...window.__TRANSPORT_CALLS__ },
  };
});

/** Wrap the live engine's transport entry points so the shortcut leaves a trace. */
async function instrument(page) {
  const ok = await page.evaluate(() => {
    const engine = window.__SKEER_MIDIVAULT_DEBUG__?.engine;
    if (!engine) return 'no engine';
    window.__TRANSPORT_CALLS__ = { play: 0, pause: 0, stop: 0 };
    const play = engine.play.bind(engine);
    const pause = engine.pause.bind(engine);
    const stop = engine.stop.bind(engine);
    engine.play = (...args) => { window.__TRANSPORT_CALLS__.play += 1; return play(...args); };
    engine.pause = (...args) => { window.__TRANSPORT_CALLS__.pause += 1; return pause(...args); };
    engine.stop = (...args) => { window.__TRANSPORT_CALLS__.stop += 1; return stop(...args); };
    return typeof engine.play === 'function' ? 'ok' : 'failed';
  });
  assert.equal(ok, 'ok', 'could not instrument the engine transport — every check below would be vacuous');
}

const resetCalls = (page) => page.evaluate(() => {
  window.__TRANSPORT_CALLS__ = { play: 0, pause: 0, stop: 0 };
});

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
  const settingsCalls = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/settings')) settingsCalls.push(request.method());
  });

  await stubAppRoutes(page, { autoplay: false });
  await page.goto(`${ORIGIN}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);
  await instrument(page);

  // Open a healthy row so the transport has a sequence and Space has something
  // to steal. Autoplay is off, so nothing plays on its own.
  await page.locator('.file-row', { hasText: FILES[0].name }).first().click();
  await page.locator('.detail-title-row h2', { hasText: FILES[0].name }).first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(400);
  const ready = await snapshot(page);
  assert.equal(ready.hasSequence, true, 'the row click did not install a sequence');
  assert.equal(ready.playing, false, 'the setup click must not be playing');
  console.log(`   ready: sequence installed for ${FILES[0].name}, transport idle`);

  const autoplayButton = page.locator('.transport-autoplay');

  const settleIdle = async () => {
    for (let attempt = 0; attempt < 4; attempt += 1) {
      if (await autoplayButton.getAttribute('aria-pressed') === 'true') await autoplayButton.click();
      else break;
      await sleep(300);
    }
    await page.locator('.transport-bar button[aria-label="Stop"]').click().catch(() => {});
    await sleep(350);
    assert.equal(await autoplayButton.getAttribute('aria-pressed'), 'false', 'autoplay did not reset');
    assert.equal((await snapshot(page)).playing, false, 'the transport did not reset');
    await resetCalls(page);
  };

  const pressSpace = async (locator) => {
    await locator.focus();
    const focused = await locator.evaluate((node) => `${node.tagName.toLowerCase()}[${node.className}]`);
    await resetCalls(page);
    const marks = { settingsCalls: settingsCalls.length };
    const before = await snapshot(page);
    await page.keyboard.press('Space');
    await sleep(500);
    const after = await snapshot(page);
    return {
      focused,
      before,
      after,
      shortcutCalls: (after.calls.play - before.calls.play) + (after.calls.pause - before.calls.pause),
      settingsFired: settingsCalls.length > marks.settingsCalls,
    };
  };

  await checkpoint('guard: Space with focus on the page body plays and pauses', async () => {
    await settleIdle();
    await page.evaluate(() => document.activeElement?.blur());
    const run = await pressSpace(page.locator('body'));
    assert.equal(run.shortcutCalls, 1, `the shortcut did not run on the body at all (calls ${JSON.stringify(run.before.calls)} -> ${JSON.stringify(run.after.calls)})`);
    assert.equal(run.after.playing, true, 'the first Space did not start the preview');
    await page.keyboard.press('Space');
    await sleep(400);
    assert.equal((await snapshot(page)).playing, false, 'the second Space did not pause');
    console.log('   Space on the body still owns the transport (counter moved by 1)');
  });

  await checkpoint('Space on the focused Autoplay button toggles autoplay, not the transport', async () => {
    await settleIdle();
    const run = await pressSpace(autoplayButton);
    assert.equal(
      await autoplayButton.getAttribute('aria-pressed'),
      'true',
      `the button did not activate itself (Space landed on "${run.focused}", aria-pressed still false)`,
    );
    assert.ok(run.settingsFired, 'the button click handler never reached the settings endpoint');
    assert.equal(run.shortcutCalls, 0, 'the global Space shortcut fired as well and stole the key');
  });

  await checkpoint('Space on the focused Loop button toggles loop, not the transport', async () => {
    await settleIdle();
    const loopButton = page.locator('.transport-bar button[aria-label="Loop off"]');
    await loopButton.waitFor({ state: 'visible', timeout: 10000 });
    const run = await pressSpace(loopButton);
    assert.equal(run.after.loop, true, `loop stayed off — the button did not activate (focus was "${run.focused}")`);
    assert.equal(run.shortcutCalls, 0, 'the global Space shortcut fired as well and stole the key');
  });

  await checkpoint('Space on the focused file row activates the row without touching the transport', async () => {
    await settleIdle();
    // The row that is already open: selecting it again is a no-op, so nothing
    // else can mask what the global handler does to the transport here.
    const row = page.locator('.file-row', { hasText: FILES[0].name }).first();
    assert.match(await row.getAttribute('class'), /is-active/, 'the setup row is not the active one');
    const run = await pressSpace(row);
    assert.match(await row.getAttribute('class'), /is-active/, 'the row lost its own activation to the shortcut');
    assert.equal(run.shortcutCalls, 0, 'the global Space shortcut fired on top of the row activation');
  });

  await checkpoint('guard: no console errors from the keyboard path', async () => {
    assert.deepEqual(consoleErrors, [], consoleErrors.slice(0, 3).join(' | '));
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
