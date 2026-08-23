"""
FaceSentry Secure PIN Fallback API Router
Handles localhost-only PIN setup, change, verification, and rate-limited lockout status.
"""

import time
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import JSONResponse

from packages.shared.schemas import (
    PinSetupRequest,
    PinChangeRequest,
    PinVerifyRequest,
    PinStatusResponse,
    PinVerifyResponse,
    WebSocketMessage,
)
from apps.agent.facesentry_agent.pin_service import PinAuthService
from apps.api.database import db_manager
from apps.api.routers.telemetry_ws import telemetry_broker

logger = logging.getLogger("facesentry.api.pin")
router = APIRouter(prefix="/api/v1/pin", tags=["pin"])

# Global in-process PIN authentication service instance
pin_service = PinAuthService()


def _enforce_localhost(request: Request) -> None:
    """Verify incoming HTTP request originates from localhost."""
    client_host = request.client.host if request.client else "unknown"
    if client_host not in ["127.0.0.1", "localhost", "::1", "testclient"]:
        logger.warning(f"Rejected non-localhost PIN API request from: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PIN API is strictly accessible only from localhost.",
        )


@router.get("/status", response_model=PinStatusResponse)
async def get_pin_status(request: Request):
    """Retrieve safe overview of PIN configuration, attempts, and lockout state."""
    _enforce_localhost(request)
    return pin_service.get_status()


@router.post("/setup", response_model=PinStatusResponse)
async def setup_pin(req: PinSetupRequest, request: Request):
    """Configure initial emergency fallback PIN."""
    _enforce_localhost(request)
    success, message = pin_service.setup_pin(req.new_pin, req.confirm_pin)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    await db_manager.log_event(
        event_type="PIN_SETUP",
        action_taken="PIN_CONFIGURED",
        metadata={"service": "pin_service"},
    )

    msg = WebSocketMessage(
        type="PIN_AUTHENTICATED",
        timestamp=time.time(),
        schema_version="1.0",
        payload={"event": "PIN_SETUP", "status": "CONFIGURED"},
    )
    await telemetry_broker.broadcast_message(msg)
    return pin_service.get_status()


@router.post("/change", response_model=PinStatusResponse)
async def change_pin(req: PinChangeRequest, request: Request):
    """Change existing PIN credentials after verifying current PIN."""
    _enforce_localhost(request)
    success, message = pin_service.change_pin(req.current_pin, req.new_pin, req.confirm_pin)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    await db_manager.log_event(
        event_type="PIN_CHANGED",
        action_taken="PIN_UPDATED",
        metadata={"service": "pin_service"},
    )
    return pin_service.get_status()


@router.post("/verify", response_model=PinVerifyResponse)
async def verify_pin(req: PinVerifyRequest, request: Request):
    """
    Authenticate emergency PIN to grant temporary recovery.
    Enforces brute-force lockout and safe audit logging.
    """
    _enforce_localhost(request)
    result = pin_service.verify_pin(req.pin)

    if result.authenticated:
        await db_manager.log_event(
            event_type="PIN_AUTHENTICATED",
            action_taken="EMERGENCY_RECOVERY_GRANTED",
            metadata={"recovery_until": result.recovery_until},
        )
        # Broadcast recovery event to connected WebSockets
        msg = WebSocketMessage(
            type="PIN_AUTHENTICATED",
            timestamp=time.time(),
            schema_version="1.0",
            payload={
                "event": "PIN_AUTHENTICATED",
                "recovery_until": result.recovery_until,
            },
        )
        await telemetry_broker.broadcast_message(msg)
    else:
        event_type = "PIN_LOCKOUT_STARTED" if result.is_locked else "PIN_FAILED"
        await db_manager.log_event(
            event_type=event_type,
            action_taken="ATTEMPT_REJECTED",
            metadata={
                "attempts_remaining": result.attempts_remaining,
                "is_locked": result.is_locked,
                "locked_until": result.locked_until,
            },
        )
        msg = WebSocketMessage(
            type="PIN_FAILED",
            timestamp=time.time(),
            schema_version="1.0",
            payload={
                "event": event_type,
                "attempts_remaining": result.attempts_remaining,
                "is_locked": result.is_locked,
                "locked_until": result.locked_until,
            },
        )
        await telemetry_broker.broadcast_message(msg)

    return result
