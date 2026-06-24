import app as app_mod


def make_client(tmp_path):
    cfg = {
        "serverchan_sendkey": "", "login_password": "pw",
        "summary_time": "09:00", "rollover_time": "00:05", "port": 5005,
    }
    application = app_mod.create_app(cfg, db_path=str(tmp_path / "app.db"))
    application.testing = True
    return application.test_client()


def _login(client):
    return client.post("/login", json={"password": "pw"})


def test_requires_auth(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/api/todos").status_code == 401


def test_login_wrong_password(tmp_path):
    c = make_client(tmp_path)
    assert c.post("/login", json={"password": "nope"}).status_code == 401


def test_login_then_crud(tmp_path):
    c = make_client(tmp_path)
    assert _login(c).status_code == 200
    # 新增
    r = c.post("/api/todos", json={"title": "写周报", "date": "2026-06-23"})
    assert r.status_code == 200
    tid = r.get_json()["id"]
    # 列表
    r = c.get("/api/todos?date=2026-06-23")
    assert r.status_code == 200
    items = r.get_json()["todos"]
    assert len(items) == 1 and items[0]["title"] == "写周报"
    # 勾销
    assert c.post(f"/api/todos/{tid}/done", json={"done": True}).status_code == 200
    assert c.get("/api/todos?date=2026-06-23").get_json()["todos"][0]["done"] == 1
    # 改内容/时间
    assert c.patch(f"/api/todos/{tid}", json={"title": "改了", "remind_at": "10:00"}).status_code == 200
    # 删除
    assert c.delete(f"/api/todos/{tid}").status_code == 200
    assert c.get("/api/todos?date=2026-06-23").get_json()["todos"] == []


def test_due_endpoint(tmp_path):
    c = make_client(tmp_path)
    _login(c)
    c.post("/api/todos", json={"title": "开会", "date": "2026-06-23", "remind_at": "15:00"})
    # since 远早于到点、now 远晚于到点 → 应返回
    r = c.get("/api/due?date=2026-06-23&since=2026-06-23T00:00:00&now=2026-06-23T23:59:00")
    assert r.status_code == 200
    due = r.get_json()["due"]
    assert len(due) == 1 and due[0]["title"] == "开会"
    # since 在到点之后 → 不返回（避免重复弹）
    r = c.get("/api/due?date=2026-06-23&since=2026-06-23T16:00:00&now=2026-06-23T23:59:00")
    assert r.get_json()["due"] == []


def test_pick_port_returns_preferred_when_free():
    # 端口 0 表示让系统选，返回值应是有效端口
    p = app_mod.pick_port(0)
    assert isinstance(p, int) and p > 0


def test_pick_port_pins_configured_port():
    # 配了固定端口就始终返回它（钉死，不漂移），保证书签 URL 稳定
    assert app_mod.pick_port(5005) == 5005
    assert app_mod.pick_port(8123) == 8123


def test_add_todo_bad_remind_at_returns_400(tmp_path):
    """POST /api/todos 传入格式错误的 remind_at 应返回 400，不创建待办。"""
    c = make_client(tmp_path)
    _login(c)
    r = c.post("/api/todos", json={"title": "测试", "date": "2026-06-23", "remind_at": "badtime"})
    assert r.status_code == 400
    assert "remind_at" in r.get_json().get("error", "")
    # 确认没有插入
    items = c.get("/api/todos?date=2026-06-23").get_json()["todos"]
    assert items == []


def test_add_todo_valid_remind_at_works(tmp_path):
    """POST /api/todos 传入合法的短格式 remind_at 应成功。"""
    c = make_client(tmp_path)
    _login(c)
    r = c.post("/api/todos", json={"title": "开会", "date": "2026-06-23", "remind_at": "9:30"})
    assert r.status_code == 200


def test_patch_todo_bad_remind_at_returns_400(tmp_path):
    """PATCH /api/todos/<id> 传入格式错误的 remind_at 应返回 400。"""
    c = make_client(tmp_path)
    _login(c)
    r = c.post("/api/todos", json={"title": "开会", "date": "2026-06-23"})
    tid = r.get_json()["id"]
    r = c.patch(f"/api/todos/{tid}", json={"remind_at": "badtime"})
    assert r.status_code == 400
    assert "remind_at" in r.get_json().get("error", "")


def test_add_recurring_and_per_date_completion(tmp_path):
    c = make_client(tmp_path)
    _login(c)
    tid = c.post("/api/todos", json={"title": "每日喝水", "date": "2026-06-24",
                                     "remind_at": "09:00", "repeat": "daily"}).get_json()["id"]
    items = c.get("/api/todos?date=2026-06-25").get_json()["todos"]
    rec = [t for t in items if t["id"] == tid][0]
    assert rec["repeat"] == "daily" and rec["done"] == 0
    # 在 6/25 勾完成（带 date）
    assert c.post(f"/api/todos/{tid}/done", json={"done": True, "date": "2026-06-25"}).status_code == 200
    d25 = [t for t in c.get("/api/todos?date=2026-06-25").get_json()["todos"] if t["id"] == tid][0]
    d26 = [t for t in c.get("/api/todos?date=2026-06-26").get_json()["todos"] if t["id"] == tid][0]
    assert d25["done"] == 1 and d26["done"] == 0   # 当天完成，次日自动回到未完成


def test_add_invalid_repeat_returns_400(tmp_path):
    c = make_client(tmp_path)
    _login(c)
    assert c.post("/api/todos", json={"title": "x", "repeat": "hourly"}).status_code == 400


def test_patch_date_and_repeat(tmp_path):
    c = make_client(tmp_path)
    _login(c)
    tid = c.post("/api/todos", json={"title": "t", "date": "2026-06-24", "remind_at": "09:00"}).get_json()["id"]
    assert c.patch(f"/api/todos/{tid}", json={"date": "2026-06-30", "remind_at": "11:00",
                                              "repeat": "weekly"}).status_code == 200
    t = [x for x in c.get("/api/todos?date=2026-06-30").get_json()["todos"] if x["id"] == tid][0]
    assert t["repeat"] == "weekly" and t["remind_at"] == "11:00"


def test_all_endpoint_sorted(tmp_path):
    c = make_client(tmp_path)
    _login(c)
    c.post("/api/todos", json={"title": "晚", "date": "2026-06-30"})
    c.post("/api/todos", json={"title": "早", "date": "2026-06-24"})
    assert [t["title"] for t in c.get("/api/all").get_json()["todos"]] == ["早", "晚"]


def test_overview_requires_auth(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/overview").status_code in (302, 308)
