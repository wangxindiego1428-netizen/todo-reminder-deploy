import json
import os

TZ = "Asia/Shanghai"

DEFAULTS = {
    "serverchan_sendkey": "",
    "login_password": "change-me",
    "summary_time": "09:00",
    "rollover_time": "00:05",
    "port": 5005,
}


def load_config(path):
    """读取 config.json；文件不存在或缺项时用 DEFAULTS 补齐。"""
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if v is not None})
    return cfg
