import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from config import TZ

_COLUMNS = ["id", "title", "date", "remind_at", "done", "notified", "rolled_from", "created_at"]


def get_conn(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            remind_at TEXT,
            done INTEGER NOT NULL DEFAULT 0,
            notified INTEGER NOT NULL DEFAULT 0,
            rolled_from TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _row_to_dict(row):
    return {k: row[k] for k in _COLUMNS} if row is not None else None


def add_todo(conn, title, date, remind_at=None):
    now = datetime.now(ZoneInfo(TZ)).isoformat()
    cur = conn.execute(
        "INSERT INTO todos (title, date, remind_at, done, notified, rolled_from, created_at) "
        "VALUES (?, ?, ?, 0, 0, NULL, ?)",
        (title, date, remind_at, now),
    )
    conn.commit()
    return cur.lastrowid


def list_todos(conn, date):
    rows = conn.execute(
        "SELECT * FROM todos WHERE date = ? ORDER BY done ASC, "
        "CASE WHEN remind_at IS NULL THEN 1 ELSE 0 END, remind_at ASC, id ASC",
        (date,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_todo(conn, tid):
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (tid,)).fetchone()
    return _row_to_dict(row)


def set_done(conn, tid, done):
    conn.execute("UPDATE todos SET done = ? WHERE id = ?", (1 if done else 0, tid))
    conn.commit()


def update_todo(conn, tid, title=None, remind_at=None):
    cur = get_todo(conn, tid)
    if cur is None:
        return
    new_title = title if title is not None else cur["title"]
    new_remind = remind_at if remind_at is not None else cur["remind_at"]
    # 改了到点时间 → 重置 notified，让新的时间能重新提醒
    notified = 0 if remind_at is not None else cur["notified"]
    conn.execute(
        "UPDATE todos SET title = ?, remind_at = ?, notified = ? WHERE id = ?",
        (new_title, new_remind, notified, tid),
    )
    conn.commit()


def delete_todo(conn, tid):
    conn.execute("DELETE FROM todos WHERE id = ?", (tid,))
    conn.commit()


def mark_notified(conn, tid):
    conn.execute("UPDATE todos SET notified = 1 WHERE id = ?", (tid,))
    conn.commit()


def unfinished_on(conn, date):
    rows = conn.execute(
        "SELECT * FROM todos WHERE date = ? AND done = 0 "
        "ORDER BY CASE WHEN remind_at IS NULL THEN 1 ELSE 0 END, remind_at ASC, id ASC",
        (date,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def due_timed_todos(conn, date):
    """当天、有到点时间、未完成、未推送的待办。"""
    rows = conn.execute(
        "SELECT * FROM todos WHERE date = ? AND remind_at IS NOT NULL "
        "AND done = 0 AND notified = 0 ORDER BY remind_at ASC, id ASC",
        (date,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def rollover_unfinished(conn, from_date, to_date):
    """把 from_date 未完成的待办挪到 to_date，记录最初来源，重置 notified；
    同时清理 from_date 已完成的待办（旧日期完成项无需保留）。返回滚动条数。"""
    rows = conn.execute(
        "SELECT * FROM todos WHERE date = ? AND done = 0", (from_date,)
    ).fetchall()
    for r in rows:
        origin = r["rolled_from"] if r["rolled_from"] is not None else from_date
        conn.execute(
            "UPDATE todos SET date = ?, rolled_from = ?, notified = 0 WHERE id = ?",
            (to_date, origin, r["id"]),
        )
    # 清理旧日期已完成项
    conn.execute("DELETE FROM todos WHERE date = ? AND done = 1", (from_date,))
    conn.commit()
    return len(rows)
