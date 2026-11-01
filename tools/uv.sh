#!/usr/bin/env bash
# Run uv from the repo root with the settings in project.env applied.
set -euo pipefail
shopt -s nullglob
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd -- "$SCRIPT_DIR/.."

set -a
source ./project.env
set +a
export PATH="$(cd "$HOME" && pwd)/.local/bin:$PATH"

exec uv "$@"
