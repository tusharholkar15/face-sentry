<#
.SYNOPSIS
Registers FaceSentry Agent to start automatically upon user logon.

.DESCRIPTION
Uses Windows Task Scheduler to create a task that runs FaceSentryAgent.exe in the 
current user's interactive session. Does not require Administrator privileges.
#>

$ErrorActionPreference = "Stop"

$taskName = "FaceSentry Agent"
$appDataDir = [System.Environment]::GetFolderPath('LocalApplicationData')
$installDir = Join-Path $appDataDir "FaceSentry"
$exePath = Join-Path $installDir "FaceSentryAgent.exe"

Write-Host "============================================="
Write-Host " FaceSentry Task Scheduler Registration"
Write-Host "============================================="

if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: Executable not found at $exePath."
    Write-Host "You must install FaceSentry first using install_windows.ps1."
    exit 1
}

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Task '$taskName' already exists. Unregistering old task to recreate..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Write-Host "Creating Scheduled Task for interactive user logon..."

# 1. Action: Run the executable
$action = New-ScheduledTaskAction -Execute $exePath -WorkingDirectory $installDir

# 2. Trigger: At Logon for the current user
$trigger = New-ScheduledTaskTrigger -AtLogon

# 3. Settings: Restart on failure, don't stop on idle, allow demand start
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)

# Register the task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "FaceSentry Biometric Security Agent" | Out-Null

Write-Host "SUCCESS: Registered scheduled task '$taskName'."
Write-Host "The agent will now launch automatically next time you log in."
