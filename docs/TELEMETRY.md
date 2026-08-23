# FaceSentry Real-Time Telemetry & WebSocket Specification

**Document:** `docs/TELEMETRY.md`  
**Endpoint:** `ws://127.0.0.1:8000/api/v1/telemetry/ws`  
**Network Scope:** Localhost-Only (`127.0.0.1`, `localhost`, `::1`)  
**Security Baseline:** Zero Biometric Data in Flight  

---

## 1. Architectural Pipeline

```
+-----------------------------------------------------------------------------------------------+
|                             FACESENTRY REAL-TIME TELEMETRY STREAM                             |
|                                                                                               |
|  [ Windows Agent Engine ]                                                                     |
|  - Detection & Recognition Results                                                            |
|  - Liveness Verification & Confidences                                                        |
|  - Decision Engine States & Presence Timers                                                   |
|         │                                                                                     |
|         ▼                                                                                     |
|  [ AgentTelemetryPublisher ] ──► (Throttled to Max 5 Hz, State Deduplication)                |
|         │                                                                                     |
|         ▼ HTTP POST /api/v1/telemetry/publish                                                 |
|  [ FastAPI In-Process State Broker ]                                                          |
|         │                                                                                     |
|         ▼ WebSocket Broadcast (ws://127.0.0.1:8000/api/v1/telemetry/ws)                       |
|  [ Next.js Web Dashboard HUD ]                                                                |
|  - `useTelemetry` Hook with Exponential Reconnect                                             |
|  - Live Protection & Liveness Badges                                                          |
|  - Real-Time Countdown Progress Bars                                                          |
|  - Merged Security Audit Event Feed                                                           |
+-----------------------------------------------------------------------------------------------+
```

---

## 2. Telemetry Schemas & Privacy Boundaries

### 2.1 Privacy Guarantees
To prevent biometric data leakage, FaceSentry strictly guarantees that the telemetry stream **never** contains:
- Raw video frames or image buffers
- Facial crops or aligned face patches
- Biometric embedding vectors ($128\text{-D}$ floats)
- DPAPI cryptographic templates
- Raw 5-point landmark coordinates
- Windows PINs or authentication secrets

Only minimal non-biometric visualization metadata (`bounding_box: [x, y, w, h]`) and high-level status indicators are transmitted.

### 2.2 Operational Snapshot Payload (`SNAPSHOT`)
```json
{
  "type": "SNAPSHOT",
  "timestamp": 1724285000.123,
  "schema_version": "1.0",
  "payload": {
    "timestamp": 1724285000.123,
    "agent_status": "RUNNING",
    "camera_status": "CONNECTED",
    "authentication_state": "AUTHENTICATED",
    "recognition_similarity": 0.892,
    "liveness_state": "VERIFIED",
    "liveness_verified": true,
    "liveness_confidence": 0.965,
    "face_detected": true,
    "face_count": 1,
    "absence_duration": 0.0,
    "stranger_duration": 0.0,
    "spoof_duration": 0.0,
    "decision_state": "AUTHENTICATED_PRESENT",
    "lock_requested": false,
    "last_security_event": {
      "event_type": "FACE_AUTHENTICATED",
      "reason": "Authorized user recognized and liveness verified",
      "timestamp": 1724285000.0
    },
    "system_uptime": 342.5,
    "bounding_box": [120, 95, 180, 220]
  }
}
```

### 2.3 Immediate Transition Security Event (`SECURITY_EVENT`)
```json
{
  "type": "SECURITY_EVENT",
  "timestamp": 1724285010.55,
  "schema_version": "1.0",
  "payload": {
    "event_type": "ABSENCE_STARTED",
    "reason": "No face detected in video stream",
    "timestamp": 1724285010.55,
    "details": {}
  }
}
```

---

## 3. Rate Limiting & Deduplication

1. **Max Rate Limiting:** Status snapshots are throttled to a maximum of **5 updates per second** ($200\text{ms}$ min interval).
2. **State Deduplication:** If the agent state remains identical across consecutive frames, redundant network broadcasts are suppressed until a state change occurs or $1.0\text{s}$ has elapsed (heartbeat sync).
3. **Immediate Event Dispatch:** Security transition events (e.g. `LOCK_REQUESTED`, `ABSENCE_STARTED`, `SPOOF_ALERT`) bypass rate-limiting and are broadcast immediately.

---

## 4. Connection Lifecycle & Reconnect Policy

```
[ DISCONNECTED ] ──► [ CONNECTING ] ──► [ CONNECTED ]
                            │                  │
                            │ (Error/Close)    │ (No msg > 3.5s)
                            ▼                  ▼
                    [ RECONNECTING ]    [ STALE DATA / AGENT OFFLINE ]
                 (Exp Backoff: 1s-10s)
```

- **Heartbeat:** Dashboard client sends `{"type": "PING"}` every $2.0\text{s}$; API replies with `{"type": "PONG"}`.
- **Staleness Detection:** If no message is received for $> 3.5\text{s}$, the dashboard marks telemetry as `STALE DATA` and flags `AGENT_OFFLINE`.
- **Exponential Backoff:** If disconnected, client retries at $1\text{s}, 2\text{s}, 4\text{s}, 8\text{s}$, capped at $10\text{s}$.
