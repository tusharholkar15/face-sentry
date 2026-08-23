"""
Tests for Production Agent Entry Point and Startup Validations
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure we test with local paths instead of production LOCALAPPDATA
os.environ["FACESENTRY_DEV_MODE"] = "1"

from apps.agent.facesentry_agent.main import check_installation, setup_logging
from packages.shared.constants import (
    DEFAULT_MODELS_DIR,
    DEFAULT_LOGS_DIR,
    get_base_dir
)

@pytest.fixture
def mock_models_exist():
    with patch('os.path.exists') as mock_exists:
        # Let's say all paths exist by default for this mock
        mock_exists.return_value = True
        yield mock_exists

def test_base_dir_resolution_dev_mode():
    os.environ["FACESENTRY_DEV_MODE"] = "1"
    base_dir = get_base_dir()
    assert "data" in base_dir
    assert not base_dir.endswith("FaceSentry")

def test_base_dir_resolution_prod_mode():
    os.environ["FACESENTRY_DEV_MODE"] = "0"
    os.environ["LOCALAPPDATA"] = "C:\\Users\\TestUser\\AppData\\Local"
    base_dir = get_base_dir()
    assert base_dir == "C:\\Users\\TestUser\\AppData\\Local\\FaceSentry"

def test_check_installation_success(mock_models_exist):
    # Should not raise any system exit
    try:
        check_installation()
    except SystemExit:
        pytest.fail("check_installation() raised SystemExit unexpectedly!")

def test_check_installation_missing_models():
    with patch('os.path.exists', return_value=False):
        with pytest.raises(SystemExit) as exc:
            check_installation()
        assert exc.value.code == 1

@patch('os.makedirs')
@patch('apps.agent.facesentry_agent.main.RotatingFileHandler')
def test_setup_logging(mock_rfh, mock_makedirs):
    import logging
    logger = logging.getLogger("facesentry")
    original_handlers = logger.handlers[:]
    try:
        # Just verify it doesn't crash and creates the directory
        setup_logging("DIAGNOSTIC")
        mock_makedirs.assert_called_with(DEFAULT_LOGS_DIR, exist_ok=True)
        mock_rfh.assert_called_once()
    finally:
        logger.handlers = original_handlers


def test_absence_lock_production_flow_e2e():
    """
    Verifies the complete production pipeline flow:
    Camera (Absence) -> RecognitionResult(face_count=0) -> Liveness -> DecisionEngine
    -> DecisionResult (lock_requested=True) -> WorkstationLockManager.lock_if_needed()
    -> LockDispatchResult(LOCK_SIMULATED)
    
    Guarantees no AttributeError: 'str' object has no attribute 'lock_requested' occurs.
    """
    from apps.agent.facesentry_agent.decision_engine import AuthenticationDecisionEngine, DecisionConfig, DecisionEventType
    from apps.agent.facesentry_agent.lock_manager import WorkstationLockManager, LockDispatchStatus
    from apps.agent.facesentry_agent.recognition import RecognitionResult
    from apps.agent.facesentry_agent.liveness import LivenessResult, LivenessState

    events_captured = []
    lock_events_captured = []

    mock_time = 1000.0

    def get_time():
        return mock_time

    decision_engine = AuthenticationDecisionEngine(
        config=DecisionConfig(absence_timeout_seconds=5.0),
        clock_fn=get_time,
        on_event=lambda evt: events_captured.append(evt),
    )

    lock_manager = WorkstationLockManager(
        enable_real_windows_lock=False,
        clock_fn=get_time,
        on_event=lambda evt: lock_events_captured.append(evt),
    )

    # Frame 1: User is absent (face_count = 0)
    rec_result_empty = RecognitionResult(
        recognized=False,
        similarity=0.0,
        face_count=0,
        timestamp=mock_time,
        reason="NO_FACE_DETECTED",
    )
    liveness_empty = LivenessResult(
        state=LivenessState.OBSERVING,
        blink_detected=False,
        head_movement_detected=False,
        temporal_score=0.0,
        verified=False,
        confidence=0.0,
        timestamp=mock_time,
        reason="NO_FACE",
    )

    dec_res_1 = decision_engine.evaluate(
        recognition=rec_result_empty,
        liveness=liveness_empty,
        camera_available=True,
    )
    assert dec_res_1.lock_requested is False
    lock_res_1 = lock_manager.lock_if_needed(dec_res_1)
    assert lock_res_1 is None

    # Verify ABSENCE_STARTED event was recorded
    assert any(e.event_type == DecisionEventType.ABSENCE_STARTED for e in events_captured)

    # Fast-forward time past the absence timeout (+6.0s)
    mock_time = 1006.0

    dec_res_2 = decision_engine.evaluate(
        recognition=rec_result_empty,
        liveness=liveness_empty,
        camera_available=True,
    )

    # Verify lock is requested
    assert dec_res_2.lock_requested is True
    assert "ABSENCE_TIMEOUT" in dec_res_2.reason

    # Execute lock_manager with the typed DecisionResult object
    lock_dispatch_res = lock_manager.lock_if_needed(dec_res_2)
    assert lock_dispatch_res is not None
    assert lock_dispatch_res.status == LockDispatchStatus.LOCK_SIMULATED
    assert lock_dispatch_res.success is True

    # Verify lock manager emitted LOCK_REQUESTED and LOCK_SIMULATED
    assert any(e.event_type == "LOCK_REQUESTED" for e in lock_events_captured)
    assert any(e.event_type == "LOCK_SIMULATED" for e in lock_events_captured)

