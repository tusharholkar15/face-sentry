"""
FaceSentry FastAPI Application Entrypoint
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from packages.shared.constants import VERSION, SYSTEM_NAME
from apps.api.config import api_settings
from apps.api.database import db_manager
from apps.api.routers import health, status, config, events, telemetry_ws, enroll_routes, pin_routes

# Configure logging
logging.basicConfig(
    level=getattr(logging, api_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("facesentry.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: initialize DB on startup and log shutdown."""
    logger.info(f"Starting {SYSTEM_NAME} API v{VERSION} on {api_settings.host}:{api_settings.port}")
    await db_manager.init_db()
    await db_manager.log_event(
        event_type="SYSTEM_STARTUP",
        action_taken="DAEMON_INITIALIZED",
        metadata={"service": "facesentry-api", "version": VERSION},
    )
    yield
    logger.info("FaceSentry API shutting down...")
    await db_manager.log_event(
        event_type="SYSTEM_SHUTDOWN",
        action_taken="DAEMON_TERMINATED",
        metadata={"service": "facesentry-api"},
    )


def create_app() -> FastAPI:
    """Factory function for FastAPI application."""
    app = FastAPI(
        title=SYSTEM_NAME,
        description="Privacy-First Windows Face Authentication & Auto-Lock Security Engine",
        version=VERSION,
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Routers
    app.include_router(health.router)
    app.include_router(status.router)
    app.include_router(config.router)
    app.include_router(events.router)
    app.include_router(telemetry_ws.router)
    app.include_router(enroll_routes.router)
    app.include_router(pin_routes.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.api.main:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=False,
    )
