"""
System Status Endpoints
"""

import time
from fastapi import APIRouter, status
from packages.shared.schemas import SystemStatusResponse
from packages.shared.enums import SystemState
from apps.api.database import db_manager

router = APIRouter(prefix="/api/v1", tags=["Status"])

START_TIME = time.time()


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get System Status",
    description="Returns current presence state, active profile existence, and uptime.",
)
async def get_system_status() -> SystemStatusResponse:
    """Retrieve operational status."""
    uptime = time.time() - START_TIME
    
    # Check if any profile is registered
    profile_enrolled = False
    async with db_manager.get_connection() as conn:
        async with conn.execute("SELECT COUNT(*) FROM biometric_profiles WHERE is_active = 1;") as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                profile_enrolled = True

    # Retrieve last event description
    last_event_desc = None
    events = await db_manager.get_recent_events(limit=1)
    if events:
        last_event_desc = f"{events[0]['event_type']} ({events[0]['action_taken']})"

    return SystemStatusResponse(
        state=SystemState.IDLE if profile_enrolled else SystemState.UNINITIALIZED,
        profile_enrolled=profile_enrolled,
        active_camera_index=0,
        is_snoozed=False,
        snooze_remaining_seconds=0,
        uptime_seconds=round(uptime, 2),
        last_event=last_event_desc,
    )
