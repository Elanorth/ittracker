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


def test_csp_header_present(client, db):
    """v5.23 — CSP header'ı temel direktiflerle her yanıtta bulunmalı."""
    csp = client.get("/portal").headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp
    # inline onclick/style için 'unsafe-inline' zorunlu (Faz 2'ye kadar)
    assert "script-src 'self' 'unsafe-inline'" in csp
    # dış kaynak whitelist
    assert "https://fonts.gstatic.com" in csp
    assert "https://assospharma.com" in csp


def test_other_security_headers(client, db):
    h = client.get("/portal").headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "same-origin"
