#!/bin/bash
set -e


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
echo "Running 'uv run ruff format --exclude deps,.venv,.worktrees,.worktrees.bak .'"
echo '============================================================='
uv run ruff format --exclude deps,.venv,.worktrees,.worktrees.bak .
echo '============================================================='
echo "Running 'uv run ruff check --fix --exclude deps,.venv,.worktrees,.worktrees.bak .'"
echo '============================================================='
uv run ruff check --fix --exclude deps,.venv,.worktrees,.worktrees.bak .

# type check
echo '============================================================='
echo "Running 'uv run ty check'"
echo '============================================================='
uv run ty check

# run tests
echo '============================================================='
echo "Running 'uv run pytest --ignore deps --ignore .worktrees --disable-warnings'"
echo '============================================================='
uv run pytest --ignore deps --ignore .worktrees --disable-warnings

# Run integration tests only if --int flag is provided
if [ "$RUN_INTEGRATION" = true ]; then
    echo '============================================================='
    echo "Running integration workflow checks..."
    echo '============================================================='
    uv run python scripts/check_integration_workflow.py
fi
