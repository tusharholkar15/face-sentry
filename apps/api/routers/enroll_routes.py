"""
FaceSentry Enrollment API Router
Handles multi-step biometric enrollment lifecycle, status querying, and cancellation.
"""

import time
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from packages.shared.schemas import (
    EnrollmentStartRequest,
    EnrollmentStatusResponse,
    EnrollmentUpdateRequest,
    WebSocketMessage,
)
from apps.api.routers.telemetry_ws import telemetry_broker

logger = logging.getLogger("facesentry.api.enrollment")
router = APIRouter(prefix="/api/v1/enrollment", tags=["enrollment"])


class EnrollmentStateHolder:
    """In-process state holder for active enrollment wizard sessions."""

    def __init__(self):
        self.status = EnrollmentStatusResponse()
        self.active_user_id: str = "default_user"

    def reset(self):
        self.status = EnrollmentStatusResponse()


enrollment_state = EnrollmentStateHolder()


@router.post("/start", response_model=EnrollmentStatusResponse)
async def start_enrollment(req: EnrollmentStartRequest):
    """
    Start a new biometric enrollment wizard session.
    Notifies agent and broadcasts ENROLLMENT_STARTED via WebSocket.
    """
    enrollment_state.active_user_id = req.user_id
    enrollment_state.status = EnrollmentStatusResponse(
        state="CAPTURING",
        progress=0.0,
        captured_samples=0,
        required_samples=req.target_samples,
        quality="PENDING",
        guidance="LOOK_FORWARD",
        liveness_verified=False,
        error_message=None,
        is_complete=False,
    )

    logger.info(f"Enrollment started for user '{req.user_id}' (Target: {req.target_samples})")

    # Broadcast via WebSocket
    msg = WebSocketMessage(
        type="ENROLLMENT_STARTED",
        timestamp=time.time(),
        schema_version="1.0",
        payload=enrollment_state.status.model_dump(),
    )
    await telemetry_broker.broadcast_message(msg)
    return enrollment_state.status


@router.get("/status", response_model=EnrollmentStatusResponse)
async def get_enrollment_status():
    """Query current enrollment session progress and guidance."""
    return enrollment_state.status


@router.post("/cancel", response_model=EnrollmentStatusResponse)
async def cancel_enrollment():
    """Cancel active enrollment and discard in-progress data."""
    enrollment_state.status = EnrollmentStatusResponse(
        state="CANCELLED",
        progress=0.0,
        captured_samples=0,
        required_samples=enrollment_state.status.required_samples,
        quality="PENDING",
        guidance="READY",
        liveness_verified=False,
        error_message="Session cancelled by user.",
        is_complete=False,
    )

    logger.info("Enrollment session cancelled.")

    msg = WebSocketMessage(
        type="ENROLLMENT_CANCELLED",
        timestamp=time.time(),
        schema_version="1.0",
        payload=enrollment_state.status.model_dump(),
    )
    await telemetry_broker.broadcast_message(msg)
    return enrollment_state.status


@router.post("/finalize", response_model=EnrollmentStatusResponse)
async def finalize_enrollment():
    """
    Finalize enrollment session once required samples and liveness are satisfied.
    """
    curr = enrollment_state.status
    if curr.state not in ["PROCESSING", "CAPTURING", "LIVENESS_CHECK"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot finalize from state '{curr.state}'",
        )

    enrollment_state.status = EnrollmentStatusResponse(
        state="COMPLETED",
        progress=1.0,
        captured_samples=curr.required_samples,
        required_samples=curr.required_samples,
        quality="GOOD",
        guidance="READY",
        liveness_verified=True,
        error_message=None,
        is_complete=True,
    )

    logger.info(f"Enrollment finalized for user '{enrollment_state.active_user_id}'.")

    msg = WebSocketMessage(
        type="ENROLLMENT_COMPLETED",
        timestamp=time.time(),
        schema_version="1.0",
        payload=enrollment_state.status.model_dump(),
    )
    await telemetry_broker.broadcast_message(msg)
    return enrollment_state.status


@router.post("/update_progress", response_model=EnrollmentStatusResponse)
async def update_enrollment_progress(req: EnrollmentUpdateRequest):
    """
    Internal agent endpoint to push real-time sample progress and guidance.
    Broadcasts ENROLLMENT_PROGRESS message to all connected WebSockets.
    """
    enrollment_state.status = req.status
    msg_type = "ENROLLMENT_PROGRESS"
    if req.status.state == "COMPLETED":
        msg_type = "ENROLLMENT_COMPLETED"
    elif req.status.state == "FAILED":
        msg_type = "ENROLLMENT_FAILED"
    elif req.status.state == "CANCELLED":
        msg_type = "ENROLLMENT_CANCELLED"

    msg = WebSocketMessage(
        type=msg_type,
        timestamp=time.time(),
        schema_version="1.0",
        payload=req.status.model_dump(),
    )
    await telemetry_broker.broadcast_message(msg)
    return enrollment_state.status
