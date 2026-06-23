import auth


def test_check_password():
    cfg = {"login_password": "secret"}
    assert auth.check_password(cfg, "secret") is True
    assert auth.check_password(cfg, "wrong") is False


def test_token_roundtrip():
    cfg = {"login_password": "secret"}
    tok = auth.expected_token(cfg)
    assert isinstance(tok, str) and len(tok) >= 32
    assert auth.verify_token(cfg, tok) is True
    assert auth.verify_token(cfg, "garbage") is False


def test_token_changes_with_password():
    assert auth.expected_token({"login_password": "a"}) != auth.expected_token(
        {"login_password": "b"}
    )


def test_verify_token_handles_none():
    assert auth.verify_token({"login_password": "x"}, None) is False
