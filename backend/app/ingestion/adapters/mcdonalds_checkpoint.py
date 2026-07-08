"""SQLite checkpoint/resume for the McDonald's adaptive grid crawl."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHECKPOINT_FILENAME = "grid.sqlite"
META_ADAPTER_VERSION = "adapter_version"
META_REQUEST_COUNT = "request_count"
META_INITIAL_FEED_COMPLETE = "initial_feed_complete"


@dataclass(frozen=True)
class McDonaldsCheckpointState:
    adapter_version: str
    request_count: int
    initial_feed_complete: bool
    visited_points: set[tuple[float, float]]
    queue: list[tuple[float, float, float]]
    stores: dict[str, dict[str, Any]]


class McDonaldsGridCheckpoint:
    def __init__(self, directory: Path, *, adapter_version: str) -> None:
        self.directory = directory
        self.adapter_version = adapter_version
        self.path = directory / CHECKPOINT_FILENAME
        self.directory.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=30.0)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visited (
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                PRIMARY KEY (lat, lng)
            );
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                step REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stores (
                external_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    @property
    def exists(self) -> bool:
        if not self.path.exists():
            return False
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?",
            (META_ADAPTER_VERSION,),
        ).fetchone()
        return row is not None

    def load(self) -> McDonaldsCheckpointState | None:
        if not self.exists:
            return None

        meta = dict(self._conn.execute("SELECT key, value FROM meta").fetchall())
        saved_version = meta.get(META_ADAPTER_VERSION)
        if saved_version != self.adapter_version:
            logger.warning(
                "mcdonalds_checkpoint_version_mismatch",
                extra={"saved": saved_version, "expected": self.adapter_version},
            )
            return None

        visited_points = {
            (float(lat), float(lng))
            for lat, lng in self._conn.execute("SELECT lat, lng FROM visited")
        }
        queue = [
            (float(lat), float(lng), float(step))
            for lat, lng, step in self._conn.execute(
                "SELECT lat, lng, step FROM queue ORDER BY id"
            )
        ]
        stores: dict[str, dict[str, Any]] = {}
        for external_id, payload in self._conn.execute("SELECT external_id, payload FROM stores"):
            stores[str(external_id)] = json.loads(payload)

        return McDonaldsCheckpointState(
            adapter_version=saved_version,
            request_count=int(meta.get(META_REQUEST_COUNT, "0")),
            initial_feed_complete=meta.get(META_INITIAL_FEED_COMPLETE, "0") == "1",
            visited_points=visited_points,
            queue=queue,
            stores=stores,
        )

    def save(
        self,
        *,
        request_count: int,
        initial_feed_complete: bool,
        visited_points: set[tuple[float, float]],
        queue: list[tuple[float, float, float]],
        stores: dict[str, dict[str, Any]],
    ) -> None:
        temp_path = self.path.with_suffix(".tmp")
        temp_conn = sqlite3.connect(temp_path, timeout=30.0)
        try:
            temp_conn.execute("PRAGMA journal_mode=WAL")
            temp_conn.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE visited (lat REAL NOT NULL, lng REAL NOT NULL, PRIMARY KEY (lat, lng));
                CREATE TABLE queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    step REAL NOT NULL
                );
                CREATE TABLE stores (external_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                """
            )
            temp_conn.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                [
                    (META_ADAPTER_VERSION, self.adapter_version),
                    (META_REQUEST_COUNT, str(request_count)),
                    (META_INITIAL_FEED_COMPLETE, "1" if initial_feed_complete else "0"),
                ],
            )
            if visited_points:
                temp_conn.executemany(
                    "INSERT INTO visited (lat, lng) VALUES (?, ?)",
                    list(visited_points),
                )
            if queue:
                temp_conn.executemany(
                    "INSERT INTO queue (lat, lng, step) VALUES (?, ?, ?)",
                    queue,
                )
            if stores:
                temp_conn.executemany(
                    "INSERT INTO stores (external_id, payload) VALUES (?, ?)",
                    [(key, json.dumps(value, ensure_ascii=False)) for key, value in stores.items()],
                )
            temp_conn.commit()
        finally:
            temp_conn.close()

        os.replace(temp_path, self.path)

        logger.info(
            "mcdonalds_checkpoint_saved",
            extra={
                "path": str(self.path),
                "request_count": request_count,
                "visited_points": len(visited_points),
                "queue_size": len(queue),
                "store_count": len(stores),
            },
        )

    def reopen(self) -> None:
        self._conn.close()
        self._conn = sqlite3.connect(self.path, timeout=30.0)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def clear(self) -> None:
        self._conn.close()
        if self.path.exists():
            self.path.unlink()
        logger.info("mcdonalds_checkpoint_cleared", extra={"path": str(self.path)})

    def close(self) -> None:
        self._conn.close()
