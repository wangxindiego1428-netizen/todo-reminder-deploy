import hashlib
import hmac

_SALT = "todo-reminder-v1"


def check_password(cfg, password):
    return hmac.compare_digest(str(password or ""), str(cfg.get("login_password", "")))


def expected_token(cfg):
    raw = (_SALT + str(cfg.get("login_password", ""))).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_token(cfg, token):
    if not token:
        return False
    return hmac.compare_digest(str(token), expected_token(cfg))
