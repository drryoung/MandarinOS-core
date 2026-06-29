# MandarinOS — quick session review launcher.
# Run from repo root: .\review.ps1
# Delegates all logic to tools\session_review.ps1.

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "tools\session_review.ps1"
& $script @args
