"""
test_case_messages.py — v5.15 Faz B — Portal case yazışması.

- Portal: kullanıcı yanıtı (POST /portal/api/case/reply, kod+mail doğrulama).
- IT: GET/POST /api/tasks/<id>/messages (it | internal).
- GÖRÜNÜRLÜK: portal reporter+it görür, internal ASLA; IT hepsini görür.
- Durum: IT "it" yanıtı sonrası portal durumu received → in_progress.
"""

import pytest

import app as app_module
from models.database import CaseMessage, Task


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


def _open_case(client):
    r = client.post(
        "/portal/api/cases",
        json={
            "firm": "inventist",
            "name": "Ahmet Yılmaz",
            "email": "ahmet@inventist.com.tr",
            "subject": "Portal Faz B testi",
            "category": "support",
            "description": "Bu bir Faz B yazışma testidir, açıklama en az altmış karakter olmalı bu yüzden uzatıyorum.",
        },
    )
    return r.get_json()["case_code"]


class TestPortalReply:
    def test_kullanici_yanit_yazar(self, db, client):
        code = _open_case(client)
        r = client.post(
            "/portal/api/case/reply",
            json={"case_code": code, "email": "ahmet@inventist.com.tr", "body": "Sorun devam ediyor."},
        )
        assert r.status_code == 201
        d = r.get_json()
        assert any(m["sender"] == "reporter" and m["body"] == "Sorun devam ediyor." for m in d["messages"])

    def test_yanlis_mail_reddedilir(self, db, client):
        code = _open_case(client)
        r = client.post("/portal/api/case/reply", json={"case_code": code, "email": "yanlis@x.com", "body": "test123"})
        assert r.status_code == 404

    def test_bos_mesaj_400(self, db, client):
        code = _open_case(client)
        r = client.post(
            "/portal/api/case/reply", json={"case_code": code, "email": "ahmet@inventist.com.tr", "body": " "}
        )
        assert r.status_code == 400


class TestITMessages:
    def _case_and_admin(self, db, client, user_factory, login_as):
        code = _open_case(client)
        task = Task.query.filter_by(case_code=code).first()
        admin = user_factory(username="cm_admin", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        return code, task, admin

    def test_it_yanit_ve_ic_not(self, db, client, user_factory, login_as):
        code, task, admin = self._case_and_admin(db, client, user_factory, login_as)
        # IT → kullanıcıya yanıt
        r1 = client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "it", "body": "Merhaba, bakıyoruz."})
        assert r1.status_code == 201
        # IT → iç not
        r2 = client.post(
            f"/api/tasks/{task.id}/messages", json={"sender_type": "internal", "body": "Switch portu arızalı."}
        )
        assert r2.status_code == 201
        # IT tümünü görür (reporter yok ama it+internal var)
        allm = client.get(f"/api/tasks/{task.id}/messages").get_json()["messages"]
        types = {m["sender_type"] for m in allm}
        assert "it" in types and "internal" in types

    def test_gecersiz_tur_400(self, db, client, user_factory, login_as):
        code, task, admin = self._case_and_admin(db, client, user_factory, login_as)
        assert (
            client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "reporter", "body": "x"}).status_code
            == 400
        )

    def test_yetkisiz_junior_403(self, db, client, user_factory, login_as):
        code = _open_case(client)
        task = Task.query.filter_by(case_code=code).first()
        junior = user_factory(username="cm_jr", firm="assos", permission_level="junior")
        login_as(junior)
        assert client.get(f"/api/tasks/{task.id}/messages").status_code == 403
        assert client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "it", "body": "x"}).status_code == 403


class TestVisibilityAndStatus:
    def test_internal_portalda_sizmaz(self, db, client, user_factory, login_as):
        code = _open_case(client)
        task = Task.query.filter_by(case_code=code).first()
        admin = user_factory(username="cm_v", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "internal", "body": "GİZLİ İÇ NOT"})
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "it", "body": "Kullanıcıya görünür yanıt"})
        # Portal lookup — internal görünmemeli
        pub = client.post("/portal/api/lookup", json={"case_code": code, "email": "ahmet@inventist.com.tr"}).get_json()
        bodies = [m["body"] for m in pub["messages"]]
        assert "Kullanıcıya görünür yanıt" in bodies
        assert "GİZLİ İÇ NOT" not in bodies
        assert all(m["sender"] in ("reporter", "it") for m in pub["messages"])

    def test_durum_it_yanitiyla_in_progress(self, db, client, user_factory, login_as):
        code = _open_case(client)
        task = Task.query.filter_by(case_code=code).first()
        # Yeni case: atanmış ama IT yanıtı yok → received
        d0 = client.post("/portal/api/lookup", json={"case_code": code, "email": "ahmet@inventist.com.tr"}).get_json()
        assert d0["status"] == "received"
        admin = user_factory(username="cm_s", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "it", "body": "İlk yanıt"})
        d1 = client.post("/portal/api/lookup", json={"case_code": code, "email": "ahmet@inventist.com.tr"}).get_json()
        assert d1["status"] == "in_progress"

    def test_internal_durumu_degistirmez(self, db, client, user_factory, login_as):
        code = _open_case(client)
        task = Task.query.filter_by(case_code=code).first()
        admin = user_factory(username="cm_s2", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "internal", "body": "sadece iç not"})
        d = client.post("/portal/api/lookup", json={"case_code": code, "email": "ahmet@inventist.com.tr"}).get_json()
        assert d["status"] == "received"  # iç not IT yanıtı sayılmaz
