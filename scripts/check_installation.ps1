<#
.SYNOPSIS
Validates a FaceSentry installation.

.DESCRIPTION
Checks directories, models, configurations, and enrollment data to ensure the agent can start.
#>

$appDataDir = [System.Environment]::GetFolderPath('LocalApplicationData')
$installDir = Join-Path $appDataDir "FaceSentry"

Write-Host "============================================="
Write-Host " FaceSentry Installation Diagnostics"
Write-Host "============================================="

$checksFailed = 0

function Test-Check {
    param([string]$name, [bool]$condition)
    if ($condition) {
        Write-Host "[ PASS ] $name" -ForegroundColor Green
    } else {
        Write-Host "[ FAIL ] $name" -ForegroundColor Red
        $script:checksFailed++
    }
}

Test-Check "Installation Directory exists" (Test-Path $installDir)

$exePath = Join-Path $installDir "FaceSentryAgent.exe"
Test-Check "Agent Executable exists" (Test-Path $exePath)

$model1 = Join-Path $installDir "models\face_detection_yunet_2023mar.onnx"
$model2 = Join-Path $installDir "models\face_recognition_sface_2021dec.onnx"
Test-Check "YuNet Model exists" (Test-Path $model1)
Test-Check "SFace Model exists" (Test-Path $model2)

$enrollment = Join-Path $installDir "enrollment\default_user.dat"
if (Test-Path $enrollment) {
    Write-Host "[ INFO ] Biometric Profile is enrolled (default_user.dat)." -ForegroundColor Cyan
} else {
    Write-Host "[ WARN ] No Biometric Profile found. Enrollment required." -ForegroundColor Yellow
}

$task = Get-ScheduledTask -TaskName "FaceSentry Agent" -ErrorAction SilentlyContinue
Test-Check "Startup Task Registered" ($null -ne $task)

Write-Host "============================================="
if ($checksFailed -eq 0) {
    Write-Host " SUMMARY: ALL CORE CHECKS PASSED" -ForegroundColor Green
} else {
    Write-Host " SUMMARY: $checksFailed CHECKS FAILED" -ForegroundColor Red
}
