# FaceSentry 🛡️

**Privacy-First Windows Face Authentication & Auto-Lock Security Engine**

FaceSentry is a zero-cloud, on-device biometric security system engineered for Windows 10 & 11 workstations. It continuously monitors user presence via the local webcam, evaluates multi-tier anti-spoofing liveness, and locks the Windows session when the authorized user steps away or when strangers/spoofs are detected.

---

## 🏛️ Monorepo Architecture

FaceSentry is built with a decoupled architecture:

- **Windows Background Agent (`apps/agent`)**: A headless Python daemon that performs realtime video capture, YuNet face detection, SFace biometric extraction, Argon2 PIN verification, and interacts directly with `user32.dll` to lock the workstation.
- **FastAPI Backend (`apps/api`)**: A local-only (`127.0.0.1:8000`) HTTP/WebSocket server that manages SQLite configurations and streams real-time biometric telemetry events.
- **Next.js Dashboard (`apps/web`)**: A React/Tailwind local HUD (`localhost:3000`) that provides a user-friendly interface for configuration, biometric enrollment, and real-time status monitoring.

All production data (encrypted biometrics, models, logs, DB) is securely sandboxed in `%LOCALAPPDATA%\FaceSentry`.

---

## 🚀 Installation & Setup

### Prerequisites
- **Operating System:** Windows 10 or Windows 11 (x64)
- **Python:** Python 3.10+ (Added to `PATH`)
- **Node.js:** Node.js 18+ & npm (Added to `PATH`)
- **Webcam:** Any DirectShow-compatible USB or integrated camera

### 1. Build the Agent
FaceSentry must be compiled into a standalone Windows executable.
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\scripts\build_windows.ps1
```

### 2. Install the Agent
Run the installation script to deploy the application to your local AppData.
```powershell
.\scripts\install_windows.ps1
```
*(Ensure `face_detection_yunet_2023mar.onnx` and `face_recognition_sface_2021dec.onnx` are placed in `%LOCALAPPDATA%\FaceSentry\models`)*

### 3. Register Startup Task
Enable FaceSentry to start automatically in the background when you log into Windows:
```powershell
.\scripts\register_startup.ps1
```

---

## ⚙️ Configuration & First-Time Setup

Before FaceSentry will actively lock your workstation, you must enroll your face and configure a recovery PIN.

1. Start the local backend:
   ```powershell
   $env:PYTHONPATH="."
   .\.venv\Scripts\python scripts\dev_api.py
   ```
2. Start the web dashboard:
   ```powershell
   cd apps\web
   npm install
   npm run dev
   ```
3. Open `http://localhost:3000` in your browser.
4. Navigate to the **Enrollment** wizard and capture your biometric profile.
5. Set an emergency **Recovery PIN**.
6. Set your operational **Absence and Stranger Timeouts**.

---

## 🛡️ Core Features

### 1. Continuous Authentication & Auto-Lock
If the authorized user steps away from the camera for longer than the configured `ABSENCE_TIMEOUT`, the agent immediately locks Windows. If an unrecognized face is detected for longer than the `STRANGER_TIMEOUT`, the system locks.

### 2. Safe Browser Protection (Optional)
If enabled, FaceSentry can provide defense-in-depth by automatically closing Chromium-based browsers (Chrome, Edge) upon a workstation lock and wiping active session cookies. **It will never delete saved passwords, autofill data, or bookmarks.**

### 3. Emergency PIN Fallback
If the camera fails, lighting is poor, or you are wearing a mask, you can use the secure Argon2-hashed local PIN to temporarily pause biometric enforcement for 60 seconds, allowing you to save work and fix the camera.

---

## 🔒 Security & Privacy

FaceSentry is designed around a strict Local-Only Privacy Model.

- **Zero Cloud Exposure:** No data is ever transmitted to the internet.
- **No Image Storage:** Raw webcam frames exist only in volatile RAM buffers during analysis and are discarded immediately.
- **DPAPI Encryption:** The 128-dimensional biometric profile is encrypted at rest using the Windows Data Protection API (`CryptProtectData`), tied irreversibly to your logged-in Windows user account.
- **Process Isolation:** The WebSocket telemetry server binds strictly to `127.0.0.1` and deliberately excludes biometric vectors from all event payloads.

### Known Security Limitations
FaceSentry relies on 2D camera feeds and temporal liveness checks (blinking, head movement). While it deters casual physical intrusion and "shoulder-surfing", it is **not** impervious to highly sophisticated, targeted presentation attacks (e.g., 3D animated deepfake masks) and should not replace enterprise-grade IR depth scanners like Windows Hello for high-security environments.

---

## 🛠️ Diagnostics & Uninstallation

**Run Diagnostics:**
To verify the camera and models without risking a Windows lockout:
```powershell
.\scripts\smoke_test_windows.ps1
```

**Uninstall:**
To remove FaceSentry from Windows Task Scheduler and safely delete the agent:
```powershell
.\scripts\uninstall_windows.ps1
```
*You will be explicitly prompted before your biometric data is destroyed.*

---

## 🗺️ Implementation Status

FaceSentry is fully implemented across 11 Phases, featuring a complete 125-test verification suite, Next.js frontend, Python FastAPI backend, PyInstaller compilation, and Windows Task Scheduler integration.
