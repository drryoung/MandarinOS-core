# MandarinOS Trace Conformance Validator (Windows)
#
# Usage: .\validate_traces.ps1 -Path "C:\path\to\traces"
#
# This PowerShell script validates all *.json trace files in the given directory
# against the TurnStateTrace schema and conformance rules.

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$Path = "."
)

$ErrorActionPreference = "Stop"

Write-Host "Mandresden-OS Trace Conformance Validator (v1)" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "Traces directory: $Path"
Write-Host ""

# Resolve path
if (-not (Test-Path $Path -PathType Container)) {
    Write-Error "Error: Directory '$Path' not found" -ErrorAction Stop
}

$ResolvedPath = (Resolve-Path $Path).Path

# Check for Python
$PythonCmd = $null
if (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} else {
    Write-Error "Error: Python 3.7+ not found. Please install Python." -ErrorAction Stop
}

# Detect MandarinOS-core repository root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CoreRoot = Split-Path -Parent $ScriptDir

$ConformancePath = Join-Path $CoreRoot "conformance" "run_trace_conformance.py"

if (-not (Test-Path $ConformancePath)) {
    Write-Error "Error: Cannot find MandarinOS-core conformance runner at: $ConformancePath" -ErrorAction Stop
}

Write-Host "Running conformance checks..."
Write-Host ""

# Run the conformance validator
& $PythonCmd $ConformancePath $CoreRoot --path $ResolvedPath
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "===========================================" -ForegroundColor Cyan
if ($ExitCode -eq 0) {
    Write-Host "✓ All traces passed conformance validation" -ForegroundColor Green
} else {
    Write-Host "✗ Trace validation failed (exit code: $ExitCode)" -ForegroundColor Red
}

exit $ExitCode
