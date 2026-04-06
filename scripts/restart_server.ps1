# restart_server.ps1
# Kills any process listening on port 8765, then starts ui_server.py fresh.
# Run from repo root: .\scripts\restart_server.ps1

$PORT = 8765
$REPO_ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "[restart] Checking for processes on port $PORT..."

# Find PIDs listening on the target port
$listeners = netstat -ano | Select-String "LISTENING" | Select-String ":$PORT\s"
$killed = 0
foreach ($line in $listeners) {
    $parts = $line.ToString().Trim() -split '\s+'
    $procId = $parts[-1]
    if ($procId -match '^\d+$' -and $procId -ne '0') {
        try {
            Stop-Process -Id ([int]$procId) -Force -ErrorAction Stop
            Write-Host "[restart] Killed PID $procId"
            $killed++
        } catch {
            Write-Host "[restart] Could not kill PID $procId : $_"
        }
    }
}

if ($killed -eq 0) {
    Write-Host "[restart] No processes found on port $PORT"
}

# Also kill any stray python ui_server processes not on the port
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
        if ($cmdline -like "*ui_server*") {
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            Write-Host "[restart] Killed stray ui_server PID $($proc.Id)"
        }
    } catch {}
}

Start-Sleep -Milliseconds 800

Write-Host "[restart] Starting ui_server.py..."
Set-Location $REPO_ROOT
python scripts/ui_server.py
