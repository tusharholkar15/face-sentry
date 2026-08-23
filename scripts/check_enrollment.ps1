# Diagnostic script to check biometric profile encryption and contents.

$appDataDir = [System.Environment]::GetFolderPath('LocalApplicationData')
$installDir = Join-Path $appDataDir "FaceSentry"
$enrollmentDir = Join-Path $installDir "enrollment"
$profilePath = Join-Path $enrollmentDir "default_user.dat"

Write-Host "============================================="
Write-Host " FaceSentry Biometric Enrollment Diagnostics"
Write-Host "============================================="
Write-Host "Enrollment directory: $enrollmentDir"
Write-Host "Profile file: $profilePath"

$profileExists = Test-Path $profilePath
Write-Host "Profile exists: $profileExists"

if ($profileExists) {
    # Call python to safely load and validate the profile without leaking embedding values
    $pythonCmd = @"
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(r'$PSScriptRoot', '..')))

from apps.agent.facesentry_agent.biometric_storage import BiometricStorage, validate_template_embedding

try:
    # Use production AppData enrollment dir
    storage = BiometricStorage(r'$enrollmentDir')
    profile = storage.load_profile('default_user')
    if profile is None:
        print("READABLE:False|VALID:False|REASON:Loaded profile is None.")
        sys.exit(0)
    
    is_valid, reason = validate_template_embedding(profile.reference_embedding, expected_dim=profile.embedding_dim)
    print(f"READABLE:True|VALID:{is_valid}|REASON:{reason}|DIM:{profile.embedding_dim}|SAMPLES:{profile.sample_count}")
except Exception as e:
    print(f"READABLE:False|VALID:False|REASON:Decryption failed ({e})")
"@

    # Run Python code inline
    $pythonExe = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = "python"
    }

    $res = & $pythonExe -c $pythonCmd
    if ($res -match "READABLE:(True|False)\|VALID:(True|False)\|REASON:([^\|]+)(?:\|DIM:(\d+)\|SAMPLES:(\d+))?") {
        $readable = $Matches[1]
        $valid = $Matches[2]
        $reason = $Matches[3]
        $dim = $Matches[4]
        $samples = $Matches[5]

        Write-Host "Profile readable: $readable"
        Write-Host "Profile valid: $valid"
        if ($readable -eq "True") {
            Write-Host "Embedding dimension: $dim"
            Write-Host "Profile sample count: $samples"
        }
    } else {
        Write-Host "Profile readable: False"
        Write-Host "Profile valid: False (Python execution failed: $res)"
    }
} else {
    Write-Host "Profile readable: False"
    Write-Host "Profile valid: False"
}
Write-Host "============================================="
