"""
Unit Tests for Agent State and Hardware Abstractions
"""

import time
from packages.shared.enums import SystemState, LockReason
from apps.agent.state import AgentStateController
from apps.agent.win32_interop import WindowsSystemBridge
from apps.agent.camera import CameraManager


def test_agent_state_transitions():
    """Verify presence state transitions and timer logic."""
    lock_triggers = []

    def on_lock(reason):
        lock_triggers.append(reason)

    controller = AgentStateController(
        absence_timeout_s=1,
        unknown_timeout_s=1,
        spoof_timeout_s=0,
        on_lock_trigger=on_lock,
    )

    assert controller.current_state == SystemState.IDLE

    # User authenticated
    controller.handle_authenticated_user()
    assert controller.current_state == SystemState.MONITORING_AUTHENTICATED

    # Absence start
    controller.handle_absence()
    assert controller.current_state == SystemState.MONITORING_ABSENT
    assert len(lock_triggers) == 0

    # Simulate timeout
    time.sleep(1.1)
    controller.handle_absence()
    assert controller.current_state == SystemState.LOCKED
    assert len(lock_triggers) == 1
    assert lock_triggers[0] == LockReason.ABSENCE_TIMEOUT


def test_win32_dry_run_bridge():
    """Verify Windows bridge operates safely in dry-run mode."""
    bridge = WindowsSystemBridge(dry_run=True)
    assert bridge.dry_run is True
    success = bridge.lock_workstation(reason="TEST_SIMULATION")
    assert success is True


def test_camera_manager_lifecycle():
    """Verify camera manager instantiation and safe release."""
    cam = CameraManager(camera_index=999)  # Non-existent camera index
    assert cam.is_connected() is False
    cam.release()
    assert cam.is_connected() is False
