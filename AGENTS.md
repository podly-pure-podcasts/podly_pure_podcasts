Project-specific rules:
- Do not create Alembic migrations yourself; request the user to generate migrations after model changes using `./scripts/create_migration.sh "<message>"`.
- Only use ./scripts/ci.sh to run tests & lints - do not attempt to run directly
- Expect ./scripts/ci.sh to modify files because it runs formatting and auto-fixes; review the working tree after running it.
- use uv (not pipenv)
- All database writes must go through the `writer` service. Do not use `db.session.commit()` directly in application code. Use `writer_client.action()` instead.
- If you change behavior, including bug fixes, add or update test coverage for it.
- For frontend work, use `npm` in `frontend/` and keep `package-lock.json` authoritative; do not switch package managers.
- never use /tmp/ - always use ./tmp/ instead