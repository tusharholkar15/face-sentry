<#
.SYNOPSIS
Uninstalls FaceSentry Windows Agent from the current user's profile.

.DESCRIPTION
Removes the scheduled task and application files.
Asks for explicit confirmation before deleting biometric data and settings.
#>

$ErrorActionPreference = "Stop"

$appDataDir = [System.Environment]::GetFolderPath('LocalApplicationData')
$installDir = Join-Path $appDataDir "FaceSentry"
$taskName = "FaceSentry Agent"

Write-Host "============================================="
Write-Host " FaceSentry Agent Uninstaller"
Write-Host "============================================="

# 1. Stop Process
Write-Host "`n[1/4] Stopping Agent..."
$runningProcs = Get-Process -Name "FaceSentryAgent" -ErrorAction SilentlyContinue
if ($runningProcs) {
    Write-Host "  -> Stopping currently running FaceSentryAgent processes..."
    $runningProcs | Stop-Process -Force -Wait
} else {
    Write-Host "  -> Agent is not currently running."
}

# 2. Unregister Task
Write-Host "`n[2/4] Removing Scheduled Task..."
$taskExists = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($taskExists) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "  -> Removed scheduled task: '$taskName'"
} else {
    Write-Host "  -> Scheduled task not found."
}

# 3. Remove Application Files
Write-Host "`n[3/4] Removing Application Files..."
if (Test-Path $installDir) {
    $exePath = Join-Path $installDir "FaceSentryAgent.exe"
    $modelsDir = Join-Path $installDir "models"
    
    if (Test-Path $exePath) { Remove-Item $exePath -Force; Write-Host "  -> Removed Agent Executable" }
    if (Test-Path $modelsDir) { Remove-Item $modelsDir -Recurse -Force; Write-Host "  -> Removed Models" }
} else {
    Write-Host "  -> Installation directory not found: $installDir"
}

# 4. Cleanup Biometrics / Settings
Write-Host "`n[4/4] Data Cleanup"
Write-Host "FaceSentry biometric enrollment data, security events, and configuration remain in:"
Write-Host "  $installDir"
Write-Host ""
$choice = Read-Host "Do you want to permanently delete all enrolled biometric data and settings? (y/N)"

if ($choice -match "^[yY]") {
    if (Test-Path $installDir) {
        Remove-Item $installDir -Recurse -Force
        Write-Host "  -> All FaceSentry data and settings have been permanently deleted."
    }
} else {
    Write-Host "  -> Biometric data and settings preserved in $installDir."
}

Write-Host "`n============================================="
Write-Host " UNINSTALLATION COMPLETE"
Write-Host "============================================="
