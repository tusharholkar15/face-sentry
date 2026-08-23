"""
Pydantic Data Schemas for FaceSentry
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field, ConfigDict

from .enums import SystemState, EventType, LockReason, BrowserProtectionMode
from .constants import (
    VERSION,
    DEFAULT_ABSENCE_TIMEOUT_SECONDS,
    DEFAULT_UNKNOWN_FACE_TIMEOUT_SECONDS,
    DEFAULT_SPOOF_LOCK_TIMEOUT_SECONDS,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_LIVENESS_THRESHOLD,
    DEFAULT_CAMERA_INDEX,
    DEFAULT_TARGET_FPS,
)


def get_current_utc_time() -> datetime:
    """Helper for timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class HealthResponse(BaseModel):
    """Standard health check response model."""
    status: str = Field(default="healthy", description="Service health indicator")
    service: str = Field(default="facesentry-api", description="Service name")
    version: str = Field(default=VERSION, description="System version")
    timestamp: datetime = Field(default_factory=get_current_utc_time, description="Current UTC timestamp")
    database: str = Field(default="connected", description="Database connection state")
    agent_status: str = Field(default="ready", description="Agent daemon availability")


class SystemStatusResponse(BaseModel):
    """Detailed operational status model."""
    state: SystemState = Field(default=SystemState.UNINITIALIZED, description="Current system state")
    profile_enrolled: bool = Field(default=False, description="Whether an authorized user profile exists")
    active_camera_index: int = Field(default=DEFAULT_CAMERA_INDEX, description="Index of camera in use")
    is_snoozed: bool = Field(default=False, description="Whether monitoring is snoozed")
    snooze_remaining_seconds: int = Field(default=0, description="Remaining seconds if snoozed")
    uptime_seconds: float = Field(default=0.0, description="Daemon uptime in seconds")
    last_event: Optional[str] = Field(default=None, description="Description of the last security event")


class HardwareConfigSchema(BaseModel):
    """Hardware capture configuration."""
    camera_index: int = Field(default=DEFAULT_CAMERA_INDEX, ge=0)
    capture_resolution: List[int] = Field(default=[640, 480], min_length=2, max_length=2)
    target_fps: int = Field(default=DEFAULT_TARGET_FPS, ge=5, le=60)
    backend_api: str = Field(default="DirectShow")


class PolicyConfigSchema(BaseModel):
    """Timing and biometric threshold policies."""
    absence_timeout_seconds: int = Field(default=DEFAULT_ABSENCE_TIMEOUT_SECONDS, ge=1, le=120)
    unknown_face_timeout_seconds: int = Field(default=DEFAULT_UNKNOWN_FACE_TIMEOUT_SECONDS, ge=1, le=60)
    spoof_lock_timeout_seconds: int = Field(default=DEFAULT_SPOOF_LOCK_TIMEOUT_SECONDS, ge=0, le=30)
    similarity_threshold: float = Field(default=DEFAULT_SIMILARITY_THRESHOLD, ge=0.1, le=1.0)
    liveness_threshold: float = Field(default=DEFAULT_LIVENESS_THRESHOLD, ge=0.1, le=1.0)
    lock_on_absence: bool = Field(default=True)
    lock_on_unknown_face: bool = Field(default=True)
    lock_on_spoof: bool = Field(default=True)


class BrowserProtectionConfigSchema(BaseModel):
    """Configuration for safe browser process and session termination."""
    enabled: bool = Field(default=False)
    mode: BrowserProtectionMode = Field(default=BrowserProtectionMode.DISABLED)
    close_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)


class SystemConfigSchema(BaseModel):
    """Complete consolidated system configuration."""
    hardware: HardwareConfigSchema = Field(default_factory=HardwareConfigSchema)
    policies: PolicyConfigSchema = Field(default_factory=PolicyConfigSchema)
    browser_protection: BrowserProtectionConfigSchema = Field(default_factory=BrowserProtectionConfigSchema)


class SecurityEventCreate(BaseModel):
    """Payload to log a security event."""
    event_type: EventType
    confidence: Optional[float] = None
    liveness_score: Optional[float] = None
    action_taken: str = "RECORD_ONLY"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SecurityEventRead(BaseModel):
    """Retrieved security audit log record."""
    id: int
    timestamp: datetime
    event_type: EventType
    confidence: Optional[float] = None
    liveness_score: Optional[float] = None
    action_taken: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Real-Time Telemetry Schemas (Phase 6)
# ==========================================

class TelemetrySnapshot(BaseModel):
    """Real-time operational snapshot transmitted to Web dashboard."""
    timestamp: float = Field(description="Epoch timestamp of snapshot generation")
    agent_status: str = Field(default="RUNNING", description="Agent daemon status")
    camera_status: str = Field(default="CONNECTED", description="Camera stream status")
    authentication_state: str = Field(default="AUTHENTICATING", description="Biometric authentication state")
    recognition_similarity: float = Field(default=0.0, description="Normalized cosine similarity score")
    liveness_state: str = Field(default="OBSERVING", description="Temporal liveness state")
    liveness_verified: bool = Field(default=False, description="Whether liveness is currently verified")
    liveness_confidence: float = Field(default=0.0, description="Confidence of face detector")
    face_detected: bool = Field(default=False, description="Whether at least one face is in frame")
    face_count: int = Field(default=0, description="Number of detected faces")
    absence_duration: float = Field(default=0.0, description="Elapsed absence countdown seconds")
    stranger_duration: float = Field(default=0.0, description="Elapsed stranger presence seconds")
    spoof_duration: float = Field(default=0.0, description="Elapsed unverified liveness seconds")
    decision_state: str = Field(default="INITIALIZING", description="Authoritative decision state")
    lock_requested: bool = Field(default=False, description="Whether lock was triggered on this cycle")
    last_security_event: Optional[Dict[str, Any]] = Field(default=None, description="Most recent security event")
    system_uptime: float = Field(default=0.0, description="Agent uptime in seconds")
    bounding_box: Optional[List[int]] = Field(default=None, description="Minimal [x, y, w, h] visualization metadata")


class WebSocketMessage(BaseModel):
    """Envelope for all WebSocket messages sent to client."""
    type: str = Field(description="Message type identifier")
    timestamp: float = Field(description="Timestamp of message dispatch")
    schema_version: str = Field(default="1.0", description="Schema format version")
    payload: Dict[str, Any] = Field(description="Structured message payload")


class TelemetryPublishRequest(BaseModel):
    """Payload sent by agent publisher to API state broker."""
    snapshot: Optional[TelemetrySnapshot] = None
    event: Optional[Dict[str, Any]] = None
    message_type: str = Field(default="SNAPSHOT")


# ==========================================
# Enrollment API & Wizard Schemas (Phase 7)
# ==========================================

class EnrollmentStartRequest(BaseModel):
    """Request payload to initiate enrollment session."""
    user_id: str = Field(default="default_user", description="Identifier of profile to enroll")
    target_samples: int = Field(default=15, ge=5, le=50, description="Required high-quality sample count")


class EnrollmentStatusResponse(BaseModel):
    """Real-time status of the enrollment wizard session."""
    state: str = Field(default="IDLE", description="Current enrollment lifecycle state")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Enrollment completion fraction (0.0 - 1.0)")
    captured_samples: int = Field(default=0, description="Number of validated samples collected")
    required_samples: int = Field(default=15, description="Target total samples needed")
    quality: str = Field(default="PENDING", description="Quality status of candidate frame")
    guidance: str = Field(default="READY", description="Real-time interactive user guidance instruction")
    liveness_verified: bool = Field(default=False, description="Whether liveness confirmation was completed")
    error_message: Optional[str] = Field(default=None, description="Detailed error reason if failed")
    is_complete: bool = Field(default=False, description="Whether enrollment has finalized successfully")


class EnrollmentUpdateRequest(BaseModel):
    """Internal message from agent to API broker updating enrollment state."""
    status: EnrollmentStatusResponse


# ==========================================
# Secure PIN Fallback Schemas (Phase 8)
# ==========================================

class PinSetupRequest(BaseModel):
    """Request payload for first-time PIN configuration."""
    new_pin: str = Field(min_length=4, max_length=12, description="New secret PIN (4-12 digits/chars)")
    confirm_pin: str = Field(min_length=4, max_length=12, description="Confirmation PIN")


class PinChangeRequest(BaseModel):
    """Request payload to change existing PIN."""
    current_pin: str = Field(description="Existing PIN for authentication")
    new_pin: str = Field(min_length=4, max_length=12, description="New secret PIN (4-12 digits/chars)")
    confirm_pin: str = Field(min_length=4, max_length=12, description="Confirmation of new PIN")


class PinVerifyRequest(BaseModel):
    """Request payload to verify PIN for temporary emergency recovery."""
    pin: str = Field(min_length=1, max_length=32, description="Entered candidate PIN")


class PinStatusResponse(BaseModel):
    """Safe status overview of the local PIN fallback subsystem."""
    is_configured: bool = Field(default=False, description="Whether a PIN has been setup")
    is_locked: bool = Field(default=False, description="Whether PIN verification is temporarily locked out")
    attempts_remaining: int = Field(default=5, description="Remaining failed attempts before lockout")
    locked_until: Optional[float] = Field(default=None, description="Epoch timestamp until lockout expires")
    in_recovery: bool = Field(default=False, description="Whether system is currently in temporary recovery")
    recovery_until: Optional[float] = Field(default=None, description="Epoch timestamp until temporary recovery expires")
    reason: Optional[str] = Field(default=None, description="Status detail or error reason")


class PinVerifyResponse(BaseModel):
    """Result of a PIN verification attempt."""
    authenticated: bool = Field(description="Whether PIN was successfully verified")
    in_recovery: bool = Field(default=False, description="Whether emergency recovery is active")
    recovery_until: Optional[float] = Field(default=None, description="Epoch timestamp until recovery expires")
    attempts_remaining: int = Field(default=5, description="Remaining attempts before lockout")
    is_locked: bool = Field(default=False, description="Whether PIN subsystem is currently locked out")
    locked_until: Optional[float] = Field(default=None, description="Lockout expiration timestamp")
    reason: Optional[str] = Field(default=None, description="Safe user-facing explanation")
