"""
Agent Presence State Controller
Manages operational state transitions, timing counters, and evaluation loops.
"""

import time
import logging
from typing import Optional, Callable
from packages.shared.enums import SystemState, LockReason

logger = logging.getLogger("facesentry.agent.state")


class AgentStateController:
    """Manages active presence monitoring states and timing rules."""

    def __init__(
        self,
        absence_timeout_s: int = 10,
        unknown_timeout_s: int = 5,
        spoof_timeout_s: int = 0,
        on_lock_trigger: Optional[Callable[[LockReason], None]] = None,
    ):
        self.absence_timeout_s = absence_timeout_s
        self.unknown_timeout_s = unknown_timeout_s
        self.spoof_timeout_s = spoof_timeout_s
        self.on_lock_trigger = on_lock_trigger

        self.current_state: SystemState = SystemState.IDLE
        self.absence_start_time: Optional[float] = None
        self.unknown_start_time: Optional[float] = None
        self.spoof_start_time: Optional[float] = None

    def set_state(self, new_state: SystemState) -> None:
        """Update system state and log transition."""
        if self.current_state != new_state:
            logger.info(f"State transition: {self.current_state.value} -> {new_state.value}")
            self.current_state = new_state

    def handle_authenticated_user(self) -> None:
        """Reset absence and stranger timers when authorized user is verified."""
        self.absence_start_time = None
        self.unknown_start_time = None
        self.spoof_start_time = None
        self.set_state(SystemState.MONITORING_AUTHENTICATED)

    def handle_absence(self) -> None:
        """Advance absence timer and trigger lock if threshold exceeded."""
        now = time.time()
        if self.absence_start_time is None:
            self.absence_start_time = now
            self.set_state(SystemState.MONITORING_ABSENT)

        elapsed = now - self.absence_start_time
        if elapsed >= self.absence_timeout_s:
            logger.warning(f"Absence timeout exceeded ({elapsed:.1f}s >= {self.absence_timeout_s}s)")
            self.set_state(SystemState.LOCKED)
            if self.on_lock_trigger:
                self.on_lock_trigger(LockReason.ABSENCE_TIMEOUT)

    def handle_unknown_face(self) -> None:
        """Advance unknown face timer and trigger lock if threshold exceeded."""
        now = time.time()
        if self.unknown_start_time is None:
            self.unknown_start_time = now
            self.set_state(SystemState.MONITORING_UNKNOWN_FACE)

        elapsed = now - self.unknown_start_time
        if elapsed >= self.unknown_timeout_s:
            logger.warning(f"Unknown face timeout exceeded ({elapsed:.1f}s >= {self.unknown_timeout_s}s)")
            self.set_state(SystemState.LOCKED)
            if self.on_lock_trigger:
                self.on_lock_trigger(LockReason.UNKNOWN_FACE_TIMEOUT)

    def handle_spoof(self) -> None:
        """Handle anti-spoofing alert and trigger lock if policy demands."""
        now = time.time()
        if self.spoof_start_time is None:
            self.spoof_start_time = now
            self.set_state(SystemState.MONITORING_SPOOF_ATTEMPT)

        elapsed = now - self.spoof_start_time
        if elapsed >= self.spoof_timeout_s:
            logger.warning(f"Anti-spoofing policy triggered lock ({elapsed:.1f}s)")
            self.set_state(SystemState.LOCKED)
            if self.on_lock_trigger:
                self.on_lock_trigger(LockReason.SPOOF_DETECTED)
