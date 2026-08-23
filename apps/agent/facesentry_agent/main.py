"""
FaceSentry Production Agent Entry Point
"""

import os
import sys
import time
import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler

from packages.shared.constants import (
    SYSTEM_NAME,
    VERSION,
    DEFAULT_LOGS_DIR,
    DEFAULT_MODELS_DIR,
    DEFAULT_DATABASE_PATH,
    DEFAULT_ENROLLMENT_DIR,
)

from apps.agent.facesentry_agent.biometric_storage import BiometricStorage
from apps.agent.facesentry_agent.models.face_detector import FaceDetector
from apps.agent.facesentry_agent.models.face_recognizer import FaceRecognizer
from apps.agent.facesentry_agent.models.model_manager import ModelManager
from apps.agent.facesentry_agent.recognition import FaceRecognitionEngine, RecognitionResult
from apps.agent.facesentry_agent.liveness import TemporalLivenessStateMachine
from apps.agent.facesentry_agent.decision_engine import AuthenticationDecisionEngine, DecisionEvent, DecisionEventType, DecisionState
from apps.agent.facesentry_agent.lock_manager import WorkstationLockManager
from apps.agent.facesentry_agent.enrollment_coordinator import EnrollmentCoordinator
from packages.shared.schemas import EnrollmentStatusResponse
from apps.agent.camera import CameraManager
import urllib.request
import json
from typing import Optional

logger = logging.getLogger("facesentry")

def setup_logging(mode: str):
    """Initializes rotating file logs in the correct directory."""
    os.makedirs(DEFAULT_LOGS_DIR, exist_ok=True)
    log_file = os.path.join(DEFAULT_LOGS_DIR, "agent.log")
    
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    logger.setLevel(logging.INFO if mode != "DIAGNOSTIC" else logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

def check_installation():
    """Performs strict pre-flight checks."""
    logger.info("Performing pre-flight startup checks...")
    
    models = [
        os.path.join(DEFAULT_MODELS_DIR, "face_detection_yunet_2023mar.onnx"),
        os.path.join(DEFAULT_MODELS_DIR, "face_recognition_sface_2021dec.onnx")
    ]
    
    missing_models = [m for m in models if not os.path.exists(m)]
    if missing_models:
        logger.error(f"Missing required model files: {missing_models}")
        sys.exit(1)
        
    logger.info("Models verified.")
    logger.info(f"Database path: {DEFAULT_DATABASE_PATH}")
    logger.info(f"Enrollment dir: {DEFAULT_ENROLLMENT_DIR}")

import threading

def publish_telemetry_event(event: DecisionEvent):
    """Publish a decision event to the local telemetry API in a non-blocking background thread."""
    def _send():
        try:
            payload = {
                "event": {
                    "event_type": event.event_type.value,
                    "reason": event.reason,
                    "timestamp": event.timestamp,
                    "details": event.details
                }
            }
            payload_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                "http://127.0.0.1:8000/api/v1/telemetry/publish",
                data=payload_bytes,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=0.2):
                pass
        except Exception:
            pass  # Skip logging to avoid spam if backend is offline

    threading.Thread(target=_send, daemon=True).start()

def get_remote_enrollment_status() -> Optional[dict]:
    """Poll local FastAPI backend for active enrollment wizard requests."""
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/enrollment/status",
            headers={'Content-Type': 'application/json'},
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=0.2) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

def post_enrollment_update(status_resp: EnrollmentStatusResponse):
    """Push real-time sample progress and guidance to FastAPI broker."""
    def _send():
        try:
            payload = {"status": status_resp.model_dump()}
            payload_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                "http://127.0.0.1:8000/api/v1/enrollment/update_progress",
                data=payload_bytes,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=0.2):
                pass
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()

async def main_loop(mode: str):
    """The core operational loop of the agent."""
    logger.info(f"Starting {SYSTEM_NAME} v{VERSION} in {mode} mode.")
    check_installation()
    
    if mode == "DIAGNOSTIC":
        logger.info("Diagnostic mode complete. Exiting.")
        sys.exit(0)
        
    camera = None
    try:
        # 1. Initialize core dependencies
        logger.info("Initializing Agent Subsystems...")
        storage = BiometricStorage(DEFAULT_ENROLLMENT_DIR)
        
        # 2. Initialize Models
        model_manager = ModelManager(DEFAULT_MODELS_DIR)
        detector = FaceDetector(model_manager.get_model_path("face_detection_yunet"))
        recognizer = FaceRecognizer(model_manager.get_model_path("face_recognition_sface"))
        
        # 3. Initialize Engines
        recognition_engine = FaceRecognitionEngine(detector, recognizer, storage)
        liveness_engine = TemporalLivenessStateMachine()
        enrollment_coordinator = EnrollmentCoordinator(detector=detector, recognizer=recognizer)
        
        # 4. Initialize Decision & Lock Managers
        decision_engine = AuthenticationDecisionEngine(on_event=publish_telemetry_event)
        
        enable_real_lock = (mode == "NORMAL")
        lock_manager = WorkstationLockManager(
            enable_real_windows_lock=enable_real_lock,
            on_event=lambda e: logger.info(f"LOCK_EVENT: {e.event_type} (Result: {e.result})")
        )
        
        # 5. Initialize Camera
        camera = CameraManager(camera_index=0, width=640, height=480, target_fps=15)
        
        logger.info("Agent protection loop running... (Press Ctrl+C to stop)")
        
        # Loop variables
        last_enrollment_check = 0.0
        enrollment_warning_printed = False
        last_api_check = 0.0
        api_enrollment_active = False
        
        while True:
            now = time.time()

            # Check if an interactive enrollment session was initiated via the Web Dashboard
            if now - last_api_check > 0.4:
                last_api_check = now
                remote_status = get_remote_enrollment_status()
                if remote_status:
                    remote_state = remote_status.get("state", "IDLE")
                    if remote_state in ["CAPTURING", "LIVENESS_CHECK"]:
                        api_enrollment_active = True
                        if enrollment_coordinator.state in ["IDLE", "CANCELLED", "COMPLETED"]:
                            enrollment_coordinator.start_session(
                                user_id="default_user",
                                target_samples=remote_status.get("required_samples", 15)
                            )
                    elif remote_state == "CANCELLED":
                        api_enrollment_active = False
                        if enrollment_coordinator.state != "IDLE":
                            enrollment_coordinator.cancel_session()
                    elif remote_state in ["COMPLETED", "IDLE"]:
                        if api_enrollment_active and enrollment_coordinator.captured_sample_count >= 5:
                            success, profile, err = enrollment_coordinator.finalize_session(storage)
                            if success:
                                recognition_engine.reload_profile()
                                decision_engine.reset()
                                logger.info("Enrollment finalized on COMPLETED signal.")
                        api_enrollment_active = False

            # Read frame
            if not camera.is_connected():
                camera.open()
                
            ret, frame = camera.read_frame()
            camera_available = ret and frame is not None

            # Handle live enrollment session
            if api_enrollment_active or enrollment_coordinator.state in ["CAPTURING", "LIVENESS_CHECK", "PROCESSING"]:
                if camera_available:
                    faces = detector.detect(frame)
                    liveness_faces = [faces[0]] if len(faces) == 1 else []
                    liveness_res = liveness_engine.process_frame(liveness_faces)
                    is_live_ok = bool(liveness_res.verified or liveness_res.blink_detected) if liveness_res else False
                    
                    enroll_status = enrollment_coordinator.process_frame(
                        frame,
                        detected_faces=faces,
                        liveness_verified=is_live_ok
                    )
                    post_enrollment_update(enroll_status)
                    
                    if enrollment_coordinator.captured_sample_count >= enrollment_coordinator._target_samples:
                        success, profile, err = enrollment_coordinator.finalize_session(storage)
                        if success:
                            completed_status = enrollment_coordinator.get_status()
                            post_enrollment_update(completed_status)
                            recognition_engine.reload_profile()
                            decision_engine.reset()
                            api_enrollment_active = False
                            logger.info("Enrollment finalized successfully. Continuous protection active.")
                
                await asyncio.sleep(1 / 15.0)
                continue
            
            # If not enrolled and not in enrollment session, wait in standby mode without locking
            if not recognition_engine.is_enrolled:
                if now - last_enrollment_check > 5.0:
                    last_enrollment_check = now
                    if recognition_engine.reload_profile():
                        logger.info("Enrollment profile successfully loaded.")
                    else:
                        if not enrollment_warning_printed:
                            logger.info("ENROLLMENT_REQUIRED: No biometric profile found. Awaiting enrollment via Web UI.")
                            enrollment_warning_printed = True
                
                await asyncio.sleep(0.2)
                continue
            
            # Read frame
            if not camera.is_connected():
                camera.open()
                
            ret, frame = camera.read_frame()
            camera_available = ret and frame is not None
            
            # If workstation is in locked state, remain in standby and do not process liveness
            if decision_engine.current_state == DecisionState.LOCKED_ACTION_DISPATCHED:
                await asyncio.sleep(0.5)
                continue

            rec_result = None
            liveness_result = None
            
            if camera_available:
                # Process Recognition
                rec_result = recognition_engine.process_frame(frame)
                
                # Process Liveness
                faces = [rec_result.detected_face] if (rec_result.face_count == 1 and rec_result.detected_face is not None) else []
                liveness_result = liveness_engine.process_frame(faces)
                    
            # Evaluate Decision
            decision_result = decision_engine.evaluate(
                recognition=rec_result,
                liveness=liveness_result,
                camera_available=camera_available
            )

            # Runtime Diagnostics (Privacy-Safe: Zero vector/landmark logging)
            if rec_result and rec_result.face_count == 0:
                logger.debug(f"[FRAME] No face in frame (Absence duration: {decision_result.absence_duration:.1f}s)")
            elif rec_result and rec_result.face_count > 0:
                logger.debug(
                    f"[FRAME] Face in frame: count={rec_result.face_count}, "
                    f"recognition_similarity={rec_result.similarity:.4f}, "
                    f"recognition_threshold={recognition_engine.similarity_threshold:.4f}, "
                    f"recognized={str(rec_result.recognized).lower()}, match_reason={rec_result.reason}"
                )
            
            # Dispatch Lock Request
            if decision_result.lock_requested:
                logger.warning(f"LOCK_REQUESTED: {decision_result.reason}")
                lock_res = lock_manager.lock_if_needed(decision_result)
                liveness_engine.reset()
                if lock_res and lock_res.success:
                    logger.info(f"POST_LOCK: Lock action completed ({lock_res.status.value}). Session locked standby active.")
                    if mode == "DRY_RUN":
                        logger.info("DRY_RUN simulation completed successfully. Exiting.")
                        break
            
            # Sleep to yield event loop and match ~15 FPS target
            await asyncio.sleep(1 / 15.0)
            
    except asyncio.CancelledError:
        logger.info("Agent shutdown requested.")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        if camera is not None:
            camera.release()
        logger.info("Graceful shutdown complete.")

def main():
    parser = argparse.ArgumentParser(description="FaceSentry Agent Entry Point")
    parser.add_argument(
        "--mode", 
        type=str, 
        choices=["NORMAL", "DRY_RUN", "DIAGNOSTIC"],
        default="NORMAL",
        help="Operational mode"
    )
    args = parser.parse_args()
    
    setup_logging(args.mode)
    
    try:
        asyncio.run(main_loop(args.mode))
    except KeyboardInterrupt:
        logger.info("Process exited via KeyboardInterrupt.")
    except Exception as e:
        logger.error(f"Fatal unhandled exception: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
