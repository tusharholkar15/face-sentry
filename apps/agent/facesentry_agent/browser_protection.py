"""
FaceSentry Browser Protection Manager

Provides defense-in-depth safe browser session protection upon workstation lock.
- Graceful shutdown of Chrome, Edge, and Firefox.
- Best-effort SQLite session cookie deletion for Chromium browsers (Chrome, Edge).
- Explictly returns SESSION_CLEANUP_UNSUPPORTED for Firefox to avoid volatile DB corruption.
"""

import os
import time
import logging
import sqlite3
from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    psutil = None

from packages.shared.schemas import BrowserProtectionConfigSchema
from packages.shared.enums import BrowserProtectionMode

logger = logging.getLogger("facesentry.browser_protection")


@dataclass(frozen=True)
class BrowserProtectionEvent:
    event_type: str
    timestamp: float
    browser: str
    action: str
    result: str
    details: str = ""


class BrowserProtectionManager:
    def __init__(
        self,
        config: BrowserProtectionConfigSchema,
        clock_fn: Callable[[], float] = time.time,
        on_event: Optional[Callable[[BrowserProtectionEvent], None]] = None,
        is_windows: bool = True
    ):
        self.config = config
        self.clock_fn = clock_fn
        self.on_event = on_event
        self.is_windows = is_windows

        # Map browser process names to their localized profile paths on Windows
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        self.supported_browsers = {
            "chrome.exe": {
                "name": "Google Chrome",
                "cookie_paths": [
                    os.path.join(local_app_data, "Google", "Chrome", "User Data", "Default", "Network", "Cookies"),
                ],
                "supports_cookie_cleanup": True,
            },
            "msedge.exe": {
                "name": "Microsoft Edge",
                "cookie_paths": [
                    os.path.join(local_app_data, "Microsoft", "Edge", "User Data", "Default", "Network", "Cookies"),
                ],
                "supports_cookie_cleanup": True,
            },
            "firefox.exe": {
                "name": "Mozilla Firefox",
                "cookie_paths": [],  # Avoid touching Firefox cookies.sqlite directly
                "supports_cookie_cleanup": False,
            }
        }

    def _emit(self, event_type: str, browser: str, action: str, result: str, details: str = ""):
        event = BrowserProtectionEvent(
            event_type=event_type,
            timestamp=self.clock_fn(),
            browser=browser,
            action=action,
            result=result,
            details=details,
        )
        logger.info(f"[BrowserProtection] {event.event_type} - {browser} - {result} - {details}")
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                logger.error(f"Error in browser protection event callback: {e}")

    def protect(self) -> None:
        """
        Main entry point triggered by LockManager.
        Executes protection rules based on configured mode.
        """
        if not self.config.enabled or self.config.mode == BrowserProtectionMode.DISABLED:
            logger.debug("Browser protection is disabled or in DISABLED mode.")
            return

        if not self.is_windows or psutil is None:
            logger.warning("Browser protection requires Windows platform and psutil.")
            return

        self._emit(
            "BROWSER_PROTECTION_TRIGGERED",
            "System",
            "PROTECT",
            "STARTED",
            f"Mode: {self.config.mode.value}"
        )

        detected_procs = self._detect_browsers()
        for proc_name, procs in detected_procs.items():
            browser_info = self.supported_browsers[proc_name]
            browser_name = browser_info["name"]

            self._emit("BROWSER_DETECTED", browser_name, "DETECT", "SUCCESS", f"Found {len(procs)} processes")

            # 1. Close Browser
            closed = self._close_browser(browser_name, procs)

            # 2. Clear Session Cookies (if configured and supported)
            if self.config.mode == BrowserProtectionMode.CLOSE_BROWSER_AND_CLEAR_SESSION_COOKIES:
                if closed:
                    self._clear_session_cookies(browser_name, browser_info)
                else:
                    self._emit("SESSION_CLEANUP_FAILED", browser_name, "CLEANUP_COOKIES", "FAILED", "Browser failed to close")

    def _detect_browsers(self) -> Dict[str, List[Any]]:
        """Finds all running instances of supported browser processes."""
        detected = {k: [] for k in self.supported_browsers.keys()}
        try:
            for proc in psutil.process_iter(['name']):
                name = proc.info.get('name')
                if name and name.lower() in detected:
                    detected[name.lower()].append(proc)
        except Exception as e:
            logger.error(f"Error iterating processes: {e}")
        
        # Filter out empty lists
        return {k: v for k, v in detected.items() if v}

    def _close_browser(self, browser_name: str, procs: List[Any]) -> bool:
        """Gracefully asks processes to terminate and waits for close_timeout_seconds."""
        self._emit("BROWSER_CLOSE_REQUESTED", browser_name, "CLOSE_PROCESS", "PENDING", f"Requesting termination of {len(procs)} processes")
        
        # Send graceful terminate
        for p in procs:
            try:
                if p.is_running():
                    p.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Wait for termination
        start_time = self.clock_fn()
        gone, alive = psutil.wait_procs(procs, timeout=self.config.close_timeout_seconds)
        
        if alive:
            self._emit("BROWSER_CLOSE_FAILED", browser_name, "CLOSE_PROCESS", "TIMEOUT", f"{len(alive)} processes did not terminate")
            return False
            
        self._emit("BROWSER_CLOSE_SUCCEEDED", browser_name, "CLOSE_PROCESS", "SUCCESS")
        return True

    def _clear_session_cookies(self, browser_name: str, browser_info: Dict[str, Any]) -> None:
        """
        Safely clears session cookies (is_persistent = 0) from Chromium SQLite databases.
        Never touches passwords or autofill.
        """
        self._emit("SESSION_CLEANUP_STARTED", browser_name, "CLEANUP_COOKIES", "PENDING")

        if not browser_info.get("supports_cookie_cleanup", False):
            self._emit("SESSION_CLEANUP_UNSUPPORTED", browser_name, "CLEANUP_COOKIES", "UNSUPPORTED", "Safe cleanup not supported for this browser architecture")
            return

        success = False
        paths = browser_info.get("cookie_paths", [])
        for path in paths:
            if not os.path.exists(path):
                continue
            
            try:
                # Use uri=True to open read/write and avoid creating the file if missing
                # timeout=1 to immediately fail if the DB is still locked by a background process
                conn = sqlite3.connect(f"file:{path}?mode=rw", uri=True, timeout=1.0)
                cursor = conn.cursor()
                
                # Chromium cookies schema check
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cookies'")
                if cursor.fetchone():
                    # Delete only session cookies (persistent cookies have expires_utc > 0 or is_persistent = 1 depending on version)
                    # For safety across Chromium versions, we target is_persistent = 0
                    # This query does NOT delete passwords, logins, autofill, or saved bookmarks.
                    cursor.execute("DELETE FROM cookies WHERE is_persistent = 0 OR is_persistent = '0'")
                    deleted_count = cursor.rowcount
                    conn.commit()
                    logger.debug(f"Deleted {deleted_count} session cookies from {path}")
                    success = True
                
                conn.close()
            except sqlite3.OperationalError as e:
                logger.warning(f"SQLite lock or permission error on {path}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error cleaning cookies on {path}: {e}")

        if success:
            self._emit("SESSION_CLEANUP_SUCCEEDED", browser_name, "CLEANUP_COOKIES", "SUCCESS", "Session cookies safely cleared")
        else:
            # If no paths existed, or all failed
            self._emit("SESSION_CLEANUP_FAILED", browser_name, "CLEANUP_COOKIES", "FAILED", "Could not modify cookie database")
