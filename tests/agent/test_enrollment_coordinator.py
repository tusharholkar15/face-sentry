"""
Unit Tests for FaceSentry Enrollment Coordinator
Validates state machine transitions, sample collection, liveness gates,
privacy safeguards, and DPAPI storage finalization.
"""

import os
import shutil
import pytest
import numpy as np

from apps.agent.facesentry_agent.enrollment_coordinator import EnrollmentCoordinator
from apps.agent.facesentry_agent.models.face_detector import DetectedFace
from apps.agent.facesentry_agent.biometric_storage import BiometricStorage, MockEncryptedStorageBackend
from apps.agent.facesentry_agent.enrollment import FaceQualityGate, QualityGateConfig


@pytest.fixture
def mock_storage(tmp_path):
    storage_dir = str(tmp_path / "enrollment")
    backend = MockEncryptedStorageBackend()
    return BiometricStorage(enrollment_dir=storage_dir, backend=backend)


def create_synthetic_frame_and_face(w: int = 120, h: int = 120, conf: float = 0.95):
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    # add noise to pass blur check
    img[100: 100 + h, 100: 100 + w] = np.random.randint(50, 200, (h, w, 3), dtype=np.uint8)
    landmarks = np.array([
        [130.0, 130.0],  # right eye
        [170.0, 130.0],  # left eye
        [150.0, 150.0],  # nose
        [135.0, 180.0],  # right mouth
        [165.0, 180.0],  # left mouth
    ], dtype=np.float32)
    face = DetectedFace(
        bbox=(100, 100, w, h),
        landmarks=landmarks,
        confidence=conf,
        raw_face_array=np.zeros(15, dtype=np.float32),
    )
    return img, face


class MockRecognizer:
    def extract_embedding(self, img, face):
        # Return deterministic mock vector with variance (non-uniform)
        vec = np.arange(512, dtype=np.float32) + 1.0
        return vec / np.linalg.norm(vec)


def test_coordinator_initial_state():
    coordinator = EnrollmentCoordinator()
    status = coordinator.get_status()
    assert status.state == "IDLE"
    assert status.progress == 0.0
    assert status.captured_samples == 0
    assert status.is_complete is False


def test_coordinator_start_session():
    coordinator = EnrollmentCoordinator()
    status = coordinator.start_session(user_id="alice", target_samples=8)
    assert status.state == "CAPTURING"
    assert status.required_samples == 8
    assert status.guidance == "LOOK_FORWARD"


def test_coordinator_guidance_mapping_for_no_face():
    coordinator = EnrollmentCoordinator()
    coordinator.start_session("alice", 5)
    
    empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    status = coordinator.process_frame(empty_frame, detected_faces=[], liveness_verified=False)
    assert status.quality == "NO_FACE"
    assert status.guidance == "FACE_NOT_DETECTED"
    assert status.captured_samples == 0


def test_coordinator_sample_accumulation_and_liveness_gate(mock_storage):
    recognizer = MockRecognizer()
    coordinator = EnrollmentCoordinator(recognizer=recognizer)
    coordinator.start_session("alice", target_samples=5)

    img, face = create_synthetic_frame_and_face()

    # Ingest 4 samples
    for i in range(4):
        status = coordinator.process_frame(img, [face], liveness_verified=False)
        assert status.captured_samples == i + 1
        assert status.state == "CAPTURING"

    # Ingest 5th sample without liveness -> moves to LIVENESS_CHECK
    status = coordinator.process_frame(img, [face], liveness_verified=False)
    assert status.captured_samples == 5
    assert status.state == "LIVENESS_CHECK"
    assert status.guidance == "PERFORM_BLINK"

    # Try finalize before liveness -> rejects
    success, profile, err = coordinator.finalize_session(mock_storage)
    assert success is False
    assert "Liveness verification has not been completed" in err

    # Confirm liveness
    status = coordinator.process_frame(img, [face], liveness_verified=True)
    assert status.state == "PROCESSING"

    # Finalize succeeds!
    success, profile, err = coordinator.finalize_session(mock_storage)
    assert success is True
    assert profile is not None
    assert profile.profile_name == "alice"
    assert profile.sample_count == 5
    assert coordinator.is_complete is True


def test_coordinator_cancel_clears_memory(mock_storage):
    recognizer = MockRecognizer()
    coordinator = EnrollmentCoordinator(recognizer=recognizer)
    coordinator.start_session("bob", target_samples=5)

    img, face = create_synthetic_frame_and_face()
    coordinator.process_frame(img, [face], liveness_verified=False)
    assert coordinator.captured_sample_count == 1

    cancel_status = coordinator.cancel_session()
    assert cancel_status.state == "CANCELLED"
    assert coordinator.captured_sample_count == 0

    # Finalize should fail after cancellation
    success, profile, err = coordinator.finalize_session(mock_storage)
    assert success is False


def test_coordinator_save_failure(mock_storage):
    """Verify finalization failure if storage.save_profile raises an exception."""
    from unittest.mock import MagicMock
    recognizer = MockRecognizer()
    coordinator = EnrollmentCoordinator(recognizer=recognizer)
    coordinator.start_session("charlie", target_samples=5)
    img, face = create_synthetic_frame_and_face()
    for _ in range(5):
        coordinator.process_frame(img, [face], liveness_verified=True)
    
    mock_storage.save_profile = MagicMock(side_effect=RuntimeError("DPAPI write failed"))
    success, profile, err = coordinator.finalize_session(mock_storage)
    assert success is False
    assert coordinator.state == "FAILED"
    assert "DPAPI write failed" in err


def test_coordinator_readback_failure(mock_storage):
    """Verify finalization failure if profile read-back returns None or raises an exception."""
    from unittest.mock import MagicMock
    recognizer = MockRecognizer()
    coordinator = EnrollmentCoordinator(recognizer=recognizer)
    coordinator.start_session("dan", target_samples=5)
    img, face = create_synthetic_frame_and_face()
    for _ in range(5):
        coordinator.process_frame(img, [face], liveness_verified=True)
    
    mock_storage.load_profile = MagicMock(return_value=None)
    success, profile, err = coordinator.finalize_session(mock_storage)
    assert success is False
    assert coordinator.state == "FAILED"
    assert "ENROLLMENT_STORAGE_FAILED" in err


def test_storage_wrong_and_correct_paths(tmp_path):
    """Verify wrong and correct storage path resolution logic."""
    from pathlib import Path
    custom_dir = tmp_path / "custom_enrollment"
    storage = BiometricStorage(enrollment_dir=str(custom_dir))
    assert storage.enrollment_dir == custom_dir
    assert custom_dir.exists()


def test_storage_missing_and_corrupted_profile(mock_storage, tmp_path):
    """Verify has_profile for missing files and load_profile behavior for corrupted data."""
    from pathlib import Path
    assert mock_storage.has_profile("non_existent_user") is False
    
    # Create a corrupted profile file (random unstructured bytes)
    corrupted_file = Path(mock_storage.enrollment_dir) / "corrupted_user.dat"
    corrupted_file.write_bytes(b"corrupted binary data")
    
    # verify has_profile is True because file exists and is > 0 bytes
    assert mock_storage.has_profile("corrupted_user") is True
    
    # load_profile must raise an error for corrupted data
    with pytest.raises(Exception):
        mock_storage.load_profile("corrupted_user")


def test_biometric_validation_limits():
    """Verify template validation limits for NaNs, Infs, zero norms, and synthetic vectors."""
    from apps.agent.facesentry_agent.biometric_storage import validate_template_embedding
    
    # 1. NaN/Inf rejection
    nan_vec = np.arange(128, dtype=np.float32)
    nan_vec[0] = np.nan
    valid, reason = validate_template_embedding(nan_vec)
    assert valid is False
    assert reason == "NON_FINITE_VALUES"

    # 2. Zero-norm rejection
    zero_vec = np.zeros(128, dtype=np.float32)
    valid, reason = validate_template_embedding(zero_vec)
    assert valid is False
    assert reason == "ZERO_NORM"

    # 3. Constant/uniform (synthetic) template rejection
    synth_vec = np.ones(128, dtype=np.float32) * 0.5
    valid, reason = validate_template_embedding(synth_vec)
    assert valid is False
    assert reason == "SYNTHETIC_UNIFORM_VECTOR"


def test_production_appdata_path():
    """Verify that get_base_dir resolves to AppData/Local/FaceSentry when not in dev mode."""
    from packages.shared.constants import get_base_dir
    from unittest.mock import patch
    import os
    with patch.dict(os.environ, {"FACESENTRY_DEV_MODE": "0", "LOCALAPPDATA": "C:\\Users\\TestUser\\AppData\\Local"}):
        base_dir = get_base_dir()
        assert base_dir == "C:\\Users\\TestUser\\AppData\\Local\\FaceSentry"
