"""
Простая база данных на SQLite.
Хранит связку telegram_id → ФИО водителя после регистрации.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bot.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    """Создаёт таблицы при первом запуске."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                telegram_id INTEGER PRIMARY KEY,
                full_name   TEXT NOT NULL,
                username    TEXT,
                status      TEXT DEFAULT 'pending'
            )
        """)
        conn.commit()


def save_driver(telegram_id: int, full_name: str, username: str = None):
    """Сохраняет или обновляет водителя."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO drivers (telegram_id, full_name, username, status)
            VALUES (?, ?, ?, 'pending')
            ON CONFLICT(telegram_id) DO UPDATE SET
                full_name = excluded.full_name,
                username  = excluded.username,
                status    = 'pending'
        """, (telegram_id, full_name, username))
        conn.commit()


def get_driver_name(telegram_id: int) -> str | None:
    """Возвращает ФИО водителя по telegram_id, или None если не найден."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT full_name FROM drivers WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()
    return row[0] if row else None


def set_driver_status(telegram_id: int, status: str):
    """Обновляет статус верификации водителя."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE drivers SET status = ? WHERE telegram_id = ?",
            (status, telegram_id)
        )
        conn.commit()


def get_driver_status(telegram_id: int) -> str | None:
    """Возвращает статус водителя."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM drivers WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()
    return row[0] if row else None
