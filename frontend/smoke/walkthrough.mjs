// End-to-end walkthrough of a fresh Podly instance: sign in, tour Settings, add a
// feed, process its newest episode, inspect the stats, then check Jobs and the
// phone layout. Screenshots, a video and a log land in <out-dir>.
import { chromium, devices } from 'playwright';
import { MASK_SETTINGS, createRun, enableEpisode, parseArgs, waitForStatsButtons } from './lib.mjs';

const args = parseArgs('walkthrough.mjs');
const { base, outDir } = args;
const FEED_URL = process.env.SMOKE_FEED_URL || 'https://feeds.npr.org/500005/podcast.xml';
const run = createRun(outDir, '');

const browser = await chromium.launch();
const desktop = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  colorScheme: 'dark',
  recordVideo: { dir: `${outDir}/video`, size: { width: 1280, height: 800 } },
});
await desktop.addInitScript(MASK_SETTINGS);
const page = await desktop.newPage();
run.watch(page, 'desktop', base);

try {
  // Sign in: a wrong password first, then the real one.
  await page.goto(`${base}/`);
  await page.locator('#username').waitFor({ timeout: 30000 });
  await page.waitForTimeout(800);
  await run.shot(page, 'login');
  await page.fill('#username', args.username);
  await page.fill('#password', 'wrong-password');
  await page.keyboard.press('Enter');
  await page.getByText('Invalid username or password.').waitFor({ timeout: 10000 });
  await run.shot(page, 'login-wrong-password');
  await page.fill('#password', args.password);
  await page.keyboard.press('Enter');
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 });
  await page.waitForTimeout(2000);
  await run.shot(page, 'home');
  run.note('signed in');

  // Settings tour.
  await page.getByRole('link', { name: 'Settings' }).first().click();
  await page.waitForTimeout(2000);
  await run.shot(page, 'settings-basics');
  for (const [query, label] of [
    ['tab=advanced&section=llm', 'settings-llm'],
    ['tab=advanced&section=whisper', 'settings-transcription'],
    ['tab=users', 'settings-users'],
    ['tab=costs', 'settings-costs'],
  ]) {
    await page.goto(`${base}/config?${query}`);
    await page.waitForTimeout(1800);
    await run.shot(page, label);
  }

  // Add a feed by RSS URL.
  await page.getByRole('link', { name: 'Home' }).first().click();
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: /^Add feed$/ }).first().click();
  await page.waitForTimeout(1000);
  await page.getByRole('button', { name: 'Enter RSS URL' }).click();
  await page.fill('#feed-url', FEED_URL);
  await page.mouse.move(5, 5);
  await page.waitForTimeout(600);
  await run.shot(page, 'add-feed-form');
  await page.locator('form button[type="submit"]').first().click();
  await page.locator('button').filter({ hasText: /episodes/ }).first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(2000);
  await run.shot(page, 'feed-added');
  run.note('feed added');

  // Open the feed. A new feed usually enables and queues its newest episode on
  // its own. Press Process when the episode is enabled but not queued, and
  // enable it by hand when neither happened.
  await page.locator('button').filter({ hasText: /episodes/ }).first().click();
  await page.waitForTimeout(3500);
  await run.shot(page, 'feed-detail');
  const toggle = page.getByRole('switch').first();
  await toggle.waitFor({ timeout: 20000 });
  if ((await toggle.getAttribute('aria-checked')) !== 'true') {
    const dialog = await enableEpisode(page, 0);
    await run.shot(page, 'enable-confirm');
    await dialog.confirm();
    await dialog.enabled();
    run.note('enabled newest episode');
  } else {
    const processButton = page.getByRole('button', { name: /^Process$/ }).first();
    if (await processButton.count()) {
      await processButton.click();
      await page.waitForTimeout(1500);
      if (await page.getByText(/before processing/i).count()) {
        throw new Error('Podly refused to process: no LLM API key is configured');
      }
      run.note('pressed Process on the newest episode');
    } else {
      run.note('newest episode queued automatically');
    }
  }
  await page.waitForTimeout(3000);
  await run.shot(page, 'processing');

  const { buttons: statsButtons, seconds } = await waitForStatsButtons(page, 1);
  run.note(`processing finished after ${seconds}s`);
  await page.waitForTimeout(1500);
  await run.shot(page, 'episode-processed');

  // Inspect the stats.
  await statsButtons.first().click();
  await page.getByRole('tab', { name: /Model calls/ }).waitFor({ timeout: 20000 });
  await page.waitForTimeout(2500);
  await run.shot(page, 'stats-overview');
  await page.mouse.wheel(0, 900);
  await page.waitForTimeout(1500);
  await run.shot(page, 'stats-overview-lower');
  for (const tab of ['Model calls', 'Transcript segments', 'Identifications']) {
    await page.getByRole('tab', { name: new RegExp(tab) }).click();
    await page.waitForTimeout(1200);
    await run.shot(page, `stats-${tab.split(' ')[0].toLowerCase()}`);
  }
  await page.getByRole('tab', { name: /Model calls/ }).click();
  await page.waitForTimeout(800);
  const details = page.getByRole('button', { name: 'Details' }).first();
  if (await details.count()) {
    await details.click();
    await page.waitForTimeout(800);
    await run.shot(page, 'stats-model-call-details');
  }
  await page.keyboard.press('Escape');
  await page.waitForTimeout(800);

  // Jobs after the run.
  await page.getByRole('link', { name: 'Jobs' }).first().click();
  await page.waitForTimeout(2000);
  await page.getByRole('button', { name: 'Load all jobs' }).click().catch(() => {});
  await page.waitForTimeout(2000);
  await run.shot(page, 'jobs');
} catch (err) {
  run.fail(err.message);
  await run.shot(page, 'failure').catch(() => {});
}

const cookies = await desktop.cookies();
await desktop.close();

// Phone layout with the same session.
const phone = await browser.newContext({ ...devices['iPhone 13'], colorScheme: 'light' });
await phone.addInitScript(MASK_SETTINGS);
await phone.addCookies(cookies);
const phonePage = await phone.newPage();
run.watch(phonePage, 'phone', base);
try {
  await phonePage.goto(`${base}/`);
  await phonePage.waitForTimeout(2500);
  await run.shot(phonePage, 'phone-home');
  await phonePage.locator('button').filter({ hasText: /episodes/ }).first().click();
  await phonePage.waitForTimeout(2500);
  await run.shot(phonePage, 'phone-feed');
  const close = phonePage.getByRole('button', { name: /close|back/i }).first();
  if (await close.count()) {
    await close.click();
    await phonePage.waitForTimeout(1500);
    await run.shot(phonePage, 'phone-closed');
  }
} catch (err) {
  run.fail(`phone: ${err.message}`);
  await run.shot(phonePage, 'phone-failure').catch(() => {});
}
await phone.close();
await browser.close();
run.finish('walkthrough.log');
