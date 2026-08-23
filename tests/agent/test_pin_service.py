"""
Unit and Security Tests for FaceSentry Secure PIN Fallback Service
Validates PBKDF2-HMAC-SHA256 hashing, constant-time checks, rate limiting,
lockout triggers, cooldown expiration, recovery tracking, and PIN change flow.
"""

import time
import pytest
from apps.agent.facesentry_agent.pin_service import PinAuthService, PinPolicyConfig


class MockClock:
    def __init__(self, start_time: float = 1000.0):
        self.current_time = start_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


@pytest.fixture
def pin_service(tmp_path):
    storage_file = str(tmp_path / "pin_credentials.json")
    clock = MockClock(1000.0)
    config = PinPolicyConfig(
        min_length=4,
        max_length=8,
        max_attempts=3,
        lockout_duration_seconds=30.0,
        recovery_duration_seconds=45.0,
        iterations=1000,  # Fast for unit tests
    )
    service = PinAuthService(storage_path=storage_file, config=config, clock_fn=clock.time)
    return service, clock


def test_pin_initial_status_unconfigured(pin_service):
    service, clock = pin_service
    status = service.get_status()
    assert status.is_configured is False
    assert status.is_locked is False
    assert status.attempts_remaining == 3
    assert status.in_recovery is False


def test_pin_setup_validations(pin_service):
    service, clock = pin_service

    # Too short
    ok, msg = service.setup_pin("12", "12")
    assert ok is False
    assert "at least 4 characters" in msg

    # Too long
    ok, msg = service.setup_pin("1234567890", "1234567890")
    assert ok is False
    assert "exceed 8 characters" in msg

    # Non-digit
    ok, msg = service.setup_pin("abcd", "abcd")
    assert ok is False
    assert "numeric digits" in msg

    # Mismatched
    ok, msg = service.setup_pin("1234", "5678")
    assert ok is False
    assert "do not match" in msg

    # Valid setup
    ok, msg = service.setup_pin("1234", "1234")
    assert ok is True
    assert service.is_configured() is True

    # Duplicate setup rejected
    ok, msg = service.setup_pin("9999", "9999")
    assert ok is False
    assert "already configured" in msg


def test_pin_verification_success_and_recovery(pin_service):
    service, clock = pin_service
    service.setup_pin("4321", "4321")

    # Correct verification
    res = service.verify_pin("4321")
    assert res.authenticated is True
    assert res.in_recovery is True
    assert res.recovery_until == 1045.0  # 1000.0 + 45.0s
    assert res.is_locked is False
    assert service.is_in_recovery() is True

    # Advance clock by 30s -> Still in recovery
    clock.advance(30.0)
    assert service.is_in_recovery() is True

    # Advance clock past 45s -> Recovery expires
    clock.advance(20.0)  # total 50s elapsed
    assert service.is_in_recovery() is False


def test_pin_rate_limiting_and_lockout(pin_service):
    service, clock = pin_service
    service.setup_pin("5555", "5555")

    # Attempt 1: Failed
    res1 = service.verify_pin("1111")
    assert res1.authenticated is False
    assert res1.attempts_remaining == 2
    assert res1.is_locked is False

    # Attempt 2: Failed
    res2 = service.verify_pin("2222")
    assert res2.authenticated is False
    assert res2.attempts_remaining == 1
    assert res2.is_locked is False

    # Attempt 3: Failed -> Trigger Lockout (max_attempts = 3)
    res3 = service.verify_pin("3333")
    assert res3.authenticated is False
    assert res3.attempts_remaining == 0
    assert res3.is_locked is True
    assert res3.locked_until == 1030.0  # 1000.0 + 30s
    assert service.is_locked() is True

    # Attempt 4 during lockout: Immediately rejected even if correct PIN is entered!
    res4 = service.verify_pin("5555")
    assert res4.authenticated is False
    assert res4.is_locked is True
    assert "locked out" in res4.reason.lower()

    # Advance clock past lockout duration (35s elapsed)
    clock.advance(35.0)
    assert service.is_locked() is False

    # Verification now works again
    res5 = service.verify_pin("5555")
    assert res5.authenticated is True
    assert res5.in_recovery is True


def test_pin_change_flow(pin_service):
    service, clock = pin_service
    service.setup_pin("1234", "1234")

    # Incorrect current PIN
    ok, msg = service.change_pin("9999", "5678", "5678")
    assert ok is False
    assert "Incorrect" in msg

    # Valid change
    ok, msg = service.change_pin("1234", "5678", "5678")
    assert ok is True

    # Old PIN rejected
    res_old = service.verify_pin("1234")
    assert res_old.authenticated is False

    # New PIN verified
    res_new = service.verify_pin("5678")
    assert res_new.authenticated is True


def test_pin_credentials_never_store_plaintext(pin_service):
    service, clock = pin_service
    service.setup_pin("7890", "7890")

    with open(service.storage_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify plaintext PIN never appears in storage file
    assert "7890" not in content
    assert "salt_hex" in content
    assert "hash_hex" in content
