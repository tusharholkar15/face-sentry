<#
.SYNOPSIS
Hardware End-to-End Test Harness for FaceSentry

.DESCRIPTION
Provides a safe environment to trigger various E2E test states.
Never auto-runs real lock without explicit confirmation (--real-lock).

.PARAMETER mode
The test mode to execute.

Available modes:
- diagnostic: Checks hardware and models. Does not lock.
- dry-run: Runs the full agent loop but mocks user32.LockWorkStation.
- normal: Runs the real agent. Requires -RealLock.
- absence-lock: Helps test absence locks. Uses DRY_RUN unless -RealLock is passed.
- unknown-face-lock: Helps test stranger locks. Uses DRY_RUN unless -RealLock is passed.
- pin: Tests PIN fallback. Uses DRY_RUN for safe dashboard interaction.
- browser: Tests browser cleanup. Uses DRY_RUN unless -RealLock is passed.
- camera: Tests camera disconnect/reconnect. Uses DRY_RUN.
- full: Runs the full E2E suite. Uses DRY_RUN unless -RealLock is passed.
#>

param (
    [ValidateSet("diagnostic", "dry-run", "normal", "absence-lock", "unknown-face-lock", "pin", "browser", "camera", "full")]
    [string]$mode = "diagnostic",
    [switch]$RealLock
)

$ErrorActionPreference = "Stop"
$appDataDir = [System.Environment]::GetFolderPath('LocalApplicationData')
$exePath = Join-Path $appDataDir "FaceSentry\FaceSentryAgent.exe"

Write-Host "============================================="
Write-Host " FaceSentry E2E Hardware Test Harness"
Write-Host "============================================="

if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: Executable not found at $exePath."
    Write-Host "Install first using scripts\install_windows.ps1."
    exit 1
}

function Confirm-RealLock {
    Write-Host "=============================================" -ForegroundColor Red
    Write-Host " WARNING: REAL LOCK ENABLED" -ForegroundColor Red
    Write-Host " This test will issue ACTUAL LockWorkStation API calls." -ForegroundColor Red
    Write-Host " You must log back in manually." -ForegroundColor Red
    Write-Host "=============================================" -ForegroundColor Red
    
    $confirm = Read-Host "Type 'YES' to proceed with destructive/lock testing"
    if ($confirm -notmatch '^(YES|yes|y|Y)$') {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
    return "--mode NORMAL"
}

function Resolve-RealLock-Or-DryRun {
    if ($RealLock) {
        return Confirm-RealLock
    } else {
        Write-Host "  -> Simulating lock (DRY_RUN) because -RealLock was not provided." -ForegroundColor Yellow
        return "--mode DRY_RUN"
    }
}

$agentArg = ""

switch ($mode) {
    "diagnostic" {
        Write-Host "Selected Mode: DIAGNOSTIC (Hardware pre-flight checks only)" -ForegroundColor Cyan
        $agentArg = "--mode DIAGNOSTIC"
    }
    "dry-run" {
        Write-Host "Selected Mode: DRY_RUN (Full loop, simulated locks)" -ForegroundColor Cyan
        $agentArg = "--mode DRY_RUN"
    }
    "normal" {
        Write-Host "Selected Mode: NORMAL" -ForegroundColor Cyan
        if (-not $RealLock) {
            Write-Host "ERROR: Normal mode requires the -RealLock flag to explicitly acknowledge real Windows locking." -ForegroundColor Red
            Write-Host "Usage: .\e2e_hardware_test.ps1 -mode normal -RealLock"
            exit 1
        }
        $agentArg = Confirm-RealLock
    }
    "absence-lock" {
        Write-Host "TEST: Absence Lock" -ForegroundColor Cyan
        Write-Host "  -> [ACTION REQUIRED] Step completely out of camera view OR cover the camera lens." -ForegroundColor Yellow
        Write-Host "  -> Wait for ABSENCE_TIMEOUT (10 seconds) to trigger."
        $agentArg = Resolve-RealLock-Or-DryRun
    }
    "unknown-face-lock" {
        Write-Host "TEST: Unknown Face Lock" -ForegroundColor Cyan
        Write-Host "  -> [ACTION REQUIRED] Have an unenrolled person look into the camera (or look into camera without enrolling your profile)." -ForegroundColor Yellow
        Write-Host "  -> Wait for STRANGER_TIMEOUT (3 seconds) to trigger."
        $agentArg = Resolve-RealLock-Or-DryRun
    }
    "pin" {
        Write-Host "TEST: PIN Recovery" -ForegroundColor Cyan
        Write-Host "  -> Deliberately fail liveness or block camera to trigger fallback."
        Write-Host "  -> Use the dashboard to enter the PIN."
        Write-Host "  -> Real lock is FORCED DISABLED for this test to allow safe dashboard interaction." -ForegroundColor Yellow
        $agentArg = "--mode DRY_RUN"
    }
    "browser" {
        Write-Host "TEST: Browser Protection" -ForegroundColor Cyan
        Write-Host "  -> Open Chrome/Edge. Ensure browser protection is enabled in config."
        Write-Host "  -> Step out of frame to trigger a lock."
        $agentArg = Resolve-RealLock-Or-DryRun
    }
    "camera" {
        Write-Host "TEST: Camera Failure/Recovery" -ForegroundColor Cyan
        Write-Host "  -> Physically disconnect the webcam."
        Write-Host "  -> Wait for dashboard offline status, then reconnect."
        Write-Host "  -> Real lock is FORCED DISABLED for this test." -ForegroundColor Yellow
        $agentArg = "--mode DRY_RUN"
    }
    "full" {
        Write-Host "TEST: Full E2E Suite" -ForegroundColor Cyan
        Write-Host "  -> Execute all scenarios in sequence according to docs/E2E_TEST_PLAN.md."
        $agentArg = Resolve-RealLock-Or-DryRun
    }
}

Write-Host "`nLaunching FaceSentry..."
try {
    $proc = Start-Process -FilePath $exePath -ArgumentList $agentArg -NoNewWindow -Wait -PassThru -ErrorAction Stop
    if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne $null) {
        throw "Process exited with code $($proc.ExitCode)"
    }
} catch {
    Write-Host "Packaged executable could not be started directly ($($_.Exception.Message))." -ForegroundColor Yellow
    Write-Host "Running via project Python environment..." -ForegroundColor Cyan
    $pythonExe = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    if (Test-Path $pythonExe) {
        $argList = $agentArg.Split(' ') | Where-Object { $_ -ne "" }
        & $pythonExe -m apps.agent.facesentry_agent.main @argList
    } else {
        throw $_
    }
}

Write-Host "`nTest Execution Finished."
