"""
test_kb_gate.py — Portal KB erişim kapısı (v5.103'ten itibaren O365 oturumu).

- Oturum yoksa KB list/detail/feedback → 401 (login_required).
- Giriş yapılmış kullanıcı → oturum domain'ine göre firma kilidi; başka
  firmanın makalesi listede yok + detay 404 (/istekteki firm parametresi
  yok sayılır).
- KB istekleri _KB_HITS kovasını kullanır → _PORTAL_HITS (case açma bütçesi)
  tüketilmez.

v5.103 — Eski /portal/api/kb/verify endpoint'i kaldırıldı; portal_login
fixture'ı doğrudan session anahtarlarını kurar (SSO callback eşdeğeri).
"""

import pytest

import app as app_module
from models.database import KbArticle, db


@pytest.fixture(autouse=True)
def _reset_limiters():
    app_module._PORTAL_HITS.clear()
    app_module._KB_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()
    app_module._KB_HITS.clear()


def _art(title, firm, published=True):
    a = KbArticle(title=title, firm=firm, category="genel", published=published, body="içerik")
    db.session.add(a)
    db.session.commit()
    return a


class TestGate:
    def test_oturumsuz_401(self, db, client):
        a = _art("M", "inventist")
        assert client.get("/portal/api/kb").status_code == 401
        assert client.get(f"/portal/api/kb/{a.id}").status_code == 401
        assert client.post(f"/portal/api/kb/{a.id}/feedback", json={"helpful": True}).status_code == 401
        assert client.get("/portal/api/kb").get_json().get("login_required") is True

    def test_verify_endpoint_kaldirildi(self, db, client):
        """Eski /portal/api/kb/verify kaldırıldı — 404 ya da 405."""
        r = client.post("/portal/api/kb/verify", json={"email": "ali@inventist.com.tr"})
        assert r.status_code in (404, 405)

    def test_sirket_oturumu_sonrasi_erisim(self, db, client, portal_login):
        a = _art("İnv makale", "inventist")
        portal_login(email="ali@inventist.com.tr")
        arts = client.get("/portal/api/kb").get_json()
        assert any(x["id"] == a.id for x in arts)
        assert client.get(f"/portal/api/kb/{a.id}").status_code == 200


class TestFirmLock:
    def test_baska_firmanin_makalesi_gorunmez(self, db, client, portal_login):
        inv = _art("İnv makale", "inventist")
        ass = _art("Assos makale", "assos")
        glob = _art("Global makale", "")
        portal_login(email="ali@inventist.com.tr")
        ids = {x["id"] for x in client.get("/portal/api/kb").get_json()}
        assert inv.id in ids and glob.id in ids and ass.id not in ids
        # istekteki firm parametresi YOK SAYILIR (oturum kilidi kazanır)
        ids2 = {x["id"] for x in client.get("/portal/api/kb?firm=assos").get_json()}
        assert ass.id not in ids2
        # detay da 404
        assert client.get(f"/portal/api/kb/{ass.id}").status_code == 404
        assert client.post(f"/portal/api/kb/{ass.id}/feedback", json={"helpful": True}).status_code == 404


class TestSeparateLimiter:
    def test_kb_istekleri_portal_butcesini_yemez(self, db, client, portal_login):
        """15 KB isteği sonrası case açma hâlâ çalışmalı (eskiden 10'da 429 olurdu)."""
        _art("M", "inventist")
        portal_login(email="ali@inventist.com.tr")  # 0 portal hit (fixture doğrudan session kurar)
        for _ in range(15):
            assert client.get("/portal/api/kb").status_code == 200  # KB kovası (60'a kadar)
        r = client.post(
            "/portal/api/cases",
            json={
                "subject": "Limit testi",
                "category": "support",
                "description": "Ayrı kova testi için en az altmış karakter olması gereken uzun açıklama metni.",
            },
        )
        assert r.status_code == 201  # portal bütçesi KB tarafından tüketilmedi
