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
    validate_template_embedding,
)


def create_mock_face(bbox=(50, 50, 100, 100)) -> DetectedFace:
    return DetectedFace(
        bbox=bbox,
        landmarks=np.zeros((5, 2), dtype=np.float32),
        confidence=0.95,
        raw_face_array=np.zeros(15, dtype=np.float32),
    )


def test_missing_enrollment_handling(tmp_path):
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

    assert engine.is_enrolled is False
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    res = engine.process_frame(img)

    assert res.recognized is False
    assert res.reason == "NO_ENROLLED_PROFILE"
    assert res.face_count == 0


def test_recognition_with_no_face_detected(tmp_path):
    """Verify recognition returns NO_FACE_DETECTED when frame contains no face."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    
    # Save a valid enrolled profile with realistic distribution
    np.random.seed(10)
    enrolled_vec = np.random.randn(128).astype(np.float32)
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
    np.random.seed(20)
    enrolled_vec = np.random.randn(128).astype(np.float32)
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


def test_genuine_enrolled_user_recognized(tmp_path):
    """Verify successful recognition of genuine enrolled user when similarity >= threshold."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    
    # Enrolled vector
    np.random.seed(42)
    enrolled_vec = np.random.randn(128).astype(np.float32)
    enrolled_vec /= np.linalg.norm(enrolled_vec)
    storage.save_profile("authorized_user", enrolled_vec)

    # Candidate live vector (genuine user with slight sensor variation)
    noise = np.random.randn(128).astype(np.float32) * 0.05
    candidate_vec = enrolled_vec + noise
    candidate_vec /= np.linalg.norm(candidate_vec)

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
    assert res.similarity >= 0.85
    assert res.face_count == 1
    assert res.detected_face is mock_face


def test_unknown_user_rejected(tmp_path):
    """Verify that an unknown user / stranger face is rejected."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    
    # Enrolled vector
    np.random.seed(100)
    enrolled_vec = np.random.randn(128).astype(np.float32)
    enrolled_vec /= np.linalg.norm(enrolled_vec)
    storage.save_profile("authorized_user", enrolled_vec)

    # Unrelated stranger face vector (statistically low cosine similarity)
    np.random.seed(999)
    stranger_vec = np.random.randn(128).astype(np.float32)
    stranger_vec /= np.linalg.norm(stranger_vec)

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
    assert res.similarity < 0.65
    assert res.face_count == 1


def test_similarity_threshold_behavior(tmp_path):
    """Verify exact boundary behavior around the similarity threshold."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    
    np.random.seed(77)
    base_vec = np.random.randn(128).astype(np.float32)
    base_vec /= np.linalg.norm(base_vec)
    storage.save_profile("threshold_user", base_vec)

    mock_detector = MagicMock()
    mock_detector.detect.return_value = [create_mock_face()]
    mock_recognizer = MagicMock()

    threshold = 0.65
    engine = FaceRecognitionEngine(
        detector=mock_detector,
        recognizer=mock_recognizer,
        storage=storage,
        similarity_threshold=threshold,
        profile_name="threshold_user",
    )

    # Sub-case A: Similarity 0.64 (just below threshold) -> rejected
    # Construct vector with exact cosine similarity 0.64
    ortho = np.random.randn(128).astype(np.float32)
    ortho -= np.dot(ortho, base_vec) * base_vec
    ortho /= np.linalg.norm(ortho)

    target_sim = 0.64
    candidate_below = target_sim * base_vec + np.sqrt(1 - target_sim**2) * ortho
    candidate_below /= np.linalg.norm(candidate_below)
    mock_recognizer.extract_embedding.return_value = candidate_below

    res_below = engine.process_frame(np.zeros((480, 640, 3), dtype=np.uint8))
    assert res_below.recognized is False
    assert res_below.reason == "SIMILARITY_BELOW_THRESHOLD"
    assert np.isclose(res_below.similarity, 0.64, atol=1e-2)

    # Sub-case B: Similarity 0.66 (just above threshold) -> accepted
    target_sim_above = 0.66
    candidate_above = target_sim_above * base_vec + np.sqrt(1 - target_sim_above**2) * ortho
    candidate_above /= np.linalg.norm(candidate_above)
    mock_recognizer.extract_embedding.return_value = candidate_above

    res_above = engine.process_frame(np.zeros((480, 640, 3), dtype=np.uint8))
    assert res_above.recognized is True
    assert res_above.reason == "MATCH_CONFIRMED"
    assert np.isclose(res_above.similarity, 0.66, atol=1e-2)


def test_synthetic_invalid_template_detection(tmp_path):
    """Verify that synthetic (e.g. constant/all-ones) or corrupted templates are detected and rejected."""
    # Test validator directly
    valid_norm, reason = validate_template_embedding(np.random.randn(128))
    assert valid_norm is True
    assert reason == "VALID"

    # Synthetic uniform constant vector (like the bug: np.ones(128))
    synthetic_vec = np.ones(128, dtype=np.float32) / np.sqrt(128)
    valid_synth, synth_reason = validate_template_embedding(synthetic_vec)
    assert valid_synth is False
    assert synth_reason == "SYNTHETIC_UNIFORM_VECTOR"

    # Zero vector
    zero_vec = np.zeros(128, dtype=np.float32)
    valid_zero, zero_reason = validate_template_embedding(zero_vec)
    assert valid_zero is False
    assert zero_reason == "ZERO_NORM"

    # NaN vector
    nan_vec = np.ones(128, dtype=np.float32)
    nan_vec[0] = np.nan
    valid_nan, nan_reason = validate_template_embedding(nan_vec)
    assert valid_nan is False
    assert nan_reason == "NON_FINITE_VALUES"

    # Dimension mismatch
    dim_mismatch_vec = np.random.randn(64).astype(np.float32)
    valid_dim, dim_reason = validate_template_embedding(dim_mismatch_vec, expected_dim=128)
    assert valid_dim is False
    assert "DIMENSION_MISMATCH" in dim_reason

    # Test engine behavior with synthetic template saved on disk
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    storage.save_profile("synthetic_user", synthetic_vec)

    engine = FaceRecognitionEngine(
        detector=MagicMock(),
        recognizer=MagicMock(),
        storage=storage,
        profile_name="synthetic_user",
    )

    # Engine must refuse to activate synthetic template and report is_enrolled = False
    assert engine.is_enrolled is False
    res = engine.process_frame(np.zeros((480, 640, 3), dtype=np.uint8))
    assert res.recognized is False
    assert res.reason == "NO_ENROLLED_PROFILE"
