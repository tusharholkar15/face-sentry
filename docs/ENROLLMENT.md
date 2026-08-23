# FaceSentry Biometric Enrollment Specification

**Document:** `docs/ENROLLMENT.md`  
**Endpoint:** `http://127.0.0.1:8000/api/v1/enrollment`  
**Storage Backend:** Windows DPAPI (`CryptProtectData`)  
**Security Baseline:** 100% On-Device, Zero Image Storage, Liveness Gated  

---

## 1. Enrollment Lifecycle Architecture

```
+-----------------------------------------------------------------------------------------------+
|                             FACESENTRY BIOMETRIC ENROLLMENT FLOW                              |
|                                                                                               |
|  [ Web Wizard (apps/web) ]                                                                    |
|  - Multi-step guided UI (Steps 1 to 9)                                                        |
|  - Real-time guidance badges & progress bar                                                   |
|         │                                                                                     |
|         ▼ POST /api/v1/enrollment/start                                                       |
|  [ FastAPI Enrollment Router ]                                                                |
|         │                                                                                     |
|         ▼ Internal Dispatch                                                                   |
|  [ EnrollmentCoordinator & QualityGate ]                                                      |
|  - Ingests camera frames at runtime                                                           |
|  - Checks blur, illumination, pose, and face size                                             |
|  - Extracts 128-D unit normalized embeddings (SFace)                                          |
|  - Gated by temporal liveness verification (natural blink/head turn)                          |
|         │                                                                                     |
|         ▼ Finalize                                                                            |
|  [ BiometricStorage (Windows DPAPI) ]                                                         |
|  - Computes normalized centroid reference vector                                              |
|  - Encrypts via `CryptProtectData` to `data/enrollment/<user>.dat`                            |
|  - Purges all candidate frames and vector buffers from volatile RAM                          |
+-----------------------------------------------------------------------------------------------+
```

---

## 2. API Endpoints

All endpoints are strictly bound to localhost (`127.0.0.1`):

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/enrollment/start` | Initiates multi-sample collection session (`user_id`, `target_samples`). |
| `GET` | `/api/v1/enrollment/status` | Returns non-biometric progress, quality, guidance, and liveness flags. |
| `POST` | `/api/v1/enrollment/cancel` | Safely cancels session and immediately purges in-memory vector cache. |
| `POST` | `/api/v1/enrollment/finalize` | Verifies sample count and liveness confirmation before DPAPI storage. |
| `POST` | `/api/v1/enrollment/update_progress` | Internal agent-to-broker sync updating live WebSocket subscribers. |

---

## 3. Privacy & Biometric Guarantees

1. **Zero Frame Persistence:** Raw camera frames, cropped face patches, and facial landmark coordinates are **never written to disk**.
2. **Volatile RAM Purge:** Temporary candidate embeddings are cleared from memory immediately upon `finalize` or `cancel`.
3. **Encrypted Centroid Template:** Only the mathematical normalized centroid vector ($128\text{-D}$ float array) is encrypted using the Windows user account master key (`CryptProtectData`).
4. **Zero Biometric Exposure in API:** API responses return exclusively high-level enum strings (`CAPTURING`, `GOOD`, `LOOK_FORWARD`, `MOVE_CLOSER`) and float progress percentages ($0.0 \to 1.0$).

---

## 4. User-Facing Wizard Steps

1. **Welcome:** Explains FaceSentry on-device continuous authentication.
2. **Privacy Notice:** Transparently details DPAPI storage and zero cloud transmissions.
3. **Camera Check:** Verifies webcam accessibility and agent daemon connectivity.
4. **Position Face:** Interactive instructions for lighting and angle calibration.
5. **Capture Samples:** Captures 15 high-quality samples with real-time feedback.
6. **Quality Verification:** Aggregates sample sharpness and pose variance.
7. **Liveness Confirmation Gate:** Demands a natural blink to ensure physical presence.
8. **Processing & Encryption:** Calculates centroid vector and persists with DPAPI.
9. **Enrollment Complete:** Profile activated and monitoring initiated.

---

## 5. Biometric Template Integrity & Synthetic Vector Prevention

### Critical Rule
Never create or store synthetic biometric templates (such as all-ones, all-zeroes, or constant vectors) in production enrollment storage. Genuine templates must strictly originate from live webcam samples passing all quality gates.

### Mathematical Integrity Gate (`validate_template_embedding`)
At load and reload time, templates must pass automated validation:
- **Non-Zero Variance:** $\text{std}(v) \ge 10^{-4}$ (rejects uniform constant vectors).
- **L2 Norm Normalization:** $\|v\|_2 > 0$ and finite values ($\text{no NaN/Inf}$).
- **Dimensionality:** Exactly $128\text{-D}$ for SFace feature embeddings.
- **Privacy-Safe Diagnostics:** Logs similarity scores and thresholds without exposing the underlying vector array.
