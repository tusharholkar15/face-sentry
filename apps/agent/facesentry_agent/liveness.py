"""
Temporal Liveness & Anti-Spoofing Subsystem
Implements a temporal state machine detecting biological micro-actions (eye blinks, head movement)
across sequential frames to mitigate static 2D photo and presentation attacks.

CRITICAL SECURITY NOTICE:
- Blink and head movement analysis reduces basic static presentation attacks (e.g. printed photos, static screens).
- It is NOT a complete defense against sophisticated deepfakes or high-frame-rate video replay attacks.
- Liveness is an anti-spoofing verification signal, NEVER an identity authentication factor.
- Identity recognition and liveness MUST BOTH be satisfied independently by the policy engine.
- Zero raw frames or biometric video buffers are persisted to disk or exposed in logs.
"""

import time
import math
import logging
from enum import Enum
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any
import numpy as np

from .models.face_detector import DetectedFace

logger = logging.getLogger("facesentry.liveness")


class LivenessState(str, Enum):
    """States of the temporal liveness state machine."""
    INITIALIZING = "INITIALIZING"
    OBSERVING = "OBSERVING"
    BLINK_DETECTED = "BLINK_DETECTED"
    HEAD_MOVEMENT_DETECTED = "HEAD_MOVEMENT_DETECTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class LivenessConfig:
    """Configurable parameters and thresholds for the liveness state machine."""
    blink_required: bool = True
    head_movement_required: bool = True
    liveness_timeout_seconds: float = 10.0
    min_blink_duration_frames: int = 2
    max_blink_duration_frames: int = 12
    blink_open_threshold: float = 0.60
    blink_closed_threshold: float = 0.35
    min_head_movement_delta: float = 0.08
    head_movement_window_frames: int = 15
    no_face_reset_timeout_seconds: float = 2.0
    verification_validity_duration_seconds: float = 5.0
    min_sequential_frames_for_verification: int = 5


@dataclass(frozen=True)
class LivenessResult:
    """Structured result returned by the liveness detection subsystem."""
    state: LivenessState
    verified: bool
    blink_detected: bool
    head_movement_detected: bool
    temporal_score: float
    confidence: float
    reason: str
    timestamp: float


class BlinkDetector:
    """
    Detects natural eye blink cycles (Open -> Closed -> Reopened)
    across consecutive temporal frames using facial landmark geometry and ocular aperture.
    """

    def __init__(self, config: LivenessConfig):
        self.config = config
        self._state = "AWAITING_OPEN"
        self._closed_frame_count = 0
        self._blink_completed = False
        self._last_blink_time: Optional[float] = None

    def reset(self) -> None:
        """Reset blink detection state."""
        self._state = "AWAITING_OPEN"
        self._closed_frame_count = 0
        self._blink_completed = False

    def process(self, face: DetectedFace, eye_openness_override: Optional[float] = None) -> bool:
        """
        Process a face detection frame.
        Returns True at the exact frame a full valid blink cycle completes.
        """
        if eye_openness_override is not None:
            openness = eye_openness_override
        else:
            # Estimate ocular openness from landmarks
            # Landmarks: [0: right_eye, 1: left_eye, 2: nose, 3: right_mouth, 4: left_mouth]
            landmarks = face.landmarks
            right_eye = landmarks[0]
            left_eye = landmarks[1]
            nose = landmarks[2]
            mouth_mid_y = (landmarks[3][1] + landmarks[4][1]) / 2.0

            eye_dist = math.hypot(left_eye[0] - right_eye[0], left_eye[1] - right_eye[1])
            if eye_dist < 1.0:
                openness = 0.5
            else:
                eye_mid_y = (right_eye[1] + left_eye[1]) / 2.0
                face_height_proxy = max(1.0, mouth_mid_y - eye_mid_y)
                # Vertical eye-to-nose ratio proxy for baseline openness
                eye_nose_dist = abs(nose[1] - eye_mid_y)
                openness = min(1.0, max(0.0, (eye_nose_dist / face_height_proxy) * 2.0))

        is_open = openness >= self.config.blink_open_threshold
        is_closed = openness <= self.config.blink_closed_threshold

        now = time.time()
        # Cooldown check
        if self._last_blink_time and (now - self._last_blink_time) < 0.3:
            return False

        if self._state == "AWAITING_OPEN":
            if is_open:
                self._state = "OPEN"
                self._closed_frame_count = 0

        elif self._state == "OPEN":
            if is_closed:
                self._state = "CLOSING"
                self._closed_frame_count = 1

        elif self._state == "CLOSING":
            if is_closed:
                self._closed_frame_count += 1
                if self._closed_frame_count > self.config.max_blink_duration_frames:
                    # Eye held closed too long (e.g. sleeping, squinting, or occlusion) -> Reset
                    self._state = "AWAITING_OPEN"
                    self._closed_frame_count = 0
            elif is_open:
                # Reopened! Verify closed duration was within physiological human blink range
                if self._closed_frame_count >= self.config.min_blink_duration_frames:
                    self._state = "OPEN"
                    self._closed_frame_count = 0
                    self._blink_completed = True
                    self._last_blink_time = now
                    logger.info("Valid biological eye blink detected.")
                    return True
                else:
                    # Too fast (noise)
                    self._state = "OPEN"
                    self._closed_frame_count = 0

        return False


class HeadMovementDetector:
    """
    Tracks 3D head pose and spatial landmark variance across a sliding temporal window.
    Static 2D photos yield near-zero variance.
    """

    def __init__(self, config: LivenessConfig):
        self.config = config
        self._history: deque = deque(maxlen=self.config.head_movement_window_frames)

    def reset(self) -> None:
        """Clear temporal history."""
        self._history.clear()

    def process(self, face: DetectedFace) -> Tuple[bool, float]:
        """
        Record landmark geometry and evaluate spatial variance across history window.
        Returns (movement_detected: bool, movement_score: float).
        """
        landmarks = face.landmarks
        right_eye = landmarks[0]
        left_eye = landmarks[1]
        nose = landmarks[2]

        dx = left_eye[0] - right_eye[0]
        dy = left_eye[1] - right_eye[1]
        eye_dist = math.hypot(dx, dy)
        if eye_dist < 1.0:
            return False, 0.0

        eye_mid_x = (right_eye[0] + left_eye[0]) / 2.0
        eye_mid_y = (right_eye[1] + left_eye[1]) / 2.0

        # Relative normalized landmark metrics
        yaw_proxy = (nose[0] - eye_mid_x) / eye_dist
        pitch_proxy = (nose[1] - eye_mid_y) / eye_dist
        roll_angle = math.atan2(dy, dx)
        scale_proxy = eye_dist

        self._history.append({
            "yaw": yaw_proxy,
            "pitch": pitch_proxy,
            "roll": roll_angle,
            "scale": scale_proxy,
            "time": time.time(),
        })

        if len(self._history) < self.config.min_sequential_frames_for_verification:
            return False, 0.0

        yaws = [h["yaw"] for h in self._history]
        pitches = [h["pitch"] for h in self._history]
        rolls = [h["roll"] for h in self._history]
        scales = [h["scale"] for h in self._history]

        delta_yaw = max(yaws) - min(yaws)
        delta_pitch = max(pitches) - min(pitches)
        delta_roll = max(rolls) - min(rolls)
        delta_scale = (max(scales) - min(scales)) / max(1.0, min(scales))

        # Composite dynamic movement score
        movement_score = float(delta_yaw * 1.5 + delta_pitch * 1.5 + delta_roll * 1.0 + delta_scale * 0.5)

        movement_detected = movement_score >= self.config.min_head_movement_delta
        if movement_detected:
            logger.debug(f"Natural head movement detected (Score: {movement_score:.3f} >= {self.config.min_head_movement_delta})")

        return movement_detected, round(movement_score, 4)


class TemporalLivenessStateMachine:
    """
    State machine coordinating temporal observations, blink verification,
    head movement tracking, timeouts, and face disappearance resets.
    """

    def __init__(self, config: Optional[LivenessConfig] = None):
        self.config = config or LivenessConfig()
        self.blink_detector = BlinkDetector(self.config)
        self.movement_detector = HeadMovementDetector(self.config)

        self._state: LivenessState = LivenessState.INITIALIZING
        self._session_start_time: Optional[float] = None
        self._last_face_time: Optional[float] = None
        self._verified_time: Optional[float] = None
        self._sequential_frame_count = 0

        self._blink_satisfied = False
        self._movement_satisfied = False
        self._last_temporal_score = 0.0

    @property
    def current_state(self) -> LivenessState:
        return self._state

    def reset(self) -> None:
        """Reset state machine to INITIALIZING and clear all tracking data."""
        self._state = LivenessState.INITIALIZING
        self._session_start_time = None
        self._last_face_time = None
        self._verified_time = None
        self._sequential_frame_count = 0
        self._blink_satisfied = False
        self._movement_satisfied = False
        self._last_temporal_score = 0.0
        self.blink_detector.reset()
        self.movement_detector.reset()

    def process_frame(
        self,
        detected_faces: List[DetectedFace],
        eye_openness_override: Optional[float] = None,
    ) -> LivenessResult:
        """
        Process incoming detection output for a single frame.
        Evaluates temporal state transitions and returns LivenessResult.
        """
        now = time.time()

        # Handle face disappearance
        if len(detected_faces) == 0:
            if self._last_face_time and (now - self._last_face_time) > self.config.no_face_reset_timeout_seconds:
                self.reset()
                return LivenessResult(
                    state=LivenessState.INITIALIZING,
                    verified=False,
                    blink_detected=False,
                    head_movement_detected=False,
                    temporal_score=0.0,
                    confidence=0.0,
                    reason="FACE_DISAPPEARED_TIMEOUT_RESET",
                    timestamp=now,
                )
            return LivenessResult(
                state=self._state,
                verified=self._state == LivenessState.VERIFIED and self._is_verification_valid(now),
                blink_detected=self._blink_satisfied,
                head_movement_detected=self._movement_satisfied,
                temporal_score=self._last_temporal_score,
                confidence=0.0,
                reason="NO_FACE_IN_FRAME",
                timestamp=now,
            )

        if len(detected_faces) > 1:
            # Ambiguous multi-face
            return LivenessResult(
                state=self._state,
                verified=False,
                blink_detected=self._blink_satisfied,
                head_movement_detected=self._movement_satisfied,
                temporal_score=self._last_temporal_score,
                confidence=0.0,
                reason="MULTIPLE_FACES_REJECTED",
                timestamp=now,
            )

        face = detected_faces[0]
        self._last_face_time = now
        self._sequential_frame_count += 1

        # Initialize session timer
        if self._session_start_time is None:
            self._session_start_time = now
            self._state = LivenessState.OBSERVING

        # Check if already verified and still within validity duration
        if self._state == LivenessState.VERIFIED:
            if self._is_verification_valid(now):
                return LivenessResult(
                    state=LivenessState.VERIFIED,
                    verified=True,
                    blink_detected=self._blink_satisfied,
                    head_movement_detected=self._movement_satisfied,
                    temporal_score=1.0,
                    confidence=face.confidence,
                    reason="LIVENESS_MAINTAINED",
                    timestamp=now,
                )
            else:
                # Validity expired -> Re-verify
                self.reset()
                self._session_start_time = now
                self._state = LivenessState.OBSERVING

        # Check for session timeout
        if (now - self._session_start_time) > self.config.liveness_timeout_seconds:
            self._state = LivenessState.TIMEOUT
            return LivenessResult(
                state=LivenessState.TIMEOUT,
                verified=False,
                blink_detected=self._blink_satisfied,
                head_movement_detected=self._movement_satisfied,
                temporal_score=self._last_temporal_score,
                confidence=face.confidence,
                reason="LIVENESS_OBSERVATION_TIMEOUT",
                timestamp=now,
            )

        # 1. Process Blink Signal
        blink_occurred = self.blink_detector.process(face, eye_openness_override=eye_openness_override)
        if blink_occurred:
            self._blink_satisfied = True

        # 2. Process Head Movement Signal
        movement_occurred, movement_score = self.movement_detector.process(face)
        self._last_temporal_score = movement_score
        if movement_occurred:
            self._movement_satisfied = True

        # Determine state transitions
        blink_ok = self._blink_satisfied or (not self.config.blink_required)
        movement_ok = self._movement_satisfied or (not self.config.head_movement_required)

        # Single frame safety rule: never verify on fewer than min_sequential_frames
        can_verify = self._sequential_frame_count >= self.config.min_sequential_frames_for_verification

        if blink_ok and movement_ok and can_verify:
            self._state = LivenessState.VERIFIED
            self._verified_time = now
            logger.info("Liveness state transitioned to VERIFIED.")
            return LivenessResult(
                state=LivenessState.VERIFIED,
                verified=True,
                blink_detected=self._blink_satisfied,
                head_movement_detected=self._movement_satisfied,
                temporal_score=max(1.0, self._last_temporal_score),
                confidence=face.confidence,
                reason="ALL_LIVENESS_SIGNALS_SATISFIED",
                timestamp=now,
            )

        # Intermediate progress states
        if self._blink_satisfied and not self._movement_satisfied:
            self._state = LivenessState.BLINK_DETECTED
            reason = "BLINK_CONFIRMED_AWAITING_HEAD_MOVEMENT"
        elif self._movement_satisfied and not self._blink_satisfied:
            self._state = LivenessState.HEAD_MOVEMENT_DETECTED
            reason = "HEAD_MOVEMENT_CONFIRMED_AWAITING_BLINK"
        else:
            self._state = LivenessState.OBSERVING
            reason = "OBSERVING_TEMPORAL_SIGNALS"

        return LivenessResult(
            state=self._state,
            verified=False,
            blink_detected=self._blink_satisfied,
            head_movement_detected=self._movement_satisfied,
            temporal_score=self._last_temporal_score,
            confidence=face.confidence,
            reason=reason,
            timestamp=now,
        )

    def _is_verification_valid(self, current_time: float) -> bool:
        if self._verified_time is None:
            return False
        return (current_time - self._verified_time) <= self.config.verification_validity_duration_seconds
