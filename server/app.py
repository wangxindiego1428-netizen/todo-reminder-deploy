import logging
import os
import re
import socket
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, redirect, request

import auth
import db as db_mod
import scheduler as sched_mod
from config import TZ, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("todo.app")
_TZ = ZoneInfo(TZ)

HERE = os.path.dirname(os.path.abspath(__file__))

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _valid_remind_at(value):
    """None/空字符串视为合法（不设提醒）；否则必须符合 H:MM 或 HH:MM 24h 格式。"""
    if not value:
        return True
    return bool(_TIME_RE.match(value))


def pick_port(preferred):
    """preferred 可用就用它；被占用或为 0 时由系统选一个空闲端口。"""
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", preferred))
                return preferred
            except OSError:
                log.warning("端口 %s 被占用，改用随机空闲端口", preferred)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def create_app(cfg, db_path):
    app = Flask(__name__, template_folder=os.path.join(HERE, "templates"),
                static_folder=os.path.join(HERE, "static"))
    conn = db_mod.get_conn(db_path)
    db_mod.init_db(conn)
    app.config["TODO_CONN"] = conn
    app.config["TODO_CFG"] = cfg
    app.config["TODO_SCHED"] = None  # 由 run() 注入，测试时为 None

    def _today():
        return datetime.now(_TZ).strftime("%Y-%m-%d")

    def require_auth(f):
        @wraps(f)
        def wrapper(*a, **kw):
            token = request.cookies.get("token") or request.headers.get("X-Token")
            if not auth.verify_token(cfg, token):
                return jsonify({"error": "unauthorized"}), 401
            return f(*a, **kw)
        return wrapper

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return app.send_static_file("login.html")
        data = request.get_json(silent=True) or request.form
        if not auth.check_password(cfg, data.get("password")):
            return jsonify({"error": "wrong password"}), 401
        resp = jsonify({"ok": True})
        resp.set_cookie("token", auth.expected_token(cfg), max_age=60 * 60 * 24 * 365,
                        httponly=True, samesite="Lax")
        return resp

    @app.route("/")
    def index():
        token = request.cookies.get("token")
        if not auth.verify_token(cfg, token):
            return redirect("/login")
        return app.send_static_file("index.html")

    @app.route("/api/todos", methods=["GET"])
    @require_auth
    def list_todos():
        date = request.args.get("date") or _today()
        return jsonify({"todos": db_mod.list_todos(conn, date)})

    @app.route("/api/todos", methods=["POST"])
    @require_auth
    def add_todo():
        d = request.get_json(force=True)
        title = (d.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title required"}), 400
        date = d.get("date") or _today()
        remind_at = d.get("remind_at") or None
        if remind_at and not _valid_remind_at(remind_at):
            return jsonify({"error": "invalid remind_at"}), 400
        tid = db_mod.add_todo(conn, title, date, remind_at)
        _reschedule(tid)
        return jsonify({"id": tid})

    @app.route("/api/todos/<int:tid>/done", methods=["POST"])
    @require_auth
    def set_done(tid):
        d = request.get_json(silent=True) or {}
        db_mod.set_done(conn, tid, bool(d.get("done", True)))
        return jsonify({"ok": True})

    @app.route("/api/todos/<int:tid>", methods=["PATCH"])
    @require_auth
    def update_todo(tid):
        d = request.get_json(force=True)
        remind_at = d.get("remind_at")
        if remind_at and not _valid_remind_at(remind_at):
            return jsonify({"error": "invalid remind_at"}), 400
        db_mod.update_todo(conn, tid, title=d.get("title"), remind_at=remind_at)
        _reschedule(tid)
        return jsonify({"ok": True})

    @app.route("/api/todos/<int:tid>", methods=["DELETE"])
    @require_auth
    def delete_todo(tid):
        db_mod.delete_todo(conn, tid)
        return jsonify({"ok": True})

    @app.route("/api/due", methods=["GET"])
    @require_auth
    def due():
        date = request.args.get("date") or _today()
        now_s = request.args.get("now")
        since_s = request.args.get("since")
        now = datetime.fromisoformat(now_s).replace(tzinfo=_TZ) if now_s else datetime.now(_TZ)
        since = datetime.fromisoformat(since_s).replace(tzinfo=_TZ) if since_s else None
        out = []
        for t in db_mod.list_todos(conn, date):
            if t["done"] or not t["remind_at"]:
                continue
            dt = sched_mod.remind_datetime(t, day=date)
            if dt is None or dt > now:
                continue
            if since is not None and dt <= since:
                continue
            out.append(t)
        return jsonify({"due": out})

    def _reschedule(tid):
        sched = app.config.get("TODO_SCHED")
        if sched is None:
            return
        todo = db_mod.get_todo(conn, tid)
        if todo:
            sched_mod.schedule_timed_todo(sched, conn, cfg["serverchan_sendkey"], todo)

    return app


def run():
    cfg = load_config(os.path.join(HERE, "config.json"))
    db_path = os.path.join(HERE, "todos.db")
    app = create_app(cfg, db_path)
    conn = app.config["TODO_CONN"]
    sched = sched_mod.start_scheduler(conn, cfg)
    app.config["TODO_SCHED"] = sched
    port = pick_port(cfg["port"])
    with open(os.path.join(HERE, "current_port.txt"), "w") as f:
        f.write(str(port))
    log.info("待办提醒服务启动：http://0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, use_reloader=False)


if __name__ == "__main__":
    run()
