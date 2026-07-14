#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
formatter=${CLANG_FORMAT:-clang-format}

if ! command -v "$formatter" >/dev/null 2>&1; then
  echo "clang-format is required; set CLANG_FORMAT to its executable path." >&2
  exit 1
fi

find "$repo_root/cpp" "$repo_root/tests" -type f \( -name '*.cpp' -o -name '*.hpp' \) \
  -exec "$formatter" --dry-run --Werror {} +
