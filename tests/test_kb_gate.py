"""
test_kb_gate.py — v5.28 — KB e-posta kapısı + firma kilidi + ayrı rate-limit.

- Doğrulama olmadan KB list/detail/feedback → 401 (verify_required).
- verify: şirket domain'i → ok + firma; yabancı domain → 403; bozuk e-posta → 400.
- FİRMA KİLİDİ: inventist e-postası ile doğrulanan oturum assos makalesini GÖREMEZ
  (listede yok + detay 404) — istekteki firm parametresi yok sayılır.
- KB istekleri artık _PORTAL_HITS (case-açma bütçesi) yerine _KB_HITS kovasını kullanır.
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
    def test_dogrulamasiz_401(self, db, client):
        a = _art("M", "inventist")
        assert client.get("/portal/api/kb").status_code == 401
        assert client.get(f"/portal/api/kb/{a.id}").status_code == 401
        assert client.post(f"/portal/api/kb/{a.id}/feedback", json={"helpful": True}).status_code == 401
        assert client.get("/portal/api/kb").get_json().get("verify_required") is True

    def test_verify_sirket_domaini(self, db, client):
        r = client.post("/portal/api/kb/verify", json={"email": "ali@inventist.com.tr"})
        assert r.status_code == 200 and r.get_json()["firm"] == "inventist"
        r2 = client.post("/portal/api/kb/verify", json={"email": "ayse@assospharma.com"})
        assert r2.status_code == 200 and r2.get_json()["firm"] == "assos"

    def test_verify_yabanci_domain_403(self, db, client):
        assert client.post("/portal/api/kb/verify", json={"email": "x@gmail.com"}).status_code == 403

    def test_verify_bozuk_eposta_400(self, db, client):
        assert client.post("/portal/api/kb/verify", json={"email": "bozuk"}).status_code == 400

    def test_dogrulama_sonrasi_erisim(self, db, client):
        a = _art("İnv makale", "inventist")
        client.post("/portal/api/kb/verify", json={"email": "ali@inventist.com.tr"})
        arts = client.get("/portal/api/kb").get_json()
        assert any(x["id"] == a.id for x in arts)
        assert client.get(f"/portal/api/kb/{a.id}").status_code == 200


class TestFirmLock:
    def test_baska_firmanin_makalesi_gorunmez(self, db, client):
        inv = _art("İnv makale", "inventist")
        ass = _art("Assos makale", "assos")
        glob = _art("Global makale", "")
        client.post("/portal/api/kb/verify", json={"email": "ali@inventist.com.tr"})
        ids = {x["id"] for x in client.get("/portal/api/kb").get_json()}
        assert inv.id in ids and glob.id in ids and ass.id not in ids
        # istekteki firm parametresi YOK SAYILIR (oturum kilidi kazanır)
        ids2 = {x["id"] for x in client.get("/portal/api/kb?firm=assos").get_json()}
        assert ass.id not in ids2
        # detay da 404
        assert client.get(f"/portal/api/kb/{ass.id}").status_code == 404
        assert client.post(f"/portal/api/kb/{ass.id}/feedback", json={"helpful": True}).status_code == 404


class TestSeparateLimiter:
    def test_kb_istekleri_portal_butcesini_yemez(self, db, client):
        """15 KB isteği sonrası case açma hâlâ çalışmalı (eskiden 10'da 429 olurdu)."""
        _art("M", "inventist")
        client.post("/portal/api/kb/verify", json={"email": "ali@inventist.com.tr"})  # 1 portal hit
        for _ in range(15):
            assert client.get("/portal/api/kb").status_code == 200  # KB kovası (60'a kadar)
        r = client.post(
            "/portal/api/cases",
            json={
                "firm": "inventist",
                "name": "Ali Veli",
                "email": "ali@x.com",
                "subject": "Limit testi",
                "category": "support",
                "description": "Ayrı kova testi için en az altmış karakter olması gereken uzun açıklama metni.",
            },
        )
        assert r.status_code == 201  # portal bütçesi KB tarafından tüketilmedi
