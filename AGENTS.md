Project-specific rules:
- Create Alembic migrations yourself.
- Run tests and lints directly.
- use uv
- All database writes must go through the `writer` service. Do not use `db.session.commit()` directly in application code. Use `writer_client.action()` instead.
