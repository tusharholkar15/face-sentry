"""
FaceSentry Authentication Decision Engine
Authoritative policy layer coordinating Identity Recognition, Temporal Liveness,
and Presence Timeouts into a deterministic state machine.

CRITICAL ARCHITECTURAL BOUNDARIES:
- Does NOT execute webcam capture, neural network inference, or liveness algorithms.
- Does NOT directly execute Win32 LockWorkStation or manipulate browser sessions.
- Emits explicit transition-level events (e.g. LOCK_REQUESTED) and typed DecisionResult.
- Enforces single lock dispatch (prevents repeated frame-by-frame lock spam).
- Supports deterministic testing via injected clock functions.
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable

from .recognition import RecognitionResult
from .liveness import LivenessResult, LivenessState

logger = logging.getLogger("facesentry.decision_engine")


class DecisionState(str, Enum):
    """Authoritative states of the authentication decision engine."""
    INITIALIZING = "INITIALIZING"
    AUTHENTICATED_PRESENT = "AUTHENTICATED_PRESENT"
    ABSENCE_COUNTDOWN = "ABSENCE_COUNTDOWN"
    STRANGER_COUNTDOWN = "STRANGER_COUNTDOWN"
    LIVENESS_FAILURE = "LIVENESS_FAILURE"
    SPOOF_ALERT = "SPOOF_ALERT"
    LOCK_PENDING = "LOCK_PENDING"
    LOCKED_ACTION_DISPATCHED = "LOCKED_ACTION_DISPATCHED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    CAMERA_UNAVAILABLE = "CAMERA_UNAVAILABLE"


class DecisionEventType(str, Enum):
    """Transition-level events emitted on state boundaries."""
    FACE_AUTHENTICATED = "FACE_AUTHENTICATED"
    ABSENCE_STARTED = "ABSENCE_STARTED"
    ABSENCE_CANCELLED = "ABSENCE_CANCELLED"
    UNKNOWN_FACE_STARTED = "UNKNOWN_FACE_STARTED"
    UNKNOWN_FACE_CANCELLED = "UNKNOWN_FACE_CANCELLED"
    LIVENESS_FAILURE = "LIVENESS_FAILURE"
    SPOOF_ALERT = "SPOOF_ALERT"
    LOCK_REQUESTED = "LOCK_REQUESTED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    CAMERA_UNAVAILABLE = "CAMERA_UNAVAILABLE"


@dataclass(frozen=True)
class DecisionConfig:
    """Configurable security policy timeouts and thresholds."""
    absence_timeout_seconds: float = 10.0
    unknown_face_timeout_seconds: float = 3.0
    spoof_lock_timeout_seconds: float = 3.0
    camera_failure_timeout_seconds: float = 5.0
    debounce_frames: int = 2
    require_liveness: bool = True


@dataclass(frozen=True)
class DecisionEvent:
    """Structured transition event for audit logs and system telemetry."""
    event_type: DecisionEventType
    reason: str
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionResult:
    """Authoritative decision evaluation result for a single cycle."""
    state: DecisionState
    authenticated: bool
    lock_requested: bool
    reason: str
    timestamp: float
    absence_duration: float
    stranger_duration: float
    spoof_duration: float
    recognition_similarity: float
    liveness_confidence: float


class AuthenticationDecisionEngine:
    """
    Stateful decision engine combining biometric identity, liveness verification,
    presence duration history, and camera health into deterministic state transitions.
    """

    def __init__(
        self,
        config: Optional[DecisionConfig] = None,
        clock_fn: Callable[[], float] = time.time,
        on_event: Optional[Callable[[DecisionEvent], None]] = None,
    ):
        self.config = config or DecisionConfig()
        self.clock_fn = clock_fn
        self.on_event = on_event

        self._state: DecisionState = DecisionState.INITIALIZING
        self._absence_start_time: Optional[float] = None
        self._stranger_start_time: Optional[float] = None
        self._spoof_start_time: Optional[float] = None
        self._camera_failure_start_time: Optional[float] = None
        self._lock_dispatched: bool = False

        self._consecutive_authenticated_frames = 0
        self._consecutive_unrecognized_frames = 0
        self._last_absence_log_sec: int = -1
        self._last_stranger_log_sec: int = -1

    @property
    def current_state(self) -> DecisionState:
        return self._state

    def reset(self) -> None:
        """Reset decision state to INITIALIZING and clear all active timers."""
        self._state = DecisionState.INITIALIZING
        self._absence_start_time = None
        self._stranger_start_time = None
        self._spoof_start_time = None
        self._camera_failure_start_time = None
        self._lock_dispatched = False
        self._consecutive_authenticated_frames = 0
        self._consecutive_unrecognized_frames = 0
        self._last_absence_log_sec = -1
        self._last_stranger_log_sec = -1

    def start_recovery(self) -> None:
        """Initiate recovery sequence after a lock dispatch (e.g. PIN unlocked or admin resume)."""
        now = self.clock_fn()
        self._emit_event(DecisionEventType.RECOVERY_STARTED, "User authentication recovery initiated", now)
        self.reset()
        self._state = DecisionState.RECOVERY_PENDING

    def _emit_event(
        self,
        event_type: DecisionEventType,
        reason: str,
        timestamp: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit transition-level event if listener is registered."""
        event = DecisionEvent(
            event_type=event_type,
            reason=reason,
            timestamp=timestamp,
            details=details or {},
        )
        logger.info(f"Decision Event: [{event.event_type.value}] Reason: {reason}")
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as exc:
                logger.error(f"Error invoking decision event callback: {exc}")

    def evaluate(
        self,
        recognition: Optional[RecognitionResult],
        liveness: Optional[LivenessResult],
        camera_available: bool = True,
        current_time_override: Optional[float] = None,
    ) -> DecisionResult:
        """
        Evaluate recognition and liveness signals against security policy.
        Returns authoritative DecisionResult.
        """
        now = current_time_override if current_time_override is not None else self.clock_fn()
        lock_requested = False

        # If already locked, maintain state without emitting duplicate lock requests
        if self._state == DecisionState.LOCKED_ACTION_DISPATCHED:
            return DecisionResult(
                state=DecisionState.LOCKED_ACTION_DISPATCHED,
                authenticated=False,
                lock_requested=False,
                reason="LOCKED_ACTION_ALREADY_DISPATCHED",
                timestamp=now,
                absence_duration=0.0,
                stranger_duration=0.0,
                spoof_duration=0.0,
                recognition_similarity=recognition.similarity if recognition else 0.0,
                liveness_confidence=liveness.confidence if liveness else 0.0,
            )

        # 1. Camera Health / Availability Check
        if not camera_available:
            self._consecutive_authenticated_frames = 0
            if self._camera_failure_start_time is None:
                self._camera_failure_start_time = now
                self._emit_event(DecisionEventType.CAMERA_UNAVAILABLE, "Camera hardware disconnected or stream failed", now)

            cam_fail_duration = now - self._camera_failure_start_time
            if cam_fail_duration >= self.config.camera_failure_timeout_seconds and not self._lock_dispatched:
                self._state = DecisionState.LOCKED_ACTION_DISPATCHED
                self._lock_dispatched = True
                lock_requested = True
                self._emit_event(DecisionEventType.LOCK_REQUESTED, "Camera failure timeout exceeded", now, {"duration": cam_fail_duration})
            else:
                self._state = DecisionState.CAMERA_UNAVAILABLE

            return DecisionResult(
                state=self._state,
                authenticated=False,
                lock_requested=lock_requested,
                reason=f"CAMERA_UNAVAILABLE_DURATION_{cam_fail_duration:.1f}S",
                timestamp=now,
                absence_duration=0.0,
                stranger_duration=0.0,
                spoof_duration=0.0,
                recognition_similarity=0.0,
                liveness_confidence=0.0,
            )
        else:
            self._camera_failure_start_time = None

        # Extract telemetry metrics
        face_count = recognition.face_count if recognition else 0
        is_identity_matched = recognition.recognized if recognition else False
        similarity = recognition.similarity if recognition else 0.0
        is_liveness_verified = liveness.verified if liveness else False
        liveness_conf = liveness.confidence if liveness else 0.0

        # Calculate active durations
        absence_duration = (now - self._absence_start_time) if self._absence_start_time else 0.0
        stranger_duration = (now - self._stranger_start_time) if self._stranger_start_time else 0.0
        spoof_duration = (now - self._spoof_start_time) if self._spoof_start_time else 0.0

        # 2. Case: No Face Detected in Frame
        if face_count == 0:
            self._consecutive_authenticated_frames = 0
            self._stranger_start_time = None
            self._spoof_start_time = None
            self._last_stranger_log_sec = -1

            if self._absence_start_time is None:
                self._absence_start_time = now
                self._last_absence_log_sec = 0
                self._state = DecisionState.ABSENCE_COUNTDOWN
                logger.info(f"ABSENCE_STARTED t={now:.3f}")
                self._emit_event(DecisionEventType.ABSENCE_STARTED, "No face detected in video stream", now)

            absence_duration = now - self._absence_start_time
            curr_absence_sec = int(absence_duration)
            if curr_absence_sec > self._last_absence_log_sec:
                self._last_absence_log_sec = curr_absence_sec
                logger.info(f"ABSENCE_DURATION={absence_duration:.1f}s/{self.config.absence_timeout_seconds:.1f}s")

            if absence_duration >= self.config.absence_timeout_seconds:
                self._state = DecisionState.LOCKED_ACTION_DISPATCHED
                self._lock_dispatched = True
                lock_requested = True
                logger.info(f"ABSENCE_TIMEOUT_REACHED (Duration: {absence_duration:.2f}s >= {self.config.absence_timeout_seconds:.1f}s)")
                logger.warning("LOCK_REQUESTED Reason: Absence timeout exceeded")
                self._emit_event(DecisionEventType.LOCK_REQUESTED, "Absence timeout exceeded", now, {"duration": absence_duration})
                reason = "LOCK_TRIGGERED_BY_ABSENCE_TIMEOUT"
            else:
                self._state = DecisionState.ABSENCE_COUNTDOWN
                reason = f"ABSENCE_COUNTDOWN_{absence_duration:.1f}S_OF_{self.config.absence_timeout_seconds}S"

            return DecisionResult(
                state=self._state,
                authenticated=False,
                lock_requested=lock_requested,
                reason=reason,
                timestamp=now,
                absence_duration=round(absence_duration, 2),
                stranger_duration=0.0,
                spoof_duration=0.0,
                recognition_similarity=similarity,
                liveness_confidence=liveness_conf,
            )

        # Cancel absence timer if face is present
        if self._absence_start_time is not None:
            logger.info(f"ABSENCE_CANCELLED (Face detected after {absence_duration:.1f}s)")
            self._emit_event(DecisionEventType.ABSENCE_CANCELLED, "Face presence restored", now, {"absence_duration": absence_duration})
            self._absence_start_time = None
            self._last_absence_log_sec = -1
            absence_duration = 0.0

        # 3. Case: Multiple Faces Detected
        if face_count > 1:
            self._consecutive_authenticated_frames = 0
            if self._stranger_start_time is None:
                self._stranger_start_time = now
                self._last_stranger_log_sec = 0
                self._state = DecisionState.STRANGER_COUNTDOWN
                logger.info(f"STRANGER_STARTED t={now:.3f} (Multiple faces detected)")
                self._emit_event(DecisionEventType.UNKNOWN_FACE_STARTED, "Multiple faces detected in frame", now)

            stranger_duration = now - self._stranger_start_time
            curr_stranger_sec = int(stranger_duration)
            if curr_stranger_sec > self._last_stranger_log_sec:
                self._last_stranger_log_sec = curr_stranger_sec
                logger.info(f"STRANGER_DURATION={stranger_duration:.1f}s/{self.config.unknown_face_timeout_seconds:.1f}s")

            if stranger_duration >= self.config.unknown_face_timeout_seconds:
                self._state = DecisionState.LOCKED_ACTION_DISPATCHED
                self._lock_dispatched = True
                lock_requested = True
                logger.info(f"STRANGER_TIMEOUT_REACHED (Duration: {stranger_duration:.2f}s >= {self.config.unknown_face_timeout_seconds:.1f}s)")
                logger.warning("LOCK_REQUESTED Reason: Multiple faces timeout exceeded")
                self._emit_event(DecisionEventType.LOCK_REQUESTED, "Multiple faces timeout exceeded", now, {"duration": stranger_duration})
                reason = "LOCK_TRIGGERED_BY_MULTIPLE_FACES"
            else:
                self._state = DecisionState.STRANGER_COUNTDOWN
                reason = f"MULTIPLE_FACES_COUNTDOWN_{stranger_duration:.1f}S"

            return DecisionResult(
                state=self._state,
                authenticated=False,
                lock_requested=lock_requested,
                reason=reason,
                timestamp=now,
                absence_duration=0.0,
                stranger_duration=round(stranger_duration, 2),
                spoof_duration=0.0,
                recognition_similarity=similarity,
                liveness_confidence=liveness_conf,
            )

        # 4. Case: Single Face - Unrecognized Identity (Stranger)
        if not is_identity_matched:
            self._consecutive_authenticated_frames = 0
            self._consecutive_unrecognized_frames += 1
            self._spoof_start_time = None

            if self._stranger_start_time is None:
                self._stranger_start_time = now
                self._last_stranger_log_sec = 0
                self._state = DecisionState.STRANGER_COUNTDOWN
                logger.info(f"STRANGER_STARTED t={now:.3f}")
                self._emit_event(DecisionEventType.UNKNOWN_FACE_STARTED, "Unrecognized face present in frame", now, {"similarity": similarity})

            stranger_duration = now - self._stranger_start_time
            curr_stranger_sec = int(stranger_duration)
            if curr_stranger_sec > self._last_stranger_log_sec:
                self._last_stranger_log_sec = curr_stranger_sec
                logger.info(f"STRANGER_DURATION={stranger_duration:.1f}s/{self.config.unknown_face_timeout_seconds:.1f}s")

            if stranger_duration >= self.config.unknown_face_timeout_seconds:
                self._state = DecisionState.LOCKED_ACTION_DISPATCHED
                self._lock_dispatched = True
                lock_requested = True
                logger.info(f"STRANGER_TIMEOUT_REACHED (Duration: {stranger_duration:.2f}s >= {self.config.unknown_face_timeout_seconds:.1f}s)")
                logger.warning("LOCK_REQUESTED Reason: Unknown face timeout exceeded")
                self._emit_event(DecisionEventType.LOCK_REQUESTED, "Unknown face timeout exceeded", now, {"duration": stranger_duration})
                reason = "LOCK_TRIGGERED_BY_UNKNOWN_FACE_TIMEOUT"
            else:
                self._state = DecisionState.STRANGER_COUNTDOWN
                reason = f"STRANGER_COUNTDOWN_{stranger_duration:.1f}S_OF_{self.config.unknown_face_timeout_seconds}S"

            return DecisionResult(
                state=self._state,
                authenticated=False,
                lock_requested=lock_requested,
                reason=reason,
                timestamp=now,
                absence_duration=0.0,
                stranger_duration=round(stranger_duration, 2),
                spoof_duration=0.0,
                recognition_similarity=similarity,
                liveness_confidence=liveness_conf,
            )

        # Cancel stranger timer if identity is matched
        if self._stranger_start_time is not None:
            self._emit_event(DecisionEventType.UNKNOWN_FACE_CANCELLED, "Authorized identity verified", now, {"stranger_duration": stranger_duration})
            self._stranger_start_time = None
            stranger_duration = 0.0

        # 5. Case: Authorized Identity Matched, but Liveness Verification Failed
        liveness_required = self.config.require_liveness
        if liveness_required and not is_liveness_verified:
            self._consecutive_authenticated_frames = 0

            if self._spoof_start_time is None:
                self._spoof_start_time = now
                self._state = DecisionState.LIVENESS_FAILURE
                self._emit_event(DecisionEventType.LIVENESS_FAILURE, "Authorized identity detected but liveness unverified", now)

            spoof_duration = now - self._spoof_start_time
            if spoof_duration >= self.config.spoof_lock_timeout_seconds:
                self._state = DecisionState.LOCKED_ACTION_DISPATCHED
                self._lock_dispatched = True
                lock_requested = True
                self._emit_event(DecisionEventType.LOCK_REQUESTED, "Liveness failure timeout exceeded", now, {"spoof_duration": spoof_duration})
                reason = "LOCK_TRIGGERED_BY_LIVENESS_FAILURE_TIMEOUT"
            else:
                self._state = DecisionState.SPOOF_ALERT
                reason = f"LIVENESS_UNVERIFIED_COUNTDOWN_{spoof_duration:.1f}S"

            return DecisionResult(
                state=self._state,
                authenticated=False,
                lock_requested=lock_requested,
                reason=reason,
                timestamp=now,
                absence_duration=0.0,
                stranger_duration=0.0,
                spoof_duration=round(spoof_duration, 2),
                recognition_similarity=similarity,
                liveness_confidence=liveness_conf,
            )

        # 6. Case: Authorized Identity + Verified Liveness -> Fully Authenticated Present
        self._consecutive_authenticated_frames += 1
        self._spoof_start_time = None
        self._absence_start_time = None
        self._stranger_start_time = None

        if self._state != DecisionState.AUTHENTICATED_PRESENT:
            self._state = DecisionState.AUTHENTICATED_PRESENT
            self._emit_event(
                DecisionEventType.FACE_AUTHENTICATED,
                "Authorized user recognized and liveness verified",
                now,
                {"similarity": similarity, "liveness_confidence": liveness_conf},
            )

        return DecisionResult(
            state=DecisionState.AUTHENTICATED_PRESENT,
            authenticated=True,
            lock_requested=False,
            reason="AUTHORIZED_USER_PRESENT_AND_VERIFIED",
            timestamp=now,
            absence_duration=0.0,
            stranger_duration=0.0,
            spoof_duration=0.0,
            recognition_similarity=similarity,
            liveness_confidence=liveness_conf,
        )
