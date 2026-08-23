"""
Biometric Enrollment Engine & Quality Gates
Validates incoming camera frames against strict quality thresholds and computes
a stable normalized centroid template from multiple high-quality face samples.
Never persists raw images or crops to disk.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import cv2
import numpy as np

from .models.face_detector import FaceDetector, DetectedFace
from .models.face_recognizer import FaceRecognizer, normalize_embedding
from .biometric_storage import BiometricStorage, EnrolledProfile

logger = logging.getLogger("facesentry.enrollment")


@dataclass(frozen=True)
class QualityGateConfig:
    """Configurable quality validation thresholds for face enrollment."""
    min_face_size_pixels: int = 80
    min_confidence: float = 0.80
    min_blur_laplacian_var: float = 70.0
    min_mean_luminance: float = 35.0
    max_mean_luminance: float = 230.0
    max_eye_tilt_degrees: float = 18.0
    max_yaw_ratio: float = 0.40


@dataclass(frozen=True)
class QualityAssessment:
    """Result of quality gate validation on a candidate frame."""
    passed: bool
    reason: str
    metrics: Dict[str, float]
    detected_face: Optional[DetectedFace] = None


class FaceQualityGate:
    """Evaluates facial bounding boxes, illumination, blur, and pose heuristics."""

    def __init__(self, config: Optional[QualityGateConfig] = None):
        self.config = config or QualityGateConfig()

    def evaluate(self, image_bgr: np.ndarray, detected_faces: List[DetectedFace]) -> QualityAssessment:
        """Evaluate a frame and detected faces against all biometric quality gates."""
        if image_bgr is None or image_bgr.size == 0:
            return QualityAssessment(passed=False, reason="EMPTY_FRAME", metrics={})

        if len(detected_faces) == 0:
            return QualityAssessment(passed=False, reason="NO_FACE_DETECTED", metrics={})

        if len(detected_faces) > 1:
            return QualityAssessment(
                passed=False,
                reason="MULTIPLE_FACES_DETECTED",
                metrics={"face_count": float(len(detected_faces))},
            )

        face = detected_faces[0]
        x, y, w, h = face.bbox

        # 1. Face size check
        if w < self.config.min_face_size_pixels or h < self.config.min_face_size_pixels:
            return QualityAssessment(
                passed=False,
                reason="FACE_TOO_SMALL",
                metrics={"width": float(w), "height": float(h), "min_required": float(self.config.min_face_size_pixels)},
                detected_face=face,
            )

        # 2. Detection confidence check
        if face.confidence < self.config.min_confidence:
            return QualityAssessment(
                passed=False,
                reason="LOW_DETECTION_CONFIDENCE",
                metrics={"confidence": face.confidence, "min_required": self.config.min_confidence},
                detected_face=face,
            )

        # 3. Blur / Sharpness check (Laplacian variance over face ROI)
        face_roi = image_bgr[y: y + h, x: x + w]
        if face_roi.size == 0:
            return QualityAssessment(passed=False, reason="INVALID_ROI", metrics={}, detected_face=face)

        gray_roi = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray_roi, cv2.CV_64F).var())

        if laplacian_var < self.config.min_blur_laplacian_var:
            return QualityAssessment(
                passed=False,
                reason="IMAGE_BLURRY",
                metrics={"blur_score": laplacian_var, "min_required": self.config.min_blur_laplacian_var},
                detected_face=face,
            )

        # 4. Illumination / Brightness check (Mean pixel luminance)
        mean_luminance = float(np.mean(gray_roi))
        if mean_luminance < self.config.min_mean_luminance:
            return QualityAssessment(
                passed=False,
                reason="POOR_LIGHTING_TOO_DARK",
                metrics={"mean_luminance": mean_luminance, "min_required": self.config.min_mean_luminance},
                detected_face=face,
            )
        if mean_luminance > self.config.max_mean_luminance:
            return QualityAssessment(
                passed=False,
                reason="POOR_LIGHTING_TOO_BRIGHT",
                metrics={"mean_luminance": mean_luminance, "max_allowed": self.config.max_mean_luminance},
                detected_face=face,
            )

        # 5. Pose Heuristics based on 5 landmarks:
        # Landmarks: [0: right_eye, 1: left_eye, 2: nose_tip, 3: right_mouth, 4: left_mouth]
        landmarks = face.landmarks
        right_eye = landmarks[0]
        left_eye = landmarks[1]
        nose = landmarks[2]

        # Calculate eye tilt angle
        dx = left_eye[0] - right_eye[0]
        dy = left_eye[1] - right_eye[1]
        eye_distance = math.hypot(dx, dy)
        
        if eye_distance < 1.0:
            return QualityAssessment(passed=False, reason="DEGENERATE_LANDMARKS", metrics={}, detected_face=face)

        tilt_angle_degrees = abs(math.degrees(math.atan2(dy, dx)))
        if tilt_angle_degrees > self.config.max_eye_tilt_degrees:
            return QualityAssessment(
                passed=False,
                reason="EXTREME_HEAD_TILT",
                metrics={"eye_tilt_deg": tilt_angle_degrees, "max_allowed": self.config.max_eye_tilt_degrees},
                detected_face=face,
            )

        # Calculate Yaw asymmetry ratio: offset of nose from eye midpoint relative to inter-pupillary distance
        eye_midpoint_x = (right_eye[0] + left_eye[0]) / 2.0
        yaw_offset = (nose[0] - eye_midpoint_x) / eye_distance
        if abs(yaw_offset) > self.config.max_yaw_ratio:
            return QualityAssessment(
                passed=False,
                reason="EXTREME_HEAD_YAW",
                metrics={"yaw_offset_ratio": abs(yaw_offset), "max_allowed": self.config.max_yaw_ratio},
                detected_face=face,
            )

        # All quality gates passed
        return QualityAssessment(
            passed=True,
            reason="ACCEPTED",
            metrics={
                "face_width": float(w),
                "face_height": float(h),
                "confidence": face.confidence,
                "blur_score": laplacian_var,
                "mean_luminance": mean_luminance,
                "eye_tilt_deg": tilt_angle_degrees,
                "yaw_offset_ratio": abs(yaw_offset),
            },
            detected_face=face,
        )


class EnrollmentSession:
    """
    Manages interactive multi-sample enrollment session.
    Aggregates verified samples and computes a normalized centroid reference vector.
    """

    def __init__(
        self,
        detector: FaceDetector,
        recognizer: FaceRecognizer,
        quality_gate: Optional[FaceQualityGate] = None,
        target_samples: int = 5,
    ):
        self.detector = detector
        self.recognizer = recognizer
        self.quality_gate = quality_gate or FaceQualityGate()
        self.target_samples = max(1, target_samples)

        self._collected_embeddings: List[np.ndarray] = []
        self._collected_metrics: List[Dict[str, float]] = []

    @property
    def current_sample_count(self) -> int:
        return len(self._collected_embeddings)

    @property
    def is_complete(self) -> bool:
        return self.current_sample_count >= self.target_samples

    def process_frame(self, image_bgr: np.ndarray) -> Tuple[bool, QualityAssessment]:
        """
        Process a single candidate frame.
        If quality criteria are met, extracts and stores normalized embedding.
        Raw image is never stored.
        """
        if self.is_complete:
            return True, QualityAssessment(passed=True, reason="ENROLLMENT_ALREADY_COMPLETE", metrics={})

        detected_faces = self.detector.detect(image_bgr)
        assessment = self.quality_gate.evaluate(image_bgr, detected_faces)

        if not assessment.passed or assessment.detected_face is None:
            return False, assessment

        # Extract normalized embedding
        embedding = self.recognizer.extract_embedding(image_bgr, assessment.detected_face)
        normalized = normalize_embedding(embedding)

        self._collected_embeddings.append(normalized)
        self._collected_metrics.append(assessment.metrics)
        logger.info(f"Accepted enrollment sample ({len(self._collected_embeddings)}/{self.target_samples})")

        return True, assessment

    def finalize(
        self,
        profile_name: str,
        storage: BiometricStorage,
    ) -> EnrolledProfile:
        """
        Compute normalized centroid reference template from collected embeddings,
        encrypt and persist using BiometricStorage, and purge memory.
        """
        if len(self._collected_embeddings) == 0:
            raise ValueError("Cannot finalize enrollment: No valid face samples collected.")

        # Compute centroid embedding vector
        stacked = np.vstack(self._collected_embeddings)
        mean_vector = np.mean(stacked, axis=0)
        centroid_embedding = normalize_embedding(mean_vector)

        # Aggregate quality statistics
        agg_metrics: Dict[str, Any] = {
            "sample_count": len(self._collected_embeddings),
            "avg_blur_score": float(np.mean([m.get("blur_score", 0.0) for m in self._collected_metrics])),
            "avg_confidence": float(np.mean([m.get("confidence", 0.0) for m in self._collected_metrics])),
            "avg_luminance": float(np.mean([m.get("mean_luminance", 0.0) for m in self._collected_metrics])),
        }

        # Persist securely via DPAPI
        storage.save_profile(
            profile_name=profile_name,
            reference_embedding=centroid_embedding,
            sample_count=len(self._collected_embeddings),
            quality_metrics=agg_metrics,
        )

        # Read back decrypted profile object for confirmation
        profile = storage.load_profile(profile_name)

        # Clear volatile memory
        self._collected_embeddings.clear()
        self._collected_metrics.clear()

        logger.info(f"Enrollment finalized successfully for profile '{profile_name}'.")
        return profile
