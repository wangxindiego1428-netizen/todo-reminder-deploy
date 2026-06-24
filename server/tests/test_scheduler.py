from datetime import datetime
from zoneinfo import ZoneInfo

import scheduler


def _todo(tid, title, remind_at=None, rolled_from=None):
    return {
        "id": tid, "title": title, "date": "2026-06-23", "remind_at": remind_at,
        "done": 0, "notified": 0, "rolled_from": rolled_from, "created_at": "x",
    }


def test_format_summary_basic():
    todos = [_todo(1, "写周报"), _todo(2, "开会", remind_at="15:00")]
    title, body = scheduler.format_summary("2026-06-23", todos)
    assert "今日待办" in title
    assert "2" in title              # 2 项未完成
    assert "写周报" in body
    assert "15:00" in body
    assert "开会" in body


def test_format_summary_counts_rolled():
    todos = [_todo(1, "新事"), _todo(2, "旧事", rolled_from="2026-06-21")]
    title, body = scheduler.format_summary("2026-06-23", todos)
    assert "往日遗留" in title or "往日遗留" in body
    assert "1" in title


def test_format_summary_empty_returns_none():
    assert scheduler.format_summary("2026-06-23", []) is None


def test_format_timed():
    title, body = scheduler.format_timed(_todo(1, "对接会", remind_at="15:00"))
    assert "对接会" in title or "对接会" in body
    assert "15:00" in body


def test_remind_datetime():
    todo = _todo(1, "x", remind_at="15:30")
    dt = scheduler.remind_datetime(todo)
    assert dt == datetime(2026, 6, 23, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_remind_datetime_none_when_no_time():
    assert scheduler.remind_datetime(_todo(1, "x")) is None


import db


def _conn(tmp_path):
    c = db.get_conn(str(tmp_path / "s.db"))
    db.init_db(c)
    return c


class Recorder:
    def __init__(self):
        self.pushes = []

    def __call__(self, sendkey, title, body, session=None):
        self.pushes.append((title, body))
        return True


def test_run_daily_summary_pushes_when_unfinished(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    db.add_todo(conn, "写周报", "2026-06-23")
    rec = Recorder()
    monkeypatch.setattr(scheduler, "push_serverchan", rec)
    scheduler.run_daily_summary(conn, sendkey="KEY", date="2026-06-23")
    assert len(rec.pushes) == 1
    assert "写周报" in rec.pushes[0][1]


def test_run_daily_summary_silent_when_empty(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    rec = Recorder()
    monkeypatch.setattr(scheduler, "push_serverchan", rec)
    scheduler.run_daily_summary(conn, sendkey="KEY", date="2026-06-23")
    assert rec.pushes == []          # 无未完成不打扰


def test_run_rollover_moves_unfinished(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    db.add_todo(conn, "leftover", "2026-06-22")
    monkeypatch.setattr(scheduler, "push_serverchan", Recorder())
    scheduler.run_rollover(conn, from_date="2026-06-22", to_date="2026-06-23")
    assert len(db.list_todos(conn, "2026-06-23")) == 1


def test_fire_timed_pushes_and_marks(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    tid = db.add_todo(conn, "开会", "2026-06-23", remind_at="15:00")
    rec = Recorder()
    monkeypatch.setattr(scheduler, "push_serverchan", rec)
    scheduler.fire_timed(conn, sendkey="KEY", todo_id=tid)
    assert len(rec.pushes) == 1
    assert db.get_todo(conn, tid)["notified"] == 1


def test_fire_timed_skips_if_done(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    tid = db.add_todo(conn, "已完成", "2026-06-23", remind_at="15:00")
    db.set_done(conn, tid, True)
    rec = Recorder()
    monkeypatch.setattr(scheduler, "push_serverchan", rec)
    scheduler.fire_timed(conn, sendkey="KEY", todo_id=tid)
    assert rec.pushes == []          # 已勾销不再提醒


class FakeSched:
    """记录 add_job 调用，用于测试 schedule_timed_todo 的触发。"""
    def __init__(self):
        self.jobs = []

    def add_job(self, *a, **kw):
        self.jobs.append((a, kw))


def test_run_rollover_schedules_timed_todos(tmp_path):
    """run_rollover 带 sched+sendkey 时，应为滚过来的有效 timed todo 注册调度。"""
    conn = _conn(tmp_path)
    # 用相对今天的未来日期，避免硬编码日期随真实时间推移而失效
    from datetime import timedelta
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    from_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    to_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    # to_date 在未来，remind_at 任意时间都晚于现在 → schedule_timed_todo 必会注册
    db.add_todo(conn, "滚动待办", from_date, remind_at="23:59")
    fake_sched = FakeSched()
    scheduler.run_rollover(conn, from_date=from_date, to_date=to_date,
                           sched=fake_sched, sendkey="KEY")
    # 滚动后今天应有该待办
    assert len(db.list_todos(conn, to_date)) == 1
    # 且应注册了到点任务
    assert len(fake_sched.jobs) >= 1


def test_fire_recurring_pushes_when_due(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    today = scheduler._today()
    tid = db.add_todo(conn, "每日喝水", today, remind_at="09:00", repeat="daily")
    rec = Recorder()
    monkeypatch.setattr(scheduler, "push_serverchan", rec)
    scheduler.fire_recurring(conn, "KEY", tid)
    assert len(rec.pushes) == 1 and "每日喝水" in rec.pushes[0][1]


def test_fire_recurring_skips_when_done_today(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    today = scheduler._today()
    tid = db.add_todo(conn, "每日", today, remind_at="09:00", repeat="daily")
    db.set_completion(conn, tid, today, True)
    rec = Recorder()
    monkeypatch.setattr(scheduler, "push_serverchan", rec)
    scheduler.fire_recurring(conn, "KEY", tid)
    assert rec.pushes == []


def test_fire_recurring_skips_when_not_occurring(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    from datetime import timedelta
    future = (datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=3)).strftime("%Y-%m-%d")
    tid = db.add_todo(conn, "未来开始", future, remind_at="09:00", repeat="daily")
    rec = Recorder()
    monkeypatch.setattr(scheduler, "push_serverchan", rec)
    scheduler.fire_recurring(conn, "KEY", tid)
    assert rec.pushes == []


def test_format_recurring():
    title, body = scheduler.format_recurring(
        {"title": "喝水", "remind_at": "09:00", "repeat": "daily"})
    assert "每日" in title and "喝水" in body and "09:00" in body


def test_schedule_recurring_registers_cron(tmp_path):
    conn = _conn(tmp_path)
    todo = {"id": 1, "title": "周会", "date": "2026-06-24", "remind_at": "10:00",
            "repeat": "weekly", "done": 0, "notified": 0}
    fake = FakeSched()
    scheduler.schedule_recurring_todo(fake, conn, "KEY", todo)
    assert len(fake.jobs) == 1
    # 周三锚点 → day_of_week 应为 2（周一=0）
    assert fake.jobs[0][1].get("day_of_week") == 2
