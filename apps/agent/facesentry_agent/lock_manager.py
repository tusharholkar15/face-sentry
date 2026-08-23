"""
FaceSentry Workstation Lock Manager
Executes or simulates Windows workstation session locking (LockWorkStation)
in response to authoritative security decisions.

CRITICAL SAFETY & ARCHITECTURAL RULES:
- Default mode is DRY-RUN simulation (enable_real_windows_lock=False).
- Real locking requires explicit configuration (ENABLE_REAL_WINDOWS_LOCK=true).
- Workstation lock calls use native user32.dll; shell execution (rundll32/cmd/powershell) is strictly forbidden.
- Does NOT contain recognition, liveness, or model inference logic.
- Preserves single lock dispatch guarantee and cooldown debounce.
- Never logs or exposes raw biometrics, templates, or PINs in lock events.
"""

import sys
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Set, Union

from .decision_engine import DecisionResult

logger = logging.getLogger("facesentry.lock_manager")


class LockMode(str, Enum):
    """Execution mode of the lock manager."""
    REAL = "REAL"
    DRY_RUN = "DRY_RUN"


class LockDispatchStatus(str, Enum):
    """Detailed status resulting from a lock dispatch attempt."""
    LOCK_SUCCEEDED = "LOCK_SUCCEEDED"
    LOCK_SIMULATED = "LOCK_SIMULATED"
    LOCK_FAILED = "LOCK_FAILED"
    LOCK_SKIPPED_COOLDOWN = "LOCK_SKIPPED_COOLDOWN"
    LOCK_BLOCKED_UNSUPPORTED = "LOCK_BLOCKED_UNSUPPORTED"
    INVALID_REASON = "INVALID_REASON"


# Whitelist of permissible lock reasons
VALID_LOCK_REASONS: Set[str] = {
    "ABSENCE_TIMEOUT",
    "UNKNOWN_FACE_TIMEOUT",
    "SPOOF_TIMEOUT",
    "MANUAL_LOCK",
    "CAMERA_UNAVAILABLE",
    "POLICY_TRIGGER",
}


@dataclass(frozen=True)
class LockEvent:
    """Transition-level audit event emitted on lock actions."""
    event_type: str
    timestamp: float
    reason: str
    mode: str
    result: str


@dataclass(frozen=True)
class LockDispatchResult:
    """Structured response detailing the outcome of a lock request."""
    timestamp: float
    reason: str
    mode: LockMode
    status: LockDispatchStatus
    success: bool
    error_message: Optional[str] = None


class WorkstationLockManager:
    """
    Manages OS-level session locking with safety sandboxing,
    cooldown debounce, and structured audit events.
    """

    def __init__(
        self,
        enable_real_windows_lock: bool = False,
        cooldown_seconds: float = 5.0,
        lock_reason_required: bool = True,
        clock_fn: Callable[[], float] = time.time,
        on_event: Optional[Callable[[LockEvent], None]] = None,
        user32_dll_override: Optional[Any] = None,
        platform_override: Optional[str] = None,
        browser_protection: Optional[Any] = None,
    ):
        self.enable_real_windows_lock = enable_real_windows_lock
        self.cooldown_seconds = cooldown_seconds
        self.lock_reason_required = lock_reason_required
        self.clock_fn = clock_fn
        self.on_event = on_event
        self.platform = platform_override if platform_override is not None else sys.platform
        self.browser_protection = browser_protection

        self._last_lock_time: Optional[float] = None
        self._last_lock_request: Optional[LockDispatchResult] = None
        self._user32 = user32_dll_override

        # Initialize Windows user32.dll if on Windows and no override was passed
        if self.platform == "win32" and self._user32 is None:
            try:
                import ctypes
                self._user32 = ctypes.windll.user32
                logger.info("Windows user32.dll loaded successfully.")
            except Exception as exc:
                logger.warning(f"Failed to bind to user32.dll: {exc}")
                self._user32 = None

        mode_str = "REAL LOCK ENABLED" if self.enable_real_windows_lock else "DRY-RUN MODE (Simulated)"
        logger.info(f"[FaceSentry LockManager] Initialized in {mode_str} on platform '{self.platform}'")

    def is_supported(self) -> bool:
        """Check if Windows workstation locking is supported on the current platform/host."""
        return self.platform == "win32" and self._user32 is not None

    def get_last_lock_request(self) -> Optional[LockDispatchResult]:
        """Retrieve the most recent lock dispatch result."""
        return self._last_lock_request

    def reset_lock_dispatch(self) -> None:
        """Reset lock timestamp and state to allow immediate re-dispatch."""
        self._last_lock_time = None
        self._last_lock_request = None
        logger.debug("Lock dispatch cooldown state reset.")

    def _normalize_reason(self, raw_reason: str) -> str:
        """Normalize raw decision engine reason string to a standard whitelisted reason code."""
        reason_upper = raw_reason.upper()
        for valid in VALID_LOCK_REASONS:
            if valid in reason_upper:
                return valid
        return raw_reason

    def _emit_event(self, event_type: str, reason: str, mode: str, result: str, timestamp: float) -> None:
        """Emit structured lock audit event."""
        event = LockEvent(
            event_type=event_type,
            timestamp=timestamp,
            reason=reason,
            mode=mode,
            result=result,
        )
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as exc:
                logger.error(f"Error invoking lock event callback: {exc}")

    def request_lock(self, reason: str, force: bool = False) -> LockDispatchResult:
        """
        Request a workstation lock with reason validation, cooldown check,
        and execution or simulation based on configured mode.
        """
        now = self.clock_fn()
        normalized_reason = self._normalize_reason(reason)
        mode = LockMode.REAL if self.enable_real_windows_lock else LockMode.DRY_RUN

        # 1. Validate Reason Whitelist
        if self.lock_reason_required and normalized_reason not in VALID_LOCK_REASONS:
            logger.warning(f"Lock request rejected: invalid or unapproved reason '{reason}'")
            res = LockDispatchResult(
                timestamp=now,
                reason=reason,
                mode=mode,
                status=LockDispatchStatus.INVALID_REASON,
                success=False,
                error_message=f"Reason '{reason}' is not whitelisted.",
            )
            self._last_lock_request = res
            return res

        # 2. Check Cooldown
        if not force and self._last_lock_time is not None:
            elapsed = now - self._last_lock_time
            if elapsed < self.cooldown_seconds:
                logger.debug(f"Lock request skipped due to cooldown ({elapsed:.2f}s < {self.cooldown_seconds}s)")
                res = LockDispatchResult(
                    timestamp=now,
                    reason=normalized_reason,
                    mode=mode,
                    status=LockDispatchStatus.LOCK_SKIPPED_COOLDOWN,
                    success=False,
                    error_message=f"Lock cooldown active ({elapsed:.1f}s / {self.cooldown_seconds}s)",
                )
                self._last_lock_request = res
                return res

        self._emit_event("LOCK_REQUESTED", normalized_reason, mode.value, "PENDING", now)

        # 3. Dry-Run Simulation Mode
        if not self.enable_real_windows_lock:
            self._last_lock_time = now
            logger.info(f"Lock requested (DRY-RUN) [Reason: {normalized_reason}]. Workstation lock simulated.")
            self._emit_event("LOCK_SIMULATED", normalized_reason, mode.value, "SUCCESS", now)
            res = LockDispatchResult(
                timestamp=now,
                reason=normalized_reason,
                mode=LockMode.DRY_RUN,
                status=LockDispatchStatus.LOCK_SIMULATED,
                success=True,
            )
            self._last_lock_request = res
            return res

        # 4. Real Lock Execution Mode
        if not self.is_supported():
            logger.error("Real Windows lock requested but Windows user32.dll is not supported/available.")
            self._emit_event("LOCK_FAILED", normalized_reason, mode.value, "UNSUPPORTED_PLATFORM", now)
            res = LockDispatchResult(
                timestamp=now,
                reason=normalized_reason,
                mode=LockMode.REAL,
                status=LockDispatchStatus.LOCK_BLOCKED_UNSUPPORTED,
                success=False,
                error_message=f"Platform '{self.platform}' or user32.dll not available.",
            )
            self._last_lock_request = res
            return res

        self._emit_event("LOCK_DISPATCHED", normalized_reason, mode.value, "DISPATCHED", now)
        try:
            # Native user32.dll LockWorkStation invocation
            lock_success = self._user32.LockWorkStation()
            if lock_success != 0:
                self._last_lock_time = now
                logger.info(f"Windows workstation lock dispatched successfully [Reason: {normalized_reason}]")
                self._emit_event("LOCK_SUCCEEDED", normalized_reason, mode.value, "SUCCESS", now)
                res = LockDispatchResult(
                    timestamp=now,
                    reason=normalized_reason,
                    mode=LockMode.REAL,
                    status=LockDispatchStatus.LOCK_SUCCEEDED,
                    success=True,
                )
                if self.browser_protection:
                    try:
                        self.browser_protection.protect()
                    except Exception as b_exc:
                        logger.error(f"Browser protection failed: {b_exc}")
            else:
                err_code = 0
                try:
                    import ctypes
                    err_code = ctypes.GetLastError()
                except Exception:
                    pass
                logger.error(f"Windows workstation lock failed: LockWorkStation() returned 0 (GetLastError={err_code}).")
                self._emit_event("LOCK_FAILED", normalized_reason, mode.value, f"API_RETURNED_ZERO_ERR_{err_code}", now)
                res = LockDispatchResult(
                    timestamp=now,
                    reason=normalized_reason,
                    mode=LockMode.REAL,
                    status=LockDispatchStatus.LOCK_FAILED,
                    success=False,
                    error_message=f"LockWorkStation returned 0 (GetLastError={err_code}).",
                )
        except Exception as exc:
            logger.error(f"Windows workstation lock failed with exception: {exc}")
            self._emit_event("LOCK_FAILED", normalized_reason, mode.value, f"EXCEPTION_{type(exc).__name__}", now)
            res = LockDispatchResult(
                timestamp=now,
                reason=normalized_reason,
                mode=LockMode.REAL,
                status=LockDispatchStatus.LOCK_FAILED,
                success=False,
                error_message=str(exc),
            )

        self._last_lock_request = res
        return res

    def lock_if_needed(self, decision_result: Union[DecisionResult, str]) -> Optional[LockDispatchResult]:
        """
        Evaluate DecisionResult and dispatch lock ONLY if lock_requested is True.
        Preserves Decision Engine single-dispatch guarantee.
        Defensively handles string reason inputs without throwing AttributeError.
        """
        if isinstance(decision_result, str):
            logger.warning(
                f"lock_if_needed received raw string '{decision_result}' instead of typed DecisionResult. "
                f"Dispatching lock directly."
            )
            return self.request_lock(reason=decision_result)

        if hasattr(decision_result, "lock_requested") and decision_result.lock_requested:
            reason = getattr(decision_result, "reason", "POLICY_TRIGGER")
            return self.request_lock(reason=reason)

        return None
