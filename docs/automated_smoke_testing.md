# Automated Smoke Testing

Two Playwright scripts in `frontend/smoke/` drive a real Podly instance in a browser and record what they see. Use them to check a change end to end before opening a pull request, and to capture screenshots and video for it.

- `walkthrough.mjs` signs in (a wrong password first), tours Settings, adds a feed, processes its newest episode, inspects every Stats tab, opens Jobs, and checks the phone layout.
- `enable-and-process.mjs` enables the feed's second episode by hand, confirms processing, waits for it, and opens its stats. Run it after `walkthrough.mjs`.

Each run writes numbered screenshots, a video and a log to the output directory. A run fails (exit code 1) on a failed step, a page error or a 5xx response. 4xx responses are logged but don't fail the run, because some are expected: the session check before sign-in, the wrong password, and the Settings connection probes when a real provider rejects them.

The scripts add a feed and process episodes, so run them against a fresh, disposable instance, never one you use.

## Two modes

- **Mock providers (default).** `frontend/smoke/mock-providers.mjs` stands in for the podcast host, the transcription API and the LLM. It serves a three-episode feed of six-minute episodes, a fixed transcript with two sponsor reads, and LLM answers that mark exactly those reads. Podly runs its whole pipeline against it (download, transcription, ad classification, boundary refinement, cutting), so every Stats tab fills in, with no keys, no cost and no network access. Each episode processes in a few seconds.
- **Real providers.** A real feed with your transcription and LLM settings. Use it when a change depends on how real models behave, such as prompts, token parameters or parsing. One run costs a few cents.

In mock mode, the expected result for every episode is two ad breaks, 1:28–2:12 and 4:02–4:35, removing 1m 17s. Anything else means the pipeline changed how it treats the same transcript and classifications.

## In CI

Adding the `smoke-test` label to a pull request runs `.github/workflows/smoke-test.yml`, which runs the mock-provider mode on a GitHub runner. To test new commits, remove the label and add it again. It can also be started from the Actions tab.

For speed, it runs Podly directly on the runner (lite Python dependencies, the built frontend copied into `src/app/static`) instead of building the Docker image. It fails if either script fails or the cuts differ from the expected two ad breaks. Screenshots, video and logs are uploaded as the `smoke-output` artifact whether it passes or fails.

`.github/workflows/smoke-report.yml` then keeps one comment on the pull request up to date: pass or fail, the cuts, a 4× GIF of the walkthrough, six screenshots (or the failure screenshots) and links to both videos. The smoke run can't comment itself, because pull request code runs with a read-only token, so the report workflow runs from the default branch, reads only that run's `smoke-report` artifact, and checks the pull request's head is the commit that was tested. The media is hosted on a `smoke-media` prerelease, not in git, and a pull request's files are deleted when it closes.

## 1. Build an image

From the repository root, build the branch you want to test. The lite build skips local Whisper, which neither mode needs:

```bash
docker build --build-arg LITE_BUILD=true -t podly:smoke .
```

## 2. Write an env file

Create `smoke.env` in the repository root. It is in `.gitignore`; keep it readable only by you.

**Mock providers:** both services point at the mock on the host, which the container reaches as `host.docker.internal`. The keys only have to be non-empty:

```bash
umask 077
{
  echo "LLM_API_KEY=smoke-mock"
  echo "LLM_MODEL=gpt-4o-mini"
  echo "OPENAI_BASE_URL=http://host.docker.internal:5098/v1"
  echo "WHISPER_TYPE=remote"
  echo "WHISPER_REMOTE_API_KEY=smoke-mock"
  echo "WHISPER_REMOTE_BASE_URL=http://host.docker.internal:5098/v1"
  echo "WHISPER_REMOTE_MODEL=whisper-1"
  echo "REQUIRE_AUTH=true"
  echo "PODLY_ADMIN_USERNAME=admin"
  echo "PODLY_ADMIN_PASSWORD=$(openssl rand -hex 16)"
  echo "PODLY_SECRET_KEY=$(openssl rand -hex 32)"
} > smoke.env
```

**Real providers:** copy the provider settings from your `.env.local` instead:

```bash
umask 077
{
  grep -E '^(LLM_API_KEY|LLM_MODEL|OPENAI_BASE_URL|WHISPER_TYPE|WHISPER_REMOTE_API_KEY|WHISPER_REMOTE_BASE_URL|WHISPER_REMOTE_MODEL|GROQ_API_KEY|GROQ_WHISPER_MODEL|GROQ_MAX_RETRIES)=' .env.local
  echo "REQUIRE_AUTH=true"
  echo "PODLY_ADMIN_USERNAME=admin"
  echo "PODLY_ADMIN_PASSWORD=$(openssl rand -hex 16)"
  echo "PODLY_SECRET_KEY=$(openssl rand -hex 32)"
} > smoke.env
```

`LLM_MODEL` has to be a model the backend sends the right token-limit parameter for. Models listed in `model_uses_max_completion_tokens` (`src/shared/llm_utils.py`) get `max_completion_tokens`; everything else gets `max_tokens`, which newer OpenAI models reject. When that happens every LLM call fails and episodes are published without ad removal.

## 3. Start a fresh instance

Start the image with an empty instance directory, so migrations run from scratch and nothing from a real install is reused:

```bash
mkdir -p smoke-instance
docker run -d --name podly-smoke -p 5099:5001 \
  --add-host=host.docker.internal:host-gateway \
  --env-file smoke.env \
  -e PUID="$(id -u)" -e PGID="$(id -g)" \
  -v "$PWD/smoke-instance:/app/src/instance" \
  podly:smoke

until curl -sf -o /dev/null http://localhost:5099/; do sleep 3; done
```

The app log is in `smoke-instance/logs/app.log`.

## 4. Run the scripts

Install the frontend dependencies and Playwright's Chromium once:

```bash
cd frontend
npm ci
npx playwright install chromium
```

Each script takes the base URL, an output directory and, optionally, the env file to read the admin credentials from (otherwise they come from `PODLY_ADMIN_USERNAME` and `PODLY_ADMIN_PASSWORD` in the environment).

**Mock providers:** start the mock in a second terminal and leave it running (it listens on port 5098; pass another port as an argument and change the env file to match):

```bash
npm run smoke:mock
```

Then point the feed at it:

```bash
export SMOKE_FEED_URL=http://host.docker.internal:5098/feed.xml
npm run smoke -- http://localhost:5099 ../smoke-output ../smoke.env
npm run smoke:enable -- http://localhost:5099 ../smoke-output ../smoke.env
```

The mock logs every request it serves, which shows which provider calls Podly made.

**Real providers:** leave `SMOKE_FEED_URL` unset to use the default, NPR News Now, which has five-minute episodes with sponsor messages at the start and end, so each episode processes in under a minute. Set it to any RSS URL to test another feed.

## 5. Review the output

`smoke-output/` holds the screenshots in run order, `video/` and `video-manual/` recordings, and a log for each script with every step, timing and non-2xx response.

Settings fields are blurred in every screenshot and recording, because they show API keys, key previews and server addresses. Check the rest before sharing it: screenshots also show feed titles, episode text and the admin username.

## 6. Tear down

Stop the mock with Ctrl-C, then:

```bash
docker rm -f podly-smoke
rm -rf smoke-instance smoke-output
rm smoke.env
```
