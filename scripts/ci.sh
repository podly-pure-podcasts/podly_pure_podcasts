#!/bin/bash

# format
echo '============================================================='
echo "Running 'uv run ruff format .'"
echo '============================================================='
uv run ruff format .
echo '============================================================='
echo "Running 'uv run ruff check --select I --fix .'"
echo '============================================================='
uv run ruff check --select I --fix .

# lint and type check
echo '============================================================='
echo "Running 'uv run mypy .'"
echo '============================================================='
uv run mypy . \
    --explicit-package-bases \
    --exclude 'migrations' \
    --exclude 'build' \
    --exclude 'scripts' \
    --exclude 'src/tests' \
    --exclude 'src/tests/test_routes.py' \
    --exclude 'src/app/routes.py'

echo '============================================================='
echo "Running 'uv run pylint src/ --ignore=migrations,tests'"
echo '============================================================='
uv run pylint src/ --ignore=migrations,tests

# run tests
echo '============================================================='
echo "Running 'uv run pytest --disable-warnings'"
echo '============================================================='
uv run pytest --disable-warnings
