# Ensure Git bash is available, then put it on PATH. -Update pulls it to latest.
param([switch]$Update)

$ErrorActionPreference = "Stop"

function Install-Tool($id, $probe) {
    if (-not $Update -and (& $probe)) { return }

    # `winget install` updates a package that is already present, and exits
    # non-zero when it is already current; neither is an error here.
    winget install --id $id -e --source winget --disable-interactivity `
        --accept-package-agreements --accept-source-agreements 2>&1 |
        Where-Object { $_ -notmatch "No available upgrade found|No newer package versions are available|Found an existing package already installed" }
    $global:LASTEXITCODE = 0
}

Install-Tool "Git.Git" { [bool](& "$PSScriptRoot\find-bash.ps1") }

$bash = & "$PSScriptRoot\find-bash.ps1"

if (-not $bash) {
    throw "Could not locate Git bash.exe. Ensure Git for Windows installed correctly."
}

$bashDir = Split-Path $bash
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")

# Persist on PATH for future shell instances...
if (($userPath -split ";") -notcontains $bashDir) {
    $userPath = if ($userPath) { "$bashDir;$userPath" } else { $bashDir }
    [Environment]::SetEnvironmentVariable("Path", $userPath, "User")
}

# ...and in this shell now, without a restart, with whatever the installs added.
# Prepended so it wins over the System32 bash.exe that launches WSL.
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = (@($bashDir) + ($env:Path, $machinePath, $userPath -split ";") |
    Where-Object { $_ } | Select-Object -Unique) -join ";"
