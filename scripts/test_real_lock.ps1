<#
.SYNOPSIS
    FaceSentry Manual Real Workstation Lock Verification Tool

.DESCRIPTION
    Tests the native Windows user32.dll LockWorkStation() invocation.
    This script is strictly for manual on-device hardware verification and must
    NEVER be executed automatically in CI or automated unit test runners.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\test_real_lock.ps1
#>

[CmdletBinding()]
param()

Clear-Host
Write-Host "==========================================================" -ForegroundColor Red
Write-Host " [WARNING] FaceSentry Real Workstation Lock Manual Test   " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Red
Write-Host ""
Write-Host "CRITICAL NOTICE:" -ForegroundColor Yellow
Write-Host "Executing this script will IMMEDIATELY lock your Windows workstation screen." -ForegroundColor White
Write-Host "You will be prompted to enter your Windows PIN or password to log back in." -ForegroundColor White
Write-Host ""
Write-Host "Ensure you have saved all open work before proceeding." -ForegroundColor Cyan
Write-Host ""

$confirmation = Read-Host "Type 'YES' to confirm and lock this workstation immediately"

if ($confirmation -ne "YES") {
    Write-Host ""
    Write-Host "[ABORTED] Workstation lock test cancelled by user. No lock executed." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "[*] Invoking FaceSentry WorkstationLockManager (REAL LOCK MODE)..." -ForegroundColor Yellow

$scriptBlock = @"
import time
from apps.agent.facesentry_agent.lock_manager import WorkstationLockManager, LockMode

mgr = WorkstationLockManager(enable_real_windows_lock=True)
if not mgr.is_supported():
    print("[ERROR] Windows user32.dll locking is not supported on this platform.")
    exit(1)

result = mgr.request_lock(reason='MANUAL_LOCK', force=True)
print(f'Status: {result.status.value}')
print(f'Success: {result.success}')
print(f'Timestamp: {result.timestamp}')
print(f'Reason: {result.reason}')
"@

$env:PYTHONPATH = "."
.\.venv\Scripts\python -c $scriptBlock

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[+] WorkstationLockManager lock dispatch completed successfully." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[-] WorkstationLockManager lock dispatch failed." -ForegroundColor Red
}
