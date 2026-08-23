"""
Unit Tests for Model Management and Checksum Verification
"""

import pytest
from pathlib import Path
from apps.agent.facesentry_agent.models.model_manager import (
    ModelManager,
    ModelNotFoundError,
    ModelCorruptedError,
    PINNED_MODELS,
)


def test_model_manager_paths(tmp_path):
    """Verify model manager resolves correct file paths."""
    manager = ModelManager(models_dir=str(tmp_path))
    yunet_path = manager.get_model_path("face_detection_yunet")
    assert yunet_path == tmp_path / "face_detection_yunet_2023mar.onnx"


def test_missing_model_raises_error(tmp_path):
    """Verify that verifying a non-existent model raises ModelNotFoundError."""
    manager = ModelManager(models_dir=str(tmp_path))
    with pytest.raises(ModelNotFoundError) as exc_info:
        manager.verify_model("face_detection_yunet")
    assert "face_detection_yunet_2023mar.onnx" in str(exc_info.value)


def test_corrupted_model_hash_raises_error(tmp_path):
    """Verify that a corrupted model file fails SHA-256 integrity check."""
    manager = ModelManager(models_dir=str(tmp_path))
    model_file = tmp_path / "face_detection_yunet_2023mar.onnx"
    
    # Write invalid content
    with open(model_file, "wb") as f:
        f.write(b"CORRUPTED_ONNX_HEADER")

    with pytest.raises(ModelCorruptedError) as exc_info:
        manager.verify_model("face_detection_yunet")
    assert "failed SHA-256 integrity check" in str(exc_info.value)


def test_check_all_models_dict(tmp_path):
    """Verify check_all_models returns dictionary of booleans."""
    manager = ModelManager(models_dir=str(tmp_path))
    status = manager.check_all_models()
    assert "face_detection_yunet" in status
    assert "face_recognition_sface" in status
    assert status["face_detection_yunet"] is False
    assert status["face_recognition_sface"] is False
