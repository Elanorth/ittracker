"""
test_kb.py — v5.24 — Bilgi Bankası (portal self-service FAQ + IT yönetimi).

- Portal (login yok): yayınlanmış makaleler firma+global; arama; kategori; view_count;
  feedback; taslak/kapsam-dışı gizli.
- IT CRUD: director firma-kapsamlı; global yalnız super_admin.
- v6.1: makaleye PDF ek yükleme + satır içi görüntüleme.
"""

import io

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
    """v5.103 — Eski e-posta kapısı kaldırıldı; O365 oturumu doğrudan kurulur
    (SSO callback eşdeğeri)."""
    import app as _app

    email = email.lower()
    domain = email.rsplit("@", 1)[-1]
    firm = _app._kb_domain_map().get(domain, "")
    with client.session_transaction() as s:
        s["portal_email"] = email
        s["portal_firm"] = firm
        s["portal_name"] = email.split("@")[0]
    return firm


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


class TestKbReadForAllRoles:
    """v6.0 — KB okuma tüm giriş yapmış rollere açık, yazma director+ kalır.
    Önceden GET /api/kb sadece director+'ye açıktı → operatör case'e bakarken
    benzer çözülmüş vakaları göremiyordu. Bu davranış artık düzeltildi."""

    def test_junior_operator_yayinlanan_makaleleri_gorur(self, db, client, user_factory, login_as):
        _art("Yayınlanmış inv", firm="inventist", published=True)
        _art("Taslak inv", firm="inventist", published=False)
        op = user_factory(username="kb_jr", firm="inventist", permission_level="junior")
        login_as(op)
        r = client.get("/api/kb")
        assert r.status_code == 200
        titles = {a["title"] for a in r.get_json()}
        assert "Yayınlanmış inv" in titles
        assert "Taslak inv" not in titles  # non-director taslak görmez

    def test_junior_operator_yazma_403(self, db, client, user_factory, login_as):
        op = user_factory(username="kb_jr2", firm="inventist", permission_level="junior")
        login_as(op)
        assert client.post("/api/kb", json={"title": "X", "firm": "inventist"}).status_code == 403

    def test_operator_makale_detayi_okur(self, db, client, user_factory, login_as):
        a = _art("Yazıcı kılavuzu", firm="inventist", published=True, body="Adım 1…")
        op = user_factory(username="kb_op", firm="inventist", permission_level="senior")
        login_as(op)
        r = client.get(f"/api/kb/{a.id}")
        assert r.status_code == 200
        assert r.get_json()["body"] == "Adım 1…"

    def test_operator_taslak_makale_404(self, db, client, user_factory, login_as):
        a = _art("Taslak", firm="inventist", published=False)
        op = user_factory(username="kb_op2", firm="inventist", permission_level="junior")
        login_as(op)
        # Non-director için taslak görünmemeli (yayın bilgi sızıntısı olmasın)
        assert client.get(f"/api/kb/{a.id}").status_code == 404

    def test_operator_kapsam_disi_makale_404(self, db, client, user_factory, login_as):
        a = _art("Assos makale", firm="assos", published=True)
        op = user_factory(username="kb_op3", firm="inventist", permission_level="senior")
        login_as(op)
        # İnv operatörü Assos yayın makalesini bile görmez (firma izolasyonu)
        assert client.get(f"/api/kb/{a.id}").status_code == 404

    def test_director_taslak_detay_erisir(self, db, client, user_factory, login_as):
        a = _art("Taslak inv", firm="inventist", published=False, body="wip")
        d = user_factory(username="kb_dr", firm="inventist", permission_level="it_director")
        login_as(d)
        r = client.get(f"/api/kb/{a.id}")
        assert r.status_code == 200
        assert r.get_json()["body"] == "wip"


def _pdf_bytes(payload=b"test"):
    """Minimal geçerli PDF imzası + yük (yüklemenin başarılı olması için yeterli)."""
    return b"%PDF-1.4\n" + payload + b"\n%%EOF\n"


class TestKbPdfUpload:
    """v6.1 — Makaleye PDF ek yükleme/kaldırma + satır içi görüntüleme."""

    def test_director_pdf_yukler(self, db, client, user_factory, login_as, tmp_path, monkeypatch):
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("Yazıcı kılavuzu", firm="inventist")
        d = user_factory(username="kb_pdf_dir", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "kilavuz.pdf")}
        r = client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data")
        assert r.status_code == 200
        body = r.get_json()
        assert body["has_pdf"] is True
        assert body["pdf_filename"] == "kilavuz.pdf"
        assert body["pdf_size_bytes"] > 0

    def test_izinsiz_uzanti_400(self, db, client, user_factory, login_as, tmp_path, monkeypatch):
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist")
        d = user_factory(username="kb_pdf_bad", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(b"MZ..."), "payload.exe")}
        r = client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data")
        assert r.status_code == 400

    def test_pdf_imzasi_yoksa_400(self, db, client, user_factory, login_as, tmp_path, monkeypatch):
        """Uzantı .pdf ama içerik PDF değil → reddedilir (uzantı taklidi engellenir)."""
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist")
        d = user_factory(username="kb_pdf_fake", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(b"not a pdf"), "fake.pdf")}
        r = client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data")
        assert r.status_code == 400

    def test_kapsam_disi_direktor_403(self, db, client, user_factory, login_as, tmp_path, monkeypatch):
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("Assos makale", firm="assos")
        d = user_factory(username="kb_pdf_cross", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "k.pdf")}
        r = client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data")
        assert r.status_code == 403

    def test_non_director_403(self, db, client, user_factory, login_as, tmp_path, monkeypatch):
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist")
        op = user_factory(username="kb_pdf_jr", firm="inventist", permission_level="junior")
        login_as(op)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "k.pdf")}
        r = client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data")
        assert r.status_code == 403

    def test_pdf_satir_ici_stream(self, db, client, user_factory, login_as, tmp_path, monkeypatch):
        """Yüklenen PDF /api/kb/<id>/pdf ile inline (attachment DEĞİL) döner."""
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist", published=True)
        d = user_factory(username="kb_pdf_stream", firm="inventist", permission_level="it_director")
        login_as(d)
        payload = _pdf_bytes(b"icerik")
        data = {"pdf": (io.BytesIO(payload), "k.pdf")}
        assert client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data").status_code == 200
        r = client.get(f"/api/kb/{a.id}/pdf")
        assert r.status_code == 200
        assert r.mimetype == "application/pdf"
        assert "inline" in r.headers.get("Content-Disposition", "")
        assert r.data.startswith(b"%PDF-")

    def test_portal_pdf_satir_ici(self, db, client, tmp_path, monkeypatch, user_factory, login_as):
        """Portal (login yok): yayınlanmış makalenin PDF'i e-posta kapısı sonrası inline döner."""
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist", published=True)
        d = user_factory(username="kb_portal_up", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "k.pdf")}
        assert client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data").status_code == 200
        # IT oturumunu kapat; portal doğrulamayı yeniden kullansın
        with client.session_transaction() as s:
            s.clear()
        _verify(client)
        r = client.get(f"/portal/api/kb/{a.id}/pdf")
        assert r.status_code == 200
        assert r.mimetype == "application/pdf"
        assert r.data.startswith(b"%PDF-")

    def test_portal_pdf_dogrulama_yoksa_401(self, db, client, tmp_path, monkeypatch, user_factory, login_as):
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist", published=True)
        d = user_factory(username="kb_portal_up2", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "k.pdf")}
        assert client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data").status_code == 200
        with client.session_transaction() as s:
            s.clear()
        # KB kapısı doğrulamadan — 401
        assert client.get(f"/portal/api/kb/{a.id}/pdf").status_code == 401

    def test_portal_taslak_pdf_404(self, db, client, tmp_path, monkeypatch, user_factory, login_as):
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("Taslak", firm="inventist", published=True)
        d = user_factory(username="kb_portal_dr", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "k.pdf")}
        assert client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data").status_code == 200
        # Yayından kaldır
        client.patch(f"/api/kb/{a.id}", json={"published": False})
        with client.session_transaction() as s:
            s.clear()
        _verify(client)
        assert client.get(f"/portal/api/kb/{a.id}/pdf").status_code == 404

    def test_pdf_silme(self, db, client, user_factory, login_as, tmp_path, monkeypatch):
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist")
        d = user_factory(username="kb_pdf_del", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "k.pdf")}
        client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data")
        r = client.delete(f"/api/kb/{a.id}/pdf")
        assert r.status_code == 200
        assert r.get_json()["has_pdf"] is False
        assert db.session.get(KbArticle, a.id).pdf_path is None

    def test_portal_detay_has_pdf_flag(self, db, client, tmp_path, monkeypatch, user_factory, login_as):
        """Portal makale detayı has_pdf + pdf_filename alanlarını taşımalı."""
        monkeypatch.setattr("services.storage.KB_DIR", str(tmp_path))
        a = _art("M", firm="inventist", published=True)
        d = user_factory(username="kb_portal_meta", firm="inventist", permission_level="it_director")
        login_as(d)
        data = {"pdf": (io.BytesIO(_pdf_bytes()), "k.pdf")}
        client.post(f"/api/kb/{a.id}/pdf", data=data, content_type="multipart/form-data")
        with client.session_transaction() as s:
            s.clear()
        _verify(client)
        d2 = client.get(f"/portal/api/kb/{a.id}").get_json()
        assert d2["has_pdf"] is True
        assert d2["pdf_filename"] == "k.pdf"
