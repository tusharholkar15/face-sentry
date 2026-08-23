# FaceSentry Windows Installation Guide

This guide describes how to build, install, and configure the FaceSentry agent on a Windows workstation.

## 1. Build the Application

FaceSentry is built into a standalone executable using PyInstaller.

1. Open PowerShell and navigate to the repository root.
2. Ensure you have activated your Python virtual environment and installed dependencies.
3. Run the build script:
   ```powershell
   .\scripts\build_windows.ps1
   ```
4. Wait for the `BUILD SUCCESS` message. The packaged application is now in `dist\FaceSentryAgent`.

## 2. Install the Agent

The installer safely registers FaceSentry into your local AppData without requiring administrator privileges.

1. Run the installation script:
   ```powershell
   .\scripts\install_windows.ps1
   ```
2. The agent is installed to `%LOCALAPPDATA%\FaceSentry`.

## 3. Provision Model Files

The ONNX models are large and may be tracked outside of source control.
If the build script did not copy them automatically, manually ensure these two files exist:

- `%LOCALAPPDATA%\FaceSentry\models\face_detection_yunet_2023mar.onnx`
- `%LOCALAPPDATA%\FaceSentry\models\face_recognition_sface_2021dec.onnx`

## 4. Run Diagnostics

Before relying on FaceSentry for security, verify the installation and hardware.

```powershell
.\scripts\check_installation.ps1
.\scripts\smoke_test_windows.ps1
```

If the smoke test reports `SMOKE TEST PASSED (Exit Code: 0)`, the models and configuration are correct.

## 5. Enroll User & Configure Settings

Start the backend and Next.js frontend in development mode to configure the system:

1. Enroll your biometric profile via the Wizard in the web dashboard.
2. **Configure PIN**: Set an emergency recovery PIN.
3. **Browser Protection**: Go to settings and configure browser protection mode.
4. **Enable Real Lock**: Verify the Dashboard settings to ensure lock enforcement is enabled.

## 6. Register Startup Task

To enable FaceSentry to start automatically whenever you log into Windows:

```powershell
.\scripts\register_startup.ps1
```

This creates a Windows Task Scheduler task named `FaceSentry Agent`.
You can restart your machine to verify the agent boots automatically.

## Uninstalling FaceSentry

To completely remove FaceSentry from your system:

```powershell
.\scripts\uninstall_windows.ps1
```

You will be explicitly prompted if you want to permanently delete your encrypted biometric enrollment profile and configuration.
