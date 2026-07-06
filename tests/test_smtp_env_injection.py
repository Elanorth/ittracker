"""
test_smtp_env_injection.py — /api/settings/smtp sertleştirmesi (v5.12+).

En kritik açık: değerler .env'e ham yazıldığı için newline içeren bir değer YENİ
env satırı enjekte edebiliyordu (örn. smtp_pass="x\\nADMIN_PASSWORD=attacker").
super_admin gate vardı ama oturum ele geçirme / kötü niyetli super_admin ile
SECRET_KEY/ADMIN_PASSWORD yazılabilirdi.

Testler:
1. Newline/CR içeren değer → 400, .env DEĞİŞMEZ.
2. Geçersiz port → 400.
3. Geçerli güncelleme → 200, .env yazılır, audit log oluşur, dosya izni 0600.
"""

import os
import stat

import pytest

from models.database import AuditLog


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """Geçici .env yolu — gerçek repo .env'ine dokunmadan test."""
    p = tmp_path / ".env"
    p.write_text("SMTP_HOST=old.example.com\nSMTP_PASS=eski\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE_PATH", str(p))
    return p


@pytest.fixture
def super_admin(user_factory, login_as):
    u = user_factory(username="smtp_sa", permission_level="super_admin", is_admin=True)
    login_as(u)
    return u


def test_newline_injection_reddedilir(client, db, super_admin, env_file):
    """smtp_pass içinde \\n → 400 ve .env dosyası HİÇ değişmez (enjeksiyon yok)."""
    before = env_file.read_text(encoding="utf-8")
    resp = client.post(
        "/api/settings/smtp",
        json={"smtp_pass": "gizli\nADMIN_PASSWORD=saldirgan"},
    )
    assert resp.status_code == 400
    assert "kontrol karakteri" in resp.get_json()["error"].lower()
    # Dosya değişmemeli — enjekte edilen satır yazılmamalı
    after = env_file.read_text(encoding="utf-8")
    assert after == before
    assert "ADMIN_PASSWORD" not in after


def test_carriage_return_reddedilir(client, db, super_admin, env_file):
    """smtp_host içinde \\r → 400."""
    resp = client.post("/api/settings/smtp", json={"smtp_host": "a\rb"})
    assert resp.status_code == 400


def test_gecersiz_port_400(client, db, super_admin, env_file):
    """Sayı olmayan / aralık dışı port → 400."""
    assert client.post("/api/settings/smtp", json={"smtp_port": "abc"}).status_code == 400
    assert client.post("/api/settings/smtp", json={"smtp_port": "70000"}).status_code == 400
    assert client.post("/api/settings/smtp", json={"smtp_port": "0"}).status_code == 400


def test_gecerli_guncelleme_yazilir_ve_audit(client, db, super_admin, env_file):
    """Geçerli değerler .env'e yazılır, audit log oluşur, şifre değeri loglanmaz."""
    resp = client.post(
        "/api/settings/smtp",
        json={
            "smtp_host": "smtp.office365.com",
            "smtp_port": "587",
            "smtp_user": "mail@firma.com",
            "smtp_pass": "yenisifre",
        },
    )
    assert resp.status_code == 200
    content = env_file.read_text(encoding="utf-8")
    assert "SMTP_HOST=smtp.office365.com" in content
    assert "SMTP_PORT=587" in content
    assert "SMTP_PASS=yenisifre" in content

    # Audit: settings.smtp kaydı var, details şifre DEĞERİNİ içermez
    entry = AuditLog.query.filter_by(action="settings.smtp").order_by(AuditLog.id.desc()).first()
    assert entry is not None
    assert "SMTP_PASS" in entry.details  # anahtar loglanır
    assert "yenisifre" not in entry.details  # değer loglanmaz
    assert "yenisifre" not in (entry.summary or "")


def test_env_dosya_izni_0600(client, db, super_admin, env_file):
    """Yazımdan sonra .env yalnızca sahibi okuyup yazabilsin (0600)."""
    resp = client.post("/api/settings/smtp", json={"smtp_user": "x@y.com"})
    assert resp.status_code == 200
    mode = stat.S_IMODE(os.stat(env_file).st_mode)
    # group/other bitleri kapalı olmalı
    assert mode & 0o077 == 0, f"Beklenen 0600, bulunan {oct(mode)}"


def test_maskeli_sifre_yazilmaz(client, db, super_admin, env_file):
    """GET'in döndürdüğü mask (••••••) POST'ta gelirse şifre değiştirilmez."""
    resp = client.post("/api/settings/smtp", json={"smtp_pass": "••••••"})
    assert resp.status_code == 200
    content = env_file.read_text(encoding="utf-8")
    # Eski değer korunmalı, mask yazılmamalı
    assert "SMTP_PASS=eski" in content
    assert "••••••" not in content
