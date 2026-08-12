# Installs anonymize.py's Python dependencies with whichever interpreter
# actually works. Tries `py` (Windows Python Launcher) first, then
# `python`, and actually invokes each candidate rather than just checking
# it resolves to something, because on Windows `python`/`python3` are
# often Microsoft Store redirect stubs that exist on PATH but fail the
# moment you run them (see CONTRIBUTING.md).

$ErrorActionPreference = "Stop"

function Find-Python {
    foreach ($name in @("py", "python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            try {
                & $cmd.Source --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    return $cmd.Source
                }
            } catch {
                continue
            }
        }
    }
    return $null
}

$pythonExe = Find-Python
if (-not $pythonExe) {
    Write-Error "No working Python interpreter found (tried py, python, python3). Install Python 3.9+ first."
    exit 1
}

$requirementsPath = Join-Path $PSScriptRoot "..\requirements.txt"

Write-Host "Using $(& $pythonExe --version) ($pythonExe)"
& $pythonExe -m pip install -r $requirementsPath
