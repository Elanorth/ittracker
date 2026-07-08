"""
test_portal.py — v5.15 İntranet portal (self-service destek talebi, LOGIN YOK).

POST /portal/api/cases  → case oluştur (Case No üret, source=portal)
POST /portal/api/lookup → Case No + e-posta İKİSİ birlikte doğrulanır
GET  /portal            → public sayfa
"""

import pytest

import app as app_module
from models.database import Task


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    """Portal IP rate-limiter modül-global; testler arası state taşımasın."""
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


def _valid_case(firm="inventist", **over):
    d = {
        "firm": firm,
        "name": "Ahmet Yılmaz",
        "email": "ahmet@inventist.com.tr",
        "subject": "Toplantı odasında internet yok",
        "category": "infra",
        "description": "3. kat toplantı odasındaki ethernet portu bu sabahtan beri çalışmıyor, kablo takılıyken bağlantı kurulamıyor.",
    }
    d.update(over)
    return d


class TestPortalCreate:
    def test_public_erisim_login_yok(self, client):
        assert client.get("/portal").status_code == 200

    def test_gecerli_case_201(self, db, client):
        r = client.post("/portal/api/cases", json=_valid_case())
        assert r.status_code == 201
        code = r.get_json()["case_code"]
        assert code.startswith("INV-")
        t = Task.query.filter_by(case_code=code).first()
        assert t is not None
        assert t.source == "portal"
        assert t.category == "support"
        assert t.reporter_email == "ahmet@inventist.com.tr"
        assert t.reporter_name == "Ahmet Yılmaz"

    def test_assos_prefix(self, db, client):
        r = client.post("/portal/api/cases", json=_valid_case(firm="assos"))
        assert r.status_code == 201
        assert r.get_json()["case_code"].startswith("ASS-")

    def test_kisa_aciklama_400(self, db, client):
        r = client.post("/portal/api/cases", json=_valid_case(description="çok kısa"))
        assert r.status_code == 400
        assert "60" in r.get_json()["error"]

    def test_gecersiz_email_400(self, db, client):
        assert client.post("/portal/api/cases", json=_valid_case(email="bozuk")).status_code == 400

    def test_eksik_ad_konu_400(self, db, client):
        assert client.post("/portal/api/cases", json=_valid_case(name="")).status_code == 400
        assert client.post("/portal/api/cases", json=_valid_case(subject="")).status_code == 400

    def test_gecersiz_firma_400(self, db, client):
        assert client.post("/portal/api/cases", json=_valid_case(firm="baska")).status_code == 400

    def test_case_kodu_unique(self, db, client):
        codes = set()
        for _ in range(5):
            r = client.post("/portal/api/cases", json=_valid_case())
            codes.add(r.get_json()["case_code"])
        assert len(codes) == 5  # her biri farklı


class TestPortalLookup:
    def _make(self, client):
        return client.post("/portal/api/cases", json=_valid_case()).get_json()["case_code"]

    def test_dogru_kod_ve_mail_200(self, db, client):
        code = self._make(client)
        r = client.post("/portal/api/lookup", json={"case_code": code, "email": "ahmet@inventist.com.tr"})
        assert r.status_code == 200
        d = r.get_json()
        assert d["case_code"] == code
        assert d["status"] in ("received", "in_progress", "resolved")
        # İç alanlar sızmamalı
        assert "user_id" not in d
        assert "manager_note" not in d
        assert "reporter_email" not in d

    def test_yanlis_mail_404(self, db, client):
        code = self._make(client)
        r = client.post("/portal/api/lookup", json={"case_code": code, "email": "baska@x.com"})
        assert r.status_code == 404

    def test_yanlis_kod_404(self, db, client):
        assert (
            client.post(
                "/portal/api/lookup", json={"case_code": "INV-XXXXXX", "email": "ahmet@inventist.com.tr"}
            ).status_code
            == 404
        )

    def test_kod_buyuk_harfe_normalize(self, db, client):
        code = self._make(client)
        r = client.post("/portal/api/lookup", json={"case_code": code.lower(), "email": "ahmet@inventist.com.tr"})
        assert r.status_code == 200
