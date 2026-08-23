"""
FaceSentry Secure Local PIN Fallback Service
Provides PBKDF2-HMAC-SHA256 hashed PIN authentication, brute-force rate limiting,
temporary lockout periods, and emergency biometric recovery state transitions.
"""

import os
import json
import time
import hmac
import secrets
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from packages.shared.schemas import PinStatusResponse, PinVerifyResponse

logger = logging.getLogger("facesentry.pin_service")


@dataclass(frozen=True)
class PinPolicyConfig:
    """Configurable security constraints for local PIN authentication."""
    min_length: int = 4
    max_length: int = 12
    max_attempts: int = 5
    lockout_duration_seconds: float = 60.0
    recovery_duration_seconds: float = 60.0
    iterations: int = 100_000


class PinAuthService:
    """
    Cryptographic PIN manager with rate limiting, constant-time verification,
    and temporary recovery duration tracking.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        config: Optional[PinPolicyConfig] = None,
        clock_fn=time.time,
    ):
        self.config = config or PinPolicyConfig()
        self.clock_fn = clock_fn

        if storage_path:
            self.storage_file = Path(storage_path)
        else:
            project_root = Path(__file__).resolve().parents[3]
            self.storage_file = project_root / "data" / "pin_credentials.json"

        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

        self._failed_attempts: int = 0
        self._locked_until: Optional[float] = None
        self._recovery_until: Optional[float] = None

    def is_configured(self) -> bool:
        """Check whether a hashed PIN credential file exists."""
        return self.storage_file.exists()

    def _hash_pin(self, pin: str, salt: bytes) -> bytes:
        """Derive cryptographic key using standard PBKDF2-HMAC-SHA256."""
        return hashlib.pbkdf2_hmac(
            hash_name="sha256",
            password=pin.encode("utf-8"),
            salt=salt,
            iterations=self.config.iterations,
        )

    def _load_credentials(self) -> Optional[Tuple[bytes, bytes]]:
        """Load salt and expected hash bytes from storage."""
        if not self.is_configured():
            return None
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            salt = bytes.fromhex(data["salt_hex"])
            expected_hash = bytes.fromhex(data["hash_hex"])
            return salt, expected_hash
        except Exception as exc:
            logger.error(f"Error loading PIN credentials: {exc}")
            return None

    def _save_credentials(self, salt: bytes, pin_hash: bytes) -> None:
        """Persist salt and hash hex to storage file."""
        data = {
            "salt_hex": salt.hex(),
            "hash_hex": pin_hash.hex(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock_fn())),
            "iterations": self.config.iterations,
        }
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def validate_pin_format(self, pin: str) -> Tuple[bool, Optional[str]]:
        """Validate candidate PIN against length and format rules."""
        if not pin or not isinstance(pin, str):
            return False, "PIN cannot be empty."
        pin = pin.strip()
        if len(pin) < self.config.min_length:
            return False, f"PIN must be at least {self.config.min_length} characters."
        if len(pin) > self.config.max_length:
            return False, f"PIN must not exceed {self.config.max_length} characters."
        if not pin.isdigit():
            # Allow digits for standard numeric PINs
            return False, "PIN must consist exclusively of numeric digits (0-9)."
        return True, None

    def setup_pin(self, new_pin: str, confirm_pin: str) -> Tuple[bool, str]:
        """Configure initial PIN credentials."""
        if self.is_configured():
            return False, "PIN is already configured. Use change PIN instead."

        valid, err = self.validate_pin_format(new_pin)
        if not valid:
            return False, err or "Invalid PIN format."

        if new_pin != confirm_pin:
            return False, "PINs do not match."

        salt = secrets.token_bytes(32)
        pin_hash = self._hash_pin(new_pin, salt)
        self._save_credentials(salt, pin_hash)

        logger.info("Initial PIN configured successfully.")
        return True, "PIN configured successfully."

    def change_pin(self, current_pin: str, new_pin: str, confirm_pin: str) -> Tuple[bool, str]:
        """Change existing PIN after validating current credentials."""
        if not self.is_configured():
            return False, "PIN is not configured yet."

        # Verify current credentials first
        verify_res = self.verify_pin(current_pin)
        if not verify_res.authenticated:
            return False, verify_res.reason or "Incorrect current PIN."

        valid, err = self.validate_pin_format(new_pin)
        if not valid:
            return False, err or "Invalid new PIN format."

        if new_pin != confirm_pin:
            return False, "New PINs do not match."

        salt = secrets.token_bytes(32)
        pin_hash = self._hash_pin(new_pin, salt)
        self._save_credentials(salt, pin_hash)

        logger.info("PIN changed successfully.")
        return True, "PIN updated successfully."

    def is_locked(self) -> bool:
        """Check if PIN verification is currently locked out."""
        if self._locked_until is None:
            return False
        now = self.clock_fn()
        if now < self._locked_until:
            return True
        # Lockout expired -> reset
        self._locked_until = None
        self._failed_attempts = 0
        return False

    def is_in_recovery(self) -> bool:
        """Check if temporary emergency recovery duration is active."""
        if self._recovery_until is None:
            return False
        now = self.clock_fn()
        if now < self._recovery_until:
            return True
        # Recovery period expired
        self._recovery_until = None
        return False

    def verify_pin(self, pin: str) -> PinVerifyResponse:
        """
        Authenticate candidate PIN using constant-time comparison.
        Enforces failed-attempt rate limiting and temporary lockout.
        """
        now = self.clock_fn()

        # Check if already locked out
        if self.is_locked():
            return PinVerifyResponse(
                authenticated=False,
                in_recovery=False,
                recovery_until=None,
                attempts_remaining=0,
                is_locked=True,
                locked_until=self._locked_until,
                reason="PIN verification is temporarily locked out due to multiple failed attempts.",
            )

        creds = self._load_credentials()
        if creds is None:
            return PinVerifyResponse(
                authenticated=False,
                in_recovery=False,
                recovery_until=None,
                attempts_remaining=self.config.max_attempts,
                is_locked=False,
                locked_until=None,
                reason="PIN is not configured on this system.",
            )

        salt, expected_hash = creds
        computed_hash = self._hash_pin(pin, salt)

        # Constant-time comparison
        is_match = hmac.compare_digest(computed_hash, expected_hash)

        if is_match:
            self._failed_attempts = 0
            self._locked_until = None
            self._recovery_until = now + self.config.recovery_duration_seconds
            logger.info("PIN verification succeeded. Temporary recovery granted.")
            return PinVerifyResponse(
                authenticated=True,
                in_recovery=True,
                recovery_until=self._recovery_until,
                attempts_remaining=self.config.max_attempts,
                is_locked=False,
                locked_until=None,
                reason="PIN authentication successful.",
            )
        else:
            self._failed_attempts += 1
            remaining = max(0, self.config.max_attempts - self._failed_attempts)
            if remaining == 0:
                self._locked_until = now + self.config.lockout_duration_seconds
                logger.warning("PIN lockout triggered due to excessive failed attempts.")
                return PinVerifyResponse(
                    authenticated=False,
                    in_recovery=False,
                    recovery_until=None,
                    attempts_remaining=0,
                    is_locked=True,
                    locked_until=self._locked_until,
                    reason=f"Too many failed attempts. Subsystem locked for {self.config.lockout_duration_seconds:.0f} seconds.",
                )
            else:
                logger.warning(f"Invalid PIN entered. Attempts remaining: {remaining}")
                return PinVerifyResponse(
                    authenticated=False,
                    in_recovery=False,
                    recovery_until=None,
                    attempts_remaining=remaining,
                    is_locked=False,
                    locked_until=None,
                    reason=f"Incorrect PIN. {remaining} attempt(s) remaining.",
                )

    def get_status(self) -> PinStatusResponse:
        """Return safe overview of PIN configuration, lockout, and recovery status."""
        is_locked_now = self.is_locked()
        in_rec_now = self.is_in_recovery()
        remaining = 0 if is_locked_now else max(0, self.config.max_attempts - self._failed_attempts)

        return PinStatusResponse(
            is_configured=self.is_configured(),
            is_locked=is_locked_now,
            attempts_remaining=remaining,
            locked_until=self._locked_until,
            in_recovery=in_rec_now,
            recovery_until=self._recovery_until,
            reason="Nominal" if not is_locked_now else "Locked out",
        )
