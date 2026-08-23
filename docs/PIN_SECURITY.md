# FaceSentry Secure Local PIN Fallback Specification

**Document:** `docs/PIN_SECURITY.md`  
**Endpoint:** `http://127.0.0.1:8000/api/v1/pin`  
**Algorithm:** `PBKDF2-HMAC-SHA256` ($100{,}000$ iterations, $32\text{-byte}$ CSPRNG salt)  
**Verification:** Constant-Time `hmac.compare_digest`  
**Security Baseline:** Zero Plaintext Storage, Brute-Force Rate Limiting, Temporary Recovery Only  

---

## 1. PIN Purpose & Operational Model

The emergency PIN provides a localized fallback for adverse environmental or hardware conditions:
- Webcam hardware disconnection or sensor fault
- Extreme low light / high glare causing temporary false rejections
- Physical camera obstruction or lens smudge

> [!IMPORTANT]
> The emergency PIN **never** permanently disables FaceSentry.
> Authenticating via PIN grants a temporary **60-second recovery window** (`RECOVERY_PENDING`). Once this window elapses, the system immediately returns to normal continuous biometric presence monitoring (`BIOMETRIC_REAUTH_REQUIRED`).

---

## 2. Cryptographic Architecture

```
+-----------------------------------------------------------------------------------------------+
|                            FACESENTRY LOCAL PIN CRYPTOGRAPHIC MODEL                           |
|                                                                                               |
|  [ User Input PIN ] ──► (Masked Input, Cleared from Memory after Hash)                        |
|                               │                                                               |
|                               ▼                                                               |
|  [ Key Derivation ] ──► PBKDF2-HMAC-SHA256 (Salt: secrets.token_bytes(32), 100,000 iters)     |
|                               │                                                               |
|                               ▼                                                               |
|  [ Verification ]   ──► Constant-time `hmac.compare_digest(computed_hash, stored_hash)`      |
|                               │                                                               |
|            ┌──────────────────┴──────────────────┐                                            |
|            ▼                                     ▼                                            |
|     [ MATCH: True ]                       [ MATCH: False ]                                    |
|     - Reset failed counter                - Increment failed attempt count                    |
|     - Grant 60s temporary recovery        - If attempts >= 5: Trigger 60s Lockout             |
|     - Emit `PIN_AUTHENTICATED`            - Emit `PIN_FAILED` / `PIN_LOCKOUT_STARTED`         |
+-----------------------------------------------------------------------------------------------+
```

---

## 3. Rate Limiting & Lockout Policy

| Policy Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `PIN_MIN_LENGTH` | `4` | Minimum numeric characters allowed |
| `PIN_MAX_LENGTH` | `12` | Maximum numeric characters allowed |
| `PIN_MAX_ATTEMPTS` | `5` | Failed attempts permitted before lockout |
| `PIN_LOCKOUT_DURATION_SECONDS` | `60.0` | Cooldown duration during lockout |
| `PIN_RECOVERY_DURATION_SECONDS` | `60.0` | Temporary emergency recovery window |

### Lockout Behavior
- While locked out, **all** verification attempts are rejected immediately, even if the correct PIN is provided.
- Lockout automatically expires after 60 seconds of inactivity.

---

## 4. API Endpoints

All endpoints are strictly bound to localhost (`127.0.0.1`, `localhost`, `::1`):

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/pin/status` | Returns safe status (`is_configured`, `attempts_remaining`, `is_locked`, `in_recovery`). |
| `POST` | `/api/v1/pin/setup` | Configures initial PIN credentials. |
| `POST` | `/api/v1/pin/change` | Updates PIN after authenticating current credentials. |
| `POST` | `/api/v1/pin/verify` | Authenticates candidate PIN and grants temporary recovery window. |

---

## 5. Security & Privacy Safeguards

1. **Zero Plaintext Storage:** Plaintext PINs are never stored on disk or in browser storage (`localStorage` / `sessionStorage`).
2. **Zero Secret Leakage:** Salts and hashes are never exposed in API responses or WebSocket messages.
3. **No Plaintext Logging:** Loggers strip and omit all candidate PINs, hashes, and raw passwords.
4. **Timing Attack Protection:** Hash comparison is executed strictly via constant-time `hmac.compare_digest`.
