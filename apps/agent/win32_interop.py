"""
Windows Native API Interop Layer
Handles OS detection, session lock triggers, and safe simulation hooks.
"""

import sys
import logging
from typing import Optional

logger = logging.getLogger("facesentry.win32")


class WindowsSystemBridge:
    """Encapsulates Windows API interactions (LockWorkStation, session changes)."""

    def __init__(self, dry_run: bool = True):
        self.is_windows = sys.platform == "win32"
        self.dry_run = dry_run
        self._user32 = None

        if self.is_windows:
            try:
                import ctypes
                self._user32 = ctypes.windll.user32
                logger.info("Windows user32.dll loaded successfully.")
            except Exception as exc:
                logger.warning(f"Unable to bind to user32.dll: {exc}")

    def lock_workstation(self, reason: str = "POLICY_TRIGGER") -> bool:
        """
        Request Windows to lock the active workstation session.
        In dry_run mode, this logs the action without locking the physical screen.
        """
        logger.info(f"Workstation lock requested [Reason: {reason}] [Dry-run: {self.dry_run}]")
        
        if self.dry_run:
            logger.info("[DRY-RUN] LockWorkStation() call simulated successfully.")
            return True

        if not self.is_windows or self._user32 is None:
            logger.warning("LockWorkStation called on non-Windows environment or uninitialized DLL.")
            return False

        try:
            result = self._user32.LockWorkStation()
            if result != 0:
                logger.info("LockWorkStation() executed successfully.")
                return True
            else:
                logger.error("LockWorkStation() returned 0 (failed to lock).")
                return False
        except Exception as exc:
            logger.error(f"Exception during LockWorkStation invocation: {exc}")
            return False

    def is_available(self) -> bool:
        """Check if Windows native subsystem is available."""
        return self.is_windows and self._user32 is not None
