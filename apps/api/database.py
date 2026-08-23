"""
SQLite Database Connection and Schema Management
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager
import aiosqlite

from apps.api.config import api_settings

logger = logging.getLogger("facesentry.database")


class DatabaseManager:
    """Manages SQLite asynchronous connection pool and database lifecycle."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or api_settings.database_path

    def _ensure_dir(self) -> None:
        """Ensure parent directory exists for SQLite database."""
        parent_dir = Path(self.db_path).parent
        parent_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Yield an active asynchronous SQLite connection context."""
        self._ensure_dir()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA foreign_keys=ON;")
            yield conn

    async def init_db(self) -> None:
        """Initialize database schema tables and indexes."""
        self._ensure_dir()
        logger.info(f"Initializing database schema at {self.db_path}")
        async with self.get_connection() as conn:
            # 1. Security Events Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT NOT NULL,
                    confidence REAL,
                    liveness_score REAL,
                    action_taken TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                );
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON security_events(timestamp);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON security_events(event_type);")

            # 2. System Settings Key-Value Store
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. Biometric Profiles Metadata Table (Templates stored securely)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS biometric_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT NOT NULL UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sample_count INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                );
            """)

            await conn.commit()
            logger.info("Database schema initialized successfully.")

    async def check_health(self) -> bool:
        """Verify database connectivity."""
        try:
            async with self.get_connection() as conn:
                async with conn.execute("SELECT 1;") as cursor:
                    row = await cursor.fetchone()
                    return row is not None and row[0] == 1
        except Exception as exc:
            logger.error(f"Database health check failed: {exc}")
            return False

    async def log_event(
        self,
        event_type: str,
        action_taken: str = "RECORD_ONLY",
        confidence: Optional[float] = None,
        liveness_score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Insert a security event audit record."""
        meta_json = json.dumps(metadata or {})
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO security_events (event_type, action_taken, confidence, liveness_score, metadata_json)
                VALUES (?, ?, ?, ?, ?);
                """,
                (event_type, action_taken, confidence, liveness_score, meta_json),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent security audit logs."""
        async with self.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, timestamp, event_type, confidence, liveness_score, action_taken, metadata_json
                FROM security_events
                ORDER BY id DESC
                LIMIT ?;
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    meta = {}
                    try:
                        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                    except Exception:
                        pass
                    results.append({
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "event_type": row["event_type"],
                        "confidence": row["confidence"],
                        "liveness_score": row["liveness_score"],
                        "action_taken": row["action_taken"],
                        "metadata": meta,
                    })
                return results


db_manager = DatabaseManager()
