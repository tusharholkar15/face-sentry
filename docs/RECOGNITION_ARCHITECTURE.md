# FaceSentry Face Recognition Architecture Specification & Analysis

**Status:** Architecture Decision Record (ADR) & Specification  
**Document:** `docs/RECOGNITION_ARCHITECTURE.md`  
**Selected Architecture:** `EMBEDDING` (YuNet + SFace / ArcFace via OpenCV FaceRecognizerSF)  
**Target Platform:** Windows 10 / Windows 11 (x64)  
**Security & Privacy Baseline:** 100% On-Device, Zero-Cloud, DPAPI-Encrypted Storage  

---

## 1. Pinned Official Model Registry

FaceSentry exclusively utilizes official, pinned OpenCV Zoo ONNX deep learning models. Model files are never downloaded silently or executed without cryptographic SHA-256 verification.

| Model Identifier | Official Filename | Pinned Official Source URL | Expected SHA-256 Hash | Size (Bytes) | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `face_detection_yunet` | `face_detection_yunet_2023mar.onnx` | `https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx` | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | 232,589 | Real-time face detection & 5-point landmark extraction |
| `face_recognition_sface` | `face_recognition_sface_2021dec.onnx` | `https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx` | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | 38,696,353 | Deep metric feature vector embedding extraction |

### Provisioning Instructions
To download and verify official models:
```powershell
python scripts/download_models.py
```
To verify existing local models without downloading:
```powershell
python scripts/download_models.py --check
```

---

## 2. Recognition Architecture Pipeline

```
+-----------------------------------------------------------------------------------------------+
|                               FACESENTRY RECOGNITION PIPELINE                                 |
|                                                                                               |
|  [ Camera Frame (RAM) ]                                                                       |
|         │                                                                                     |
|         ▼                                                                                     |
|  [ FaceDetector (YuNet) ] ───────► DetectedFace (BBox, 5 Landmarks, Confidence)              |
|         │                                                                                     |
|         ▼                                                                                     |
|  [ Quality Gate ] ───────────────► Rejects: Blur, Extreme Yaw (>35°), Tilt (>18°), Multi-Face|
|         │                                                                                     |
|         ▼                                                                                     |
|  [ FaceRecognizerSF.alignCrop ] ─► Standardized Canonical 112x112 Crop                        |
|         │                                                                                     |
|         ▼                                                                                     |
|  [ FaceRecognizerSF.feature ] ───► Feature Vector                                             |
|         │                                                                                     |
|         ▼                                                                                     |
|  [ L2 Normalization ] ───────────► Unit Vector ||v|| = 1.0                                    |
|         │                                                                                     |
|         ▼                                                                                     |
|  [ Cosine Similarity Match ] ────► S = candidate · enrolled_reference                         |
|         │                                                                                     |
|         ▼                                                                                     |
|  [ RecognitionResult ] ──────────► (recognized: bool, similarity: float, reason: str)         |
+-----------------------------------------------------------------------------------------------+
```

---

## 3. Storage & Privacy Model

1. **Windows DPAPI Protection:** Enrolled biometric templates are serialized in a binary layout and encrypted at rest with Windows DPAPI (`CryptProtectData`). Only the logged-in Windows user session can decrypt the template.
2. **Ephemeral Memory Buffers:** Raw video frames and aligned facial crops reside in volatile memory only during analysis and are immediately purged.
3. **Non-Invertible Templates:** Persisted biometric data consists strictly of mathematical feature vectors (unit floats). High-fidelity facial imagery cannot be reverse-engineered from these embeddings.
