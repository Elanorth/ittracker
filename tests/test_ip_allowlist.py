"""
test_ip_allowlist.py — v5.29 — İç uygulama IP allowlist (kurumsal erişim).

- APP_IP_ALLOWLIST boş → kısıtlama yok (her yer açık).
- Set edildiğinde: iç yollar (/, /login, /api/*) yalnızca izinli CF-Connecting-IP'den;
  portal + statik DAİMA açık; CF header yoksa (healthcheck/internal) açık; CIDR desteklenir.
"""

import pytest


@pytest.fixture(autouse=True)
def _clear_allowlist(monkeypatch):
    monkeypatch.delenv("APP_IP_ALLOWLIST", raising=False)
    yield


def _get(client, path, ip=None):
    headers = {"CF-Connecting-IP": ip} if ip else {}
    return client.get(path, headers=headers)


class TestDisabled:
    def test_bos_allowlist_kisitlama_yok(self, db, client, monkeypatch):
        monkeypatch.delenv("APP_IP_ALLOWLIST", raising=False)
        # Yabancı IP bile iç uygulamaya erişebilir (kısıtlama kapalı; login sayfası 200)
        assert _get(client, "/login", ip="9.9.9.9").status_code == 200


class TestEnabled:
    def test_izinli_ip_gecer(self, db, client, monkeypatch):
        monkeypatch.setenv("APP_IP_ALLOWLIST", "1.2.3.4, 5.6.7.8")
        assert _get(client, "/login", ip="1.2.3.4").status_code == 200

    def test_izinsiz_ip_403(self, db, client, monkeypatch):
        monkeypatch.setenv("APP_IP_ALLOWLIST", "1.2.3.4")
        r = _get(client, "/login", ip="9.9.9.9")
        assert r.status_code == 403
        assert "kurumsal" in r.get_data(as_text=True).lower()

    def test_api_izinsiz_json_403(self, db, client, monkeypatch):
        monkeypatch.setenv("APP_IP_ALLOWLIST", "1.2.3.4")
        r = client.get("/api/me", headers={"CF-Connecting-IP": "9.9.9.9"})
        assert r.status_code == 403
        assert r.is_json and "kurumsal" in r.get_json()["error"].lower()

    def test_cidr_destegi(self, db, client, monkeypatch):
        monkeypatch.setenv("APP_IP_ALLOWLIST", "10.20.0.0/16")
        assert _get(client, "/login", ip="10.20.30.40").status_code == 200
        assert _get(client, "/login", ip="10.21.0.1").status_code == 403

    def test_portal_daima_acik(self, db, client, monkeypatch):
        monkeypatch.setenv("APP_IP_ALLOWLIST", "1.2.3.4")
        # İzinsiz IP olsa da portal + portal API açık
        assert _get(client, "/portal", ip="9.9.9.9").status_code == 200
        r = client.post(
            "/portal/api/cases",
            headers={"CF-Connecting-IP": "9.9.9.9"},
            json={
                "firm": "inventist",
                "name": "Dış Kullanıcı",
                "email": "dis@inventist.com.tr",
                "subject": "Portal açık mı",
                "category": "support",
                "description": "IP allowlist iç uygulamayı kısıtlar ama portal dış erişime açık kalmalı — bu test onu doğrular.",
            },
        )
        assert r.status_code == 201

    def test_statik_daima_acik(self, db, client, monkeypatch):
        monkeypatch.setenv("APP_IP_ALLOWLIST", "1.2.3.4")
        assert client.get("/static/app.js", headers={"CF-Connecting-IP": "9.9.9.9"}).status_code == 200

    def test_cf_header_yoksa_acik(self, db, client, monkeypatch):
        """Healthcheck/internal (CF-Connecting-IP yok) engellenmez — tek ingress tünel."""
        monkeypatch.setenv("APP_IP_ALLOWLIST", "1.2.3.4")
        assert client.get("/login").status_code == 200  # header yok → geçer
