"""
test_soft_delete_phase2.py — v5.100 Faz 2

- GET /api/tasks/deleted: director+ görebilir, firma kapsamı filtrelenir,
  super_admin tüm firmalar; junior/it_specialist yetkisiz (403).
- DELETE /api/tasks/<id>/hard: yalnız super_admin; soft-delete zorunlu.
- Portal case DELETE → reporter'a send_case_deleted mail (monkeypatch capture).
"""

from datetime import datetime, timedelta

import pytest

from models.database import Task, db


@pytest.fixture
def admin(db, user_factory, login_as):
    u = user_factory(username="p2_admin", firm="inventist", permission_level="super_admin", is_admin=True)
    login_as(u)
    return u


def _create_task(client, title="Silinecek görev", firm="inventist"):
    r = client.post(
        "/api/tasks",
        json={
            "title": title,
            "category": "other",
            "period": "Tek Seferlik",
            "priority": "orta",
            "firm": firm,
            "team": "Teknik Ekip",
            "deadline": "2026-12-31",
        },
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


class TestListDeletedTasks:
    def test_director_gorebilir(self, db, client, user_factory, login_as):
        director = user_factory(username="p2_dir", firm="inventist", permission_level="it_director")
        login_as(director)
        tid = _create_task(client, "İnv görev A", firm="inventist")
        client.delete(f"/api/tasks/{tid}")
        r = client.get("/api/tasks/deleted")
        assert r.status_code == 200
        rows = r.get_json()
        assert len(rows) == 1
        assert rows[0]["id"] == tid
        assert rows[0]["deleted_at"] is not None
        assert rows[0]["restorable_until"] is not None

    def test_super_admin_tum_firmalari_gorur(self, db, client, admin, user_factory, login_as):
        # inventist görev
        tid_i = _create_task(client, "İnv A", firm="inventist")
        client.delete(f"/api/tasks/{tid_i}")
        # assos görev (super_admin başka firmada da oluşturabilir; ama _create_task inventist döner)
        # Direkt DB'ye insert edelim
        assos_task = Task(title="Assos B", category="other", firm="assos", team="Genel")
        db.session.add(assos_task)
        db.session.commit()
        client.delete(f"/api/tasks/{assos_task.id}")

        r = client.get("/api/tasks/deleted")
        assert r.status_code == 200
        firms = {row["firm"] for row in r.get_json()}
        assert "inventist" in firms
        assert "assos" in firms

    def test_director_kapsam_disi_firma_gorulmez(self, db, client, user_factory, login_as):
        # assos direkt DB'den silinmiş görev
        t = Task(title="Assos", category="other", firm="assos", team="Genel")
        db.session.add(t)
        db.session.commit()
        t.deleted_at = datetime.utcnow()
        db.session.commit()
        # inventist director
        director = user_factory(username="p2_dir_scope", firm="inventist", permission_level="it_director")
        login_as(director)
        r = client.get("/api/tasks/deleted")
        assert r.status_code == 200
        firms = {row["firm"] for row in r.get_json()}
        assert "assos" not in firms

    def test_junior_yetkisiz(self, db, client, user_factory, login_as):
        u = user_factory(username="p2_junior", firm="inventist", permission_level="junior")
        login_as(u)
        r = client.get("/api/tasks/deleted")
        assert r.status_code == 403

    def test_it_specialist_yetkisiz(self, db, client, user_factory, login_as):
        u = user_factory(username="p2_spec", firm="inventist", permission_level="it_specialist")
        login_as(u)
        r = client.get("/api/tasks/deleted")
        assert r.status_code == 403


class TestHardDelete:
    def test_super_admin_kalici_siler(self, db, client, admin):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")  # soft-delete
        r = client.delete(f"/api/tasks/{tid}/hard")
        assert r.status_code == 200
        # DB'de artık yok (bypass ile bile)
        gone = db.session.get(Task, tid, execution_options={"include_deleted": True})
        assert gone is None

    def test_director_yetkisiz_hard_delete(self, db, client, user_factory, login_as):
        director = user_factory(username="p2_dir_hd", firm="inventist", permission_level="it_director")
        login_as(director)
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        r = client.delete(f"/api/tasks/{tid}/hard")
        assert r.status_code == 403

    def test_aktif_gorev_hard_delete_engellenir(self, db, client, admin):
        tid = _create_task(client)
        # Soft-delete edilmemiş → hard delete 400
        r = client.delete(f"/api/tasks/{tid}/hard")
        assert r.status_code == 400

    def test_var_olmayan_gorev(self, db, client, admin):
        r = client.delete("/api/tasks/999999/hard")
        assert r.status_code == 404


class TestPortalCaseDeleteMail:
    def _capture(self, monkeypatch):
        calls = []

        def _fake(email, case_code, subject):
            calls.append({"email": email, "case_code": case_code, "subject": subject})

        import services.mailer as mailer_mod

        monkeypatch.setattr(mailer_mod, "send_case_deleted", _fake)
        return calls

    def test_portal_case_silinince_reporter_mail(self, db, client, admin, monkeypatch):
        # Portal'dan yeni case aç
        r = client.post(
            "/portal/api/cases",
            json={
                "firm": "inventist",
                "name": "Ali Veli",
                "email": "ali@x.com",
                "subject": "Yazıcı arızası",
                "category": "support",
                "description": "Uzun bir açıklama metni portal case testinde en az altmış karakter olmalı.",
            },
        )
        assert r.status_code == 201
        code = r.get_json()["case_code"]
        task = Task.query.filter_by(case_code=code).first()
        assert task is not None
        # IT (super_admin) siler → reporter mail beklenir
        calls = self._capture(monkeypatch)
        rd = client.delete(f"/api/tasks/{task.id}")
        assert rd.status_code == 200
        assert len(calls) == 1
        assert calls[0]["email"] == "ali@x.com"
        assert calls[0]["case_code"] == code

    def test_manuel_gorev_silinince_reporter_mail_yok(self, db, client, admin, monkeypatch):
        # source='manual' — reporter yok, mail çağrılmamalı
        tid = _create_task(client)
        calls = self._capture(monkeypatch)
        client.delete(f"/api/tasks/{tid}")
        assert calls == []
