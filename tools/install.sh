#!/usr/bin/env bash
# Ensure uv, plus Git bash and GNU make on Windows, is present; --update pulls them to latest.
set -euo pipefail
shopt -s nullglob
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd -- "$SCRIPT_DIR/.."

update=
while [[ $# -gt 0 ]]; do
    case "$1" in
        --update) update=1; shift ;;
        *) echo "Error: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

uv_sh() { bash ./tools/uv.sh "$@"; }

# Under pwsh 7, the inherited PSModulePath makes Windows PowerShell load pwsh 7's modules.
winpwsh() { env -u PSModulePath powershell -NoProfile -ExecutionPolicy Bypass "$@"; }

is_windows() {
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
        *) return 1 ;;
    esac
}

install_uv() {
    uv_sh --version >/dev/null 2>&1 && return 0
    if is_windows; then
        winpwsh -Command "irm https://astral.sh/uv/install.ps1 | iex"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
}

if is_windows; then
    winpwsh -File tools/install-bash.ps1 ${update:+-Update}
fi

install_uv

if [[ -n $update && -z "${CI:-}" ]]; then
    uv_sh self update -q >/dev/null 2>&1 || true
fi
