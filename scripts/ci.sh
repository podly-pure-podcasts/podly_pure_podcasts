#!/bin/bash
set -uo pipefail

# Parse command line arguments
RUN_INTEGRATION=false
for arg in "$@"; do
    if [ "$arg" = "--int" ]; then
        RUN_INTEGRATION=true
    fi
done

# Track failures so every step still runs, then exit non-zero if any failed.
# Without this, a failing pytest/ruff/ty is swallowed by the trailing
# `if [ "$RUN_INTEGRATION" = true ]` (bash's status becomes 0).
status=0
run_step() {
    local label=$1
    shift
    echo '============================================================='
    echo "Running '${label}'"
    echo '============================================================='
    if ! "$@"; then
        status=1
    fi
}

# ensure dependencies are installed and are always up to date
run_step "uv sync --extra dev" uv sync --extra dev
run_step "uv run ruff format ." uv run ruff format .
run_step "uv run ruff check --fix ." uv run ruff check --fix .

# type check
run_step "uv run ty check" uv run ty check

# run tests
run_step "uv run pytest --disable-warnings" uv run pytest --disable-warnings

# Run integration tests only if --int flag is provided
if [ "$RUN_INTEGRATION" = true ]; then
    echo '============================================================='
    echo "Running integration workflow checks..."
    echo '============================================================='
    if ! uv run python scripts/check_integration_workflow.py; then
        status=1
    fi
fi

exit "${status}"
