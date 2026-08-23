"""
Agent Configuration Management
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from packages.shared.constants import (
    DEFAULT_CAMERA_INDEX,
    DEFAULT_TARGET_FPS,
    DEFAULT_ABSENCE_TIMEOUT_SECONDS,
    DEFAULT_UNKNOWN_FACE_TIMEOUT_SECONDS,
    DEFAULT_SPOOF_LOCK_TIMEOUT_SECONDS,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_LIVENESS_THRESHOLD,
)


class AgentSettings(BaseSettings):
    """Configuration settings for FaceSentry Windows background agent."""
    camera_index: int = Field(default=DEFAULT_CAMERA_INDEX, alias="FACESENTRY_CAMERA_INDEX")
    target_fps: int = Field(default=DEFAULT_TARGET_FPS, alias="FACESENTRY_TARGET_FPS")
    dry_run: bool = Field(default=True, alias="FACESENTRY_DRY_RUN", description="When true, workstation locks are simulated")
    enable_real_windows_lock: bool = Field(default=False, alias="FACESENTRY_ENABLE_REAL_WINDOWS_LOCK", description="When true, allows actual LockWorkStation calls")
    lock_dispatch_cooldown_seconds: float = Field(default=5.0, alias="FACESENTRY_LOCK_DISPATCH_COOLDOWN_SECONDS")
    lock_reason_required: bool = Field(default=True, alias="FACESENTRY_LOCK_REASON_REQUIRED")
    
    absence_timeout_seconds: int = Field(default=DEFAULT_ABSENCE_TIMEOUT_SECONDS, alias="FACESENTRY_ABSENCE_TIMEOUT_SECONDS")
    unknown_face_timeout_seconds: int = Field(default=DEFAULT_UNKNOWN_FACE_TIMEOUT_SECONDS, alias="FACESENTRY_UNKNOWN_FACE_TIMEOUT_SECONDS")
    spoof_lock_timeout_seconds: int = Field(default=DEFAULT_SPOOF_LOCK_TIMEOUT_SECONDS, alias="FACESENTRY_SPOOF_LOCK_TIMEOUT_SECONDS")
    similarity_threshold: float = Field(default=DEFAULT_SIMILARITY_THRESHOLD, alias="FACESENTRY_SIMILARITY_THRESHOLD")
    liveness_threshold: float = Field(default=DEFAULT_LIVENESS_THRESHOLD, alias="FACESENTRY_LIVENESS_THRESHOLD")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


agent_settings = AgentSettings()
