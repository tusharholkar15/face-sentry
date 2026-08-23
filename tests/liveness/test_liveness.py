"""
Comprehensive Unit Tests for Temporal Liveness Detection Subsystem
"""

import time
import pytest
import numpy as np
from apps.agent.facesentry_agent.models.face_detector import DetectedFace
from apps.agent.facesentry_agent.liveness import (
    LivenessState,
    LivenessConfig,
    LivenessResult,
    TemporalLivenessStateMachine,
    BlinkDetector,
    HeadMovementDetector,
)


def create_mock_face(
    bbox=(100, 100, 150, 150),
    confidence=0.95,
    yaw_offset=0.0,
    pitch_offset=0.0,
    eye_tilt=0.0,
) -> DetectedFace:
    """Helper to synthesize a DetectedFace with custom landmark perturbations."""
    re_x, re_y = 130.0, 140.0
    le_x, le_y = 190.0, 140.0 + eye_tilt
    nose_x = 160.0 + yaw_offset
    nose_y = 175.0 + pitch_offset
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


def test_no_face_input():
    """Verify that an empty frame list returns unverified status."""
    sm = TemporalLivenessStateMachine()
    res = sm.process_frame([])
    assert res.verified is False
    assert res.reason == "NO_FACE_IN_FRAME"
    assert res.state == LivenessState.INITIALIZING


def test_single_frame_cannot_verify():
    """Security rule: A single frame must NEVER transition to VERIFIED."""
    sm = TemporalLivenessStateMachine()
    face = create_mock_face()
    res = sm.process_frame([face], eye_openness_override=0.8)
    
    assert res.verified is False
    assert res.state in [LivenessState.INITIALIZING, LivenessState.OBSERVING]
    assert res.reason != "ALL_LIVENESS_SIGNALS_SATISFIED"


def test_static_photo_attack_fails_over_100_frames():
    """Security rule: 100 identical static frames (photo print attack) cannot verify."""
    sm = TemporalLivenessStateMachine(
        LivenessConfig(
            blink_required=True,
            head_movement_required=True,
            liveness_timeout_seconds=30.0,
        )
    )
    static_face = create_mock_face(yaw_offset=0.0, pitch_offset=0.0)

    for i in range(100):
        # Open eyes, completely static landmarks
        res = sm.process_frame([static_face], eye_openness_override=0.85)
        assert res.verified is False
        assert res.blink_detected is False
        assert res.head_movement_detected is False


def test_valid_blink_detection_cycle():
    """Verify standard biological eye blink cycle: Open -> Closed -> Reopen."""
    detector = BlinkDetector(LivenessConfig(min_blink_duration_frames=2, max_blink_duration_frames=6))
    face = create_mock_face()

    # 1. Open for 2 frames
    assert detector.process(face, eye_openness_override=0.8) is False
    assert detector.process(face, eye_openness_override=0.8) is False

    # 2. Closed for 3 frames (valid duration)
    assert detector.process(face, eye_openness_override=0.2) is False
    assert detector.process(face, eye_openness_override=0.2) is False
    assert detector.process(face, eye_openness_override=0.2) is False

    # 3. Reopened -> Blink completed!
    assert detector.process(face, eye_openness_override=0.8) is True


def test_invalid_blink_too_short():
    """Verify blink rejected if closed for fewer than min duration frames."""
    detector = BlinkDetector(LivenessConfig(min_blink_duration_frames=3))
    face = create_mock_face()

    detector.process(face, eye_openness_override=0.8)
    # Closed for only 1 frame
    detector.process(face, eye_openness_override=0.2)
    # Immediately open
    completed = detector.process(face, eye_openness_override=0.8)
    assert completed is False


def test_invalid_blink_too_long():
    """Verify blink rejected if eye held closed too long (e.g. squint / sleep)."""
    detector = BlinkDetector(LivenessConfig(max_blink_duration_frames=4))
    face = create_mock_face()

    detector.process(face, eye_openness_override=0.8)
    # Closed for 8 frames
    for _ in range(8):
        detector.process(face, eye_openness_override=0.2)
    # Reopen
    completed = detector.process(face, eye_openness_override=0.8)
    assert completed is False


def test_valid_head_movement_detection():
    """Verify head movement detected when yaw/pitch angle variations occur over window."""
    detector = HeadMovementDetector(LivenessConfig(min_head_movement_delta=0.08, head_movement_window_frames=10))

    # Feed frames with dynamic yaw movement (turning head left then right)
    yaw_offsets = [0.0, 2.0, 5.0, 9.0, 14.0, 9.0, 3.0, -4.0, -8.0, 0.0]
    movement_detected = False

    for yaw in yaw_offsets:
        face = create_mock_face(yaw_offset=yaw)
        detected, score = detector.process(face)
        if detected:
            movement_detected = True

    assert movement_detected is True


def test_insufficient_head_movement():
    """Verify subtle noise does not trigger head movement requirement."""
    detector = HeadMovementDetector(LivenessConfig(min_head_movement_delta=0.10, head_movement_window_frames=10))

    # Minor sub-pixel jitter
    for i in range(15):
        noise = 0.1 * (i % 2)
        face = create_mock_face(yaw_offset=noise)
        detected, score = detector.process(face)
        assert detected is False


def test_dual_signals_satisfaction_transitions_to_verified():
    """Verify that completing both blink and head movement transitions to VERIFIED."""
    sm = TemporalLivenessStateMachine(
        LivenessConfig(
            blink_required=True,
            head_movement_required=True,
            min_sequential_frames_for_verification=5,
        )
    )

    # 1. Provide initial open eye frames with head movement
    yaws = [0.0, 3.0, 7.0, 12.0, 6.0]
    for yaw in yaws:
        face = create_mock_face(yaw_offset=yaw)
        res = sm.process_frame([face], eye_openness_override=0.8)

    assert res.head_movement_detected is True
    assert res.blink_detected is False
    assert res.state == LivenessState.HEAD_MOVEMENT_DETECTED

    # 2. Perform valid blink (closed 3 frames -> open)
    sm.process_frame([create_mock_face()], eye_openness_override=0.2)
    sm.process_frame([create_mock_face()], eye_openness_override=0.2)
    sm.process_frame([create_mock_face()], eye_openness_override=0.2)
    res_final = sm.process_frame([create_mock_face()], eye_openness_override=0.8)

    assert res_final.blink_detected is True
    assert res_final.head_movement_detected is True
    assert res_final.state == LivenessState.VERIFIED
    assert res_final.verified is True
    assert res_final.reason == "ALL_LIVENESS_SIGNALS_SATISFIED"


def test_liveness_timeout_expiration():
    """Verify session transitions to TIMEOUT when time threshold is exceeded."""
    sm = TemporalLivenessStateMachine(LivenessConfig(liveness_timeout_seconds=0.1))
    face = create_mock_face()

    # Initial frame
    sm.process_frame([face], eye_openness_override=0.8)
    time.sleep(0.15)
    # Subsequent frame after timeout
    res = sm.process_frame([face], eye_openness_override=0.8)

    assert res.state == LivenessState.TIMEOUT
    assert res.verified is False
    assert res.reason == "LIVENESS_OBSERVATION_TIMEOUT"


def test_reset_after_face_disappearance():
    """Verify state machine resets after prolonged face disappearance."""
    sm = TemporalLivenessStateMachine(LivenessConfig(no_face_reset_timeout_seconds=0.1))
    face = create_mock_face()

    sm.process_frame([face], eye_openness_override=0.8)
    assert sm.current_state == LivenessState.OBSERVING

    time.sleep(0.15)
    # Face disappears
    res_no_face = sm.process_frame([])
    assert res_no_face.state == LivenessState.INITIALIZING
    assert res_no_face.reason == "FACE_DISAPPEARED_TIMEOUT_RESET"


def test_noisy_landmark_input_robustness():
    """Verify system remains stable under random Gaussian landmark noise."""
    sm = TemporalLivenessStateMachine()
    np.random.seed(42)

    for _ in range(20):
        noise_yaw = float(np.random.randn() * 2.0)
        noise_pitch = float(np.random.randn() * 2.0)
        face = create_mock_face(yaw_offset=noise_yaw, pitch_offset=noise_pitch)
        res = sm.process_frame([face])
        assert isinstance(res, LivenessResult)
        assert res.state in [LivenessState.OBSERVING, LivenessState.HEAD_MOVEMENT_DETECTED, LivenessState.INITIALIZING]
