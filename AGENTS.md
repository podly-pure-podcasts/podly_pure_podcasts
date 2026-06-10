Project-specific rules:
- Do not create Alembic migrations yourself; request the user to generate migrations after model changes using `./scripts/create_migration.sh "<message>"`.
- Only use ./scripts/ci.sh to run tests & lints - do not attempt to run directly
- Expect ./scripts/ci.sh to modify files because it runs formatting and auto-fixes; review the working tree after running it.
- use uv (not pipenv)
- All database writes must go through the `writer` service. Do not use `db.session.commit()` directly in application code. Use `writer_client.action()` instead.
- If you change behavior, including bug fixes, add or update test coverage for it.
- For frontend work, use `npm` in `frontend/` and keep `package-lock.json` authoritative; do not switch package managers.

## Cursor Cloud specific instructions

Podly is a Python 3.11 Flask app plus a separate **writer** process (IPC on `127.0.0.1:50001`) and a React/Vite frontend. System **ffmpeg** is required for audio tests and processing (`apt install ffmpeg` if missing).

### Dependencies and CI

- Python deps: `uv sync --extra dev` (requires `uv` on `PATH`, typically `~/.local/bin`; Python 3.11 is selected via `pyproject.toml` `requires-python`).
- Frontend deps: `cd frontend && npm ci`.
- Lint, typecheck, and unit tests: `./scripts/ci.sh` only (do not invoke ruff/pytest directly).
- Integration workflow (live server): `./scripts/ci.sh --int` or `PODLY_TEST_URL=http://127.0.0.1:5001 uv run python scripts/check_integration_workflow.py` with `DEVELOPER_MODE=true`.

### Running locally without Docker

Defaults assume Docker paths (`/app/src/instance`). On bare metal, set instance dirs before starting services:

```bash
export PODLY_INSTANCE_DIR=/workspace/src/instance
export PODLY_PODCAST_DATA_DIR=/workspace/src/instance/data
export DEVELOPER_MODE=true
export PYTHONPATH=/workspace/src
mkdir -p "$PODLY_INSTANCE_DIR/data/in" "$PODLY_INSTANCE_DIR/data/srv" "$PODLY_INSTANCE_DIR/logs"
```

Start **writer** first, wait until port `50001` accepts TCP, then start the web app:

```bash
uv run python -m app.writer
uv run python src/main.py   # http://127.0.0.1:5001 (PORT env overrides)
```

Use tmux for long-running processes. Optional: `PODLY_DISABLE_SCHEDULER=1` reduces background work during manual testing.

### Docker (optional)

`./run_podly_docker.sh --dev` sets `DEVELOPER_MODE=true` and is the documented path when Docker is available. See `docs/contributors.md`.

### Frontend dev server

`cd frontend && npm run dev` → Vite on `:5173`, proxies API to `http://localhost:5001` (`BACKEND_TARGET` in `vite.config.ts`). Production UI is built with `npm run build` into Flask static assets (Docker image does this automatically).

### Secrets

Real transcription/LLM processing needs `.env.local` (copy from `.env.local.example`, e.g. `GROQ_API_KEY`). Developer-mode integration tests do not require API keys.
