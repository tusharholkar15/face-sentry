"""
Face Recognition Engine
Evaluates video frames against enrolled biometric reference templates using normalized cosine similarity.
Performs zero workstation locking, zero liveness decisions, and zero external browser interactions.
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

from .models.face_detector import FaceDetector, DetectedFace
from .models.face_recognizer import FaceRecognizer, compute_cosine_similarity
from .biometric_storage import BiometricStorage, EnrolledProfile, validate_template_embedding
from packages.shared.constants import DEFAULT_SIMILARITY_THRESHOLD

logger = logging.getLogger("facesentry.recognition")


@dataclass(frozen=True)
class RecognitionResult:
    """Structured result returned by the face identity recognition engine."""
    recognized: bool
    similarity: float
    face_count: int
    timestamp: float
    reason: str
    detected_face: Optional[DetectedFace] = None


class FaceRecognitionEngine:
    """
    Stateless recognition engine comparing camera frames against an enrolled template.
    Strictly decoupled from state machine policy and OS locking triggers.
    """

    def __init__(
        self,
        detector: FaceDetector,
        recognizer: FaceRecognizer,
        storage: BiometricStorage,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        profile_name: str = "default_user",
    ):
        self.detector = detector
        self.recognizer = recognizer
        self.storage = storage
        self.similarity_threshold = similarity_threshold
        self.profile_name = profile_name

        self._active_profile: Optional[EnrolledProfile] = None
        self.reload_profile()

    def reload_profile(self) -> bool:
        """Load or refresh decrypted enrolled biometric template from storage."""
        try:
            if self.storage.has_profile(self.profile_name):
                profile = self.storage.load_profile(self.profile_name)
                is_valid, validation_reason = validate_template_embedding(
                    profile.reference_embedding,
                    expected_dim=profile.embedding_dim,
                )
                if not is_valid:
                    logger.warning(
                        f"Enrolled biometric profile '{self.profile_name}' is invalid or synthetic "
                        f"({validation_reason}). Disabling active profile until genuine enrollment."
                    )
                    self._active_profile = None
                    return False

                self._active_profile = profile
                logger.info(f"Loaded active biometric profile: {self._active_profile}")
                return True
            else:
                self._active_profile = None
                logger.info(f"No active profile found for '{self.profile_name}'.")
                return False
        except Exception as exc:
            logger.error(f"Error loading biometric profile '{self.profile_name}': {exc}")
            self._active_profile = None
            return False

    @property
    def is_enrolled(self) -> bool:
        """Whether a valid enrolled biometric template is currently loaded."""
        return self._active_profile is not None

    def process_frame(self, image_bgr: np.ndarray) -> RecognitionResult:
        """
        Evaluate a single video frame.
        Detects faces, aligns facial features, extracts embedding vector,
        and computes normalized cosine similarity against enrolled reference template.
        """
        now = time.time()

        if image_bgr is None or image_bgr.size == 0:
            return RecognitionResult(
                recognized=False,
                similarity=0.0,
                face_count=0,
                timestamp=now,
                reason="EMPTY_FRAME",
            )

        if not self.is_enrolled:
            return RecognitionResult(
                recognized=False,
                similarity=0.0,
                face_count=0,
                timestamp=now,
                reason="NO_ENROLLED_PROFILE",
            )

        detected_faces = self.detector.detect(image_bgr)
        face_count = len(detected_faces)

        if face_count == 0:
            return RecognitionResult(
                recognized=False,
                similarity=0.0,
                face_count=0,
                timestamp=now,
                reason="NO_FACE_DETECTED",
            )

        if face_count > 1:
            return RecognitionResult(
                recognized=False,
                similarity=0.0,
                face_count=face_count,
                timestamp=now,
                reason="MULTIPLE_FACES_DETECTED",
            )

        # Single face detected
        face = detected_faces[0]
        try:
            candidate_embedding = self.recognizer.extract_embedding(image_bgr, face)
            assert self._active_profile is not None
            similarity = compute_cosine_similarity(
                candidate_embedding,
                self._active_profile.reference_embedding,
            )

            is_match = similarity >= self.similarity_threshold
            reason = "MATCH_CONFIRMED" if is_match else "SIMILARITY_BELOW_THRESHOLD"

            # Privacy-safe diagnostic logging (strictly metadata/scores, zero biometric vectors/landmarks)
            logger.info(
                f"Face recognition evaluation: "
                f"recognition_similarity={similarity:.4f} "
                f"recognition_threshold={self.similarity_threshold:.4f} "
                f"recognized={str(is_match).lower()}"
            )

            return RecognitionResult(
                recognized=is_match,
                similarity=round(similarity, 4),
                face_count=1,
                timestamp=now,
                reason=reason,
                detected_face=face,
            )
        except Exception as exc:
            logger.error(f"Error during recognition feature extraction: {exc}")
            return RecognitionResult(
                recognized=False,
                similarity=0.0,
                face_count=1,
                timestamp=now,
                reason="EXTRACTION_FAILED",
                detected_face=face,
            )
