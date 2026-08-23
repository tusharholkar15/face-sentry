"""
Unit Tests for Enrollment Quality Gates
"""

import numpy as np
import pytest
from apps.agent.facesentry_agent.models.face_detector import DetectedFace
from apps.agent.facesentry_agent.enrollment import FaceQualityGate, QualityGateConfig


def create_dummy_face(
    bbox=(100, 100, 150, 150),
    confidence=0.95,
    eye_tilt=0.0,
    yaw_offset=0.0,
) -> DetectedFace:
    """Helper to synthesize a DetectedFace with specific landmark geometry."""
    # Landmarks: [right_eye, left_eye, nose, right_mouth, left_mouth]
    # Eye centers separated horizontally by 60px
    re_x, re_y = 130.0, 140.0
    le_x, le_y = 190.0, 140.0 + eye_tilt
    nose_x = 160.0 + yaw_offset
    nose_y = 175.0
    rm_x, rm_y = 140.0, 210.0
    lm_x, lm_y = 180.0, 210.0

    landmarks = np.array([
        [re_x, re_y],
        [le_x, le_y],
        [nose_x, nose_y],
        [rm_x, rm_y],
        [lm_x, lm_y],
    ], dtype=np.float32)

    raw_array = np.zeros(15, dtype=np.float32)
    raw_array[0:4] = bbox
    raw_array[4:14] = landmarks.flatten()
    raw_array[14] = confidence

    return DetectedFace(
        bbox=bbox,
        landmarks=landmarks,
        confidence=confidence,
        raw_face_array=raw_array,
    )


def test_quality_gate_rejects_empty_and_no_faces():
    """Verify empty frame and zero-face rejection."""
    gate = FaceQualityGate()
    
    # Empty frame
    res_empty = gate.evaluate(np.zeros((0, 0, 3), dtype=np.uint8), [])
    assert res_empty.passed is False
    assert res_empty.reason == "EMPTY_FRAME"

    # Frame with no faces
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    res_no_face = gate.evaluate(img, [])
    assert res_no_face.passed is False
    assert res_no_face.reason == "NO_FACE_DETECTED"


def test_quality_gate_rejects_multiple_faces():
    """Verify rejection when more than 1 face is present in frame."""
    gate = FaceQualityGate()
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    face1 = create_dummy_face(bbox=(50, 50, 100, 100))
    face2 = create_dummy_face(bbox=(250, 50, 100, 100))

    res = gate.evaluate(img, [face1, face2])
    assert res.passed is False
    assert res.reason == "MULTIPLE_FACES_DETECTED"


def test_quality_gate_rejects_small_face():
    """Verify rejection when face bounding box is below minimum threshold."""
    gate = FaceQualityGate(QualityGateConfig(min_face_size_pixels=100))
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    small_face = create_dummy_face(bbox=(50, 50, 70, 70))

    res = gate.evaluate(img, [small_face])
    assert res.passed is False
    assert res.reason == "FACE_TOO_SMALL"


def test_quality_gate_rejects_low_confidence():
    """Verify rejection when face detection confidence is low."""
    gate = FaceQualityGate(QualityGateConfig(min_confidence=0.85))
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    low_conf_face = create_dummy_face(confidence=0.60)

    res = gate.evaluate(img, [low_conf_face])
    assert res.passed is False
    assert res.reason == "LOW_DETECTION_CONFIDENCE"


def test_quality_gate_rejects_blurry_image():
    """Verify rejection when face region has low Laplacian variance (blurry)."""
    gate = FaceQualityGate(QualityGateConfig(min_blur_laplacian_var=80.0))
    
    # Completely uniform grey image has 0.0 Laplacian variance
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    face = create_dummy_face(bbox=(100, 100, 150, 150))

    res = gate.evaluate(img, [face])
    assert res.passed is False
    assert res.reason == "IMAGE_BLURRY"


def test_quality_gate_rejects_extreme_pose():
    """Verify rejection on extreme head tilt and extreme yaw."""
    gate = FaceQualityGate(QualityGateConfig(max_eye_tilt_degrees=15.0, max_yaw_ratio=0.35))
    
    # Synthesize textured image to pass blur check
    np.random.seed(42)
    img = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)

    # 1. Extreme tilt (tilt dy = 35px over dx = 60px -> ~30 degrees)
    tilt_face = create_dummy_face(eye_tilt=35.0)
    res_tilt = gate.evaluate(img, [tilt_face])
    assert res_tilt.passed is False
    assert res_tilt.reason == "EXTREME_HEAD_TILT"

    # 2. Extreme yaw (nose shifted horizontally by 30px on 60px eye span -> yaw ratio = 0.50)
    yaw_face = create_dummy_face(yaw_offset=30.0)
    res_yaw = gate.evaluate(img, [yaw_face])
    assert res_yaw.passed is False
    assert res_yaw.reason == "EXTREME_HEAD_YAW"


def test_quality_gate_accepts_good_face():
    """Verify acceptance when all quality parameters are satisfied."""
    gate = FaceQualityGate(QualityGateConfig(min_blur_laplacian_var=10.0))
    
    # Generate high frequency texture in face box
    np.random.seed(42)
    img = np.random.randint(60, 180, (480, 640, 3), dtype=np.uint8)
    good_face = create_dummy_face(bbox=(100, 100, 150, 150), confidence=0.96)

    res = gate.evaluate(img, [good_face])
    assert res.passed is True
    assert res.reason == "ACCEPTED"
    assert res.detected_face is not None
