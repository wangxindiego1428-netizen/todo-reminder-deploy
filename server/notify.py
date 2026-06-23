import logging

import requests

log = logging.getLogger("todo.notify")

_API = "https://sctapi.ftqq.com/{key}.send"


def push_serverchan(sendkey, title, body, session=None):
    """推送一条到 Server酱。成功返回 True；失败重试 1 次后返回 False。
    sendkey 为空时直接跳过（返回 False，不发请求）。
    """
    if not sendkey:
        log.warning("Server酱 sendkey 未配置，跳过微信推送")
        return False
    sess = session if session is not None else requests
    url = _API.format(key=sendkey)
    data = {"title": title, "desp": body}
    for attempt in range(2):  # 首次 + 1 次重试
        try:
            resp = sess.post(url, data=data, timeout=10)
            if resp.status_code == 200:
                return True
            log.warning("Server酱 返回非 200：%s（第 %s 次）", resp.status_code, attempt + 1)
        except Exception as e:  # noqa: BLE001 网络异常不应使服务崩溃
            log.warning("Server酱 推送异常：%s（第 %s 次）", e, attempt + 1)
    return False
