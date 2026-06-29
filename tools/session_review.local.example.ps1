# MandarinOS — local session review config (example / template).
#
# INSTRUCTIONS:
#   1. Copy this file to:    tools\session_review.local.ps1
#   2. Replace the placeholder values with your real Railway URL and token.
#   3. That file is .gitignored — it will never be committed.
#
# The file is dot-sourced automatically by tools\session_review.ps1
# (and therefore by .\review.ps1) before env-var checks run.

$env:MANDARINOS_APP_URL          = "https://YOUR-APP.up.railway.app"
$env:MANDARINOS_BETA_ADMIN_TOKEN = "replace_me"
