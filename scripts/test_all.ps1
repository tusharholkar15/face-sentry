# FaceSentry Comprehensive Test Suite Runner for Windows PowerShell
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Running FaceSentry Test Suites            " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Run Python Unit & Integration Tests (pytest)
Write-Host "[*] Executing Python test suite (Backend & Agent)..." -ForegroundColor Yellow
$env:PYTHONPATH = "."
.\.venv\Scripts\pytest -v tests/
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Python test suite failed." -ForegroundColor Red
    exit 1
}
Write-Host "[+] Python test suite PASSED." -ForegroundColor Green

# 2. Run TypeScript Typecheck (apps/web)
Write-Host "[*] Executing Web TypeScript typecheck..." -ForegroundColor Yellow
npm --prefix apps/web run typecheck
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Web typecheck failed." -ForegroundColor Red
    exit 1
}
Write-Host "[+] Web typecheck PASSED." -ForegroundColor Green

# 3. Run Agent Diagnostic Self-Check
Write-Host "[*] Executing Agent Diagnostic Self-Check..." -ForegroundColor Yellow
.\.venv\Scripts\python -m apps.agent.main --check
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Agent self-check failed." -ForegroundColor Red
    exit 1
}
Write-Host "[+] Agent self-check PASSED." -ForegroundColor Green

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " All FaceSentry test suites passed!        " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
