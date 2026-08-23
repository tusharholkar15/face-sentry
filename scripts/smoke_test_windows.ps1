<#
.SYNOPSIS
Runs FaceSentry in Diagnostic mode to verify execution and hardware.

.DESCRIPTION
Starts the installed FaceSentryAgent.exe in DIAGNOSTIC mode.
Does not enforce authentication or trigger real workstation locks.
#>

$appDataDir = [System.Environment]::GetFolderPath('LocalApplicationData')
$exePath = Join-Path $appDataDir "FaceSentry\FaceSentryAgent.exe"

Write-Host "============================================="
Write-Host " FaceSentry Diagnostic Smoke Test"
Write-Host "============================================="

if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: Executable not found at $exePath."
    Write-Host "Install first using install_windows.ps1."
    exit 1
}

Write-Host "Launching FaceSentry Agent in DIAGNOSTIC mode..."
Write-Host "This will run pre-flight checks and exit immediately."
Write-Host "---------------------------------------------`n"

# Run the executable with the --mode DIAGNOSTIC argument
$process = Start-Process -FilePath $exePath -ArgumentList "--mode DIAGNOSTIC" -NoNewWindow -Wait -PassThru

Write-Host "`n---------------------------------------------"
if ($process.ExitCode -eq 0) {
    Write-Host "SMOKE TEST PASSED (Exit Code: 0)" -ForegroundColor Green
} else {
    Write-Host "SMOKE TEST FAILED (Exit Code: $($process.ExitCode))" -ForegroundColor Red
}
