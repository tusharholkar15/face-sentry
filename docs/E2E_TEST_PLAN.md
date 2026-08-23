# FaceSentry End-to-End Test Plan

This document outlines the manual verification scenarios required to certify a FaceSentry agent release on real Windows hardware.

**IMPORTANT SAFETY RULE:**
Never automatically execute the real workstation-lock E2E tests in a CI/CD pipeline. The human operator must explicitly start real-lock testing using the appropriate test harness mode and the `-RealLock` flag.

For simulated lock testing, omit `-RealLock`.

```powershell
# Simulate Absence Lock
powershell -ExecutionPolicy Bypass -File scripts\e2e_hardware_test.ps1 -Mode absence-lock

# Actual Windows Absence Lock
powershell -ExecutionPolicy Bypass -File scripts\e2e_hardware_test.ps1 -Mode absence-lock -RealLock

# Simulate Unknown Face Lock
powershell -ExecutionPolicy Bypass -File scripts\e2e_hardware_test.ps1 -Mode unknown-face-lock

# Actual Windows Unknown Face Lock
powershell -ExecutionPolicy Bypass -File scripts\e2e_hardware_test.ps1 -Mode unknown-face-lock -RealLock

# PIN testing (Safe simulation)
powershell -ExecutionPolicy Bypass -File scripts\e2e_hardware_test.ps1 -Mode pin
```

---

## A. Startup

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| A1 | Windows Login | FaceSentry agent starts automatically via Task Scheduler. | [ ] |
| A2 | Task Scheduler Verification | Agent process `FaceSentryAgent.exe` is running under the interactive user session. | [ ] |
| A3 | Dashboard Connectivity | Web Dashboard successfully connects to WebSocket at `127.0.0.1:8000`. | [ ] |
| A4 | Camera Initialization | Camera indicator light turns on; live feed (if preview enabled) works. | [ ] |

---

## B. Enrollment

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| B1 | Standard Enrollment | User creates profile; 10 samples collected; `profile.enc` created. | [ ] |
| B2 | Poor Lighting | System rejects frames with low confidence scores. | [ ] |
| B3 | No Face | System waits indefinitely without progressing enrollment. | [ ] |
| B4 | Multiple Faces | Enrollment pauses, warning the user about multiple faces. | [ ] |
| B5 | Liveness Challenge | Enrollment correctly tracks required eye blinks/head movements. | [ ] |

---

## C. Normal Authentication

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| C1 | Authorized Face | Identity matched (Similarity > Threshold); Liveness confirmed. | [ ] |
| C2 | Protection Maintained | System transitions to `AUTHENTICATED_PRESENT` and does not lock. | [ ] |

---

## D. User Absence

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| D1 | User Leaves | Camera detects no face; transitions to `ABSENCE_COUNTDOWN`. | [ ] |
| D2 | User Returns Quickly | User returns before timeout; timer cancels, state reverts. | [ ] |

---

## E. Actual Lock

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| E1 | Timeout Reached | User remains absent beyond `ABSENCE_TIMEOUT_SECONDS`. | [ ] |
| E2 | Lock Dispatch | `WorkstationLockManager` calls `user32.LockWorkStation` exactly once. | [ ] |
| E3 | Telemetry | Dashboard records `WORKSTATION_LOCKED` event. | [ ] |

---

## F. Unknown Face

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| F1 | Stranger Appears | Unrecognized face appears; transitions to `STRANGER_COUNTDOWN`. | [ ] |
| F2 | Stranger Leaves Quickly | Stranger leaves before timeout; timer cancels. | [ ] |

---

## G. Persistent Unknown Face

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| G1 | Stranger Remains | Stranger remains beyond `UNKNOWN_FACE_TIMEOUT_SECONDS`. | [ ] |
| G2 | Security Lock | Windows locks immediately; `UNAUTHORIZED_USER` event recorded. | [ ] |

---

## H. Spoof / Liveness Failure

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| H1 | Presentation Attack | High-res photo held up to camera. | [ ] |
| H2 | Spoof Lock | Liveness fails; system locks according to `SPOOF_LOCK_TIMEOUT_SECONDS`. | [ ] |

---

## I. PIN Recovery

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| I1 | Incorrect PIN | Enter wrong PIN; failure logged, counter increments. | [ ] |
| I2 | Lockout Triggered | Enter wrong PIN >= 5 times; 5-minute lockout enforced. | [ ] |
| I3 | Successful Recovery | Enter correct PIN; 60s temporary recovery granted. | [ ] |
| I4 | Recovery Expiration | After 60s, system reverts to `BIOMETRIC_REAUTH_REQUIRED`. | [ ] |

---

## J. Browser Protection

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| J1 | Disabled Mode | Browsers remain open upon workstation lock. | [ ] |
| J2 | Close-Browser Mode | Chromium/Firefox close gracefully upon workstation lock. | [ ] |
| J3 | Session Cleanup (Chrome) | Session cookies deleted; Passwords/Bookmarks strictly preserved. | [ ] |
| J4 | Firefox Bypass | Firefox closes, but returns `SESSION_CLEANUP_UNSUPPORTED` safely. | [ ] |

---

## K. Camera Failure

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| K1 | Camera Disconnect | Agent remains alive; Dashboard shows camera unavailable. | [ ] |
| K2 | Camera Reconnect | Agent recovers video feed automatically without restart. | [ ] |

---

## L. API / Telemetry Failure

| ID | Scenario | Expected Outcome | Pass/Fail |
| :--- | :--- | :--- | :--- |
| L1 | API Stop | Dashboard stops; Agent background protection loop continues. | [ ] |
| L2 | API Reconnect | Dashboard refreshes and resumes real-time event streaming. | [ ] |
