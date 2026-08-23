# FaceSentry Windows Workstation Lock Architecture & Integration Guide

**Document:** `docs/WINDOWS_LOCK.md`  
**Target Platform:** Windows 10 / Windows 11 (x64)  
**Native API:** `user32.dll!LockWorkStation`  
**Security Boundary:** OS Session Locking (No Administrator Privileges Required)  

---

## 1. Architectural Overview & Lock Pipeline

The FaceSentry Workstation Lock Manager is the terminal OS actuator of the security pipeline. It is strictly decoupled from biometric recognition and temporal liveness algorithms, receiving directives exclusively from the authoritative **Authentication Decision Engine**.

```
+-----------------------------------------------------------------------------------------------+
|                               FACESENTRY LOCK DISPATCH PIPELINE                               |
|                                                                                               |
|  [ RecognitionResult ] + [ LivenessResult ] + [ Temporal Presence Counters ]                  |
|                                      │                                                        |
|                                      ▼                                                        |
|                       [ Authentication Decision Engine ]                                      |
|                       (Authoritative Security Policy)                                         |
|                                      │                                                        |
|                                      ▼ (lock_requested == True)                               |
|                         [ Lock Dispatch Request ]                                             |
|                         - Reason Whitelist Validation                                         |
|                         - Cooldown & Debounce Enforcement                                     |
|                                      │                                                        |
|                                      ▼                                                        |
|                        [ WorkstationLockManager ]                                             |
|                                      │                                                        |
|                     ┌────────────────┴────────────────┐                                       |
|                     ▼                                 ▼                                       |
|            [ Mode: DRY_RUN ]                 [ Mode: REAL_LOCK ]                              |
|            - Emit LOCK_SIMULATED             - Bind user32.dll                                |
|            - Log audit event                 - LockWorkStation()                              |
|            - Zero screen impact              - Emit LOCK_SUCCEEDED / LOCK_FAILED              |
+-----------------------------------------------------------------------------------------------+
```

---

## 2. Why `LockWorkStation()`?

FaceSentry exclusively invokes the official Windows user32 native API:
```c
BOOL LockWorkStation(void);
```

### Key Advantages:
1. **Zero Elevated Privileges:** `LockWorkStation()` operates under standard user security context. Administrator/UAC elevation is **not** required.
2. **Security Integrity:** Shelling out to `rundll32.exe user32.dll,LockWorkStation` or executing child PowerShell processes is vulnerable to command injection and process hijacking. Direct `ctypes` binding executes directly in-process.
3. **Instant OS Transition:** Instantly drops the active desktop session to the Windows Secure Attention Sequence (SAS) logon/lock screen.

---

## 3. Safety Mechanisms & Sandbox Protection

### 3.1 Dry-Run Simulation (Default)
By default, FaceSentry starts in **DRY-RUN** simulation mode (`ENABLE_REAL_WINDOWS_LOCK=false`).
- Policy timeout events trigger `LOCK_SIMULATED` audit logs.
- The physical screen is **never** locked.
- Prevents accidental developer lockouts during development, automated unit testing, or CI execution.

### 3.2 Real Lock Activation
To enable actual physical workstation locking in production:
```ini
# In .env or environment configuration:
FACESENTRY_ENABLE_REAL_WINDOWS_LOCK=true
FACESENTRY_DRY_RUN=false
```
Or via CLI argument:
```powershell
python -m apps.agent.main --real-lock
```

### 3.3 Cooldown Debounce & Single-Dispatch Guarantee
1. **Single-Dispatch:** When a policy timeout occurs, `DecisionResult.lock_requested` is set to `True` on **exactly one frame**. Subsequent frames maintain `LOCKED_ACTION_DISPATCHED` with `lock_requested=False`.
2. **Hardware Cooldown:** `WorkstationLockManager` enforces a configurable cooldown window (`LOCK_DISPATCH_COOLDOWN_SECONDS=5.0`) preventing API hammer or rapid toggle loops.

---

## 4. Whitelisted Lock Reasons

To prevent arbitrary execution triggers, the lock manager strictly validates lock reasons against a whitelist:

| Reason Code | Trigger Description |
| :--- | :--- |
| `ABSENCE_TIMEOUT` | No human face detected for $> \text{ABSENCE\_TIMEOUT}$ (default 10.0s) |
| `UNKNOWN_FACE_TIMEOUT` | Unregistered / stranger face detected for $> \text{UNKNOWN\_FACE\_TIMEOUT}$ (default 3.0s) |
| `SPOOF_TIMEOUT` | Matching face detected but temporal liveness unverified for $> \text{SPOOF\_LOCK\_TIMEOUT}$ (default 3.0s) |
| `CAMERA_UNAVAILABLE` | Camera hardware disconnected or frame capture failure exceeded safety timeout |
| `MANUAL_LOCK` | User or administrative manual lock action dispatched from UI or CLI |
| `POLICY_TRIGGER` | Custom combined security rule triggered |

---

## 5. Audit Events & Telemetry

The Lock Manager emits structured, privacy-safe transition events:
- `LOCK_REQUESTED`: Lock evaluation initiated with reason and mode.
- `LOCK_SIMULATED`: Simulation completed in DRY-RUN mode.
- `LOCK_DISPATCHED`: Native Win32 API invocation initiated.
- `LOCK_SUCCEEDED`: Windows session successfully locked.
- `LOCK_FAILED`: Win32 API returned error or platform unsupported.

> [!NOTE]
> **Privacy Guarantee:** Lock events and logs never contain facial coordinates, embeddings, biometric vectors, crops, or PIN data.

---

## 6. Manual Hardware Verification

An interactive PowerShell test script is provided for safe, intentional on-device verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test_real_lock.ps1
```

1. Warns the user and requires typing `YES` to confirm.
2. Invokes `WorkstationLockManager` with `enable_real_windows_lock=True`.
3. Verifies that the screen locks cleanly and logs back in via Windows PIN/password.

---

## 7. Known Windows Platform Considerations

1. **Remote Desktop (RDP):** When running inside an active RDP session, `LockWorkStation()` disconnects or locks the remote session according to host RDP policy.
2. **Session Zero / Service Mode:** Windows GUI sessions cannot be locked from Session 0 Windows Services. FaceSentry Agent must execute within the logged-in user desktop session.
