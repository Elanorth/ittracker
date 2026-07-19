"""
test_case_notifications.py — v5.22 — Portal case 'IT ilgisi bekliyor' (it_unread)
bayrağı + bildirim zili new_cases grubu.

- Yeni case açılınca it_unread=True.
- IT case mesajlarını GÖRÜNTÜLEYİNCE it_unread=False.
- Reporter yanıt yazınca tekrar True.
- IT yanıt/iç not yazınca False.
- /api/notifications/preview new_cases: atanan bana + havuz (firma kapsamı) görünür,
  kapsam dışı havuz görünmez.
"""

import pytest

import app as app_module
from models.database import Task, db


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


def _open(client, firm="inventist", subject="Yazıcı arızası"):
    return client.post(
        "/portal/api/cases",
        json={
            "firm": firm,
            "name": "Ali Veli",
            "email": "ali@x.com",
            "subject": subject,
            "category": "support",
            "description": "Bildirim testi için en az altmış karakter olması gereken uzunca bir açıklama metni.",
        },
    ).get_json()["case_code"]


def _task(code):
    return Task.query.filter_by(case_code=code).first()


class TestUnreadLifecycle:
    def test_yeni_case_unread(self, db, client):
        t = _task(_open(client))
        assert t.it_unread is True

    def test_it_goruntuleyince_temizlenir(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_a", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        r = client.get(f"/api/tasks/{task.id}/messages")
        assert r.status_code == 200
        assert db.session.get(Task, task.id).it_unread is False

    def test_reporter_yaniti_tekrar_unread(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_b", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.get(f"/api/tasks/{task.id}/messages")  # temizle
        # reporter yanıt (login yok)
        client.post("/portal/api/case/reply", json={"case_code": code, "email": "ali@x.com", "body": "Devam ediyor"})
        assert db.session.get(Task, task.id).it_unread is True

    def test_it_yaniti_temizler(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_c", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "it", "body": "Bakıyoruz"})
        assert db.session.get(Task, task.id).it_unread is False

    def test_ic_not_da_temizler(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_d", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "internal", "body": "iç not"})
        assert db.session.get(Task, task.id).it_unread is False


class TestNotificationPreview:
    def test_havuz_kapsam_ici_gorunur(self, db, client, user_factory, login_as):
        _open(client, "inventist")
        u = user_factory(username="np_u", firm="inventist", permission_level="it_specialist")
        login_as(u)
        d = client.get("/api/notifications/preview").get_json()
        assert any(c["kind"] == "new" and c["pooled"] for c in d["new_cases"])
        assert d["total"] >= 1

    def test_kapsam_disi_havuz_gorunmez(self, db, client, user_factory, login_as):
        _open(client, "assos")  # assos havuzu
        u = user_factory(username="np_scope", firm="inventist", permission_level="junior")
        login_as(u)
        d = client.get("/api/notifications/preview").get_json()
        assert d["new_cases"] == []

    def test_super_admin_tum_havuz(self, db, client, user_factory, login_as):
        _open(client, "inventist")
        _open(client, "assos")
        sa = user_factory(username="np_sa", permission_level="super_admin", is_admin=True)
        login_as(sa)
        firms = {c["firm"] for c in client.get("/api/notifications/preview").get_json()["new_cases"]}
        assert "inventist" in firms and "assos" in firms

    def test_it_gorunce_zilden_duser(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        u = user_factory(username="np_seen", firm="inventist", permission_level="it_specialist")
        login_as(u)
        assert len(client.get("/api/notifications/preview").get_json()["new_cases"]) >= 1
        client.get(f"/api/tasks/{task.id}/messages")  # görüntüle → temizle
        assert client.get("/api/notifications/preview").get_json()["new_cases"] == []
