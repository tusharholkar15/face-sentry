# FaceSentry Deployment Architecture

This document describes the production deployment and packaging architecture for FaceSentry Windows Agents.

## 1. PyInstaller Packaging

The agent is compiled into a standalone directory using PyInstaller.

- **Entry Point**: `apps/agent/facesentry_agent/main.py`
- **Build Script**: `scripts/build_windows.ps1`
- **Output**: `dist/FaceSentryAgent`
- **Mode**: One-Dir (`--onedir`). This is chosen over `--onefile` to significantly improve startup time (no extraction overhead) and avoid potential antivirus false positives caused by temporary file extraction.

## 2. Directory Structure & Path Resolution

To support both source-based execution (development) and binary execution (production), FaceSentry uses a dynamic path resolution strategy (`packages/shared/constants.py -> get_base_dir()`).

**Production Paths (Default):**
All runtime data is stored in the user's local application data profile: `%LOCALAPPDATA%\FaceSentry`.
- Models: `%LOCALAPPDATA%\FaceSentry\models`
- Biometrics: `%LOCALAPPDATA%\FaceSentry\enrollment`
- Logs: `%LOCALAPPDATA%\FaceSentry\logs`
- DB: `%LOCALAPPDATA%\FaceSentry\facesentry.db`

**Development Paths (`FACESENTRY_DEV_MODE=1`):**
Paths fall back to the local repository `./data/` folder for seamless developer iteration.

## 3. Installation Flow (`install_windows.ps1`)

The installer is designed to be fully idempotent and run in the interactive user context.
It:
1. Creates the `%LOCALAPPDATA%\FaceSentry` directories.
2. Stops any running `FaceSentryAgent.exe` process gracefully.
3. Copies the built executable and external ONNX models to the AppData path.
4. Preserves any existing `profile.enc` (encrypted biometric data) across upgrades.

## 4. Automatic Startup (`register_startup.ps1`)

Automatic startup relies entirely on Windows Task Scheduler.
- **Trigger**: At logon of the current user.
- **Action**: Runs `%LOCALAPPDATA%\FaceSentry\FaceSentryAgent.exe`.
- **Privileges**: Runs with standard user privileges; Administrator access is **not** required.
- **Resilience**: Configured to restart up to 3 times on failure with a 1-minute interval.

## 5. Security & Uninstallation (`uninstall_windows.ps1`)

When uninstalling, the script guarantees that user-provided configuration and highly sensitive biometric profiles are **never** deleted silently. The user is prompted explicitly to authorize the destruction of their data folder.

## 6. Recovery Modes

The production executable supports three startup modes via CLI arguments:
- `--mode NORMAL`: Full system protection, real locking, and background telemetry.
- `--mode DIAGNOSTIC`: Immediately performs hardware checks, verifies model hashes and enrollment, prints a status report to standard output, and exits `0`. Used by `smoke_test_windows.ps1`.
- `--mode DRY_RUN`: Runs the full loop but mocks the `user32.LockWorkStation` call for safety.
