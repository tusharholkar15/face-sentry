"""
Unit Tests for Agent Telemetry Publisher
Validates snapshot formatting, privacy rules, rate limiting, and state deduplication.
"""

import time
import pytest
from apps.agent.telemetry_publisher import AgentTelemetryPublisher
from apps.agent.facesentry_agent.recognition import RecognitionResult
from apps.agent.facesentry_agent.liveness import LivenessResult, LivenessState
from apps.agent.facesentry_agent.decision_engine import DecisionResult, DecisionState


class MockClock:
    def __init__(self, start_time: float = 1000.0):
        self.current_time = start_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def test_telemetry_snapshot_privacy_and_serialization():
    """Verify snapshot contains only non-biometric status indicators (no vectors/landmarks/PINs)."""
    clock = MockClock(100.0)
    publisher = AgentTelemetryPublisher(enable_network_publish=False, clock_fn=clock.time)

    dec = DecisionResult(
        state=DecisionState.AUTHENTICATED_PRESENT,
        authenticated=True,
        lock_requested=False,
        reason="AUTHORIZED_USER_PRESENT",
        timestamp=100.0,
        absence_duration=0.0,
        stranger_duration=0.0,
        spoof_duration=0.0,
        recognition_similarity=0.89,
        liveness_confidence=0.96,
    )
    rec = RecognitionResult(
        recognized=True,
        similarity=0.89,
        face_count=1,
        timestamp=100.0,
        reason="MATCH",
    )
    liv = LivenessResult(
        state=LivenessState.VERIFIED,
        verified=True,
        blink_detected=True,
        head_movement_detected=True,
        temporal_score=1.0,
        confidence=0.96,
        reason="VERIFIED",
        timestamp=100.0,
    )

    snapshot = publisher.create_snapshot(
        decision=dec,
        recognition=rec,
        liveness=liv,
        camera_available=True,
        uptime_seconds=45.2,
    )

    assert snapshot.agent_status == "RUNNING"
    assert snapshot.camera_status == "CONNECTED"
    assert snapshot.authentication_state == "AUTHENTICATED"
    assert snapshot.recognition_similarity == 0.89
    assert snapshot.liveness_verified is True
    assert snapshot.decision_state == "AUTHENTICATED_PRESENT"
    assert snapshot.lock_requested is False

    # Privacy check: inspect JSON serialized payload
    json_str = snapshot.model_dump_json().lower()
    forbidden = ["embedding", "landmark", "pin", "crop", "vector", "face_bytes"]
    for term in forbidden:
        assert term not in json_str


def test_telemetry_rate_limiting():
    """Verify snapshots are throttled to configured max update rate (e.g. 5 Hz / 200ms)."""
    clock = MockClock(100.0)
    publisher = AgentTelemetryPublisher(
        max_updates_per_second=5.0,  # 200ms interval
        enable_network_publish=False,
        clock_fn=clock.time,
    )

    dec = DecisionResult(
        state=DecisionState.AUTHENTICATED_PRESENT,
        authenticated=True,
        lock_requested=False,
        reason="AUTHORIZED",
        timestamp=100.0,
        absence_duration=0.0,
        stranger_duration=0.0,
        spoof_duration=0.0,
        recognition_similarity=0.90,
        liveness_confidence=0.95,
    )

    # First publish cycle at t=100.0s -> Published!
    res1 = publisher.publish_cycle(dec, None, None, True, 1.0)
    assert res1 is not None

    # Immediate next cycle at t=100.05s (50ms later) -> Blocked by rate limiter
    clock.advance(0.05)
    res2 = publisher.publish_cycle(dec, None, None, True, 1.05)
    assert res2 is None

    # Advance to t=100.25s (250ms elapsed) with state change -> Published!
    clock.advance(0.20)
    dec_changed = DecisionResult(
        state=DecisionState.ABSENCE_COUNTDOWN,
        authenticated=False,
        lock_requested=False,
        reason="ABSENT",
        timestamp=100.25,
        absence_duration=0.25,
        stranger_duration=0.0,
        spoof_duration=0.0,
        recognition_similarity=0.0,
        liveness_confidence=0.0,
    )
    res3 = publisher.publish_cycle(dec_changed, None, None, True, 1.25)
    assert res3 is not None


def test_telemetry_state_deduplication():
    """Verify identical unchanged states within 1s are deduplicated."""
    clock = MockClock(100.0)
    publisher = AgentTelemetryPublisher(
        max_updates_per_second=5.0,
        enable_network_publish=False,
        clock_fn=clock.time,
    )

    dec = DecisionResult(
        state=DecisionState.AUTHENTICATED_PRESENT,
        authenticated=True,
        lock_requested=False,
        reason="AUTHORIZED",
        timestamp=100.0,
        absence_duration=0.0,
        stranger_duration=0.0,
        spoof_duration=0.0,
        recognition_similarity=0.90,
        liveness_confidence=0.95,
    )

    # Cycle 1 at t=100.0s
    assert publisher.publish_cycle(dec, None, None, True, 1.0) is not None

    # Cycle 2 at t=100.3s (after min_interval, but identical state hash) -> Deduplicated
    clock.advance(0.3)
    assert publisher.publish_cycle(dec, None, None, True, 1.3) is None

    # Cycle 3 at t=101.1s (1.1s elapsed) -> Heartbeat published even if unchanged
    clock.advance(0.8)
    assert publisher.publish_cycle(dec, None, None, True, 2.1) is not None
