"""
FaceSentry Models Package
Encapsulates face detection, alignment, embedding extraction, and model management.
"""

from .model_manager import ModelManager, ModelSpec, ModelNotFoundError, ModelCorruptedError
from .face_detector import FaceDetector, DetectedFace
from .face_recognizer import FaceRecognizer

__all__ = [
    "ModelManager",
    "ModelSpec",
    "ModelNotFoundError",
    "ModelCorruptedError",
    "FaceDetector",
    "DetectedFace",
    "FaceRecognizer",
]
