"""
test_portal.py — Portal (self-service destek talebi).

v5.103 — /portal/api/cases artık O365 oturumu şart koşar. Testler
`portal_login` fixture'ı ile oturumu doğrudan kurar (SSO flow'u dolaşmadan).

POST /portal/api/cases  → O365 oturumu zorunlu; firm/reporter oturumdan
POST /portal/api/lookup → Case No + e-posta birlikte (anonim; oturum gerekmez)
GET  /portal            → public SPA
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


def _valid_body(**over):
    """v5.103 — firm/name/email oturumdan gelir; body yalnız konu+içerik."""
    d = {
        "subject": "Toplantı odasında internet yok",
        "category": "infra",
        "description": "3. kat toplantı odasındaki ethernet portu bu sabahtan beri çalışmıyor, kablo takılıyken bağlantı kurulamıyor.",
    }
    d.update(over)
    return d


class TestPortalCreate:
    def test_public_erisim_login_yok(self, client):
        assert client.get("/portal").status_code == 200

    def test_oturumsuz_401(self, db, client):
        """Oturum yoksa case açılamaz."""
        r = client.post("/portal/api/cases", json=_valid_body())
        assert r.status_code == 401
        assert r.get_json().get("login_required") is True

    def test_gecerli_case_201(self, db, client, portal_login):
        portal_login(email="ahmet@inventist.com.tr", name="Ahmet Yılmaz")
        r = client.post("/portal/api/cases", json=_valid_body())
        assert r.status_code == 201
        code = r.get_json()["case_code"]
        assert code.startswith("INV-")
        t = Task.query.filter_by(case_code=code).first()
        assert t is not None
        assert t.source == "portal"
        assert t.category == "support"
        assert t.reporter_email == "ahmet@inventist.com.tr"
        assert t.reporter_name == "Ahmet Yılmaz"
        assert t.firm == "inventist"

    def test_assos_prefix(self, db, client, portal_login):
        portal_login(email="ayse@assospharma.com", name="Ayşe")
        r = client.post("/portal/api/cases", json=_valid_body())
        assert r.status_code == 201
        assert r.get_json()["case_code"].startswith("ASS-")

    def test_body_firm_yoksayilir(self, db, client, portal_login):
        """body'de firm gönderilse bile oturumun firm'i kazanır."""
        portal_login(email="ahmet@inventist.com.tr")
        r = client.post("/portal/api/cases", json=_valid_body(firm="assos"))
        assert r.status_code == 201
        assert r.get_json()["case_code"].startswith("INV-")

    def test_anydesk_kaydedilir_ve_lookup_doner(self, db, client, portal_login):
        """v5.17 — opsiyonel AnyDesk ID kaydedilir ve case sorgusunda döner."""
        portal_login(email="ahmet@inventist.com.tr")
        code = client.post("/portal/api/cases", json=_valid_body(anydesk="123 456 789")).get_json()["case_code"]
        t = Task.query.filter_by(case_code=code).first()
        assert t.reporter_anydesk == "123 456 789"
        # Lookup anonim — oturumsuz client ile de çalışmalı
        d = client.post(
            "/portal/api/lookup",
            json={"case_code": code, "email": "ahmet@inventist.com.tr"},
        ).get_json()
        assert d["reporter_anydesk"] == "123 456 789"

    def test_anydesk_opsiyonel(self, db, client, portal_login):
        portal_login(email="ahmet@inventist.com.tr")
        code = client.post("/portal/api/cases", json=_valid_body()).get_json()["case_code"]
        assert Task.query.filter_by(case_code=code).first().reporter_anydesk is None

    def test_kisa_aciklama_400(self, db, client, portal_login):
        portal_login(email="ahmet@inventist.com.tr")
        r = client.post("/portal/api/cases", json=_valid_body(description="çok kısa"))
        assert r.status_code == 400
        assert "60" in r.get_json()["error"]

    def test_eksik_konu_400(self, db, client, portal_login):
        portal_login(email="ahmet@inventist.com.tr")
        assert client.post("/portal/api/cases", json=_valid_body(subject="")).status_code == 400

    def test_case_kodu_unique(self, db, client, portal_login):
        portal_login(email="ahmet@inventist.com.tr")
        codes = set()
        for _ in range(5):
            r = client.post("/portal/api/cases", json=_valid_body())
            codes.add(r.get_json()["case_code"])
        assert len(codes) == 5  # her biri farklı


class TestPortalLookup:
    """Lookup anonim — oturum gerekmez."""

    def _make(self, client, portal_login):
        portal_login(email="ahmet@inventist.com.tr", name="Ahmet Yılmaz")
        return client.post("/portal/api/cases", json=_valid_body()).get_json()["case_code"]

    def test_dogru_kod_ve_mail_200(self, db, client, portal_login):
        code = self._make(client, portal_login)
        # Lookup oturumsuz client ile — anonim takip
        with client.session_transaction() as s:
            s.pop("portal_email", None)
            s.pop("portal_firm", None)
        r = client.post(
            "/portal/api/lookup",
            json={"case_code": code, "email": "ahmet@inventist.com.tr"},
        )
        assert r.status_code == 200
        d = r.get_json()
        assert d["case_code"] == code
        assert d["status"] in ("received", "in_progress", "resolved")
        # İç alanlar sızmamalı
        assert "user_id" not in d
        assert "manager_note" not in d
        assert "reporter_email" not in d

    def test_yanlis_mail_404(self, db, client, portal_login):
        code = self._make(client, portal_login)
        r = client.post("/portal/api/lookup", json={"case_code": code, "email": "baska@x.com"})
        assert r.status_code == 404

    def test_yanlis_kod_404(self, db, client):
        assert (
            client.post(
                "/portal/api/lookup",
                json={"case_code": "INV-XXXXXX", "email": "ahmet@inventist.com.tr"},
            ).status_code
            == 404
        )

    def test_kod_buyuk_harfe_normalize(self, db, client, portal_login):
        code = self._make(client, portal_login)
        r = client.post(
            "/portal/api/lookup",
            json={"case_code": code.lower(), "email": "ahmet@inventist.com.tr"},
        )
        assert r.status_code == 200


class TestPortalMe:
    """v5.103 — /portal/api/me oturum durumu."""

    def test_oturumsuz_401(self, db, client):
        r = client.get("/portal/api/me")
        assert r.status_code == 401
        assert r.get_json().get("login_required") is True

    def test_oturumla_200(self, db, client, portal_login):
        portal_login(email="ali@inventist.com.tr", name="Ali")
        r = client.get("/portal/api/me")
        assert r.status_code == 200
        d = r.get_json()
        assert d["email"] == "ali@inventist.com.tr"
        assert d["firm"] == "inventist"
        assert d["name"] == "Ali"

    def test_logout_oturumu_siler(self, db, client, portal_login):
        portal_login(email="ali@inventist.com.tr")
        assert client.get("/portal/api/me").status_code == 200
        assert client.post("/portal/auth/logout").status_code == 200
        assert client.get("/portal/api/me").status_code == 401
