"""
test_webhook.py — v5.32 — Teams webhook bildirimleri.

- MAIL_SUPPRESS=1 (test varsayılanı) → notify_teams gerçek POST yapmaz (suppressed).
- URL yoksa atlanır; SystemSetting > env öncelik.
- Settings endpoint'leri (super_admin): kaydet/maskeli GET/test.
- Portal case açılışı notify_teams'i tetikler ama suppress edilir (gerçek çağrı yok).
"""

import pytest

import app as app_module
from models.database import set_setting
from services import webhook


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


class TestNotifyGuard:
    def test_suppress_gercek_post_yok(self, monkeypatch):
        # conftest MAIL_SUPPRESS=1 zorluyor → suppressed döner, ağa çıkmaz
        r = webhook.notify_teams("Test", "metin", facts=[("a", "b")])
        assert r == {"ok": True, "suppressed": True}

    def test_suppress_kapali_url_yok_hata(self, monkeypatch, db):
        monkeypatch.setenv("MAIL_SUPPRESS", "0")
        monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)
        r = webhook.notify_teams("Test")
        assert r["ok"] is False and "ayarlı değil" in r["error"]

    def test_url_oncelik_db_sonra_env(self, monkeypatch, db):
        monkeypatch.setenv("MAIL_SUPPRESS", "0")
        monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://env.example/hook")
        assert webhook._teams_url() == "https://env.example/hook"
        set_setting("teams_webhook_url", "https://db.example/hook")
        db.session.commit()
        assert webhook._teams_url() == "https://db.example/hook"  # DB kazanır


class TestTeamsSettings:
    def test_kaydet_ve_maskeli_get(self, db, client, user_factory, login_as):
        sa = user_factory(username="tw_sa", permission_level="super_admin", is_admin=True)
        login_as(sa)
        r = client.post("/api/settings/teams", json={"url": "https://outlook.office.com/webhook/abc123"})
        assert r.status_code == 200 and r.get_json()["configured"] is True
        g = client.get("/api/settings/teams").get_json()
        assert g["configured"] is True and g["masked"].endswith("…")

    def test_https_zorunlu(self, db, client, user_factory, login_as):
        sa = user_factory(username="tw_sa2", permission_level="super_admin", is_admin=True)
        login_as(sa)
        assert client.post("/api/settings/teams", json={"url": "http://insecure/hook"}).status_code == 400

    def test_bos_url_kapatir(self, db, client, user_factory, login_as):
        sa = user_factory(username="tw_sa3", permission_level="super_admin", is_admin=True)
        login_as(sa)
        client.post("/api/settings/teams", json={"url": "https://x.example/h"})
        client.post("/api/settings/teams", json={"url": ""})
        assert client.get("/api/settings/teams").get_json()["configured"] is False

    def test_director_403(self, db, client, user_factory, login_as):
        d = user_factory(username="tw_dir", firm="inventist", permission_level="it_director")
        login_as(d)
        assert client.get("/api/settings/teams").status_code == 403

    def test_test_endpoint_suppress_uyari(self, db, client, user_factory, login_as):
        sa = user_factory(username="tw_sa4", permission_level="super_admin", is_admin=True)
        login_as(sa)
        # MAIL_SUPPRESS=1 (conftest) → test kartı suppress → 400 + açıklama
        r = client.post("/api/settings/teams/test")
        assert r.status_code == 400 and "bastır" in r.get_json()["error"].lower()


class TestPortalTrigger:
    def test_case_acilinca_teams_cagirilir_ama_suppress(self, db, client, monkeypatch):
        called = {}

        def _fake(title, text="", facts=None, color="0076D7"):
            called["title"] = title
            return {"ok": True, "suppressed": True}

        monkeypatch.setattr("services.webhook.notify_teams", _fake)
        r = client.post(
            "/portal/api/cases",
            json={
                "firm": "inventist",
                "name": "Ali Veli",
                "email": "ali@inventist.com.tr",
                "subject": "Teams tetik testi",
                "category": "support",
                "description": "Teams webhook tetiklenmesi için en az altmış karakter olması gereken açıklama metni.",
            },
        )
        assert r.status_code == 201
        assert "title" in called and called["title"].startswith("🆕")
