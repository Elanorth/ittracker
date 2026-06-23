"""Oturum çerezi sertleştirme — HttpOnly / SameSite / Secure (config-gated)."""

import os


def test_session_cookie_config(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_login_response_sets_hardened_cookie(client, db):
    """Local admin login çerezi HttpOnly + SameSite=Lax ile dönmeli.

    Kullanıcı adı/şifre, init_db'nin admin'i oluştururken kullandığı env'den
    okunur (CI ADMIN_PASSWORD'ü override ediyor; hardcode şifre CI'da kırılırdı).
    """
    uname = os.environ.get("ADMIN_USERNAME", "test_admin")
    pw = os.environ.get("ADMIN_PASSWORD", "test_admin_pwd_only")
    resp = client.post("/login", json={"username": uname, "password": pw})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie
