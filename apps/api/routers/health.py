"""
Health Check Endpoints
"""

from datetime import datetime, timezone
from fastapi import APIRouter, status
from packages.shared.schemas import HealthResponse
from packages.shared.constants import VERSION
from apps.api.database import db_manager

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Root Health Check",
    description="Returns service vitality, database connection status, and current version.",
)
async def get_health() -> HealthResponse:
    """Check connectivity to database and operational status."""
    is_db_healthy = await db_manager.check_health()
    return HealthResponse(
        status="healthy" if is_db_healthy else "degraded",
        service="facesentry-api",
        version=VERSION,
        timestamp=datetime.now(timezone.utc),
        database="connected" if is_db_healthy else "disconnected",
        agent_status="ready",
    )


@router.get(
    "/api/v1/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Versioned API v1 Health Check",
    description="Returns versioned API health status.",
)
async def get_versioned_health() -> HealthResponse:
    """Returns the same health metrics under the /api/v1 prefix."""
    return await get_health()
