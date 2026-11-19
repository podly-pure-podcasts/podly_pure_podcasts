import fs from 'fs';

// Usage: <script> <base-url> <out-dir> [env-file]
// Credentials come from PODLY_ADMIN_USERNAME / PODLY_ADMIN_PASSWORD, read from the
// env file when given (for example .env.local), otherwise from the environment.
export function parseArgs(scriptName) {
  const [base, outDir, envFile] = process.argv.slice(2);
  if (!base || !outDir) {
    console.error(`Usage: node smoke/${scriptName} <base-url> <out-dir> [env-file]`);
    process.exit(2);
  }
  const fileEnv = envFile ? readEnvFile(envFile) : {};
  const get = (key) => fileEnv[key] ?? process.env[key];
  const username = get('PODLY_ADMIN_USERNAME') || 'admin';
  const password = get('PODLY_ADMIN_PASSWORD');
  if (!password) {
    console.error('PODLY_ADMIN_PASSWORD is not set.');
    process.exit(2);
  }
  fs.mkdirSync(outDir, { recursive: true });
  return { base: base.replace(/\/$/, ''), outDir, username, password };
}

function readEnvFile(path) {
  return Object.fromEntries(
    fs.readFileSync(path, 'utf8')
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#') && line.includes('='))
      .map((line) => {
        const i = line.indexOf('=');
        return [line.slice(0, i), line.slice(i + 1).replace(/^(['"])(.*)\1$/, '$2')];
      })
  );
}

export function createRun(outDir, prefix) {
  const log = [];
  const failures = [];
  let count = 0;
  const note = (msg) => {
    const line = `[${new Date().toISOString().slice(11, 19)}] ${msg}`;
    log.push(line);
    console.log(line);
  };
  return {
    note,
    fail(msg) {
      failures.push(msg);
      note(`FAIL ${msg}`);
    },
    async shot(page, label) {
      count += 1;
      const file = `${prefix}${String(count).padStart(2, '0')}-${label}.jpg`;
      await page.screenshot({ path: `${outDir}/${file}`, type: 'jpeg', quality: 70, scale: 'css' });
      note(`shot ${file}`);
    },
    // Page errors and server errors fail the run. 4xx responses are logged only:
    // the session check before sign-in, a wrong password and an unreachable
    // provider in the Settings connection probe all return them by design.
    watch(page, tag, base) {
      page.on('pageerror', (e) => failures.push(`${tag} page error: ${e.message}`));
      page.on('response', (r) => {
        if (r.status() < 400) return;
        const msg = `${tag} HTTP ${r.status()} ${r.request().method()} ${r.url().replace(base, '')}`;
        if (r.status() >= 500) failures.push(msg);
        note(msg);
      });
    },
    finish(logName) {
      fs.writeFileSync(`${outDir}/${logName}`, log.join('\n') + '\n');
      if (failures.length) {
        console.error(`\n${failures.length} failure(s):\n${failures.map((f) => `- ${f}`).join('\n')}`);
        process.exitCode = 1;
      } else {
        console.log('\nSmoke run passed.');
      }
    },
  };
}

// Settings show API keys, key previews and server addresses. Installed before any
// page script, this blurs every Settings field from the first painted frame so
// screenshots and recordings never capture them.
export const MASK_SETTINGS = () => {
  const apply = () => document.documentElement.toggleAttribute('data-smoke-mask', location.pathname.startsWith('/config'));
  for (const fn of ['pushState', 'replaceState']) {
    const original = history[fn];
    history[fn] = function (...args) {
      const result = original.apply(this, args);
      apply();
      return result;
    };
  }
  window.addEventListener('popstate', apply);
  const install = () => {
    const style = document.createElement('style');
    style.textContent = 'html[data-smoke-mask] main input, html[data-smoke-mask] main textarea, html[data-smoke-mask] main select { filter: blur(7px) !important; }';
    document.documentElement.appendChild(style);
    apply();
  };
  if (document.documentElement) install();
  else document.addEventListener('DOMContentLoaded', install);
};

export async function signIn(page, { base, username, password }) {
  await page.goto(`${base}/`);
  await page.locator('#username').waitFor({ timeout: 30000 });
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.keyboard.press('Enter');
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 });
}

// Enabling an episode asks for confirmation and queues it for processing.
export async function enableEpisode(page, index) {
  const toggle = page.getByRole('switch').nth(index);
  await toggle.click();
  const confirm = page.getByRole('button', { name: 'Confirm & process' });
  await confirm.waitFor({ timeout: 10000 });
  await page.waitForTimeout(600);
  return {
    confirm: () => confirm.click(),
    enabled: () =>
      page.waitForFunction(
        (i) => document.querySelectorAll('[role="switch"]')[i]?.getAttribute('aria-checked') === 'true',
        index,
        { timeout: 20000 }
      ),
  };
}

export async function waitForStatsButtons(page, count, timeoutMs = 15 * 60 * 1000) {
  const buttons = page.getByRole('button', { name: /^Stats$/ });
  const started = Date.now();
  while ((await buttons.count()) < count) {
    if (Date.now() - started > timeoutMs) throw new Error(`processing did not finish within ${timeoutMs / 60000} minutes`);
    await page.waitForTimeout(5000);
  }
  return { buttons, seconds: Math.round((Date.now() - started) / 1000) };
}
