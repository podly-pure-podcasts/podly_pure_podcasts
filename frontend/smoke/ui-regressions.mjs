// Browser checks for scrolling and error handling that need no backend: the API
// is answered by route mocks. Usage: node smoke/ui-regressions.mjs <base-url>
//   npm run build && npx vite preview --port 4173   (then base-url http://127.0.0.1:4173)
import { chromium } from 'playwright';

const base = (process.argv[2] || '').replace(/\/$/, '');
if (!base) {
  console.error('Usage: node smoke/ui-regressions.mjs <base-url>');
  process.exit(2);
}

const feedFor = (id) => ({
  id,
  rss_url: 'http://mock.invalid/rss',
  title: id === 1 ? 'Mock Feed' : `Mock Feed ${id}`,
  description: 'A feed with enough episodes to scroll.',
  author: 'Mock Author',
  image_url: null,
  posts_count: 30,
  is_member: true,
  is_active_subscription: true,
  ad_detection_strategy: 'llm',
});
const feeds = Array.from({ length: 40 }, (_, i) => feedFor(i + 1));
const episodes = Array.from({ length: 30 }, (_, i) => ({
  id: i + 1,
  guid: `guid-${i + 1}`,
  title: `Episode ${i + 1}`,
  description: 'An episode description. '.repeat(20),
  release_date: '2026-10-01T00:00:00',
  duration: 1800,
  whitelisted: true,
  has_processed_audio: false,
  has_unprocessed_audio: false,
  download_url: 'http://mock.invalid/a.mp3',
  image_url: null,
  download_count: 0,
}));

const jobs = Array.from({ length: 60 }, (_, i) => ({
  job_id: `job-${i + 1}`,
  post_guid: `guid-${i + 1}`,
  post_title: `Episode ${i + 1}`,
  feed_title: 'Mock Feed',
  status: 'completed',
  priority: 0,
  step: 4,
  step_name: 'Done',
  total_steps: 4,
  progress_percentage: 100,
  created_at: '2026-10-01T00:00:00',
  started_at: '2026-10-01T00:00:00',
  completed_at: '2026-10-01T00:05:00',
  error_message: null,
}));
const searchResults = Array.from({ length: 40 }, (_, i) => ({
  title: `Search result ${i + 1}`,
  author: 'Mock Author',
  feedUrl: `http://mock.invalid/search-${i + 1}.xml`,
  artworkUrl: '',
  description: 'A search result.',
  genres: ['Mock'],
}));

const config = {
  config: {
    llm: {
      llm_api_key_preview: 'sk-…mock',
      llm_model: 'mock/model',
      openai_timeout: 300,
      openai_max_tokens: 4096,
      llm_max_concurrent_calls: 3,
      llm_max_retry_attempts: 3,
      llm_enable_token_rate_limiting: false,
      enable_boundary_refinement: true,
    },
    whisper: { whisper_type: 'test' },
    processing: { num_segments_to_input_to_prompt: 30, record_word_timestamps: true },
    output: {
      fade_ms: 3000,
      bleep_padding_start_ms: 0,
      bleep_padding_end_ms: 0,
      min_ad_segement_separation_seconds: 60,
      min_ad_segment_length_seconds: 14,
      min_confidence: 0.8,
    },
    app: {
      background_update_interval_minute: 30,
      automatically_whitelist_new_episodes: true,
      post_cleanup_retention_days: null,
      number_of_episodes_to_whitelist_from_archive_of_new_feed: 1,
      enable_public_landing_page: false,
      user_limit_total: null,
      autoprocess_on_download: true,
      cost_rate_per_hour: 0,
      whisper_cost_rate_per_hour: 0,
      ina_cost_rate_per_hour: 0,
    },
    notifications: {
      enabled: false,
      apprise_urls: [],
      notify_on_failure: true,
      notify_on_success: false,
      notify_on_rust_fallback: false,
      include_llm_explanation: false,
    },
  },
  env_overrides: {},
};

const failures = [];
const check = (ok, msg) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${msg}`);
  if (!ok) failures.push(msg);
};

const browser = await chromium.launch();

async function openPage(viewport) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (e) => pageErrors.push(e.message));
  // Playwright tries the most recently registered route first.
  await page.route('**/api/**', (r) => r.fulfill({ json: {} }));
  await page.route('**/api/auth/status', (r) =>
    r.fulfill({ json: { require_auth: false, landing_page_enabled: false } })
  );
  await page.route('**/feeds', (r) => r.fulfill({ json: feeds }));
  await page.route('**/api/feeds/*/posts*', (r) =>
    r.fulfill({
      json: { items: episodes, total: 30, page: 1, page_size: 30, total_pages: 1, whitelisted_total: 30 },
    })
  );
  await page.route('**/api/feeds/search*', (r) =>
    r.fulfill({ json: { results: searchResults, total: searchResults.length } })
  );
  await page.route('**/api/jobs/active*', (r) => r.fulfill({ json: jobs }));
  await page.route('**/api/config', (r) => r.fulfill({ json: config }));
  await page.route('**/api/jobs/all*', (r) => r.fulfill({ json: jobs }));
  await page.route('**/api/jobs/cleanup/preview', (r) =>
    r.fulfill({ json: { count: 0, cutoff_utc: '2026-10-01T00:00:00', retention_days: 14 } })
  );
  await page.route('**/api/job-manager/status', (r) =>
    r.fulfill({ json: { total_jobs: 0, run_id: null, queued_jobs: 0, running_jobs: 0, workers: 0 } })
  );
  return { context, page, pageErrors };
}

// Wheel over `target` and report whether `scroller` moved. The scroller must also
// be bounded: a container that grows to its content never scrolls itself, and
// overscroll-behavior on it then blocks Chrome from scrolling anything else.
async function expectWheelScrolls(page, scroller, target, label) {
  const el = scroller.first();
  const where = target ?? el;
  const box = await el.boundingBox();
  const viewport = page.viewportSize();
  const m = await el.evaluate((node) => ({ scrollHeight: node.scrollHeight, clientHeight: node.clientHeight }));
  check(
    box !== null && box.height <= viewport.height && m.scrollHeight > m.clientHeight,
    `${label}: bounded and scrollable (client ${m.clientHeight}, content ${m.scrollHeight})`
  );
  const point = await where.first().boundingBox();
  await page.mouse.move(point.x + point.width / 2, Math.min(point.y + point.height / 2, viewport.height - 20));
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(700);
  const top = await el.evaluate((node) => node.scrollTop);
  check(top > 0, `${label}: wheel scrolls it (scrollTop ${top})`);
}

// For a list inside a page that may scroll either itself or the page around it
// depending on the width: the wheel must move one of the two.
async function expectWheelScrollsOneOf(page, scrollers, target, label) {
  const point = await target.boundingBox();
  const viewport = page.viewportSize();
  await page.mouse.move(point.x + point.width / 2, Math.min(point.y + point.height / 2, viewport.height - 20));
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(700);
  const tops = await Promise.all(scrollers.map((scroller) => scroller.first().evaluate((node) => node.scrollTop)));
  check(tops.some((top) => top > 0), `${label}: wheel scrolls the list or its page (scrollTop ${tops.join(', ')})`);
}

async function scenario(name, viewport, run) {
  console.log(`\n# ${name}`);
  const { context, page, pageErrors } = await openPage(viewport);
  try {
    await run(page);
    check(pageErrors.length === 0, `${name}: no uncaught page errors${pageErrors.length ? `: ${pageErrors.join('; ')}` : ''}`);
  } catch (err) {
    failures.push(`${name}: ${err}`);
    console.error(err);
  } finally {
    await context.close();
  }
}

const settle = (page) => page.waitForTimeout(2500);
const openFeed = async (page, title = 'Mock Feed') => {
  await page.goto(`${base}/`);
  await page.getByRole('button', { name: new RegExp(`^${title}`) }).first().click().catch(() => page.getByText(title, { exact: true }).first().click());
  await page.getByText('Episode 5', { exact: true }).waitFor({ timeout: 15000 });
  await settle(page);
};

await scenario('feed pane and error handling (desktop)', { width: 1280, height: 800 }, async (page) => {
  await openFeed(page);
  await expectWheelScrolls(page, page.locator('.overscroll-contain'), page.getByText('Episode 5', { exact: true }), 'feed pane');

  // A ResizeObserver loop notice is not an error worth a Troubleshooting popup.
  await page.evaluate(() => {
    window.dispatchEvent(
      new ErrorEvent('error', { message: 'ResizeObserver loop completed with undelivered notifications.' })
    );
    window.dispatchEvent(new ErrorEvent('error', { message: 'ResizeObserver loop limit exceeded' }));
  });
  await page.waitForTimeout(500);
  check(
    (await page.getByRole('heading', { name: 'Troubleshooting' }).count()) === 0,
    'ResizeObserver loop notices do not open the Troubleshooting popup'
  );

  // A genuine error still does, and its entry list scrolls once it is long.
  await page.evaluate(() => {
    for (let i = 0; i < 80; i += 1) console.log(`diagnostic entry ${i}`);
    window.dispatchEvent(new ErrorEvent('error', { message: 'Something actually broke' }));
  });
  const opened = await page
    .getByRole('heading', { name: 'Troubleshooting' })
    .waitFor({ timeout: 5000 })
    .then(() => true, () => false);
  check(opened, 'a genuine error still opens the Troubleshooting popup');
  if (opened) {
    await expectWheelScrolls(page, page.locator('.max-h-\\[45vh\\].overflow-auto'), null, 'diagnostics entries');
  }
});

await scenario('feed list (desktop)', { width: 1280, height: 800 }, async (page) => {
  await page.goto(`${base}/`);
  await page.getByText('Mock Feed 12', { exact: true }).first().waitFor({ timeout: 15000 });
  await settle(page);
  await expectWheelScrolls(page, page.locator('.overflow-y-auto.h-full.pb-20'), page.getByText('Mock Feed 12', { exact: true }).first(), 'feed list');
});

await scenario('feed settings modal on a short screen', { width: 1280, height: 520 }, async (page) => {
  await openFeed(page);
  await page.getByRole('button', { name: 'Feed settings' }).click();
  await page.getByRole('heading', { name: /settings/i }).first().waitFor({ timeout: 5000 });
  await page.waitForTimeout(800);
  await expectWheelScrolls(page, page.locator('.overscroll-contain').last(), null, 'feed settings body');
});

await scenario('add feed modal (desktop)', { width: 1280, height: 600 }, async (page) => {
  await page.goto(`${base}/`);
  await page.getByRole('button', { name: /add feed/i }).first().click();
  await page.locator('#search-term').fill('mock');
  await page.getByText('Search result 3', { exact: true }).waitFor({ timeout: 10000 });
  await page.waitForTimeout(800);
  await expectWheelScrolls(page, page.locator('ul.overflow-y-auto'), page.getByText('Search result 1', { exact: true }), 'search results');
});

await scenario('jobs page (desktop)', { width: 1280, height: 600 }, async (page) => {
  await page.goto(`${base}/`);
  await page.getByRole('link', { name: 'Jobs' }).first().click();
  await page.getByText('Episode 4', { exact: true }).first().waitFor({ timeout: 15000 });
  await settle(page);
  await expectWheelScrolls(page, page.locator('main'), page.getByText('Episode 4', { exact: true }).first(), 'jobs page');
});

await scenario('config page (desktop)', { width: 1280, height: 400 }, async (page) => {
  await page.goto(`${base}/`);
  await page.getByRole('link', { name: 'Settings' }).first().click();
  await settle(page);
  await expectWheelScrolls(page, page.locator('main'), null, 'config page');
});

await scenario('feed panel (phone)', { width: 390, height: 700 }, async (page) => {
  await page.goto(`${base}/`);
  await page.getByText('Mock Feed 12', { exact: true }).first().waitFor({ timeout: 15000 });
  await settle(page);
  await expectWheelScrollsOneOf(
    page,
    [page.locator('.overflow-y-auto.h-full.pb-20'), page.locator('main')],
    page.getByText('Mock Feed 12', { exact: true }).first(),
    'feed list (phone)'
  );
  await page.getByText('Mock Feed 12', { exact: true }).first().click();
  await page.getByText('Episode 5', { exact: true }).waitFor({ timeout: 15000 });
  await settle(page);
  await expectWheelScrolls(page, page.locator('.overscroll-contain'), page.getByText('Episode 5', { exact: true }), 'feed pane (phone)');
});

await browser.close();

if (failures.length) {
  console.error(`\n${failures.length} check(s) failed`);
  process.exit(1);
}
