"""
Unit Tests for Biometric Storage, Encryption, and Decryption
"""

import sys
import pytest
import numpy as np
from pathlib import Path

from apps.agent.facesentry_agent.biometric_storage import (
    BiometricStorage,
    MockEncryptedStorageBackend,
    WindowsDPAPIBackend,
    EnrolledProfile,
)


def test_mock_backend_encryption_roundtrip(tmp_path):
    """Verify save, load, and decryption using isolated mock backend."""
    mock_backend = MockEncryptedStorageBackend(key_byte=0x42)
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=mock_backend)

    # 1. Create a dummy 512-D embedding
    np.random.seed(42)
    vec = np.random.randn(512).astype(np.float32)
    vec /= np.linalg.norm(vec)

    # 2. Save profile
    dest = storage.save_profile(
        profile_name="test_user",
        reference_embedding=vec,
        sample_count=5,
        quality_metrics={"avg_blur": 120.5},
    )
    assert dest.is_file()
    assert storage.has_profile("test_user") is True

    # 3. Ensure file on disk does NOT contain plaintext float bytes
    with open(dest, "rb") as f:
        disk_bytes = f.read()
    assert disk_bytes.startswith(MockEncryptedStorageBackend.MAGIC_HEADER)
    # The raw unencrypted float array should not match the disk bytes directly
    assert vec.tobytes() not in disk_bytes

    # 4. Load profile
    loaded = storage.load_profile("test_user")
    assert loaded.profile_name == "test_user"
    assert loaded.embedding_dim == 512
    assert loaded.sample_count == 5
    assert np.allclose(loaded.reference_embedding, vec, atol=1e-6)


def test_missing_profile_raises_error(tmp_path):
    """Verify that loading a non-existent profile raises FileNotFoundError."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    with pytest.raises(FileNotFoundError):
        storage.load_profile("non_existent_profile")


def test_corrupted_profile_data_raises_error(tmp_path):
    """Verify that corrupted ciphertext raises ValueError."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    
    # Write corrupted garbage data
    bad_file = tmp_path / "corrupted_user.dat"
    with open(bad_file, "wb") as f:
        f.write(b"GARBAGE_NOT_ENCRYPTED_HEADER")

    with pytest.raises(ValueError):
        storage.load_profile("corrupted_user")


def test_profile_deletion(tmp_path):
    """Verify that delete_profile removes template from disk."""
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=MockEncryptedStorageBackend())
    vec = np.ones(512, dtype=np.float32)

    storage.save_profile("user_to_delete", vec)
    assert storage.has_profile("user_to_delete") is True

    deleted = storage.delete_profile("user_to_delete")
    assert deleted is True
    assert storage.has_profile("user_to_delete") is False


def test_profile_repr_does_not_leak_biometrics():
    """Verify that EnrolledProfile string representation does not expose raw vector numbers."""
    vec = np.array([0.12345, 0.67891], dtype=np.float32)
    profile = EnrolledProfile(
        profile_name="secret_agent",
        created_at="2026-08-22T00:00:00Z",
        updated_at="2026-08-22T00:00:00Z",
        sample_count=3,
        embedding_dim=2,
        reference_embedding=vec,
        quality_metrics={},
    )
    repr_str = repr(profile)
    assert "0.12345" not in repr_str
    assert "0.67891" not in repr_str
    assert "secret_agent" in repr_str


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI tests require Windows OS")
def test_windows_dpapi_backend_roundtrip(tmp_path):
    """Verify Windows native DPAPI encryption and decryption on Windows."""
    dpapi_backend = WindowsDPAPIBackend()
    storage = BiometricStorage(enrollment_dir=str(tmp_path), backend=dpapi_backend)

    np.random.seed(50)
    vec = np.random.randn(512).astype(np.float32)
    vec /= np.linalg.norm(vec)

    storage.save_profile("dpapi_user", vec, sample_count=3)
    loaded = storage.load_profile("dpapi_user")

    assert loaded.profile_name == "dpapi_user"
    assert np.allclose(loaded.reference_embedding, vec, atol=1e-6)
