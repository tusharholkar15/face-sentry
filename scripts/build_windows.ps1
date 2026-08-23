<#
.SYNOPSIS
Builds the FaceSentry Agent Windows executable using PyInstaller.

.DESCRIPTION
Packages apps/agent/facesentry_agent/main.py into a standalone executable in dist/.
Copies required ONNX models into the dist directory for portable deployment.
#>

$ErrorActionPreference = "Stop"

$workspaceRoot = (Get-Item $PSScriptRoot).Parent.FullName
$mainScript = Join-Path $workspaceRoot "apps\agent\facesentry_agent\main.py"
$distDir = Join-Path $workspaceRoot "dist"
$workDir = Join-Path $workspaceRoot "build"
$venvPython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"

Write-Host "============================================="
Write-Host " FaceSentry PyInstaller Build"
Write-Host "============================================="

if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: Python virtual environment not found at $venvPython."
    Write-Host "Please ensure you have run 'python -m venv .venv' and installed requirements."
    exit 1
}

Write-Host "Ensuring pyinstaller is installed..."
& $venvPython -m pip install pyinstaller --quiet

Write-Host "`nBuilding Executable..."
Set-Location $workspaceRoot

# Run PyInstaller
# -y: replace output directory without asking
# --clean: clean PyInstaller cache
# --onedir: create a one-folder bundle (better for startup speed than onefile)
# --name: the output name
# --noupx: avoid UPX compression which can trigger false positive AV detections
& $venvPython -m PyInstaller -y --clean --onedir --name "FaceSentryAgent" --noupx $mainScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller build failed."
    exit $LASTEXITCODE
}

Write-Host "`nCopying default models into dist directory..."
$sourceModels = Join-Path $workspaceRoot "data\models"
$distModels = Join-Path $distDir "FaceSentryAgent\data\models"

if (-not (Test-Path $distModels)) {
    New-Item -ItemType Directory -Path $distModels | Out-Null
}
Copy-Item -Path "$sourceModels\*" -Destination $distModels -Recurse -Force

Write-Host "`n============================================="
Write-Host " BUILD SUCCESS"
Write-Host "============================================="
Write-Host "Executable is available at: dist\FaceSentryAgent\FaceSentryAgent.exe"
