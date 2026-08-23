# FaceSentry Pre-Release Checklist

This checklist must be fully verified by the operator before the agent is deemed `RELEASE_READY`.

## 1. Build and Provisioning
- [x] PyInstaller executable builds successfully without errors (`build_windows.ps1`).
- [x] ONNX model files are successfully copied into `dist\FaceSentryAgent\models`.
- [x] 128-D SFace model verified and integrated.

## 2. Installation and Paths
- [x] `install_windows.ps1` runs safely and creates `%LOCALAPPDATA%\FaceSentry`.
- [x] Models and executables are copied to the correct AppData destinations.
- [x] Running the installer multiple times is fully idempotent.

## 3. Configuration & Startup
- [x] `register_startup.ps1` creates the Windows Task Scheduler entry successfully.
- [x] `FaceSentryAgent.exe` starts automatically upon Windows Login.
- [x] `smoke_test_windows.ps1` correctly executes `DIAGNOSTIC` mode and passes (0.96s cold startup).

## 4. Enrollment & Backend
- [x] Web dashboard connects successfully to the agent via WebSocket.
- [ ] Genuine biometric enrollment captured via Dashboard / Wizard (synthetic templates strictly forbidden).
- [ ] `default_user.dat` created and encrypted with Windows DPAPI in `%LOCALAPPDATA%\FaceSentry\enrollment`.
- [x] Template integrity gate (`validate_template_embedding`) rejects constant/synthetic/zero-norm vectors.
- [x] PIN fallback registration succeeds with Argon2id hashing.

## 5. End-to-End Operation (Hardware Tested)
- [ ] **Authentication & Absence Lock**: Authorized user leaves frame, `ABSENCE_TIMEOUT` fires, Windows locks.
  - Test command: `powershell -ExecutionPolicy Bypass -File scripts\e2e_hardware_test.ps1 -Mode absence-lock -RealLock`
  - *Automated Pipeline*: 🟢 Verified (`ABSENCE_STARTED` -> `ABSENCE_TIMEOUT` -> `LOCK_REQUESTED` -> `POST_LOCK`)
  - *Physical Verification*: Awaiting final operator physical session lock observation.
- [x] **Stranger / Unknown-Face Lock**: Unknown face appears, `STRANGER_TIMEOUT` fires, Windows `LockWorkStation` dispatches.
  - Tested via: `powershell -ExecutionPolicy Bypass -File scripts\e2e_hardware_test.ps1 -Mode unknown-face-lock -RealLock`
- [x] **Browser Protection**: Session cookies are cleared for Chrome/Edge upon lock. Passwords and bookmarks are strictly untouched.
- [x] **PIN Recovery**: Safe simulation of PIN fallback interactions on the dashboard.

## 6. Uninstallation & Data Privacy
- [x] `uninstall_windows.ps1` unregisters the Task Scheduler entry successfully.
- [x] `uninstall_windows.ps1` prompts explicitly before deleting `%LOCALAPPDATA%\FaceSentry`.
- [x] Upgrading the agent preserves `default_user.dat` and `facesentry.db`.

## 7. Audits & Performance
- [x] `SECURITY_AUDIT.md` completed. Zero CRITICAL/HIGH findings exist.
- [x] `PRIVACY_AUDIT.md` completed. Verified zero external transmission, privacy-safe diagnostics, and no raw image storage.
- [x] `PERFORMANCE.md` updated with measured hardware benchmarks (YuNet: 9.78ms, SFace: 7.95ms).
- [x] All 134 automated `pytest` suites pass (100%).
