# Registers a Windows scheduled task that runs nightly-update.ps1 on weekdays.
#   powershell -ExecutionPolicy Bypass -File scripts\register-nightly-task.ps1 [-At 17:00]
# Remove it with: Unregister-ScheduledTask -TaskName 'Markets nightly update'
#
# 17:00 is after NSE's 15:30 close and the closing price (set by ~15:35), so the day's bars are
# ready for evening analysis. A run takes about 1.5 hours for ~3,000 instruments under Angel
# One's rate limits, finishing well before SmartAPI sessions expire at midnight. Each run
# re-fetches the latest stored bar, so a bar that wasn't final yet is corrected by the next run.
# If the PC is asleep at 17:00, the task runs as soon as it wakes (each run logs in fresh).

param(
    [string]$At = '17:00',
    [string]$TaskName = 'Markets nightly update'
)

$script = Join-Path $PSScriptRoot 'nightly-update.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description 'Fetches new daily candles from Angel One into the Indian Markets DuckDB database.' | Out-Null

Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
