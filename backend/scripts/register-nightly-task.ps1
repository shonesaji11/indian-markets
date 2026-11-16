# Registers a Windows scheduled task that runs nightly-update.ps1 on weekdays.
#   powershell -ExecutionPolicy Bypass -File scripts\register-nightly-task.ps1 [-At 23:00]
# Remove it with: Unregister-ScheduledTask -TaskName 'Markets nightly update'
#
# 23:00 leaves time for the run (about 7 minutes for ~500 instruments at Angel One's
# 80 requests/minute) to finish before SmartAPI sessions expire at midnight. If the PC is
# asleep at 23:00, the task runs as soon as it wakes (each run logs in fresh).

param(
    [string]$At = '23:00',
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
