"""SQLite cache shared by every source adapter.

Each entry is (source, key) -> JSON payload plus the time it was fetched. Adapters
decide their own TTL; the cache only stores and returns. Stale entries are kept and
served when the upstream source fails, so the app degrades to old data instead of
showing nothing.
"""

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    payload: Any
    fetched_at: datetime

    def age(self) -> timedelta:
        return datetime.now(timezone.utc) - self.fetched_at


class Cache:
    def __init__(self, path: Path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS source_cache (
                source TEXT NOT NULL,
                key TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (source, key)
            )
            """
        )
        self._db.commit()

    def get(self, source: str, key: str) -> CacheEntry | None:
        with self._lock:
            row = self._db.execute(
                "SELECT payload, fetched_at FROM source_cache WHERE source = ? AND key = ?",
                (source, key),
            ).fetchone()
        if row is None:
            return None
        return CacheEntry(json.loads(row[0]), datetime.fromisoformat(row[1]))

    def put(self, source: str, key: str, payload: Any) -> CacheEntry:
        entry = CacheEntry(payload, datetime.now(timezone.utc))
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO source_cache (source, key, fetched_at, payload) VALUES (?, ?, ?, ?)",
                (source, key, entry.fetched_at.isoformat(), json.dumps(payload)),
            )
            self._db.commit()
        return entry
