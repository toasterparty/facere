# Run tools/uv.sh under Git bash (located via find-bash.ps1), forwarding all args to uv.
$ErrorActionPreference = "Stop"

$bash = & "$PSScriptRoot\find-bash.ps1"
if (-not $bash) {
    Write-Error "Could not locate Git bash - run tools/install-bash.ps1 (open a new terminal if you just installed it)"
    exit 1
}

& $bash "$PSScriptRoot\uv.sh" @args
exit $LASTEXITCODE
