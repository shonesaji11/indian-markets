# Runs the nightly market data update (markets update) and appends its output to
# backend\logs\update-YYYY-MM-DD.log. Logs older than 30 days are deleted.
# Scheduled by register-nightly-task.ps1; safe to run by hand.

$backend = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $backend 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ('update-{0:yyyy-MM-dd}.log' -f (Get-Date))
$exe = Join-Path $backend '.venv\Scripts\markets.exe'

Add-Content -Path $log -Value ("==== {0:yyyy-MM-dd HH:mm:ss} nightly update starting" -f (Get-Date))
# cmd handles the redirection so the log stays plain text (PowerShell 5.1 would write UTF-16).
cmd /c "`"$exe`" update >> `"$log`" 2>&1"
$code = $LASTEXITCODE
Add-Content -Path $log -Value ("==== {0:yyyy-MM-dd HH:mm:ss} finished with exit code {1}" -f (Get-Date), $code)

Get-ChildItem $logDir -Filter 'update-*.log' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
exit $code
