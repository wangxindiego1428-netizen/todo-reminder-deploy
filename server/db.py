import sqlite3
from datetime import date as date_cls, datetime
from zoneinfo import ZoneInfo

from config import TZ

_COLUMNS = ["id", "title", "date", "remind_at", "done", "notified",
            "rolled_from", "created_at", "repeat"]

REPEATS = ("none", "daily", "weekly", "monthly", "yearly")


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
            created_at TEXT NOT NULL,
            repeat TEXT NOT NULL DEFAULT 'none'
        )
        """
    )
    # 迁移：老库（无 repeat 列）补上该列
    cols = [r[1] for r in conn.execute("PRAGMA table_info(todos)").fetchall()]
    if "repeat" not in cols:
        conn.execute("ALTER TABLE todos ADD COLUMN repeat TEXT NOT NULL DEFAULT 'none'")
    # 周期待办的按天完成记录
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS completions (
            todo_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            PRIMARY KEY (todo_id, date)
        )
        """
    )
    conn.commit()


def _row_to_dict(row):
    return {k: row[k] for k in _COLUMNS} if row is not None else None


def _parse(d):
    y, m, dd = (int(x) for x in d.split("-"))
    return date_cls(y, m, dd)


def occurs_on(todo, date_str):
    """判断一条待办是否在 date_str 这天出现。
    一次性：日期相等；周期：从锚点日(todo['date'])起、按规则匹配。"""
    rep = todo.get("repeat", "none")
    if rep == "none":
        return todo["date"] == date_str
    anchor = _parse(todo["date"])
    target = _parse(date_str)
    if target < anchor:
        return False
    if rep == "daily":
        return True
    if rep == "weekly":
        return target.weekday() == anchor.weekday()
    if rep == "monthly":
        return target.day == anchor.day
    if rep == "yearly":
        return target.month == anchor.month and target.day == anchor.day
    return False


def add_todo(conn, title, date, remind_at=None, repeat="none"):
    if repeat not in REPEATS:
        repeat = "none"
    now = datetime.now(ZoneInfo(TZ)).isoformat()
    cur = conn.execute(
        "INSERT INTO todos (title, date, remind_at, done, notified, rolled_from, created_at, repeat) "
        "VALUES (?, ?, ?, 0, 0, NULL, ?, ?)",
        (title, date, remind_at, now, repeat),
    )
    conn.commit()
    return cur.lastrowid


def _completed_ids(conn, date):
    return {r["todo_id"] for r in
            conn.execute("SELECT todo_id FROM completions WHERE date = ?", (date,)).fetchall()}


def _sort_key(t):
    return (t["done"], 1 if t["remind_at"] is None else 0, t["remind_at"] or "", t["id"])


def todos_on(conn, date):
    """某天应展示的全部待办：当天的一次性 + 命中规则的周期项。
    周期项的 done 由该天的完成记录(completions)计算。"""
    items = []
    for r in conn.execute(
        "SELECT * FROM todos WHERE date = ? AND repeat = 'none'", (date,)
    ).fetchall():
        items.append(_row_to_dict(r))
    recurring = conn.execute(
        "SELECT * FROM todos WHERE repeat != 'none' AND date <= ?", (date,)
    ).fetchall()
    if recurring:
        completed = _completed_ids(conn, date)
        for r in recurring:
            t = _row_to_dict(r)
            if occurs_on(t, date):
                t["done"] = 1 if t["id"] in completed else 0
                items.append(t)
    items.sort(key=_sort_key)
    return items


def list_todos(conn, date):
    return todos_on(conn, date)


def get_todo(conn, tid):
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (tid,)).fetchone()
    return _row_to_dict(row)


def set_done(conn, tid, done):
    """一次性待办：直接置 done 列。"""
    conn.execute("UPDATE todos SET done = ? WHERE id = ?", (1 if done else 0, tid))
    conn.commit()


def is_completed(conn, tid, date):
    """周期待办在某天是否已完成。"""
    return conn.execute(
        "SELECT 1 FROM completions WHERE todo_id = ? AND date = ?", (tid, date)
    ).fetchone() is not None


def set_completion(conn, tid, date, done):
    """周期待办：按天记录完成/取消。"""
    if done:
        conn.execute(
            "INSERT OR IGNORE INTO completions (todo_id, date) VALUES (?, ?)", (tid, date)
        )
    else:
        conn.execute("DELETE FROM completions WHERE todo_id = ? AND date = ?", (tid, date))
    conn.commit()


def update_todo(conn, tid, title=None, remind_at=None, date=None, repeat=None):
    cur = get_todo(conn, tid)
    if cur is None:
        return
    new_title = title if title is not None else cur["title"]
    new_remind = remind_at if remind_at is not None else cur["remind_at"]
    new_date = date if date is not None else cur["date"]
    new_repeat = repeat if repeat is not None else cur["repeat"]
    if new_repeat not in REPEATS:
        new_repeat = cur["repeat"]
    # 改了到点时间 → 重置 notified，让新的时间能重新提醒（仅对一次性有意义）
    notified = 0 if remind_at is not None else cur["notified"]
    conn.execute(
        "UPDATE todos SET title = ?, remind_at = ?, date = ?, repeat = ?, notified = ? WHERE id = ?",
        (new_title, new_remind, new_date, new_repeat, notified, tid),
    )
    conn.commit()


def delete_todo(conn, tid):
    conn.execute("DELETE FROM todos WHERE id = ?", (tid,))
    conn.execute("DELETE FROM completions WHERE todo_id = ?", (tid,))
    conn.commit()


def mark_notified(conn, tid):
    conn.execute("UPDATE todos SET notified = 1 WHERE id = ?", (tid,))
    conn.commit()


def unfinished_on(conn, date):
    return [t for t in todos_on(conn, date) if not t["done"]]


def due_timed_todos(conn, date):
    """当天、一次性、有到点时间、未完成、未推送的待办（用于一次性到点排程）。"""
    rows = conn.execute(
        "SELECT * FROM todos WHERE date = ? AND repeat = 'none' AND remind_at IS NOT NULL "
        "AND done = 0 AND notified = 0 ORDER BY remind_at ASC, id ASC",
        (date,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def upcoming_timed_todos(conn, from_date):
    """from_date 当天及以后、一次性、有到点时间、未完成、未推送的待办（重启重排用）。"""
    rows = conn.execute(
        "SELECT * FROM todos WHERE date >= ? AND repeat = 'none' AND remind_at IS NOT NULL "
        "AND done = 0 AND notified = 0 ORDER BY date ASC, remind_at ASC, id ASC",
        (from_date,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def recurring_todos(conn):
    """所有周期待办（用于注册 cron 提醒）。"""
    rows = conn.execute(
        "SELECT * FROM todos WHERE repeat != 'none' ORDER BY id ASC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def all_todos(conn):
    """全部待办，按日期排序（总览用）。"""
    rows = conn.execute(
        "SELECT * FROM todos ORDER BY date ASC, "
        "CASE WHEN remind_at IS NULL THEN 1 ELSE 0 END, remind_at ASC, id ASC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def rollover_unfinished(conn, from_date, to_date):
    """把 from_date 未完成的【一次性】待办挪到 to_date（周期项不滚动，按规则自复现）；
    同时清理 from_date 已完成的一次性待办。返回滚动条数。"""
    rows = conn.execute(
        "SELECT * FROM todos WHERE date = ? AND done = 0 AND repeat = 'none'", (from_date,)
    ).fetchall()
    for r in rows:
        origin = r["rolled_from"] if r["rolled_from"] is not None else from_date
        conn.execute(
            "UPDATE todos SET date = ?, rolled_from = ?, notified = 0 WHERE id = ?",
            (to_date, origin, r["id"]),
        )
    conn.execute("DELETE FROM todos WHERE date = ? AND done = 1 AND repeat = 'none'", (from_date,))
    conn.commit()
    return len(rows)
