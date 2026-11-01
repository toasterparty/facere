# Print Git's bash.exe path (never the System32 WSL launcher), or nothing if not
# found. Reads PATH from the registry so a bash installed in another session is
# found without restarting the terminal.

$ErrorActionPreference = "SilentlyContinue"

function Find-Bash {
    $regPath = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
               [Environment]::GetEnvironmentVariable("Path", "User")

    foreach ($dir in ($regPath -split ";" | Where-Object { $_ })) {
        if ($dir -like "*System32*") { continue }
        $candidate = Join-Path $dir "bash.exe"
        if (Test-Path $candidate) { return $candidate }
    }

    # Derive from git.exe: walk up to the Git root and find bin\bash.exe.
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        $dir = Split-Path $git.Source
        while ($dir -and -not (Test-Path (Join-Path $dir "bin\bash.exe"))) {
            $parent = Split-Path $dir
            $dir = if ($parent -eq $dir) { $null } else { $parent }
        }
        if ($dir) { return (Join-Path $dir "bin\bash.exe") }
    }

    foreach ($p in @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LocalAppData\Programs\Git\bin\bash.exe"
    )) {
        if ($p -and (Test-Path $p)) { return $p }
    }
}

$bash = Find-Bash
if ($bash) { $bash.Replace('\', '/') }
