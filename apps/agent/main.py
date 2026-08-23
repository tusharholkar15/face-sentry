"""
FaceSentry Windows Background Agent Daemon Entrypoint
Coordinates Camera Capture, Face Detection, Recognition, Liveness,
Authentication Decision Engine, Workstation Lock Manager, and Real-time Telemetry.
"""

import sys
import time
import signal
import argparse
import logging
from typing import Optional, Dict, Any

from packages.shared.constants import SYSTEM_NAME, VERSION
from apps.agent.config import agent_settings
from apps.agent.camera import CameraManager
from apps.agent.facesentry_agent.models.face_detector import FaceDetector
from apps.agent.facesentry_agent.models.face_recognizer import FaceRecognizer
from apps.agent.facesentry_agent.models.model_manager import ModelManager
from apps.agent.facesentry_agent.biometric_storage import BiometricStorage, WindowsDPAPIBackend
from apps.agent.facesentry_agent.recognition import FaceRecognitionEngine
from apps.agent.facesentry_agent.liveness import TemporalLivenessStateMachine, LivenessConfig
from apps.agent.facesentry_agent.decision_engine import (
    AuthenticationDecisionEngine,
    DecisionConfig,
    DecisionResult,
    DecisionEvent,
    DecisionState,
)
from apps.agent.facesentry_agent.lock_manager import (
    WorkstationLockManager,
    LockDispatchResult,
    LockEvent,
)
from apps.agent.telemetry_publisher import AgentTelemetryPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Agent] %(message)s",
)
logger = logging.getLogger("facesentry.agent")


class FaceSentryAgent:
    """Agent orchestrator managing camera lifecycle, recognition, liveness, policy, OS lock dispatch, and telemetry."""

    def __init__(
        self,
        camera_index: Optional[int] = None,
        dry_run: Optional[bool] = None,
        enable_real_windows_lock: Optional[bool] = None,
        enable_telemetry: bool = True,
    ):
        self.camera_index = camera_index if camera_index is not None else agent_settings.camera_index
        self.dry_run = dry_run if dry_run is not None else agent_settings.dry_run
        self.enable_real_lock = (
            enable_real_windows_lock
            if enable_real_windows_lock is not None
            else (agent_settings.enable_real_windows_lock and not self.dry_run)
        )
        self.start_time = time.time()

        # Initialize Subsystems
        self.camera = CameraManager(camera_index=self.camera_index)
        self.model_manager = ModelManager()
        self.biometric_storage = BiometricStorage(backend=WindowsDPAPIBackend())

        # Models & Recognition
        self.detector: Optional[FaceDetector] = None
        self.recognizer: Optional[FaceRecognizer] = None
        self.recognition_engine: Optional[FaceRecognitionEngine] = None
        self._init_models()

        # Temporal Liveness
        self.liveness_engine = TemporalLivenessStateMachine(
            LivenessConfig(
                blink_required=True,
                head_movement_required=True,
                liveness_timeout_seconds=10.0,
            )
        )

        # Decision Engine
        self.decision_engine = AuthenticationDecisionEngine(
            config=DecisionConfig(
                absence_timeout_seconds=float(agent_settings.absence_timeout_seconds),
                unknown_face_timeout_seconds=float(agent_settings.unknown_face_timeout_seconds),
                spoof_lock_timeout_seconds=float(agent_settings.spoof_lock_timeout_seconds),
            ),
            on_event=self._on_decision_event,
        )

        # Lock Manager
        self.lock_manager = WorkstationLockManager(
            enable_real_windows_lock=self.enable_real_lock,
            cooldown_seconds=agent_settings.lock_dispatch_cooldown_seconds,
            on_event=self._on_lock_event,
        )

        # Telemetry Publisher
        self.telemetry_publisher = AgentTelemetryPublisher(
            enable_network_publish=enable_telemetry,
        )

        self._running = False
        self._last_decision: Optional[DecisionResult] = None
        self._last_security_event: Optional[Dict[str, Any]] = None

    def _init_models(self) -> None:
        """Initialize ONNX neural network models if provisioned locally."""
        try:
            if self.model_manager.is_model_present("face_detection_yunet") and self.model_manager.is_model_present("face_recognition_sface"):
                self.detector = FaceDetector(model_path=self.model_manager.get_model_path("face_detection_yunet"))
                self.recognizer = FaceRecognizer(model_path=self.model_manager.get_model_path("face_recognition_sface"))
                self.recognition_engine = FaceRecognitionEngine(
                    detector=self.detector,
                    recognizer=self.recognizer,
                    storage=self.biometric_storage,
                    similarity_threshold=agent_settings.similarity_threshold,
                )
                logger.info("Face detection and recognition models initialized successfully.")
            else:
                logger.warning("Models not provisioned. Run `python scripts/download_models.py`.")
        except Exception as exc:
            logger.error(f"Error loading models: {exc}")

    def _on_decision_event(self, event: DecisionEvent) -> None:
        """Callback for decision engine state transition events."""
        event_dict = {
            "event_type": event.event_type.value,
            "reason": event.reason,
            "timestamp": event.timestamp,
            "details": event.details,
        }
        self._last_security_event = event_dict
        self.telemetry_publisher.publish_event(event_dict)

    def _on_lock_event(self, event: LockEvent) -> None:
        """Callback for lock transition events."""
        logger.info(f"[LockAudit] [{event.event_type}] Mode: {event.mode}, Reason: {event.reason}, Result: {event.result}")
        lock_dict = {
            "event_type": event.event_type,
            "mode": event.mode,
            "reason": event.reason,
            "result": event.result,
            "timestamp": event.timestamp,
        }
        self.telemetry_publisher.publish_event(lock_dict)

    def run_diagnostics(self) -> bool:
        """Run self-check diagnostics on camera, models, and lock manager."""
        logger.info(f"--- Running {SYSTEM_NAME} Agent v{VERSION} Self-Check ---")
        logger.info(f"Target OS Platform: {sys.platform}")
        logger.info(f"Windows Workstation Lock Supported: {self.lock_manager.is_supported()}")
        mode_label = "REAL LOCK ENABLED" if self.enable_real_lock else "DRY-RUN MODE (Simulated)"
        logger.info(f"Workstation Lock Execution Mode: [{mode_label}]")

        # Test Camera connectivity
        cam_ok = self.camera.open()
        if cam_ok:
            ret, frame = self.camera.read_frame()
            logger.info(f"Camera Frame Grab: {'Success' if ret else 'Failed'} (Resolution: {frame.shape if frame is not None else 'N/A'})")
            self.camera.release()
        else:
            logger.warning(f"Camera {self.camera_index} could not be opened (hardware disconnected or in use).")

        # Check Models
        model_status = self.model_manager.check_all_models()
        for m_key, ok in model_status.items():
            logger.info(f"Model [{m_key}]: {'Verified OK' if ok else 'Missing / Invalid'}")

        logger.info("Diagnostics completed successfully.")
        return True

    def process_cycle(self) -> Optional[DecisionResult]:
        """Execute one complete sensor-to-decision-to-lock pipeline cycle."""
        camera_available = self.camera.is_connected()
        frame = None
        if camera_available:
            ret, frame = self.camera.read_frame()
            if not ret or frame is None:
                camera_available = False

        # 1. Detection & Recognition
        rec_result = None
        detected_faces = []
        if camera_available and frame is not None and self.recognition_engine:
            rec_result = self.recognition_engine.recognize(frame)
            if rec_result.detected_face:
                detected_faces.append(rec_result.detected_face)

        # 2. Liveness Evaluation
        liv_result = None
        if camera_available and self.recognition_engine:
            liv_result = self.liveness_engine.process_frame(detected_faces)

        # 3. Decision Engine Policy Evaluation
        decision = self.decision_engine.evaluate(
            recognition=rec_result,
            liveness=liv_result,
            camera_available=camera_available,
        )
        self._last_decision = decision

        # 4. OS Workstation Lock Dispatch (if policy triggered)
        if decision.lock_requested:
            self.lock_manager.lock_if_needed(decision)

        # 5. Telemetry Publishing
        uptime = time.time() - self.start_time
        self.telemetry_publisher.publish_cycle(
            decision=decision,
            recognition=rec_result,
            liveness=liv_result,
            camera_available=camera_available,
            uptime_seconds=uptime,
            last_event=self._last_security_event,
        )

        return decision

    def start(self) -> None:
        """Start the agent background processing loop."""
        mode_label = "REAL LOCK ENABLED" if self.enable_real_lock else "DRY-RUN MODE"
        logger.info(f"Starting {SYSTEM_NAME} Agent [Camera: {self.camera_index}] [{mode_label}]")
        self._running = True
        self.camera.open()

        # Handle graceful shutdown
        def handle_signal(sig, frame):
            logger.info("Shutdown signal received.")
            self.stop()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        try:
            while self._running:
                self.process_cycle()
                time.sleep(1.0 / agent_settings.target_fps)
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully release resources."""
        self._running = False
        self.camera.release()
        logger.info("FaceSentry Agent stopped.")


def main():
    parser = argparse.ArgumentParser(description=f"{SYSTEM_NAME} Windows Agent Daemon")
    parser.add_argument("--check", action="store_true", help="Run self-diagnostic check and exit")
    parser.add_argument("--dry-run", action="store_true", default=agent_settings.dry_run, help="Simulate workstation locks")
    parser.add_argument("--real-lock", action="store_true", default=False, help="Enable actual Windows workstation lock calls")
    parser.add_argument("--camera", type=int, default=agent_settings.camera_index, help="Webcam device index")
    args = parser.parse_args()

    enable_real = args.real_lock and not args.dry_run
    agent = FaceSentryAgent(
        camera_index=args.camera,
        dry_run=args.dry_run,
        enable_real_windows_lock=enable_real,
    )

    if args.check:
        success = agent.run_diagnostics()
        sys.exit(0 if success else 1)

    agent.start()


if __name__ == "__main__":
    main()
