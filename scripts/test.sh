#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$repo_root/scripts/build.sh"
ctest --test-dir "$repo_root/build" --output-on-failure
