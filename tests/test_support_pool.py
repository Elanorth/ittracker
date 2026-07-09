"""
test_support_pool.py — v5.18 Destek Havuzu + üstlenme/bırakma.

- Portal case artık ATANMAMIŞ açılır (user_id=None) → firma havuzuna düşer.
- GET /api/support/pool: firma kapsamındaki atanmamış açık destek talepleri.
- POST /api/tasks/<id>/claim: üstlen (kendine ata); kapsam kontrolü.
- POST /api/tasks/<id>/release: havuza geri bırak (sahibi/director+).
"""

import pytest

import app as app_module
from models.database import Task, db


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


def _open(client, firm="inventist"):
    return client.post(
        "/portal/api/cases",
        json={
            "firm": firm,
            "name": "Ali Veli",
            "email": "ali@x.com",
            "subject": f"{firm} havuz testi",
            "category": "support",
            "description": "Havuz testi için açıklama, en az altmış karakter olması gerektiğinden bu cümleyi uzatıyorum.",
        },
    ).get_json()["case_code"]


class TestPoolCreateUnassigned:
    def test_portal_case_atanmamis_acilir(self, db, client):
        code = _open(client)
        t = Task.query.filter_by(case_code=code).first()
        assert t.user_id is None  # havuzda


class TestPoolVisibility:
    def test_super_admin_tum_firmalar(self, db, client, user_factory, login_as):
        _open(client, "inventist")
        _open(client, "assos")
        admin = user_factory(username="pool_sa", permission_level="super_admin", is_admin=True)
        login_as(admin)
        firms = {t["firm"] for t in client.get("/api/support/pool").get_json()}
        assert "inventist" in firms and "assos" in firms

    def test_junior_yalniz_kendi_firmasi(self, db, client, user_factory, login_as):
        _open(client, "inventist")
        _open(client, "assos")
        jr = user_factory(username="pool_jr", firm="inventist", permission_level="junior")
        login_as(jr)
        firms = {t["firm"] for t in client.get("/api/support/pool").get_json()}
        assert firms == {"inventist"}  # assos görünmez

    def test_atanan_case_havuzda_gorunmez(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = Task.query.filter_by(case_code=code).first()
        u = user_factory(username="pool_u", firm="inventist", permission_level="junior")
        login_as(u)
        client.post(f"/api/tasks/{task.id}/claim")
        codes = [t["case_code"] for t in client.get("/api/support/pool").get_json()]
        assert code not in codes  # üstlenildi → havuzdan çıktı


class TestClaim:
    def test_ustlen_kendine_atar(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = Task.query.filter_by(case_code=code).first()
        u = user_factory(username="clm_u", firm="inventist", permission_level="it_specialist")
        login_as(u)
        r = client.post(f"/api/tasks/{task.id}/claim")
        assert r.status_code == 200
        assert db.session.get(Task, task.id).user_id == u.id

    def test_kapsam_disi_403(self, db, client, user_factory, login_as):
        code = _open(client, "assos")
        task = Task.query.filter_by(case_code=code).first()
        u = user_factory(username="clm_scope", firm="inventist", permission_level="junior")
        login_as(u)
        assert client.post(f"/api/tasks/{task.id}/claim").status_code == 403

    def test_baskasina_atanmis_409(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = Task.query.filter_by(case_code=code).first()
        a = user_factory(username="clm_a", firm="inventist", permission_level="junior")
        b = user_factory(username="clm_b", firm="inventist", permission_level="junior")
        login_as(a)
        client.post(f"/api/tasks/{task.id}/claim")  # a üstlendi
        login_as(b)
        assert client.post(f"/api/tasks/{task.id}/claim").status_code == 409  # b (junior) devralamaz

    def test_director_devralabilir(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = Task.query.filter_by(case_code=code).first()
        a = user_factory(username="clm_a2", firm="inventist", permission_level="junior")
        director = user_factory(username="clm_dir", firm="inventist", permission_level="it_director")
        login_as(a)
        client.post(f"/api/tasks/{task.id}/claim")
        login_as(director)
        assert client.post(f"/api/tasks/{task.id}/claim").status_code == 200  # director devralır
        assert db.session.get(Task, task.id).user_id == director.id


class TestRelease:
    def test_sahibi_havuza_birakir(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = Task.query.filter_by(case_code=code).first()
        u = user_factory(username="rel_u", firm="inventist", permission_level="it_specialist")
        login_as(u)
        client.post(f"/api/tasks/{task.id}/claim")
        r = client.post(f"/api/tasks/{task.id}/release")
        assert r.status_code == 200
        assert db.session.get(Task, task.id).user_id is None  # havuza döndü

    def test_yetkisiz_403(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = Task.query.filter_by(case_code=code).first()
        owner = user_factory(username="rel_own", firm="inventist", permission_level="it_specialist")
        login_as(owner)
        client.post(f"/api/tasks/{task.id}/claim")
        other = user_factory(username="rel_other", firm="inventist", permission_level="junior")
        login_as(other)
        assert client.post(f"/api/tasks/{task.id}/release").status_code == 403
