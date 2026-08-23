"""
FaceSentry Shared Module
Defines enums, constants, schemas, and shared utilities across API, Agent, and Web services.
"""

from .enums import SystemState, EventType, LockReason, LivenessTier
from .constants import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_ABSENCE_TIMEOUT_SECONDS,
    DEFAULT_UNKNOWN_FACE_TIMEOUT_SECONDS,
    DEFAULT_SPOOF_LOCK_TIMEOUT_SECONDS,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_LIVENESS_THRESHOLD,
    DEFAULT_EAR_BLINK_THRESHOLD,
    VERSION,
)
from .schemas import (
    HealthResponse,
    SystemStatusResponse,
    PolicyConfigSchema,
    HardwareConfigSchema,
    SystemConfigSchema,
    SecurityEventCreate,
    SecurityEventRead,
)

__all__ = [
    "SystemState",
    "EventType",
    "LockReason",
    "LivenessTier",
    "DEFAULT_API_HOST",
    "DEFAULT_API_PORT",
    "DEFAULT_ABSENCE_TIMEOUT_SECONDS",
    "DEFAULT_UNKNOWN_FACE_TIMEOUT_SECONDS",
    "DEFAULT_SPOOF_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_LIVENESS_THRESHOLD",
    "DEFAULT_EAR_BLINK_THRESHOLD",
    "VERSION",
    "HealthResponse",
    "SystemStatusResponse",
    "PolicyConfigSchema",
    "HardwareConfigSchema",
    "SystemConfigSchema",
    "SecurityEventCreate",
    "SecurityEventRead",
]
