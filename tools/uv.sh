#!/usr/bin/env bash
# Run uv from the repo root with the settings in project.env applied.
set -euo pipefail
shopt -s nullglob
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd -- "$SCRIPT_DIR/.."

while IFS='=' read -r key value; do
    [[ -v $key ]] || export "$key=$value"
done < ./project.env
export PATH="$(cd "$HOME" && pwd)/.local/bin:$PATH"

exec uv "$@"
