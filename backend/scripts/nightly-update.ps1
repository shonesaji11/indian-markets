# Runs the nightly market data update (markets update) and appends its output to
# backend\logs\update-YYYY-MM-DD.log. Logs older than 30 days are deleted; the short per-run
# summaries in backend\logs\nightly-summary.log are kept.
# Scheduled by register-nightly-task.ps1; safe to run by hand.

$backend = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $backend 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ('update-{0:yyyy-MM-dd}.log' -f (Get-Date))
$exe = Join-Path $backend '.venv\Scripts\markets.exe'

Add-Content -Path $log -Value ("==== {0:yyyy-MM-dd HH:mm:ss} nightly update starting" -f (Get-Date))
# cmd handles the redirection so the log stays plain text (PowerShell 5.1 would write UTF-16).
cmd /c "`"$exe`" update --scheduled >> `"$log`" 2>&1"
$code = $LASTEXITCODE
Add-Content -Path $log -Value ("==== {0:yyyy-MM-dd HH:mm:ss} finished with exit code {1}" -f (Get-Date), $code)
# `markets update` appends its own block to nightly-summary.log; a failed run may not get that far.
if ($code -ne 0) {
    Add-Content -Path (Join-Path $logDir 'nightly-summary.log') -Value (
        "{0:yyyy-MM-dd  HH:mm}  scheduled run failed with exit code {1}: see {2}`r`n" -f (Get-Date), $code, (Split-Path -Leaf $log))
}

Get-ChildItem $logDir -Filter 'update-*.log' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
exit $code
