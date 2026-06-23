"""Oturum çerezi sertleştirme — HttpOnly / SameSite / Secure (config-gated)."""


def test_session_cookie_config(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_login_response_sets_hardened_cookie(client, db):
    """Local admin login çerezi HttpOnly + SameSite=Lax ile dönmeli."""
    resp = client.post("/login", json={"username": "test_admin", "password": "test_admin_pwd_only"})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie
