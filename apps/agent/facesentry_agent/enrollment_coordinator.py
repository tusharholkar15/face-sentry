"""
FaceSentry Enrollment Coordinator
Coordinates interactive multi-sample enrollment, quality guidance, liveness validation,
and DPAPI encrypted persistence without persisting raw biometric images.
"""

import time
import logging
from typing import Optional, Tuple, Dict, Any, List
import numpy as np

from packages.shared.schemas import EnrollmentStatusResponse
from .models.face_detector import FaceDetector, DetectedFace
from .models.face_recognizer import FaceRecognizer
from .enrollment import FaceQualityGate, QualityAssessment, QualityGateConfig
from .biometric_storage import BiometricStorage, EnrolledProfile
from .models.face_recognizer import normalize_embedding

logger = logging.getLogger("facesentry.enrollment.coordinator")


class EnrollmentCoordinator:
    """
    Stateful enrollment manager handling live video sample ingestion,
    quality evaluation, interactive user guidance, liveness gates, and DPAPI finalization.
    """

    def __init__(
        self,
        detector: Optional[FaceDetector] = None,
        recognizer: Optional[FaceRecognizer] = None,
        quality_gate: Optional[FaceQualityGate] = None,
    ):
        self.detector = detector
        self.recognizer = recognizer
        self.quality_gate = quality_gate or FaceQualityGate()

        self._state: str = "IDLE"
        self._user_id: str = "default_user"
        self._target_samples: int = 15
        self._collected_embeddings: List[np.ndarray] = []
        self._collected_metrics: List[Dict[str, float]] = []
        self._liveness_confirmed: bool = False
        self._last_guidance: str = "READY"
        self._last_quality: str = "PENDING"
        self._error_message: Optional[str] = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def captured_sample_count(self) -> int:
        return len(self._collected_embeddings)

    @property
    def is_complete(self) -> bool:
        return self._state == "COMPLETED"

    def get_status(self) -> EnrollmentStatusResponse:
        """Construct real-time EnrollmentStatusResponse snapshot."""
        progress = min(1.0, self.captured_sample_count / max(1, self._target_samples))
        return EnrollmentStatusResponse(
            state=self._state,
            progress=round(progress, 2),
            captured_samples=self.captured_sample_count,
            required_samples=self._target_samples,
            quality=self._last_quality,
            guidance=self._last_guidance,
            liveness_verified=self._liveness_confirmed,
            error_message=self._error_message,
            is_complete=self.is_complete,
        )

    def start_session(self, user_id: str = "default_user", target_samples: int = 15) -> EnrollmentStatusResponse:
        """Start a new enrollment session and reset internal buffers."""
        self._user_id = user_id
        self._target_samples = max(5, target_samples)
        self._collected_embeddings.clear()
        self._collected_metrics.clear()
        self._liveness_confirmed = False
        self._error_message = None
        self._state = "CAPTURING"
        self._last_guidance = "LOOK_FORWARD"
        self._last_quality = "PENDING"

        logger.info(f"Enrollment session started for user '{user_id}' (Target: {self._target_samples} samples)")
        return self.get_status()

    def cancel_session(self) -> EnrollmentStatusResponse:
        """Safely cancel the session and purge all temporary biometric vectors."""
        self._state = "CANCELLED"
        self._last_guidance = "READY"
        self._collected_embeddings.clear()
        self._collected_metrics.clear()
        self._liveness_confirmed = False
        self._error_message = "Enrollment session cancelled by user."

        logger.info("Enrollment session cancelled. Memory purged.")
        return self.get_status()

    def _map_reason_to_guidance(self, reason: str) -> Tuple[str, str]:
        """Map raw quality assessment reason to user guidance and quality status."""
        if reason == "ACCEPTED":
            return "GOOD", "GOOD_SAMPLE"
        elif reason in ["EMPTY_FRAME", "NO_FACE_DETECTED"]:
            return "NO_FACE", "FACE_NOT_DETECTED"
        elif reason == "MULTIPLE_FACES_DETECTED":
            return "MULTIPLE_FACES", "MULTIPLE_FACES"
        elif reason == "FACE_TOO_SMALL":
            return "TOO_SMALL", "MOVE_CLOSER"
        elif reason == "IMAGE_BLURRY":
            return "BLURRY", "KEEP_STILL"
        elif reason in ["POOR_LIGHTING_TOO_DARK", "POOR_LIGHTING_TOO_BRIGHT"]:
            return "POOR_LIGHTING", "IMPROVE_LIGHTING"
        elif reason in ["EXTREME_HEAD_TILT", "EXTREME_HEAD_YAW"]:
            return "EXTREME_POSE", "LOOK_FORWARD"
        else:
            return "POOR", "LOOK_FORWARD"

    def process_frame(
        self,
        image_bgr: np.ndarray,
        detected_faces: Optional[List[DetectedFace]] = None,
        liveness_verified: bool = False,
    ) -> EnrollmentStatusResponse:
        """
        Process a single video frame during active enrollment.
        Extracts embeddings if quality passes; verifies liveness before completion.
        """
        if self._state not in ["CAPTURING", "LIVENESS_CHECK"]:
            return self.get_status()

        # Check Liveness requirement
        if liveness_verified:
            self._liveness_confirmed = True

        # Phase 1: Capturing Samples
        if self._state == "CAPTURING":
            if detected_faces is None and self.detector is not None:
                detected_faces = self.detector.detect(image_bgr)
            detected_faces = detected_faces or []

            assessment = self.quality_gate.evaluate(image_bgr, detected_faces)
            quality_status, guidance = self._map_reason_to_guidance(assessment.reason)
            self._last_quality = quality_status
            self._last_guidance = guidance

            if assessment.passed and assessment.detected_face is not None and self.recognizer is not None:
                embedding = self.recognizer.extract_embedding(image_bgr, assessment.detected_face)
                norm_embedding = normalize_embedding(embedding)
                self._collected_embeddings.append(norm_embedding)
                self._collected_metrics.append(assessment.metrics)

                # Check if sample collection is complete
                if len(self._collected_embeddings) >= self._target_samples:
                    if self._liveness_confirmed:
                        self._state = "PROCESSING"
                        self._last_guidance = "READY"
                    else:
                        self._state = "LIVENESS_CHECK"
                        self._last_guidance = "PERFORM_BLINK"
            
            return self.get_status()

        # Phase 2: Liveness Confirmation Gate
        if self._state == "LIVENESS_CHECK":
            self._last_guidance = "PERFORM_BLINK"
            if self._liveness_confirmed:
                self._state = "PROCESSING"
                self._last_guidance = "READY"

            return self.get_status()

        return self.get_status()

    def finalize_session(self, storage: BiometricStorage) -> Tuple[bool, Optional[EnrolledProfile], Optional[str]]:
        """
        Finalize enrollment by computing centroid template, encrypting with DPAPI,
        and clearing all volatile memory buffers.
        """
        if len(self._collected_embeddings) < self._target_samples:
            err = f"Cannot finalize: only {len(self._collected_embeddings)}/{self._target_samples} samples collected."
            self._state = "FAILED"
            self._error_message = err
            return False, None, err

        if not self._liveness_confirmed:
            err = "Cannot finalize: Liveness verification has not been completed."
            self._error_message = err
            return False, None, err

        try:
            self._state = "PROCESSING"
            # Compute normalized centroid vector
            stacked = np.vstack(self._collected_embeddings)
            centroid = normalize_embedding(np.mean(stacked, axis=0))

            agg_metrics = {
                "sample_count": len(self._collected_embeddings),
                "avg_blur_score": float(np.mean([m.get("blur_score", 0.0) for m in self._collected_metrics])),
                "avg_confidence": float(np.mean([m.get("confidence", 0.0) for m in self._collected_metrics])),
                "avg_luminance": float(np.mean([m.get("mean_luminance", 0.0) for m in self._collected_metrics])),
            }

            # Encrypt & persist via Windows DPAPI
            storage.save_profile(
                profile_name=self._user_id,
                reference_embedding=centroid,
                sample_count=len(self._collected_embeddings),
                quality_metrics=agg_metrics,
            )

            profile = storage.load_profile(self._user_id)
            self._state = "COMPLETED"
            self._last_guidance = "READY"
            self._collected_embeddings.clear()
            self._collected_metrics.clear()

            logger.info(f"Enrollment finalized and DPAPI profile saved for '{self._user_id}'.")
            return True, profile, None
        except Exception as exc:
            self._state = "FAILED"
            self._error_message = str(exc)
            logger.error(f"Failed to finalize enrollment: {exc}")
            return False, None, str(exc)
