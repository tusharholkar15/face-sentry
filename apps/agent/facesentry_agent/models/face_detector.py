"""
Face Detection Subsystem (YuNet)
Encapsulates OpenCV YuNet face detection and 5-point facial landmark extraction.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Union
import cv2
import numpy as np

from .model_manager import ModelManager, ModelNotFoundError


@dataclass(frozen=True)
class DetectedFace:
    """Represents a single face detected within a frame."""
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    landmarks: np.ndarray             # 5x2 array: [right_eye, left_eye, nose, right_mouth, left_mouth]
    confidence: float                 # Detection confidence score (0.0 to 1.0)
    raw_face_array: np.ndarray        # Raw 15-element array required by FaceRecognizerSF.alignCrop


class FaceDetector:
    """Wraps OpenCV YuNet for real-time face and landmark detection."""

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        score_threshold: float = 0.7,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        backend_id: int = cv2.dnn.DNN_BACKEND_OPENCV,
        target_id: int = cv2.dnn.DNN_TARGET_CPU,
    ):
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self.backend_id = backend_id
        self.target_id = target_id

        # Resolve model path
        if model_path is None:
            manager = ModelManager()
            model_path = manager.get_model_path("face_detection_yunet")

        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise ModelNotFoundError(
                f"YuNet model not found at {self.model_path}. "
                f"Run `python scripts/download_models.py` to download official models."
            )

        # Initial dummy input size (320x320), updated dynamically on frame input
        self._current_input_size = (320, 320)
        self._detector = cv2.FaceDetectorYN.create(
            str(self.model_path),
            "",
            self._current_input_size,
            self.score_threshold,
            self.nms_threshold,
            self.top_k,
            self.backend_id,
            self.target_id,
        )

    def detect(self, image_bgr: np.ndarray) -> List[DetectedFace]:
        """
        Detect all faces in an input BGR image frame.
        Dynamically adjusts internal detector input size if image dimensions change.
        """
        if image_bgr is None or image_bgr.size == 0:
            return []

        h, w = image_bgr.shape[:2]
        if (w, h) != self._current_input_size:
            self._current_input_size = (w, h)
            self._detector.setInputSize(self._current_input_size)

        _, faces = self._detector.detect(image_bgr)
        if faces is None:
            return []

        results: List[DetectedFace] = []
        for face_data in faces:
            # YuNet output layout:
            # [x, y, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rm, y_rm, x_lm, y_lm, confidence]
            x, y, w_box, h_box = face_data[0:4].astype(int)
            landmarks = face_data[4:14].reshape((5, 2))
            confidence = float(face_data[14])

            # Ensure bounding box is within frame boundaries
            x = max(0, x)
            y = max(0, y)
            w_box = max(1, min(w_box, w - x))
            h_box = max(1, min(h_box, h - y))

            results.append(
                DetectedFace(
                    bbox=(x, y, w_box, h_box),
                    landmarks=landmarks,
                    confidence=confidence,
                    raw_face_array=face_data.copy(),
                )
            )

        return results
