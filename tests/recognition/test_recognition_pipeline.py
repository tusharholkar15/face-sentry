"""
Unit Tests for End-to-End Face Recognition Pipeline (with Mocked Vision Ingestion)
"""

import pytest
import numpy as np
from unittest.mock import MagicMock

from apps.agent.facesentry_agent.recognition import (
    FaceRecognitionEngine,
    RecognitionResult,
)
from apps.agent.facesentry_agent.models.face_detector import DetectedFace
from apps.agent.facesentry_agent.biometric_storage import (
    BiometricStorage,
    MockEncryptedStorageBackend,
)


def create_mock_face(bbox=(50, 50, 100, 100)) -> DetectedFace:
    return DetectedFace(
        bbox=bbox,
        landmarks=np.zeros((5, 2), dtype=np.float32),
        confidence=0.95,
        raw_face_array=np.zeros(15, dtype=np.float32),
    )


def test_recognition_with_no_enrolled_profile(tmp_path):
    """Verify recognition returns NO_ENROLLED_PROFILE when no template exists."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    mock_detector = MagicMock()
    mock_recognizer = MagicMock()

    engine = FaceRecognitionEngine(
        detector=mock_detector,
        recognizer=mock_recognizer,
        storage=storage,
        profile_name="unregistered_user",
    )

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    res = engine.process_frame(img)

    assert res.recognized is False
    assert res.reason == "NO_ENROLLED_PROFILE"
    assert res.face_count == 0


def test_recognition_with_no_face_detected(tmp_path):
    """Verify recognition returns NO_FACE_DETECTED when frame contains no face."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    # Save a valid enrolled profile
    enrolled_vec = np.ones(512, dtype=np.float32)
    enrolled_vec /= np.linalg.norm(enrolled_vec)
    storage.save_profile("test_user", enrolled_vec)

    mock_detector = MagicMock()
    mock_detector.detect.return_value = []
    mock_recognizer = MagicMock()

    engine = FaceRecognitionEngine(
        detector=mock_detector,
        recognizer=mock_recognizer,
        storage=storage,
        profile_name="test_user",
    )

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    res = engine.process_frame(img)

    assert res.recognized is False
    assert res.reason == "NO_FACE_DETECTED"
    assert res.face_count == 0


def test_recognition_with_multiple_faces_detected(tmp_path):
    """Verify recognition rejects multiple faces for security."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    enrolled_vec = np.ones(512, dtype=np.float32)
    enrolled_vec /= np.linalg.norm(enrolled_vec)
    storage.save_profile("test_user", enrolled_vec)

    mock_detector = MagicMock()
    mock_detector.detect.return_value = [create_mock_face(), create_mock_face()]
    mock_recognizer = MagicMock()

    engine = FaceRecognitionEngine(
        detector=mock_detector,
        recognizer=mock_recognizer,
        storage=storage,
        profile_name="test_user",
    )

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    res = engine.process_frame(img)

    assert res.recognized is False
    assert res.reason == "MULTIPLE_FACES_DETECTED"
    assert res.face_count == 2


def test_successful_face_recognition_match(tmp_path):
    """Verify successful recognition when cosine similarity >= threshold."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    
    # Enrolled vector
    np.random.seed(42)
    enrolled_vec = np.random.randn(512).astype(np.float32)
    enrolled_vec /= np.linalg.norm(enrolled_vec)
    storage.save_profile("authorized_user", enrolled_vec)

    # Candidate vector (very close match)
    candidate_vec = enrolled_vec.copy()

    mock_detector = MagicMock()
    mock_face = create_mock_face()
    mock_detector.detect.return_value = [mock_face]

    mock_recognizer = MagicMock()
    mock_recognizer.extract_embedding.return_value = candidate_vec

    engine = FaceRecognitionEngine(
        detector=mock_detector,
        recognizer=mock_recognizer,
        storage=storage,
        similarity_threshold=0.65,
        profile_name="authorized_user",
    )

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    res = engine.process_frame(img)

    assert res.recognized is True
    assert res.reason == "MATCH_CONFIRMED"
    assert res.similarity >= 0.99
    assert res.face_count == 1
    assert res.detected_face is mock_face


def test_unrecognized_face_below_threshold(tmp_path):
    """Verify stranger face rejection when cosine similarity < threshold."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    
    # Enrolled vector
    enrolled_vec = np.zeros(512, dtype=np.float32)
    enrolled_vec[0] = 1.0
    storage.save_profile("authorized_user", enrolled_vec)

    # Orthogonal stranger vector (similarity = 0.0)
    stranger_vec = np.zeros(512, dtype=np.float32)
    stranger_vec[1] = 1.0

    mock_detector = MagicMock()
    mock_face = create_mock_face()
    mock_detector.detect.return_value = [mock_face]

    mock_recognizer = MagicMock()
    mock_recognizer.extract_embedding.return_value = stranger_vec

    engine = FaceRecognitionEngine(
        detector=mock_detector,
        recognizer=mock_recognizer,
        storage=storage,
        similarity_threshold=0.65,
        profile_name="authorized_user",
    )

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    res = engine.process_frame(img)

    assert res.recognized is False
    assert res.reason == "SIMILARITY_BELOW_THRESHOLD"
    assert res.similarity == 0.0
    assert res.face_count == 1
