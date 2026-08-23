"""
Security Audit Log Endpoints
"""

from typing import List
from fastapi import APIRouter, status, Query
from packages.shared.schemas import SecurityEventRead, SecurityEventCreate
from apps.api.database import db_manager

router = APIRouter(prefix="/api/v1", tags=["Events"])


@router.get(
    "/events",
    response_model=List[SecurityEventRead],
    status_code=status.HTTP_200_OK,
    summary="Get Security Audit Logs",
    description="Returns recent security events (locks, authentications, failures).",
)
async def list_events(limit: int = Query(default=50, ge=1, le=500)) -> List[SecurityEventRead]:
    """Fetch paginated audit log entries."""
    rows = await db_manager.get_recent_events(limit=limit)
    return [SecurityEventRead(**row) for row in rows]


@router.post(
    "/events",
    response_model=SecurityEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record Security Event",
    description="Internal endpoint to record an audit log event.",
)
async def create_event(event_in: SecurityEventCreate) -> SecurityEventRead:
    """Insert and return a newly logged event."""
    event_id = await db_manager.log_event(
        event_type=event_in.event_type.value,
        action_taken=event_in.action_taken,
        confidence=event_in.confidence,
        liveness_score=event_in.liveness_score,
        metadata=event_in.metadata,
    )
    events = await db_manager.get_recent_events(limit=1)
    if not events:
        raise RuntimeError("Failed to retrieve created event")
    return SecurityEventRead(**events[0])
