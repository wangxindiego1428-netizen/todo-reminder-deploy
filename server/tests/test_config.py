import json
import config


def test_load_config_merges_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"login_password": "secret", "serverchan_sendkey": "KEY"}))
    cfg = config.load_config(str(p))
    assert cfg["login_password"] == "secret"
    assert cfg["serverchan_sendkey"] == "KEY"
    # 缺省项要被默认值补齐
    assert cfg["summary_time"] == "09:00"
    assert cfg["rollover_time"] == "00:05"
    assert cfg["port"] == 5005


def test_load_config_missing_file_returns_defaults(tmp_path):
    cfg = config.load_config(str(tmp_path / "nope.json"))
    assert cfg["summary_time"] == "09:00"
    assert cfg["login_password"] == "change-me"
    assert cfg["serverchan_sendkey"] == ""


def test_tz_constant():
    assert config.TZ == "Asia/Shanghai"
