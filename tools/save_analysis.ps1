# MandarinOS — save manual AI batch analysis output.
#
# Usage:
#   .\tools\save_analysis.ps1 <path-to-analysis-file>
#
# Example:
#   .\tools\save_analysis.ps1 data\review_outputs\inbox\batch_2026-06-29_01_analysis.md
#
# Flags are passed through to the Python script.
# Use --dry-run to validate without writing, --overwrite to replace existing files.

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$AnalysisFile,

    [switch]$DryRun,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$script   = Join-Path $repoRoot "scripts\save_batch_review_analysis.py"

$extraArgs = @()
if ($DryRun)   { $extraArgs += "--dry-run" }
if ($Overwrite){ $extraArgs += "--overwrite" }

python $script $AnalysisFile @extraArgs
