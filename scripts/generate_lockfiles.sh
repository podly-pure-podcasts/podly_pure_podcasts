#!/bin/bash
set -e

# Generate lock file for the full project
echo "Locking pyproject.toml..."
uv lock

# Generate lock file for the lite project in a temp directory
echo "Locking pyproject.lite.toml..."
tmp_dir=$(mktemp -d)
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

cp pyproject.lite.toml "$tmp_dir/pyproject.toml"
(cd "$tmp_dir" && uv lock)
cp "$tmp_dir/uv.lock" uv.lite.lock

echo "Lockfiles generated successfully!"
echo "- uv.lock"
echo "- uv.lite.lock"
