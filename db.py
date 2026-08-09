from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import aiosqlite

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "accessflow.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    answers TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    ticket_channel_id INTEGER,
    created_at TEXT NOT NULL,
    user_copy_message_id INTEGER
)
"""

Status = Literal["pending", "accepted", "denied", "deleted", "left"]

_db: aiosqlite.Connection | None = None


@dataclass(frozen=True)
class Application:
    message_id: int
    user_id: int
    username: str
    answers: dict[str, str]
    status: Status
    ticket_channel_id: int | None
    created_at: str
    user_copy_message_id: int | None


async def init_db(db_path: Path = DB_PATH) -> None:
    global _db
    if _db is not None:
        await _db.close()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    await conn.execute(_SCHEMA)
    await conn.commit()
    _db = conn


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def _conn() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("database not initialized; call init_db() first")
    return _db


def _row_to_application(row: sqlite3.Row) -> Application:
    return Application(
        message_id=row[1],
        user_id=row[2],
        username=row[3],
        answers=json.loads(row[4]),
        status=row[5],
        ticket_channel_id=row[6],
        created_at=row[7],
        user_copy_message_id=row[8],
    )


async def save_application(
    *,
    message_id: int,
    user_id: int,
    username: str,
    answers: dict[str, str],
    ticket_channel_id: int | None = None,
    status: Status = "pending",
) -> None:
    conn = _conn()
    await conn.execute(
        "INSERT INTO applications "
        "(message_id, user_id, username, answers, status, ticket_channel_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            message_id,
            user_id,
            username,
            json.dumps(answers),
            status,
            ticket_channel_id,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await conn.commit()


async def get_by_message(message_id: int) -> Application | None:
    conn = _conn()
    cursor = await conn.execute(
        "SELECT * FROM applications WHERE message_id = ?", (message_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _row_to_application(row) if row is not None else None


async def get_by_ticket_channel(ticket_channel_id: int) -> Application | None:
    conn = _conn()
    cursor = await conn.execute(
        "SELECT * FROM applications WHERE ticket_channel_id = ?", (ticket_channel_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _row_to_application(row) if row is not None else None


async def update_status(message_id: int, status: Status) -> None:
    conn = _conn()
    await conn.execute(
        "UPDATE applications SET status = ? WHERE message_id = ?", (status, message_id)
    )
    await conn.commit()


async def set_ticket_channel(message_id: int, ticket_channel_id: int) -> None:
    conn = _conn()
    await conn.execute(
        "UPDATE applications SET ticket_channel_id = ? WHERE message_id = ?",
        (ticket_channel_id, message_id),
    )
    await conn.commit()


async def clear_ticket_channel(message_id: int) -> None:
    conn = _conn()
    await conn.execute(
        "UPDATE applications SET ticket_channel_id = NULL WHERE message_id = ?",
        (message_id,),
    )
    await conn.commit()


async def get_by_user_copy_message(user_copy_message_id: int) -> Application | None:
    conn = _conn()
    cursor = await conn.execute(
        "SELECT * FROM applications WHERE user_copy_message_id = ?",
        (user_copy_message_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _row_to_application(row) if row is not None else None


async def get_active_by_user(user_id: int) -> Application | None:
    conn = _conn()
    cursor = await conn.execute(
        "SELECT * FROM applications WHERE user_id = ? AND status = 'pending' "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    return _row_to_application(row) if row is not None else None


async def set_user_copy_message(message_id: int, user_copy_message_id: int) -> None:
    conn = _conn()
    await conn.execute(
        "UPDATE applications SET user_copy_message_id = ? WHERE message_id = ?",
        (user_copy_message_id, message_id),
    )
    await conn.commit()
