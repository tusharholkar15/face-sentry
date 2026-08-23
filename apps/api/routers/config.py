"""
System Configuration Endpoints
"""

import json
from fastapi import APIRouter, status
from packages.shared.schemas import SystemConfigSchema
from apps.api.database import db_manager

router = APIRouter(prefix="/api/v1", tags=["Configuration"])


@router.get(
    "/config",
    response_model=SystemConfigSchema,
    status_code=status.HTTP_200_OK,
    summary="Get System Configuration",
    description="Returns current hardware capture and policy settings.",
)
async def get_config() -> SystemConfigSchema:
    """Retrieve persisted configuration or defaults."""
    async with db_manager.get_connection() as conn:
        async with conn.execute("SELECT value_json FROM system_config WHERE key = 'main_config';") as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    data = json.loads(row[0])
                    return SystemConfigSchema(**data)
                except Exception:
                    pass
    
    # Return default configuration if not yet customized
    return SystemConfigSchema()


@router.patch(
    "/config",
    response_model=SystemConfigSchema,
    status_code=status.HTTP_200_OK,
    summary="Update System Configuration",
    description="Updates policy and hardware parameters.",
)
async def update_config(updated_config: SystemConfigSchema) -> SystemConfigSchema:
    """Persist updated configuration to database."""
    config_json = json.dumps(updated_config.model_dump())
    async with db_manager.get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO system_config (key, value_json, updated_at)
            VALUES ('main_config', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (config_json,),
        )
        await conn.commit()

    await db_manager.log_event(
        event_type="CONFIG_UPDATED",
        action_taken="PERSIST_CONFIG",
        metadata=updated_config.model_dump(),
    )
    return updated_config
