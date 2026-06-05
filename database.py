"""SQLite chat history storage helpers."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable


class ChatDatabase:
    """Small SQLite wrapper for one-to-one chat history."""

    def __init__(self, db_path: str | Path = "chat_history.db") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    peer_id TEXT NOT NULL,
                    peer_name TEXT NOT NULL,
                    peer_ip TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('in', 'out')),
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_peer ON messages(peer_id, id)"
            )

    def add_message(
        self,
        peer_id: str,
        peer_name: str,
        peer_ip: str,
        direction: str,
        body: str,
    ) -> None:
        if direction not in {"in", "out"}:
            raise ValueError("direction must be 'in' or 'out'")

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (peer_id, peer_name, peer_ip, direction, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (peer_id, peer_name, peer_ip, direction, body),
            )

    def get_messages(self, peer_id: str, limit: int = 100) -> list[sqlite3.Row]:
        with self._lock, self._connect() as connection:
            rows: Iterable[sqlite3.Row] = connection.execute(
                """
                SELECT peer_id, peer_name, peer_ip, direction, body, created_at
                FROM messages
                WHERE peer_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (peer_id, limit),
            )
            return list(reversed(list(rows)))
