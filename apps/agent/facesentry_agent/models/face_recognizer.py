"""
Face Recognition & Feature Vector Extraction (FaceRecognizerSF)
Encapsulates face alignment, feature extraction, L2 normalization, and cosine similarity matching.
"""

from pathlib import Path
from typing import Optional, Union
import cv2
import numpy as np

from .model_manager import ModelManager, ModelNotFoundError
from .face_detector import DetectedFace


def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    """
    Apply L2 normalization to a feature vector embedding.
    Ensures ||v||_2 = 1.0 so that cosine similarity equals standard dot product.
    """
    flat = embedding.flatten().astype(np.float32)
    norm = np.linalg.norm(flat)
    if norm == 0:
        return flat
    return flat / norm


def compute_cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute cosine similarity between two feature vector embeddings.
    Returns float in range [-1.0, 1.0].
    """
    a = vec_a.flatten().astype(np.float32)
    b = vec_b.flatten().astype(np.float32)
    
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0

    similarity = float(np.dot(a, b) / (norm_a * norm_b))
    # Bound within mathematical limits
    return max(-1.0, min(1.0, similarity))


class FaceRecognizer:
    """Wraps OpenCV FaceRecognizerSF (SFace / ArcFace) for feature vector generation."""

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        backend_id: int = cv2.dnn.DNN_BACKEND_OPENCV,
        target_id: int = cv2.dnn.DNN_TARGET_CPU,
    ):
        if model_path is None:
            manager = ModelManager()
            model_path = manager.get_model_path("face_recognition_sface")

        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise ModelNotFoundError(
                f"Face recognition model not found at {self.model_path}. "
                f"Run `python scripts/download_models.py` to download official models."
            )

        self._recognizer = cv2.FaceRecognizerSF.create(
            str(self.model_path),
            "",
            backend_id,
            target_id,
        )

    def align_face(self, image_bgr: np.ndarray, detected_face: DetectedFace) -> np.ndarray:
        """
        Align and crop detected face to standard canonical 112x112 image using 5 landmarks.
        """
        aligned_crop = self._recognizer.alignCrop(image_bgr, detected_face.raw_face_array)
        return aligned_crop

    def extract_embedding(self, image_bgr: np.ndarray, detected_face: DetectedFace) -> np.ndarray:
        """
        Extract normalized biometric feature embedding vector from a detected face.
        """
        aligned_crop = self.align_face(image_bgr, detected_face)
        feature_raw = self._recognizer.feature(aligned_crop)
        return normalize_embedding(feature_raw)

    def compute_similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """
        Calculate cosine similarity between two feature vector embeddings.
        """
        return compute_cosine_similarity(embedding_a, embedding_b)
