<#
.SYNOPSIS
Installs FaceSentry Windows Agent into the current user's profile.

.DESCRIPTION
Copies the PyInstaller packaged executable and required models to %LOCALAPPDATA%\FaceSentry.
Idempotent and safe for upgrades. Does not delete biometric data.
#>

$ErrorActionPreference = "Stop"

$appDataDir = [System.Environment]::GetFolderPath('LocalApplicationData')
$installDir = Join-Path $appDataDir "FaceSentry"
$modelsDir = Join-Path $installDir "models"
$logsDir = Join-Path $installDir "logs"
$enrollmentDir = Join-Path $installDir "enrollment"

$sourceDir = (Get-Item $PSScriptRoot).Parent.FullName
$sourceExeDir = Join-Path $sourceDir "dist\FaceSentryAgent"
$sourceModels = Join-Path $sourceDir "data\models"

Write-Host "============================================="
Write-Host " FaceSentry Agent Installer"
Write-Host "============================================="
Write-Host "Target Directory: $installDir"

# 1. Create Directories
Write-Host "`n[1/4] Creating directories..."
$dirsToCreate = @($installDir, $modelsDir, $logsDir, $enrollmentDir)
foreach ($dir in $dirsToCreate) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "  -> Created: $dir"
    } else {
        Write-Host "  -> Exists: $dir"
    }
}

# 2. Check for Executable
Write-Host "`n[2/4] Copying agent application files..."
if (-not (Test-Path $sourceExeDir)) {
    Write-Host "  -> WARNING: Built application not found at $sourceExeDir"
    Write-Host "  -> You must run build_windows.ps1 first, or you are running from source."
} else {
    # If the process is currently running, we need to stop it before overwriting
    $runningProcs = Get-Process -Name "FaceSentryAgent" -ErrorAction SilentlyContinue
    if ($runningProcs) {
        Write-Host "  -> Stopping currently running FaceSentryAgent processes..."
        $runningProcs | Stop-Process -Force
        Start-Sleep -Milliseconds 500
    }

    # Copy the entire directory contents from the PyInstaller onedir output
    Copy-Item -Path "$sourceExeDir\*" -Destination $installDir -Recurse -Force
    Write-Host "  -> Application files installed successfully."
}

# 3. Copy Models
Write-Host "`n[3/4] Provisioning biometric models..."
if (-not (Test-Path $sourceModels)) {
    Write-Host "  -> ERROR: Source models directory not found at $sourceModels."
    Write-Host "INSTALLATION FAILED: Models are required."
    exit 1
}

$modelFiles = Get-ChildItem -Path $sourceModels -Filter "*.onnx"
if ($modelFiles.Count -eq 0) {
    Write-Host "  -> ERROR: No .onnx files found in $sourceModels."
    Write-Host "INSTALLATION FAILED: Models are required."
    exit 1
}

foreach ($file in $modelFiles) {
    $destFile = Join-Path $modelsDir $file.Name
    if (-not (Test-Path $destFile)) {
        Copy-Item -Path $file.FullName -Destination $destFile
        Write-Host "  -> Copied: $($file.Name)"
    } else {
        Write-Host "  -> Exists (Skipping): $($file.Name)"
    }
}

# 4. Check Enrollment Preservation
Write-Host "`n[4/4] Checking biometric data..."
$enrollmentFile = Join-Path $enrollmentDir "profile.enc"
if (Test-Path $enrollmentFile) {
    Write-Host "  -> Found existing encrypted biometric profile. Preserving data."
} else {
    Write-Host "  -> No existing biometric profile found. Enrollment required after installation."
}

Write-Host "`n============================================="
Write-Host " INSTALLATION SUCCESS"
Write-Host "============================================="
Write-Host "FaceSentry is installed at: $installDir"
Write-Host "Next steps:"
Write-Host " 1. Run 'scripts\check_installation.ps1' to verify."
Write-Host " 2. Run 'scripts\register_startup.ps1' to enable automatic startup."
