# MandarinOS — Sample environment setup for session review pipeline.
#
# INSTRUCTIONS:
#   1. Copy this file to a location outside the repo (e.g. your Desktop or
#      a local secrets folder that is NOT committed to git).
#   2. Replace the placeholder values with your real Railway URL and token.
#   3. Dot-source this file in your terminal before running session_review.ps1:
#        . C:\path\to\your\local_env.ps1
#        .\tools\session_review.ps1
#
# DO NOT commit a file containing real tokens.
# This sample file intentionally contains only placeholder values.

$env:MANDARINOS_APP_URL          = "https://YOUR-APP.up.railway.app"
$env:MANDARINOS_BETA_ADMIN_TOKEN = "replace_me"

Write-Host "MandarinOS environment variables set (sample/placeholder values)." -ForegroundColor Yellow
Write-Host "Replace the values above with your real Railway URL and admin token." -ForegroundColor Yellow
