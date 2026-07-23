"""
test_kb.py — v5.24 — Bilgi Bankası (portal self-service FAQ + IT yönetimi).

- Portal (login yok): yayınlanmış makaleler firma+global; arama; kategori; view_count;
  feedback; taslak/kapsam-dışı gizli.
- IT CRUD: director firma-kapsamlı; global yalnız super_admin.
"""

import pytest

import app as app_module
from models.database import KbArticle, db


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    app_module._KB_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()
    app_module._KB_HITS.clear()


def _verify(client, email="calisan@inventist.com.tr"):
    """v5.28 — KB e-posta kapısı: portal KB testleri önce doğrulama yapar."""
    r = client.post("/portal/api/kb/verify", json={"email": email})
    assert r.status_code == 200
    return r.get_json()["firm"]


def _art(title="Yazıcı sıfırlama", firm="inventist", category="donanım", published=True, body="", keywords=""):
    a = KbArticle(title=title, firm=firm, category=category, published=published, body=body, keywords=keywords)
    db.session.add(a)
    db.session.commit()
    return a


class TestPortalKb:
    @pytest.fixture(autouse=True)
    def _gate(self, client):
        _verify(client)  # inventist domain → firma kilidi inventist

    def test_yayin_firma_global_gorunur(self, db, client):
        _art("İnv makale", firm="inventist")
        _art("Global makale", firm="")
        _art("Assos makale", firm="assos")
        arts = client.get("/portal/api/kb?firm=inventist").get_json()
        titles = {a["title"] for a in arts}
        assert "İnv makale" in titles and "Global makale" in titles
        assert "Assos makale" not in titles  # kapsam dışı

    def test_taslak_gizli(self, db, client):
        _art("Taslak", firm="inventist", published=False)
        assert client.get("/portal/api/kb?firm=inventist").get_json() == []

    def test_arama(self, db, client):
        _art("VPN kurulumu", firm="inventist", body="AnyConnect adımları", keywords="uzak erişim")
        _art("Yazıcı", firm="inventist", body="toner")
        r = client.get("/portal/api/kb?firm=inventist&q=anyconnect").get_json()
        assert len(r) == 1 and r[0]["title"] == "VPN kurulumu"
        # keyword üzerinden de bulunur
        assert len(client.get("/portal/api/kb?firm=inventist&q=uzak").get_json()) == 1

    def test_kategori_filtresi(self, db, client):
        _art("Ağ makale", firm="inventist", category="ağ")
        _art("Donanım makale", firm="inventist", category="donanım")
        r = client.get("/portal/api/kb?firm=inventist&category=ağ").get_json()
        assert len(r) == 1 and r[0]["category"] == "ağ"

    def test_detay_view_count_artar(self, db, client):
        a = _art("Makale", firm="inventist")
        assert a.view_count == 0
        d = client.get(f"/portal/api/kb/{a.id}").get_json()
        assert "body" in d
        assert db.session.get(KbArticle, a.id).view_count == 1

    def test_taslak_detay_404(self, db, client):
        a = _art("Taslak", firm="inventist", published=False)
        assert client.get(f"/portal/api/kb/{a.id}").status_code == 404

    def test_feedback(self, db, client):
        a = _art("Makale", firm="inventist")
        assert client.post(f"/portal/api/kb/{a.id}/feedback", json={"helpful": True}).status_code == 200
        client.post(f"/portal/api/kb/{a.id}/feedback", json={"helpful": False})
        a2 = db.session.get(KbArticle, a.id)
        assert a2.helpful_yes == 1 and a2.helpful_no == 1


class TestKbCrud:
    def test_director_ekler_kendi_firmasi(self, db, client, user_factory, login_as):
        d = user_factory(username="kb_dir", firm="inventist", permission_level="it_director")
        login_as(d)
        r = client.post("/api/kb", json={"title": "Nasıl yapılır", "firm": "inventist", "category": "ağ"})
        assert r.status_code == 201
        assert r.get_json()["published"] is False  # varsayılan taslak

    def test_director_global_403(self, db, client, user_factory, login_as):
        d = user_factory(username="kb_dg", firm="inventist", permission_level="it_director")
        login_as(d)
        assert client.post("/api/kb", json={"title": "X", "firm": ""}).status_code == 403

    def test_director_kapsam_disi_403(self, db, client, user_factory, login_as):
        d = user_factory(username="kb_ds", firm="inventist", permission_level="it_director")
        login_as(d)
        assert client.post("/api/kb", json={"title": "X", "firm": "assos"}).status_code == 403

    def test_baslik_zorunlu_400(self, db, client, user_factory, login_as):
        sa = user_factory(username="kb_sa", permission_level="super_admin", is_admin=True)
        login_as(sa)
        assert client.post("/api/kb", json={"title": "  ", "firm": "inventist"}).status_code == 400

    def test_yayinla_ve_sil(self, db, client, user_factory, login_as):
        sa = user_factory(username="kb_sa2", permission_level="super_admin", is_admin=True)
        login_as(sa)
        aid = client.post("/api/kb", json={"title": "M", "firm": "inventist"}).get_json()["id"]
        r = client.patch(f"/api/kb/{aid}", json={"published": True})
        assert r.status_code == 200 and r.get_json()["published"] is True
        # portalda görünür oldu (KB kapısı: önce doğrula)
        _verify(client)
        assert any(x["id"] == aid for x in client.get("/portal/api/kb?firm=inventist").get_json())
        assert client.delete(f"/api/kb/{aid}").status_code == 200

    def test_liste_kapsam(self, db, client, user_factory, login_as):
        _art("İnv", firm="inventist", published=False)
        _art("Assos", firm="assos", published=False)
        d = user_factory(username="kb_ls", firm="inventist", permission_level="it_director")
        login_as(d)
        firms = {a["firm"] for a in client.get("/api/kb").get_json()}
        assert "assos" not in firms  # director assos taslağını görmez
