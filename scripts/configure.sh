#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_type=${BUILD_TYPE:-Debug}

cmake -S "$repo_root" -B "$repo_root/build" -DCMAKE_BUILD_TYPE="$build_type" "$@"
