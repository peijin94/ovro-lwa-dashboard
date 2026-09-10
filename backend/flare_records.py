"""SQLite persistence for OVRO-LWA flare probability nowcasts."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class FlareRecordStore:
    """Store and retrieve timestamped R1/R2/R3 probabilities."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS flarecast_record (
                    timeUT TEXT PRIMARY KEY,
                    R1p REAL NOT NULL CHECK (R1p >= 0 AND R1p <= 1),
                    R2p REAL NOT NULL CHECK (R2p >= 0 AND R2p <= 1),
                    R3p REAL NOT NULL CHECK (R3p >= 0 AND R3p <= 1)
                )
                """
            )

    def append(self, time_ut: str, r1p: float, r2p: float, r3p: float) -> None:
        probabilities = (float(r1p), float(r2p), float(r3p))
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in probabilities):
            raise ValueError("Flare probabilities must be finite values between 0 and 1")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO flarecast_record (timeUT, R1p, R2p, R3p)
                VALUES (?, ?, ?, ?)
                """,
                (time_ut, *probabilities),
            )

    def recent(
        self,
        minutes: int = 30,
        *,
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        cutoff = reference.astimezone(timezone.utc) - timedelta(minutes=minutes)
        cutoff_text = cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT timeUT, R1p, R2p, R3p
                FROM flarecast_record
                WHERE timeUT >= ?
                ORDER BY timeUT ASC
                """,
                (cutoff_text,),
            ).fetchall()
        return [dict(row) for row in rows]
