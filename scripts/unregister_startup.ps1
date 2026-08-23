<#
.SYNOPSIS
Unregisters FaceSentry Agent from Windows Task Scheduler.

.DESCRIPTION
Removes the automatic startup task.
#>

$ErrorActionPreference = "Stop"

$taskName = "FaceSentry Agent"

Write-Host "============================================="
Write-Host " FaceSentry Task Scheduler Removal"
Write-Host "============================================="

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "SUCCESS: Unregistered scheduled task '$taskName'."
    Write-Host "FaceSentry will no longer start automatically."
} else {
    Write-Host "Task '$taskName' is not currently registered."
}
