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
from apps.agent.camera import CameraManager
import urllib.request
import json

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
        
        while True:
            # Re-check enrollment periodically if missing
            if not recognition_engine.is_enrolled:
                now = time.time()
                if now - last_enrollment_check > 5.0:
                    last_enrollment_check = now
                    if recognition_engine.reload_profile():
                        logger.info("Enrollment profile successfully loaded.")
                    else:
                        if not enrollment_warning_printed:
                            logger.error("ENROLLMENT_REQUIRED: No biometric profile found. System cannot authenticate.")
                            enrollment_warning_printed = True
                        
                        # We skip decision engine and just loop if no enrollment
                        await asyncio.sleep(1.0)
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
                logger.debug(f"[FRAME] Face in frame: count={rec_result.face_count}, recognized={rec_result.recognized}, match_reason={rec_result.reason}")
            
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
