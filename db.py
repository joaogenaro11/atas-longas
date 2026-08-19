"""
Banco leve (SQLite) para a fila de transcrição.

Guarda o estado de cada job (aguardando/processando/concluído/erro), o
progresso e o caminho do TXT gerado. Serve para acompanhar a fila e para
recuperar o trabalho caso a aplicação seja reiniciada.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.getcwd(), "data", "jobs.db"))
_LOCK = threading.Lock()


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db() -> None:
    with _LOCK, _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                quality     TEXT NOT NULL DEFAULT 'equilibrado',
                workers     INTEGER NOT NULL DEFAULT 1,
                status      TEXT NOT NULL DEFAULT 'aguardando',
                progress    REAL NOT NULL DEFAULT 0,
                message     TEXT DEFAULT '',
                txt_path    TEXT DEFAULT '',
                language    TEXT DEFAULT '',
                duration    REAL DEFAULT 0,
                model       TEXT DEFAULT '',
                created_at  TEXT NOT NULL
            )
            """
        )


def add_job(filename: str, stored_path: str, quality: str, workers: int) -> int:
    with _LOCK, _conn() as c:
        cur = c.execute(
            "INSERT INTO jobs (filename, stored_path, quality, workers, created_at) "
            "VALUES (?,?,?,?,?)",
            (filename, stored_path, quality, workers, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def update_job(job_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [job_id]
    with _LOCK, _conn() as c:
        c.execute(f"UPDATE jobs SET {cols} WHERE id=?", vals)


def get_job(job_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def delete_job(job_id: int) -> None:
    with _LOCK, _conn() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def list_jobs() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def next_pending() -> dict | None:
    """Próximo job aguardando (FIFO). Também retoma jobs 'processando' órfãos."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE status IN ('aguardando','processando') "
            "ORDER BY id ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
