"""
晚晴 — Database Models and Operations
SQLite-based storage for Tasks, Notes, and Reminders.
"""
import sqlite3
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from contextlib import contextmanager

DB_PATH = os.environ.get("WANQING_DB", os.path.join(os.path.dirname(__file__), "..", "wanqing.db"))
CST = timezone(timedelta(hours=8))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'cancelled')),
                category TEXT DEFAULT 'life',
                due_time TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                scheduler_id TEXT
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id),
                remind_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'fired', 'missed', 'cancelled')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                fired_at TEXT
            );

            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS family_messages (
                id TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pushed',
                created_at TEXT NOT NULL,
                read_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_due_time ON tasks(due_time);
            CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
            CREATE INDEX IF NOT EXISTS idx_reminders_task ON reminders(task_id);
            CREATE INDEX IF NOT EXISTS idx_family_messages_created ON family_messages(created_at);
        """)


def generate_id(prefix: str) -> str:
    """Generate a prefixed ID."""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# === Task Operations ===

def create_task(user_id: str, title: str, due_time: Optional[str] = None,
                description: Optional[str] = None, category: str = "life",
                scheduler_id: Optional[str] = None) -> dict:
    task_id = generate_id("task")
    now = datetime.now(CST).isoformat()
    with db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, title, description, status, category, due_time, created_at, scheduler_id) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
            (task_id, user_id, title, description, category, due_time, now, scheduler_id)
        )
    return get_task(task_id)


def get_task(task_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def query_tasks(user_id: str, status: str = "pending",
                date: Optional[str] = None) -> List[dict]:
    """Query tasks by user, status, and optional date."""
    with db() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE user_id = ? AND status = ? AND date(due_time) = date(?) ORDER BY due_time",
                (user_id, status, date)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE user_id = ? AND status = ? ORDER BY due_time",
                (user_id, status)
            ).fetchall()
        return [dict(r) for r in rows]


def complete_task(task_id: str) -> Optional[dict]:
    now = datetime.now(CST).isoformat()
    with db() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?",
            (now, task_id)
        )
    return get_task(task_id)


def cancel_task(task_id: str) -> Optional[dict]:
    with db() as conn:
        conn.execute("UPDATE tasks SET status = 'cancelled' WHERE id = ?", (task_id,))
    return get_task(task_id)


def find_task_by_title(user_id: str, title_keyword: str, status: str = "pending") -> List[dict]:
    """Fuzzy match tasks by title keyword."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status = ? AND title LIKE ? ORDER BY created_at DESC",
            (user_id, status, f"%{title_keyword}%")
        ).fetchall()
        return [dict(r) for r in rows]


# === Note Operations ===

def create_note(user_id: str, content: str, category: str = "general") -> dict:
    note_id = generate_id("note")
    now = datetime.now(CST).isoformat()
    with db() as conn:
        conn.execute(
            "INSERT INTO notes (id, user_id, content, category, created_at) VALUES (?, ?, ?, ?, ?)",
            (note_id, user_id, content, category, now)
        )
    return get_note(note_id)


def get_note(note_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row) if row else None


def query_notes(user_id: str, category: Optional[str] = None, limit: int = 20) -> List[dict]:
    with db() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM notes WHERE user_id = ? AND category = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]


# === Reminder Operations ===

def create_reminder(task_id: str, remind_at: str) -> dict:
    reminder_id = generate_id("rem")
    now = datetime.now(CST).isoformat()
    with db() as conn:
        conn.execute(
            "INSERT INTO reminders (id, task_id, remind_at, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (reminder_id, task_id, remind_at, now)
        )
    return get_reminder(reminder_id)


def get_reminder(reminder_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row) if row else None


def fire_reminder(reminder_id: str) -> Optional[dict]:
    now = datetime.now(CST).isoformat()
    with db() as conn:
        conn.execute(
            "UPDATE reminders SET status = 'fired', fired_at = ? WHERE id = ?",
            (now, reminder_id)
        )
    return get_reminder(reminder_id)


def get_pending_reminders(until: Optional[str] = None) -> List[dict]:
    """Get all pending reminders up to a given time."""
    if not until:
        until = datetime.now(CST).isoformat()
    with db() as conn:
        rows = conn.execute(
            """SELECT r.*, t.title, t.user_id FROM reminders r
               JOIN tasks t ON r.task_id = t.id
               WHERE r.status = 'pending' AND r.remind_at <= ?
               ORDER BY r.remind_at""",
            (until,)
        ).fetchall()
        return [dict(r) for r in rows]


# === Family Message Operations ===

def create_family_message(sender: str, text: str) -> dict:
    msg_id = generate_id("fam")
    now = datetime.now(CST).isoformat()
    with db() as conn:
        conn.execute(
            "INSERT INTO family_messages (id, sender, text, status, created_at) VALUES (?, ?, ?, 'pushed', ?)",
            (msg_id, sender, text, now)
        )
    return get_family_message(msg_id)


def get_family_message(msg_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM family_messages WHERE id = ?", (msg_id,)).fetchone()
        return dict(row) if row else None


def query_family_messages(limit: int = 10, unread_only: bool = False) -> List[dict]:
    with db() as conn:
        sql = "SELECT * FROM family_messages"
        if unread_only:
            sql += " WHERE read_at IS NULL"
        sql += " ORDER BY created_at DESC LIMIT ?"
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]


def mark_family_messages_read() -> int:
    now = datetime.now(CST).isoformat()
    with db() as conn:
        cur = conn.execute(
            "UPDATE family_messages SET read_at = ? WHERE read_at IS NULL", (now,)
        )
        return cur.rowcount


def mark_family_message_read(message_id: str) -> None:
    """单条标已读（设备已播报 mirror 投递成功时调用）。"""
    now = datetime.now(CST).isoformat()
    with db() as conn:
        conn.execute(
            "UPDATE family_messages SET read_at = ? WHERE id = ? AND read_at IS NULL",
            (now, message_id),
        )


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at: {DB_PATH}")
