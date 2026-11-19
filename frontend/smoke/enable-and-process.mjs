// Enables the second episode of the first feed by hand, confirms processing, waits
// for it to finish and opens its stats. Run after walkthrough.mjs, which adds the
// feed. Screenshots, a video and a log land in <out-dir>.
import { chromium } from 'playwright';
import { createRun, enableEpisode, parseArgs, signIn, waitForStatsButtons } from './lib.mjs';

const args = parseArgs('enable-and-process.mjs');
const { base, outDir } = args;
const run = createRun(outDir, 'manual-');

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  colorScheme: 'light',
  recordVideo: { dir: `${outDir}/video-manual`, size: { width: 1280, height: 800 } },
});
const page = await ctx.newPage();
run.watch(page, 'desktop', base);
try {
  await signIn(page, args);
  await page.locator('button').filter({ hasText: /episodes/ }).first().click();
  await page.waitForTimeout(3500);

  // Some feeds start with every episode enabled; switch it off first so the run
  // always goes through the confirm-and-process path.
  const toggle = page.getByRole('switch').nth(1);
  await toggle.waitFor({ timeout: 20000 });
  await toggle.scrollIntoViewIfNeeded();
  if ((await toggle.getAttribute('aria-checked')) === 'true') {
    await toggle.click();
    await page.waitForFunction(
      () => document.querySelectorAll('[role="switch"]')[1]?.getAttribute('aria-checked') === 'false',
      null,
      { timeout: 20000 }
    );
    run.note('disabled the second episode before re-enabling it');
  }
  await run.shot(page, 'episode-disabled');
  const dialog = await enableEpisode(page, 1);
  await run.shot(page, 'enable-confirm');
  await dialog.confirm();
  await dialog.enabled();
  run.note('enabled and queued the second episode');
  await page.waitForTimeout(2500);
  await run.shot(page, 'processing');

  const { buttons, seconds } = await waitForStatsButtons(page, 2);
  run.note(`second episode finished after ${seconds}s`);
  await run.shot(page, 'processed');
  await buttons.nth(1).click();
  await page.getByRole('tab', { name: /Model calls/ }).waitFor({ timeout: 20000 });
  await page.waitForTimeout(2500);
  await run.shot(page, 'stats');
} catch (err) {
  run.fail(err.message);
  await run.shot(page, 'failure').catch(() => {});
}
await ctx.close();
await browser.close();
run.finish('enable-and-process.log');
