#!/bin/bash


# Parse command line arguments
RUN_INTEGRATION=false
for arg in "$@"; do
    if [ "$arg" = "--int" ]; then
        RUN_INTEGRATION=true
    fi
done

# ensure dependencies are installed and are always up to date
echo '============================================================='
echo "Running 'uv sync --extra dev'"
echo '============================================================='
uv sync --extra dev
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

# Run integration tests only if --int flag is provided
if [ "$RUN_INTEGRATION" = true ]; then
    echo '============================================================='
    echo "Running integration workflow checks..."
    echo '============================================================='
    uv run python scripts/check_integration_workflow.py
fi
