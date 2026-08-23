"""
API Configuration Management
"""

import json
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from packages.shared.constants import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_DATABASE_PATH,
)


class APISettings(BaseSettings):
    """Configuration settings for FaceSentry API service."""
    host: str = Field(default=DEFAULT_API_HOST, alias="FACESENTRY_API_HOST")
    port: int = Field(default=DEFAULT_API_PORT, alias="FACESENTRY_API_PORT")
    log_level: str = Field(default="INFO", alias="FACESENTRY_LOG_LEVEL")
    cors_origins: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="FACESENTRY_CORS_ORIGINS",
    )
    database_path: str = Field(default=DEFAULT_DATABASE_PATH, alias="FACESENTRY_DATABASE_PATH")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


api_settings = APISettings()
