# FaceSentry Local Environment Setup Script for Windows PowerShell
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " FaceSentry Environment Initializer        " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Check Python installation
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Python 3.10+ is required but not found in PATH." -ForegroundColor Red
    exit 1
}
Write-Host "[+] Detected Python: $pythonVersion" -ForegroundColor Green

# 2. Check Node.js installation
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Node.js 18+ is required for the web frontend." -ForegroundColor Red
    exit 1
}
Write-Host "[+] Detected Node.js: $nodeVersion" -ForegroundColor Green

# 3. Create & configure Python Virtual Environment
if (-Not (Test-Path ".venv")) {
    Write-Host "[*] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
}
Write-Host "[+] Virtual environment ready." -ForegroundColor Green

# 4. Install Python Dependencies
Write-Host "[*] Installing Python requirements..." -ForegroundColor Yellow
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt

# 5. Install Node Dependencies for Web HUD
Write-Host "[*] Installing Frontend dependencies (apps/web)..." -ForegroundColor Yellow
cd apps/web
npm install
cd ../..

# 6. Copy environment files if missing
if (-Not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[+] Created root .env from .env.example" -ForegroundColor Green
}
if (-Not (Test-Path "apps/api/.env")) {
    Copy-Item "apps/api/.env.example" "apps/api/.env"
    Write-Host "[+] Created apps/api/.env" -ForegroundColor Green
}
if (-Not (Test-Path "apps/web/.env.local")) {
    Copy-Item "apps/web/.env.example" "apps/web/.env.local"
    Write-Host "[+] Created apps/web/.env.local" -ForegroundColor Green
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " FaceSentry setup completed successfully! " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "To start the system:"
Write-Host " 1. API Server:     python scripts/dev_api.py" -ForegroundColor Yellow
Write-Host " 2. Agent Daemon:   python scripts/dev_agent.py --check" -ForegroundColor Yellow
Write-Host " 3. Web Dashboard:  npm --prefix apps/web run dev" -ForegroundColor Yellow
