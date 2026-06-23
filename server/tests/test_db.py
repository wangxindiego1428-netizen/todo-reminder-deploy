import db


def make_conn(tmp_path):
    conn = db.get_conn(str(tmp_path / "t.db"))
    db.init_db(conn)
    return conn


def test_add_and_list(tmp_path):
    conn = make_conn(tmp_path)
    tid = db.add_todo(conn, "写周报", "2026-06-23")
    assert isinstance(tid, int)
    rows = db.list_todos(conn, "2026-06-23")
    assert len(rows) == 1
    r = rows[0]
    assert r["title"] == "写周报"
    assert r["date"] == "2026-06-23"
    assert r["remind_at"] is None
    assert r["done"] == 0
    assert r["notified"] == 0
    assert r["rolled_from"] is None
    assert r["created_at"]


def test_add_with_remind_at(tmp_path):
    conn = make_conn(tmp_path)
    db.add_todo(conn, "开会", "2026-06-23", remind_at="15:00")
    r = db.list_todos(conn, "2026-06-23")[0]
    assert r["remind_at"] == "15:00"


def test_set_done_and_unfinished(tmp_path):
    conn = make_conn(tmp_path)
    a = db.add_todo(conn, "A", "2026-06-23")
    db.add_todo(conn, "B", "2026-06-23")
    db.set_done(conn, a, True)
    unfinished = db.unfinished_on(conn, "2026-06-23")
    assert [r["title"] for r in unfinished] == ["B"]
    # 取消勾销
    db.set_done(conn, a, False)
    assert len(db.unfinished_on(conn, "2026-06-23")) == 2


def test_update_and_delete(tmp_path):
    conn = make_conn(tmp_path)
    tid = db.add_todo(conn, "old", "2026-06-23")
    db.update_todo(conn, tid, title="new", remind_at="09:30")
    r = db.get_todo(conn, tid)
    assert r["title"] == "new"
    assert r["remind_at"] == "09:30"
    db.delete_todo(conn, tid)
    assert db.get_todo(conn, tid) is None


def test_due_timed_todos_filters(tmp_path):
    conn = make_conn(tmp_path)
    t_timed = db.add_todo(conn, "timed", "2026-06-23", remind_at="15:00")
    db.add_todo(conn, "no-time", "2026-06-23")                       # 无到点 → 不算
    t_done = db.add_todo(conn, "done", "2026-06-23", remind_at="16:00")
    db.set_done(conn, t_done, True)                                  # 已完成 → 不算
    t_notified = db.add_todo(conn, "notified", "2026-06-23", remind_at="17:00")
    db.mark_notified(conn, t_notified)                               # 已推 → 不算
    rows = db.due_timed_todos(conn, "2026-06-23")
    assert [r["id"] for r in rows] == [t_timed]


def test_rollover_unfinished(tmp_path):
    conn = make_conn(tmp_path)
    a = db.add_todo(conn, "leftover", "2026-06-22", remind_at="10:00")
    b = db.add_todo(conn, "finished", "2026-06-22")
    db.set_done(conn, b, True)
    count = db.rollover_unfinished(conn, "2026-06-22", "2026-06-23")
    assert count == 1
    moved = db.list_todos(conn, "2026-06-23")
    assert len(moved) == 1
    assert moved[0]["title"] == "leftover"
    assert moved[0]["rolled_from"] == "2026-06-22"
    assert moved[0]["notified"] == 0          # 滚动后到点提醒重新生效
    # 原日期已无该未完成项
    assert db.list_todos(conn, "2026-06-22") == []


def test_rollover_keeps_original_rolled_from(tmp_path):
    """连续滚动多天，rolled_from 保留最初日期。"""
    conn = make_conn(tmp_path)
    db.add_todo(conn, "x", "2026-06-21")
    db.rollover_unfinished(conn, "2026-06-21", "2026-06-22")
    db.rollover_unfinished(conn, "2026-06-22", "2026-06-23")
    r = db.list_todos(conn, "2026-06-23")[0]
    assert r["rolled_from"] == "2026-06-21"


def test_upcoming_timed_todos(tmp_path):
    conn = make_conn(tmp_path)
    today = db.add_todo(conn, "今天到点", "2026-06-23", remind_at="15:00")
    future = db.add_todo(conn, "下周到点", "2026-06-30", remind_at="09:00")
    db.add_todo(conn, "今天无时间", "2026-06-23")                       # 无到点 → 不算
    db.add_todo(conn, "昨天到点", "2026-06-22", remind_at="10:00")      # 过去日期 → 不算
    done = db.add_todo(conn, "未来已完成", "2026-06-30", remind_at="11:00")
    db.set_done(conn, done, True)                                      # 已完成 → 不算
    rows = db.upcoming_timed_todos(conn, "2026-06-23")
    assert [r["id"] for r in rows] == [today, future]                  # 当天+未来, 按日期排序
