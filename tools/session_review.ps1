# MandarinOS — Session Intelligence review pipeline
# Runs the full import-from-Railway → batch-export workflow.
#
# Usage:
#   .\tools\session_review.ps1
#
# Required environment variables (set once per terminal session):
#   $env:MANDARINOS_APP_URL           = "https://YOUR-APP.up.railway.app"
#   $env:MANDARINOS_BETA_ADMIN_TOKEN  = "YOUR_TOKEN"
#
# Or create a local copy of tools\session_review_sample_env.ps1 with real
# values (do NOT commit that file).

$ErrorActionPreference = "Stop"

# ── Check required environment variables ────────────────────────────────────

$appUrl    = $env:MANDARINOS_APP_URL
$adminToken = $env:MANDARINOS_BETA_ADMIN_TOKEN

if (-not $appUrl -or $appUrl -eq "https://YOUR-APP.up.railway.app") {
    Write-Host ""
    Write-Host "ERROR: MANDARINOS_APP_URL is not set." -ForegroundColor Red
    Write-Host ""
    Write-Host "Set it in this terminal with:" -ForegroundColor Yellow
    Write-Host '  $env:MANDARINOS_APP_URL = "https://YOUR-APP.up.railway.app"' -ForegroundColor Cyan
    Write-Host '  $env:MANDARINOS_BETA_ADMIN_TOKEN = "YOUR_TOKEN"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or run tools\session_review_sample_env.ps1 after filling in real values." -ForegroundColor Yellow
    exit 1
}

if (-not $adminToken -or $adminToken -eq "replace_me") {
    Write-Host ""
    Write-Host "ERROR: MANDARINOS_BETA_ADMIN_TOKEN is not set." -ForegroundColor Red
    Write-Host ""
    Write-Host "Set it in this terminal with:" -ForegroundColor Yellow
    Write-Host '  $env:MANDARINOS_BETA_ADMIN_TOKEN = "YOUR_TOKEN"' -ForegroundColor Cyan
    exit 1
}

# ── Run the pipeline ─────────────────────────────────────────────────────────

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repoRoot "scripts\run_session_review_pipeline.py"

Write-Host ""
Write-Host "MandarinOS Session Review Pipeline" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "App URL    : $appUrl"
Write-Host "Token      : $($adminToken.Substring(0, [Math]::Min(4, $adminToken.Length)))****"
Write-Host ""

python $script `
    --app-url $appUrl `
    --admin-token $adminToken `
    --open

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Done. Open the batch prompt above and paste into ChatGPT or Claude." -ForegroundColor Green
} elseif ($LASTEXITCODE -eq 1) {
    Write-Host ""
    Write-Host "No new sessions to review. All sessions already exported." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Pipeline encountered an error (exit $LASTEXITCODE). See output above." -ForegroundColor Red
    exit $LASTEXITCODE
}
