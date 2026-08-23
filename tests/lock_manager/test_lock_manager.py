"""
Comprehensive Unit Tests for FaceSentry Windows Workstation Lock Manager
Ensures safe simulation, mock Windows user32 bindings, cooldown debounce,
whitelisted reasons, and robust failure containment without locking developer workstation.
"""

import sys
import pytest
from unittest.mock import MagicMock
from typing import List

from apps.agent.facesentry_agent.lock_manager import (
    WorkstationLockManager,
    LockMode,
    LockDispatchStatus,
    LockDispatchResult,
    LockEvent,
)
from apps.agent.facesentry_agent.decision_engine import DecisionResult, DecisionState


class MockClock:
    """Deterministic simulated clock."""
    def __init__(self, start_time: float = 1000.0):
        self.current_time = start_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def test_non_windows_platform():
    """Test 1: Non-Windows platform is flagged as unsupported for real lock."""
    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="linux",
    )
    assert mgr.is_supported() is False
    res = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res.status == LockDispatchStatus.LOCK_BLOCKED_UNSUPPORTED
    assert res.success is False


def test_windows_api_successfully_loaded():
    """Test 2: Windows platform with valid user32 DLL is supported."""
    mock_user32 = MagicMock()
    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=mock_user32,
    )
    assert mgr.is_supported() is True


def test_windows_api_unavailable():
    """Test 3: Windows platform without user32 DLL handles unavailability gracefully."""
    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=None,
    )
    # If on non-Windows test runner or uninitialized DLL
    mgr._user32 = None
    assert mgr.is_supported() is False
    res = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res.status == LockDispatchStatus.LOCK_BLOCKED_UNSUPPORTED


def test_dry_run_mode():
    """Test 4: Default dry-run mode returns LOCK_SIMULATED and does not call user32."""
    mock_user32 = MagicMock()
    mgr = WorkstationLockManager(
        enable_real_windows_lock=False,
        platform_override="win32",
        user32_dll_override=mock_user32,
    )
    res = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res.mode == LockMode.DRY_RUN
    assert res.status == LockDispatchStatus.LOCK_SIMULATED
    assert res.success is True
    mock_user32.LockWorkStation.assert_not_called()


def test_real_lock_disabled_by_default():
    """Test 5: Explicitly verify real lock is disabled unless configured."""
    mgr = WorkstationLockManager()
    assert mgr.enable_real_windows_lock is False


def test_real_lock_enabled_with_mock_user32():
    """Test 6: Real-lock mode invokes user32.LockWorkStation() (mocked)."""
    mock_user32 = MagicMock()
    mock_user32.LockWorkStation.return_value = 1

    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=mock_user32,
    )
    res = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res.mode == LockMode.REAL
    assert res.status == LockDispatchStatus.LOCK_SUCCEEDED
    assert res.success is True
    mock_user32.LockWorkStation.assert_called_once()


def test_valid_absence_timeout_lock():
    """Test 7: Whitelisted ABSENCE_TIMEOUT reason is accepted."""
    mgr = WorkstationLockManager(enable_real_windows_lock=False)
    res = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res.status == LockDispatchStatus.LOCK_SIMULATED
    assert res.reason == "ABSENCE_TIMEOUT"


def test_valid_unknown_face_timeout_lock():
    """Test 8: Whitelisted UNKNOWN_FACE_TIMEOUT reason is accepted."""
    mgr = WorkstationLockManager(enable_real_windows_lock=False)
    res = mgr.request_lock("UNKNOWN_FACE_TIMEOUT")
    assert res.status == LockDispatchStatus.LOCK_SIMULATED
    assert res.reason == "UNKNOWN_FACE_TIMEOUT"


def test_valid_spoof_timeout_lock():
    """Test 9: Whitelisted SPOOF_TIMEOUT reason is accepted."""
    mgr = WorkstationLockManager(enable_real_windows_lock=False)
    res = mgr.request_lock("SPOOF_TIMEOUT")
    assert res.status == LockDispatchStatus.LOCK_SIMULATED
    assert res.reason == "SPOOF_TIMEOUT"


def test_invalid_lock_reason():
    """Test 10: Non-whitelisted reason is rejected."""
    mgr = WorkstationLockManager(enable_real_windows_lock=False, lock_reason_required=True)
    res = mgr.request_lock("UNAUTHORIZED_CMD_EXECUTE")
    assert res.status == LockDispatchStatus.INVALID_REASON
    assert res.success is False


def test_duplicate_dispatch_blocked_by_cooldown():
    """Test 11: Rapid repeated lock calls are debounced by cooldown timer."""
    clock = MockClock(100.0)
    mgr = WorkstationLockManager(
        enable_real_windows_lock=False,
        cooldown_seconds=5.0,
        clock_fn=clock.time,
    )
    # First call succeeds
    res1 = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res1.status == LockDispatchStatus.LOCK_SIMULATED

    # Call 1 second later -> blocked
    clock.advance(1.0)
    res2 = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res2.status == LockDispatchStatus.LOCK_SKIPPED_COOLDOWN
    assert res2.success is False


def test_cooldown_expiry_allows_new_lock():
    """Test 12: After cooldown period expires, lock can be dispatched again."""
    clock = MockClock(100.0)
    mgr = WorkstationLockManager(
        enable_real_windows_lock=False,
        cooldown_seconds=5.0,
        clock_fn=clock.time,
    )
    mgr.request_lock("ABSENCE_TIMEOUT")

    clock.advance(5.1)
    res_after = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res_after.status == LockDispatchStatus.LOCK_SIMULATED
    assert res_after.success is True


def test_lock_api_success_mock():
    """Test 13: LockWorkStation returning non-zero is treated as success."""
    mock_user32 = MagicMock()
    mock_user32.LockWorkStation.return_value = 1
    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=mock_user32,
    )
    res = mgr.request_lock("MANUAL_LOCK")
    assert res.status == LockDispatchStatus.LOCK_SUCCEEDED
    assert res.success is True


def test_lock_api_failure_mock():
    """Test 14: LockWorkStation returning 0 is treated as LOCK_FAILED."""
    mock_user32 = MagicMock()
    mock_user32.LockWorkStation.return_value = 0
    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=mock_user32,
    )
    res = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res.status == LockDispatchStatus.LOCK_FAILED
    assert res.success is False


def test_agent_remains_alive_after_exception():
    """Test 15: Exceptions in ctypes invocation are caught without crashing."""
    mock_user32 = MagicMock()
    mock_user32.LockWorkStation.side_effect = RuntimeError("Access Violation")
    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=mock_user32,
    )
    res = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res.status == LockDispatchStatus.LOCK_FAILED
    assert res.success is False
    assert "Access Violation" in str(res.error_message)


def test_event_generation():
    """Test 16: Structured audit events are emitted during lock workflow."""
    events: List[LockEvent] = []
    mgr = WorkstationLockManager(
        enable_real_windows_lock=False,
        on_event=events.append,
    )
    mgr.request_lock("ABSENCE_TIMEOUT")
    assert len(events) >= 2
    event_types = [e.event_type for e in events]
    assert "LOCK_REQUESTED" in event_types
    assert "LOCK_SIMULATED" in event_types


def test_no_biometric_data_in_event_payloads():
    """Test 17: LockEvent and LockDispatchResult never contain embeddings, raw crops, or PINs."""
    events: List[LockEvent] = []
    mgr = WorkstationLockManager(
        enable_real_windows_lock=False,
        on_event=events.append,
    )
    res = mgr.request_lock("ABSENCE_TIMEOUT")

    # Inspect result object and event fields
    forbidden_terms = ["embedding", "crop", "pin", "landmark", "vector", "face_bytes"]
    for event in events:
        event_str = f"{event.event_type} {event.reason} {event.mode} {event.result}".lower()
        for term in forbidden_terms:
            assert term not in event_str

    res_str = f"{res.reason} {res.mode} {res.status} {res.error_message}".lower()
    for term in forbidden_terms:
        assert term not in res_str


def test_lock_if_needed_from_decision_result():
    """Test: lock_if_needed only executes when decision_result.lock_requested is True."""
    mgr = WorkstationLockManager(enable_real_windows_lock=False)

    # Case 1: lock_requested is False
    dec_no_lock = DecisionResult(
        state=DecisionState.AUTHENTICATED_PRESENT,
        authenticated=True,
        lock_requested=False,
        reason="AUTHORIZED_USER_PRESENT",
        timestamp=100.0,
        absence_duration=0.0,
        stranger_duration=0.0,
        spoof_duration=0.0,
        recognition_similarity=0.90,
        liveness_confidence=0.95,
    )
    res1 = mgr.lock_if_needed(dec_no_lock)
    assert res1 is None

    # Case 2: lock_requested is True
    dec_lock = DecisionResult(
        state=DecisionState.LOCKED_ACTION_DISPATCHED,
        authenticated=False,
        lock_requested=True,
        reason="ABSENCE_TIMEOUT",
        timestamp=110.0,
        absence_duration=10.0,
        stranger_duration=0.0,
        spoof_duration=0.0,
        recognition_similarity=0.0,
        liveness_confidence=0.0,
    )
    res2 = mgr.lock_if_needed(dec_lock)
    assert res2 is not None
    assert res2.status == LockDispatchStatus.LOCK_SIMULATED


def test_lock_if_needed_regression_string_input():
    """
    Regression Test for previous production failure:
    AttributeError: 'str' object has no attribute 'lock_requested'
    
    Verifies lock_if_needed handles raw string reasons gracefully without throwing AttributeError.
    """
    mgr = WorkstationLockManager(enable_real_windows_lock=False)

    # Calling lock_if_needed with a raw string reason directly
    res = mgr.lock_if_needed("ABSENCE_TIMEOUT")
    assert res is not None
    assert res.status == LockDispatchStatus.LOCK_SIMULATED
    assert res.reason == "ABSENCE_TIMEOUT"
    assert res.success is True

    # Calling lock_if_needed with an invalid type or object without lock_requested
    class DummyInvalidObject:
        pass

    res_dummy = mgr.lock_if_needed(DummyInvalidObject())
    assert res_dummy is None


def test_real_lock_dispatch_success_and_error_handling():
    """Verify real LockWorkStation mocked dispatch, success status, and error handling."""
    from unittest.mock import MagicMock

    # 1. Successful LockWorkStation return
    mock_user32_success = MagicMock()
    mock_user32_success.LockWorkStation.return_value = 1

    mgr_success = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=mock_user32_success,
    )
    res_success = mgr_success.request_lock("ABSENCE_TIMEOUT")
    assert res_success.success is True
    assert res_success.status == LockDispatchStatus.LOCK_SUCCEEDED
    mock_user32_success.LockWorkStation.assert_called_once()

    # 2. Failed LockWorkStation return (returns 0)
    mock_user32_fail = MagicMock()
    mock_user32_fail.LockWorkStation.return_value = 0

    mgr_fail = WorkstationLockManager(
        enable_real_windows_lock=True,
        platform_override="win32",
        user32_dll_override=mock_user32_fail,
    )
    res_fail = mgr_fail.request_lock("ABSENCE_TIMEOUT")
    assert res_fail.success is False
    assert res_fail.status == LockDispatchStatus.LOCK_FAILED
    assert "GetLastError" in (res_fail.error_message or "") or "0" in (res_fail.error_message or "")


def test_no_duplicate_lock_dispatch_during_cooldown():
    """Verify lock dispatch cooldown prevents duplicate calls."""
    from unittest.mock import MagicMock

    mock_user32 = MagicMock()
    mock_user32.LockWorkStation.return_value = 1

    current_time = 500.0
    mgr = WorkstationLockManager(
        enable_real_windows_lock=True,
        cooldown_seconds=10.0,
        clock_fn=lambda: current_time,
        platform_override="win32",
        user32_dll_override=mock_user32,
    )

    # First dispatch succeeds
    res1 = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res1.status == LockDispatchStatus.LOCK_SUCCEEDED
    assert mock_user32.LockWorkStation.call_count == 1

    # Second dispatch 2s later is suppressed by cooldown
    current_time = 502.0
    res2 = mgr.request_lock("ABSENCE_TIMEOUT")
    assert res2.status == LockDispatchStatus.LOCK_SKIPPED_COOLDOWN
    assert res2.success is False
    assert mock_user32.LockWorkStation.call_count == 1


