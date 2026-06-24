import logging
from datetime import date as date_cls, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

import db as db_mod
from notify import push_serverchan

from config import TZ

log = logging.getLogger("todo.scheduler")
_TZ = ZoneInfo(TZ)


def remind_datetime(todo, day=None):
    """把 todo 的 remind_at(HH:MM) 拼成当天的带时区 datetime；无到点时间返回 None。"""
    if not todo.get("remind_at"):
        return None
    date = day or todo["date"]
    hh, mm = todo["remind_at"].split(":")
    y, m, d = (int(x) for x in date.split("-"))
    return datetime(y, m, d, int(hh), int(mm), tzinfo=_TZ)


def _md(date):
    _, m, d = date.split("-")
    return f"{int(m)}/{int(d)}"


def format_summary(date, todos):
    """生成每日汇总消息 (title, body)；无未完成返回 None。"""
    if not todos:
        return None
    rolled = sum(1 for t in todos if t.get("rolled_from"))
    extra = f"，含 {rolled} 项往日遗留" if rolled else ""
    title = f"📋 今日待办 {_md(date)}（{len(todos)} 项未完成{extra}）"
    lines = []
    nums = "①②③④⑤⑥⑦⑧⑨⑩"
    for i, t in enumerate(todos):
        marker = nums[i] if i < len(nums) else f"{i + 1}."
        time_part = f"{t['remind_at']} " if t.get("remind_at") else ""
        head = "🔁" if t.get("repeat", "none") != "none" else ""
        tail = "（往日遗留）" if t.get("rolled_from") else ""
        lines.append(f"{marker} {head}{time_part}{t['title']}{tail}")
    return title, "\n".join(lines)


def format_timed(todo):
    """生成单条到点提醒消息 (title, body)。"""
    title = f"⏰ 到点提醒：{todo['title']}"
    body = f"{todo.get('remind_at', '')} {todo['title']}".strip()
    return title, body


_REPEAT_CN = {"daily": "每日", "weekly": "每周", "monthly": "每月", "yearly": "每年"}


def format_recurring(todo):
    """生成周期待办的到点提醒消息 (title, body)。"""
    label = _REPEAT_CN.get(todo.get("repeat"), "周期")
    title = f"🔁 {label}提醒：{todo['title']}"
    body = f"{todo.get('remind_at', '')} {todo['title']}".strip()
    return title, body


def _today():
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _yesterday():
    from datetime import timedelta
    return (datetime.now(_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def run_daily_summary(conn, sendkey, date=None):
    date = date or _today()
    todos = db_mod.unfinished_on(conn, date)
    msg = format_summary(date, todos)
    if msg is None:
        log.info("当天无未完成待办，跳过汇总")
        return
    title, body = msg
    push_serverchan(sendkey, title, body)


def run_rollover(conn, from_date=None, to_date=None, sched=None, sendkey=None):
    from_date = from_date or _yesterday()
    to_date = to_date or _today()
    n = db_mod.rollover_unfinished(conn, from_date, to_date)
    log.info("隔夜滚动：%s 项从 %s 挪到 %s", n, from_date, to_date)
    if sched is not None and sendkey is not None:
        for todo in db_mod.due_timed_todos(conn, to_date):
            schedule_timed_todo(sched, conn, sendkey, todo)


def fire_timed(conn, sendkey, todo_id):
    todo = db_mod.get_todo(conn, todo_id)
    if todo is None or todo["done"] == 1 or todo["notified"] == 1:
        return
    title, body = format_timed(todo)
    push_serverchan(sendkey, title, body)
    db_mod.mark_notified(conn, todo_id)


def schedule_timed_todo(sched, conn, sendkey, todo):
    """为单条【一次性】待办注册一次性到点任务（仅当到点在未来、未完成、未推）。"""
    if todo.get("repeat", "none") != "none":
        return
    if todo["done"] or todo["notified"] or not todo["remind_at"]:
        return
    run_at = remind_datetime(todo)
    if run_at is None or run_at <= datetime.now(_TZ):
        return
    sched.add_job(
        fire_timed, "date", run_date=run_at,
        args=[conn, sendkey, todo["id"]],
        id=f"timed-{todo['id']}", replace_existing=True,
    )


def fire_recurring(conn, sendkey, todo_id):
    """周期待办到点：仅当今天命中规则、且当天未完成时推送。"""
    todo = db_mod.get_todo(conn, todo_id)
    if todo is None or todo.get("repeat", "none") == "none":
        return
    today = _today()
    if not db_mod.occurs_on(todo, today):
        return
    if db_mod.is_completed(conn, todo_id, today):
        return
    title, body = format_recurring(todo)
    push_serverchan(sendkey, title, body)


def schedule_recurring_todo(sched, conn, sendkey, todo):
    """为周期待办注册 cron 提醒（按 每日/每周/每月/每年）。无到点时间则不排精确提醒。"""
    if todo.get("repeat", "none") == "none" or not todo["remind_at"]:
        return
    hh, mm = (int(x) for x in todo["remind_at"].split(":"))
    y, m, d = (int(x) for x in todo["date"].split("-"))
    rep = todo["repeat"]
    kwargs = {"hour": hh, "minute": mm}
    if rep == "weekly":
        kwargs["day_of_week"] = date_cls(y, m, d).weekday()  # 0=周一，与 APScheduler 一致
    elif rep == "monthly":
        kwargs["day"] = d
    elif rep == "yearly":
        kwargs["month"] = m
        kwargs["day"] = d
    sched.add_job(
        fire_recurring, "cron", args=[conn, sendkey, todo["id"]],
        id=f"recur-{todo['id']}", replace_existing=True, **kwargs,
    )


def start_scheduler(conn, cfg):
    """启动后台调度：每日汇总、隔夜滚动，并把今天及以后所有未到点的单条提醒排上。"""
    sched = BackgroundScheduler(timezone=TZ)
    sendkey = cfg["serverchan_sendkey"]

    sh, sm = (int(x) for x in cfg["summary_time"].split(":"))
    sched.add_job(run_daily_summary, "cron", hour=sh, minute=sm,
                  args=[conn, sendkey], id="daily-summary", replace_existing=True)

    rh, rm = (int(x) for x in cfg["rollover_time"].split(":"))
    # from_date/to_date 传 None，让 run_rollover 在触发时自动算昨天/今天
    sched.add_job(run_rollover, "cron", hour=rh, minute=rm,
                  args=[conn, None, None, sched, sendkey],
                  id="rollover", replace_existing=True)

    sched.start()
    # 排上今天及以后所有未到点的一次性提醒（含将来日期，确保重启不丢精确提醒）
    for todo in db_mod.upcoming_timed_todos(conn, _today()):
        schedule_timed_todo(sched, conn, sendkey, todo)
    # 重排所有周期提醒的 cron 任务（重启后照样按周期推）
    for todo in db_mod.recurring_todos(conn):
        schedule_recurring_todo(sched, conn, sendkey, todo)
    return sched
