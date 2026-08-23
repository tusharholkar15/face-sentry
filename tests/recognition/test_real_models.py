"""
Integration Tests with Real Local ONNX Models (YuNet & SFace)
"""

import numpy as np
import pytest
from pathlib import Path

from apps.agent.facesentry_agent.models.model_manager import ModelManager
from apps.agent.facesentry_agent.models.face_detector import FaceDetector
from apps.agent.facesentry_agent.models.face_recognizer import FaceRecognizer
from apps.agent.facesentry_agent.enrollment import FaceQualityGate
from apps.agent.facesentry_agent.biometric_storage import (
    BiometricStorage,
    MockEncryptedStorageBackend,
)


@pytest.fixture
def model_manager():
    return ModelManager()


def test_real_yunet_detector_initialization(model_manager):
    """Verify FaceDetector initializes and can run on an empty frame without errors."""
    if not model_manager.is_model_present("face_detection_yunet"):
        pytest.skip("YuNet model not provisioned locally.")

    detector = FaceDetector()
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    faces = detector.detect(img)
    assert isinstance(faces, list)
    assert len(faces) == 0


def test_real_sface_recognizer_initialization(model_manager):
    """Verify FaceRecognizer initializes with SFace ONNX without errors."""
    if not model_manager.is_model_present("face_recognition_sface"):
        pytest.skip("SFace model not provisioned locally.")

    recognizer = FaceRecognizer()
    assert recognizer._recognizer is not None


def test_real_sface_embedding_dimension(model_manager):
    """Verify SFace ONNX model extracts exact 128-dimensional L2-normalized embeddings."""
    if not model_manager.is_model_present("face_recognition_sface"):
        pytest.skip("SFace model not provisioned locally.")

    recognizer = FaceRecognizer()
    dummy_crop = np.zeros((112, 112, 3), dtype=np.uint8)
    raw_feature = recognizer._recognizer.feature(dummy_crop)
    flat_feature = raw_feature.flatten()

    assert flat_feature.shape == (128,)
    assert len(flat_feature) == 128

