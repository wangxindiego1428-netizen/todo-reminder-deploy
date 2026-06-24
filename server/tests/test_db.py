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


def test_occurs_on_rules():
    base = {"date": "2026-06-24"}  # 周三
    daily = {**base, "repeat": "daily"}
    weekly = {**base, "repeat": "weekly"}
    monthly = {**base, "repeat": "monthly"}
    yearly = {**base, "repeat": "yearly"}
    oneoff = {**base, "repeat": "none"}
    # 锚点当天都成立
    for t in (daily, weekly, monthly, yearly, oneoff):
        assert db.occurs_on(t, "2026-06-24")
    # 锚点之前一律不成立
    assert not db.occurs_on(daily, "2026-06-23")
    # daily: 之后每天
    assert db.occurs_on(daily, "2026-06-25")
    # weekly: 同星期三
    assert db.occurs_on(weekly, "2026-07-01") and not db.occurs_on(weekly, "2026-06-25")
    # monthly: 同号(24)
    assert db.occurs_on(monthly, "2026-07-24") and not db.occurs_on(monthly, "2026-07-25")
    # yearly: 同月日
    assert db.occurs_on(yearly, "2027-06-24") and not db.occurs_on(yearly, "2026-07-24")
    # one-off: 仅当天
    assert not db.occurs_on(oneoff, "2026-06-25")


def test_recurring_in_todos_on_with_per_date_done(tmp_path):
    conn = make_conn(tmp_path)
    rid = db.add_todo(conn, "每日喝水", "2026-06-24", remind_at="09:00", repeat="daily")
    db.add_todo(conn, "一次性会议", "2026-06-25", remind_at="14:00")
    # 6/25 应同时出现：周期"每日喝水" + 当天一次性"会议"
    items = db.list_todos(conn, "2026-06-25")
    titles = {t["title"] for t in items}
    assert titles == {"每日喝水", "一次性会议"}
    # 6/25 把"每日喝水"勾完成 → 当天 done，但 6/26 仍未完成
    db.set_completion(conn, rid, "2026-06-25", True)
    by_title = {t["title"]: t for t in db.list_todos(conn, "2026-06-25")}
    assert by_title["每日喝水"]["done"] == 1
    assert db.list_todos(conn, "2026-06-26")[0]["done"] == 0  # 次日自动回到未完成
    # 取消完成
    db.set_completion(conn, rid, "2026-06-25", False)
    assert {t["title"]: t for t in db.list_todos(conn, "2026-06-25")}["每日喝水"]["done"] == 0


def test_recurring_excluded_from_oneoff_queries(tmp_path):
    conn = make_conn(tmp_path)
    db.add_todo(conn, "周期", "2026-06-24", remind_at="09:00", repeat="daily")
    one = db.add_todo(conn, "一次性", "2026-06-24", remind_at="10:00")
    assert [t["id"] for t in db.due_timed_todos(conn, "2026-06-24")] == [one]
    assert [t["id"] for t in db.upcoming_timed_todos(conn, "2026-06-24")] == [one]
    assert [t["repeat"] for t in db.recurring_todos(conn)] == ["daily"]


def test_recurring_not_rolled(tmp_path):
    conn = make_conn(tmp_path)
    db.add_todo(conn, "周期", "2026-06-23", remind_at="09:00", repeat="daily")
    one = db.add_todo(conn, "一次性遗留", "2026-06-23")
    n = db.rollover_unfinished(conn, "2026-06-23", "2026-06-24")
    assert n == 1  # 只滚动一次性
    moved = db.list_todos(conn, "2026-06-24")
    assert any(t["title"] == "一次性遗留" for t in moved)
    # 周期项仍在其锚点、未被改日期
    assert db.recurring_todos(conn)[0]["date"] == "2026-06-23"


def test_update_todo_date_and_repeat(tmp_path):
    conn = make_conn(tmp_path)
    tid = db.add_todo(conn, "t", "2026-06-24", remind_at="09:00")
    db.update_todo(conn, tid, date="2026-06-30", remind_at="11:00", repeat="weekly")
    r = db.get_todo(conn, tid)
    assert r["date"] == "2026-06-30" and r["remind_at"] == "11:00" and r["repeat"] == "weekly"


def test_all_todos_sorted(tmp_path):
    conn = make_conn(tmp_path)
    db.add_todo(conn, "晚", "2026-06-30")
    db.add_todo(conn, "早", "2026-06-24")
    assert [t["title"] for t in db.all_todos(conn)] == ["早", "晚"]
