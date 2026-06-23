import notify


class FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeSession:
    def __init__(self, status_codes):
        self.status_codes = list(status_codes)
        self.calls = []

    def post(self, url, data=None, timeout=None):
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        code = self.status_codes.pop(0)
        if code == "raise":
            raise RuntimeError("network down")
        return FakeResp(code)


def test_push_success_first_try():
    s = FakeSession([200])
    ok = notify.push_serverchan("KEY", "标题", "正文", session=s)
    assert ok is True
    assert len(s.calls) == 1
    assert "KEY" in s.calls[0]["url"]
    assert s.calls[0]["data"]["title"] == "标题"
    assert s.calls[0]["data"]["desp"] == "正文"


def test_push_retries_once_then_succeeds():
    s = FakeSession(["raise", 200])
    ok = notify.push_serverchan("KEY", "t", "b", session=s)
    assert ok is True
    assert len(s.calls) == 2          # 失败 1 次后重试成功


def test_push_returns_false_after_retry_fails():
    s = FakeSession(["raise", "raise"])
    ok = notify.push_serverchan("KEY", "t", "b", session=s)
    assert ok is False
    assert len(s.calls) == 2          # 只重试 1 次


def test_push_skips_when_no_key():
    s = FakeSession([200])
    ok = notify.push_serverchan("", "t", "b", session=s)
    assert ok is False
    assert len(s.calls) == 0          # 没密钥直接跳过，不发请求


def test_non_200_is_failure():
    s = FakeSession([500, 500])
    ok = notify.push_serverchan("KEY", "t", "b", session=s)
    assert ok is False
    assert len(s.calls) == 2
