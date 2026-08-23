# FaceSentry Security Audit

## Executive Summary
This document summarizes the security boundaries, data protection mechanisms, and architectural risk mitigations implemented in FaceSentry.

## 1. Subsystem Reviews

### 1.1 Biometric Storage
- **Finding:** No raw image storage.
- **Risk:** High (if breached).
- **Mitigation:** The system strictly extracts the 128-float embedding vector. Raw frames are immediately discarded. The `profile.enc` file is encrypted using Windows DPAPI (Data Protection API) linked directly to the local Windows user context. 
- **Status:** PASS (INFO)

### 1.2 Emergency PIN Fallback
- **Finding:** PIN hashing mechanism.
- **Risk:** High.
- **Mitigation:** Uses Argon2id via `passlib`. Plaintext PINs are strictly wiped from memory immediately after comparison. The system prevents brute forcing by enforcing a 5-minute lockout after 5 failed attempts.
- **Status:** PASS (INFO)

### 1.3 Windows Lock Integration
- **Finding:** Execution of Windows API.
- **Risk:** Medium.
- **Mitigation:** `LockWorkStation` in `user32.dll` is explicitly loaded. No external binaries or shell executions (`cmd.exe /c`, `rundll32.exe`) are used to trigger the lock, removing the threat of arbitrary argument injection.
- **Status:** PASS (INFO)

### 1.4 Browser Protection
- **Finding:** SQLite file modification.
- **Risk:** High (Data Loss Risk).
- **Mitigation:** FaceSentry only executes safe deletion commands limited exclusively to session cookies (`WHERE is_persistent = 0`). It refuses to touch Firefox `cookies.sqlite` due to internal schema volatility, emitting a `SESSION_CLEANUP_UNSUPPORTED` event instead.
- **Status:** PASS (INFO)

### 1.5 Telemetry and API (WebSocket)
- **Finding:** Real-time data streaming over HTTP/WS.
- **Risk:** Critical (Remote exposure).
- **Mitigation:** The FastAPI server binds strictly to `127.0.0.1:8000`. It is fundamentally inaccessible from external network interfaces. The payload structures (`EventSchema`) explicitly omit the `vector` or `face_crop` fields.
- **Status:** PASS (INFO)

### 1.6 File Paths and Configuration
- **Finding:** Application configuration storage.
- **Risk:** Low (Privilege Escalation).
- **Mitigation:** PyInstaller executable and data stores live in `%LOCALAPPDATA%\FaceSentry`, restricted by default to the current Windows user. Task Scheduler is executed without `HighestPrivileges`, preventing any arbitrary agent code execution from gaining Administrator rights.
- **Status:** PASS (INFO)

## 2. Identified Vulnerabilities

*As of Phase 11, there are zero known CRITICAL or HIGH vulnerabilities within the intended scope.*

### 2.1 Known Limitations (MEDIUM / INFO)
- **Physical Spoofing (Presentation Attacks):** While `LivenessEngine` enforces blink and head-movement checks, a highly determined attacker with a 3D animated deepfake or pre-recorded video mask on an iPad could potentially bypass the threshold. FaceSentry is not an enterprise-grade 3D-depth scanner (like Windows Hello IR). 
- **Volatile Memory:** While embeddings are encrypted at rest, they remain in plaintext inside the Python process memory (`FaceSentryAgent.exe`) during the operational loop for rapid cosine similarity matching. Memory dumping tools could theoretically extract them if the attacker already has Local Admin access.

## 3. Conclusion
FaceSentry's architecture provides a strong defense-in-depth posture suitable for personal workstation protection against casual unauthorized physical access.
