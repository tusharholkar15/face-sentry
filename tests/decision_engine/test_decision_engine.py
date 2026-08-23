"""
Comprehensive Unit Tests for FaceSentry Authentication Decision Engine
Validates deterministic policy execution, state transitions, debounce, timeouts, and event generation.
"""

import pytest
from typing import List
from apps.agent.facesentry_agent.decision_engine import (
    AuthenticationDecisionEngine,
    DecisionState,
    DecisionEventType,
    DecisionConfig,
    DecisionEvent,
    DecisionResult,
)
from apps.agent.facesentry_agent.recognition import RecognitionResult
from apps.agent.facesentry_agent.liveness import LivenessResult, LivenessState


class MockClock:
    """Deterministic simulated clock for testing temporal state transitions."""
    def __init__(self, start_time: float = 1000.0):
        self.current_time = start_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def make_rec_result(
    recognized: bool = True,
    similarity: float = 0.85,
    face_count: int = 1,
    reason: str = "MATCH_CONFIRMED",
) -> RecognitionResult:
    return RecognitionResult(
        recognized=recognized,
        similarity=similarity,
        face_count=face_count,
        timestamp=0.0,
        reason=reason,
    )


def make_liv_result(
    verified: bool = True,
    state: LivenessState = LivenessState.VERIFIED,
    confidence: float = 0.95,
    reason: str = "ALL_LIVENESS_SIGNALS_SATISFIED",
) -> LivenessResult:
    return LivenessResult(
        state=state,
        verified=verified,
        blink_detected=True,
        head_movement_detected=True,
        temporal_score=1.0,
        confidence=confidence,
        reason=reason,
        timestamp=0.0,
    )


def test_authorized_user_continuous_authentication():
    """Test 1: Authorized user with verified liveness remains AUTHENTICATED_PRESENT."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(clock_fn=clock.time, on_event=events.append)

    rec = make_rec_result(recognized=True, similarity=0.90)
    liv = make_liv_result(verified=True)

    res = engine.evaluate(rec, liv)
    assert res.state == DecisionState.AUTHENTICATED_PRESENT
    assert res.authenticated is True
    assert res.lock_requested is False
    assert len(events) == 1
    assert events[0].event_type == DecisionEventType.FACE_AUTHENTICATED

    # Advance time and evaluate again (no duplicate event spam)
    clock.advance(1.0)
    res2 = engine.evaluate(rec, liv)
    assert res2.state == DecisionState.AUTHENTICATED_PRESENT
    assert res2.authenticated is True
    assert len(events) == 1  # No duplicate event


def test_authorized_face_returns_before_absence_timeout():
    """Test 2: No face starts absence countdown, but returning before timeout restores authentication."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=10.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    # Initial authentication
    engine.evaluate(make_rec_result(True), make_liv_result(True))

    # User steps away for 4 seconds (below 10s timeout)
    clock.advance(1.0)
    no_face_rec = make_rec_result(recognized=False, face_count=0)
    no_face_liv = make_liv_result(verified=False, state=LivenessState.INITIALIZING)

    res_absent1 = engine.evaluate(no_face_rec, no_face_liv)
    assert res_absent1.state == DecisionState.ABSENCE_COUNTDOWN
    assert res_absent1.lock_requested is False
    assert any(e.event_type == DecisionEventType.ABSENCE_STARTED for e in events)

    clock.advance(3.0)
    res_absent2 = engine.evaluate(no_face_rec, no_face_liv)
    assert res_absent2.state == DecisionState.ABSENCE_COUNTDOWN
    assert res_absent2.absence_duration == 3.0
    assert res_absent2.lock_requested is False

    # User returns at 4.0s
    clock.advance(1.0)
    res_return = engine.evaluate(make_rec_result(True), make_liv_result(True))
    assert res_return.state == DecisionState.AUTHENTICATED_PRESENT
    assert res_return.authenticated is True
    assert res_return.absence_duration == 0.0
    assert any(e.event_type == DecisionEventType.ABSENCE_CANCELLED for e in events)


def test_absence_reaches_timeout_triggers_lock():
    """Test 3: No face persisting for >= 10.0s triggers LOCKED_ACTION_DISPATCHED exactly once."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=10.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    no_face_rec = make_rec_result(recognized=False, face_count=0)
    no_face_liv = make_liv_result(verified=False)

    # Start absence at t=100.0
    engine.evaluate(no_face_rec, no_face_liv)

    # Advance time to t=110.1s (timeout exceeded)
    clock.advance(10.1)
    res_locked = engine.evaluate(no_face_rec, no_face_liv)

    assert res_locked.state == DecisionState.LOCKED_ACTION_DISPATCHED
    assert res_locked.lock_requested is True
    assert res_locked.authenticated is False
    assert any(e.event_type == DecisionEventType.LOCK_REQUESTED for e in events)

    # Subsequent evaluation does NOT re-emit lock_requested
    clock.advance(1.0)
    res_subsequent = engine.evaluate(no_face_rec, no_face_liv)
    assert res_subsequent.state == DecisionState.LOCKED_ACTION_DISPATCHED
    assert res_subsequent.lock_requested is False  # Single dispatch guarantee!


def test_unknown_face_disappears_before_timeout():
    """Test 4: Unknown stranger face disappears before 3s timeout without locking."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(unknown_face_timeout_seconds=3.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    stranger_rec = make_rec_result(recognized=False, similarity=0.20, face_count=1)
    liv = make_liv_result(verified=True)

    # Stranger arrives at t=100.0
    res1 = engine.evaluate(stranger_rec, liv)
    assert res1.state == DecisionState.STRANGER_COUNTDOWN
    assert res1.lock_requested is False
    assert any(e.event_type == DecisionEventType.UNKNOWN_FACE_STARTED for e in events)

    # Stranger leaves after 1.5s (before 3.0s)
    clock.advance(1.5)
    res_left = engine.evaluate(make_rec_result(False, face_count=0), make_liv_result(False))
    assert res_left.state == DecisionState.ABSENCE_COUNTDOWN
    assert res_left.lock_requested is False


def test_unknown_face_timeout_triggers_lock():
    """Test 5: Stranger presence persisting for >= 3.0s triggers LOCKED_ACTION_DISPATCHED."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(unknown_face_timeout_seconds=3.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    stranger_rec = make_rec_result(recognized=False, similarity=0.15, face_count=1)
    liv = make_liv_result(verified=True)

    engine.evaluate(stranger_rec, liv)
    clock.advance(3.1)
    res_lock = engine.evaluate(stranger_rec, liv)

    assert res_lock.state == DecisionState.LOCKED_ACTION_DISPATCHED
    assert res_lock.lock_requested is True
    assert any(e.event_type == DecisionEventType.LOCK_REQUESTED for e in events)


def test_recognized_identity_with_liveness_failure():
    """Test 6: Authorized identity without verified liveness enters SPOOF_ALERT and never authenticates."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(spoof_lock_timeout_seconds=3.0, require_liveness=True),
        clock_fn=clock.time,
        on_event=events.append,
    )

    # Photo attack: Match is True (0.92), but liveness is False
    rec_photo = make_rec_result(recognized=True, similarity=0.92, face_count=1)
    liv_photo = make_liv_result(verified=False, state=LivenessState.OBSERVING)

    res = engine.evaluate(rec_photo, liv_photo)
    assert res.state in [DecisionState.LIVENESS_FAILURE, DecisionState.SPOOF_ALERT]
    assert res.authenticated is False
    assert res.lock_requested is False
    assert any(e.event_type == DecisionEventType.LIVENESS_FAILURE for e in events)


def test_spoof_duration_timeout_triggers_lock():
    """Test 7: Static photo presentation attack persisting past SPOOF_LOCK_TIMEOUT triggers lock."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(spoof_lock_timeout_seconds=3.0, require_liveness=True),
        clock_fn=clock.time,
        on_event=events.append,
    )

    rec_photo = make_rec_result(recognized=True, similarity=0.95, face_count=1)
    liv_photo = make_liv_result(verified=False, state=LivenessState.OBSERVING)

    engine.evaluate(rec_photo, liv_photo)
    clock.advance(3.2)
    res_lock = engine.evaluate(rec_photo, liv_photo)

    assert res_lock.state == DecisionState.LOCKED_ACTION_DISPATCHED
    assert res_lock.lock_requested is True
    assert res_lock.authenticated is False


def test_camera_unavailable_is_distinct_from_no_face():
    """Test 8: Camera failure is treated as CAMERA_UNAVAILABLE rather than simple absence."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(camera_failure_timeout_seconds=5.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    res = engine.evaluate(None, None, camera_available=False)
    assert res.state == DecisionState.CAMERA_UNAVAILABLE
    assert res.authenticated is False
    assert "CAMERA_UNAVAILABLE" in res.reason
    assert any(e.event_type == DecisionEventType.CAMERA_UNAVAILABLE for e in events)


def test_multiple_rapid_state_transitions():
    """Test 9: Engine handles rapid toggling between states deterministically."""
    clock = MockClock(100.0)
    engine = AuthenticationDecisionEngine(clock_fn=clock.time)

    # Frame 1: Authorized
    res1 = engine.evaluate(make_rec_result(True), make_liv_result(True))
    assert res1.authenticated is True

    # Frame 2: Stranger
    clock.advance(0.1)
    res2 = engine.evaluate(make_rec_result(False), make_liv_result(True))
    assert res2.state == DecisionState.STRANGER_COUNTDOWN

    # Frame 3: No Face
    clock.advance(0.1)
    res3 = engine.evaluate(make_rec_result(False, face_count=0), make_liv_result(False))
    assert res3.state == DecisionState.ABSENCE_COUNTDOWN

    # Frame 4: Authorized again
    clock.advance(0.1)
    res4 = engine.evaluate(make_rec_result(True), make_liv_result(True))
    assert res4.state == DecisionState.AUTHENTICATED_PRESENT
    assert res4.authenticated is True


def test_lock_request_emitted_exactly_once():
    """Test 10: lock_requested flag is True on exactly 1 evaluation frame."""
    clock = MockClock(100.0)
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=5.0),
        clock_fn=clock.time,
    )

    no_face = make_rec_result(False, face_count=0)
    no_liv = make_liv_result(False)

    engine.evaluate(no_face, no_liv)
    clock.advance(5.1)

    # Frame of trigger
    res_trigger = engine.evaluate(no_face, no_liv)
    assert res_trigger.lock_requested is True

    # Subsequent frames
    for _ in range(10):
        clock.advance(0.1)
        res_sub = engine.evaluate(no_face, no_liv)
        assert res_sub.lock_requested is False


def test_timer_reset_behavior():
    """Test 11: All active duration counters reset properly."""
    clock = MockClock(100.0)
    engine = AuthenticationDecisionEngine(clock_fn=clock.time)

    # Advance stranger timer
    engine.evaluate(make_rec_result(False, face_count=1), make_liv_result(True))
    clock.advance(2.0)
    res_stranger = engine.evaluate(make_rec_result(False, face_count=1), make_liv_result(True))
    assert res_stranger.stranger_duration == 2.0

    # User re-authenticates
    res_auth = engine.evaluate(make_rec_result(True), make_liv_result(True))
    assert res_auth.stranger_duration == 0.0
    assert res_auth.absence_duration == 0.0
    assert res_auth.spoof_duration == 0.0


def test_clock_determinism():
    """Test 12: Timers strictly track injected mock clock time."""
    clock = MockClock(5000.0)
    engine = AuthenticationDecisionEngine(clock_fn=clock.time)

    engine.evaluate(make_rec_result(False, face_count=0), make_liv_result(False))
    clock.advance(4.25)
    res = engine.evaluate(make_rec_result(False, face_count=0), make_liv_result(False))
    assert res.absence_duration == 4.25
    assert res.timestamp == 5004.25


def test_recovery_after_lock():
    """Test 13: start_recovery resets locked state and enables fresh authentication."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=2.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    # Lock system
    engine.evaluate(make_rec_result(False, face_count=0), make_liv_result(False))
    clock.advance(2.5)
    res_locked = engine.evaluate(make_rec_result(False, face_count=0), make_liv_result(False))
    assert res_locked.state == DecisionState.LOCKED_ACTION_DISPATCHED

    # Start recovery
    engine.start_recovery()
    assert engine.current_state == DecisionState.RECOVERY_PENDING
    assert any(e.event_type == DecisionEventType.RECOVERY_STARTED for e in events)

    # Re-authenticate user
    clock.advance(1.0)
    res_reauth = engine.evaluate(make_rec_result(True), make_liv_result(True))
    assert res_reauth.state == DecisionState.AUTHENTICATED_PRESENT
    assert res_reauth.authenticated is True


def test_configurable_threshold_updates():
    """Test 14: Custom timeout settings take immediate effect."""
    clock = MockClock(100.0)
    # Custom 1-second timeout
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=1.0),
        clock_fn=clock.time,
    )

    no_face = make_rec_result(False, face_count=0)
    no_liv = make_liv_result(False)

    engine.evaluate(no_face, no_liv)
    clock.advance(1.1)
    res = engine.evaluate(no_face, no_liv)
    assert res.state == DecisionState.LOCKED_ACTION_DISPATCHED
    assert res.lock_requested is True


def test_post_lock_duplicate_dispatch_prevention():
    """Test 15: Post-lock evaluation prevents duplicate lock dispatch events."""
    clock = MockClock(100.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=2.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    no_face = make_rec_result(False, face_count=0)
    no_liv = make_liv_result(False)

    # Initial frame
    engine.evaluate(no_face, no_liv)
    clock.advance(2.5)

    # Trigger lock dispatch
    res_lock = engine.evaluate(no_face, no_liv)
    assert res_lock.lock_requested is True
    assert res_lock.state == DecisionState.LOCKED_ACTION_DISPATCHED

    # Count LOCK_REQUESTED events
    lock_event_count_before = sum(1 for e in events if e.event_type == DecisionEventType.LOCK_REQUESTED)
    assert lock_event_count_before == 1

    # Subsequent frames while locked
    clock.advance(1.0)
    res_next = engine.evaluate(no_face, no_liv)
    assert res_next.state == DecisionState.LOCKED_ACTION_DISPATCHED
    assert res_next.lock_requested is False  # Must not request lock again

    lock_event_count_after = sum(1 for e in events if e.event_type == DecisionEventType.LOCK_REQUESTED)
    assert lock_event_count_after == 1  # No duplicate lock events emitted


def test_absence_timer_lifecycle_precise_countdown():
    """
    Test 16: Precise step-by-step absence countdown simulation:
    t=0   -> NO_FACE -> ABSENCE_STARTED (duration=0.0s)
    t=5   -> still NO_FACE -> ABSENCE_COUNTDOWN (duration=5.0s)
    t=9.9 -> still NO_FACE -> ABSENCE_COUNTDOWN (duration=9.9s, lock_requested=False)
    t=10+ -> still NO_FACE -> ABSENCE_TIMEOUT -> LOCK_REQUESTED (lock_requested=True)
    """
    clock = MockClock(1000.0)
    events: List[DecisionEvent] = []
    engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=10.0),
        clock_fn=clock.time,
        on_event=events.append,
    )

    no_face = make_rec_result(False, face_count=0)
    no_liv = make_liv_result(False)

    # t = 0: Absence starts
    res_0 = engine.evaluate(no_face, no_liv)
    assert res_0.state == DecisionState.ABSENCE_COUNTDOWN
    assert res_0.absence_duration == 0.0
    assert res_0.lock_requested is False
    assert any(e.event_type == DecisionEventType.ABSENCE_STARTED for e in events)

    # t = 5.0: Mid-countdown
    clock.advance(5.0)
    res_5 = engine.evaluate(no_face, no_liv)
    assert res_5.state == DecisionState.ABSENCE_COUNTDOWN
    assert res_5.absence_duration == 5.0
    assert res_5.lock_requested is False

    # t = 9.9: Just before timeout
    clock.advance(4.9)
    res_9_9 = engine.evaluate(no_face, no_liv)
    assert res_9_9.state == DecisionState.ABSENCE_COUNTDOWN
    assert round(res_9_9.absence_duration, 1) == 9.9
    assert res_9_9.lock_requested is False

    # t = 10.05: Timeout exceeded
    clock.advance(0.15)
    res_10 = engine.evaluate(no_face, no_liv)
    assert res_10.state == DecisionState.LOCKED_ACTION_DISPATCHED
    assert res_10.lock_requested is True
    assert res_10.reason == "LOCK_TRIGGERED_BY_ABSENCE_TIMEOUT"
    assert any(e.event_type == DecisionEventType.LOCK_REQUESTED for e in events)


