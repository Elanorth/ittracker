"""
test_soft_delete.py — v5.99 Task soft-delete davranışı.

DELETE /api/tasks/<id> fiziksel silme yerine deleted_at doldurur.
- Silinmiş görev listelemede görünmez (session-level otomatik filter).
- get_or_404 (PK identity) filter'dan etkilenmez → restore endpoint çalışır.
- POST /api/tasks/<id>/restore geri getirir.
- Zaten silinmiş bir görev tekrar silinemez (404).
- Silinen görev üzerinden PATCH/toggle çalışmaz (filter_by ile SELECT).
- Yetki: sahibi veya kapsam içi director+ silebilir; silen kişi de restore edebilir.
"""

import pytest

from models.database import Task, db


@pytest.fixture
def task_owner(db, user_factory, login_as):
    # it_specialist: routine/project dahil her kategori oluşturabilir
    u = user_factory(username="sd_owner", firm="inventist", permission_level="it_specialist")
    login_as(u)
    return u


def _create_task(client, title="Silinecek görev"):
    r = client.post(
        "/api/tasks",
        json={
            "title": title,
            "category": "other",
            "period": "Tek Seferlik",
            "priority": "orta",
            "firm": "inventist",
            "team": "Teknik Ekip",
            "deadline": "2026-12-31",
        },
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


class TestSoftDeleteBasics:
    def test_delete_soft_marks_deleted_at(self, db, client, task_owner):
        tid = _create_task(client)
        r = client.delete(f"/api/tasks/{tid}")
        assert r.status_code == 200
        assert "restorable_until" in r.get_json()
        # DB'de kayıt hâlâ var, deleted_at dolu (filter bypass ile fetch)
        t = db.session.get(Task, tid, execution_options={"include_deleted": True})
        assert t is not None
        assert t.deleted_at is not None
        assert t.deleted_by == task_owner.id

    def test_soft_deleted_listede_gorunmez(self, db, client, task_owner):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        # /api/tasks listesinde silinmiş görev olmamalı
        r = client.get("/api/tasks")
        assert r.status_code == 200
        ids = [t["id"] for t in r.get_json()]
        assert tid not in ids

    def test_zaten_silinmis_tekrar_silinemez(self, db, client, task_owner):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        r = client.delete(f"/api/tasks/{tid}")
        assert r.status_code == 404

    def test_silinmis_uzerinden_patch_calismaz(self, db, client, task_owner):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        # PATCH filter_by(id, user_id).first_or_404 üzerinden gider → SELECT filter uygulanır → 404
        r = client.patch(f"/api/tasks/{tid}", json={"title": "değişti"})
        assert r.status_code == 404


class TestRestoreEndpoint:
    def test_restore_geri_getirir(self, db, client, task_owner):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        r = client.post(f"/api/tasks/{tid}/restore")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        # Restore sonrası: normal session.get de bulur (silinmiş değil artık)
        t = db.session.get(Task, tid)
        assert t is not None
        assert t.deleted_at is None
        assert t.deleted_by is None
        # Listede geri görünür
        r = client.get("/api/tasks")
        ids = [t["id"] for t in r.get_json()]
        assert tid in ids

    def test_aktif_gorevi_restore_no_op(self, db, client, task_owner):
        tid = _create_task(client)
        r = client.post(f"/api/tasks/{tid}/restore")
        assert r.status_code == 200
        assert r.get_json().get("already_active") is True

    def test_yetkisiz_kullanici_restore_edemez(self, db, client, task_owner, user_factory, login_as):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        # başka firmadan junior
        other = user_factory(username="sd_other", firm="assos", permission_level="junior")
        login_as(other)
        r = client.post(f"/api/tasks/{tid}/restore")
        assert r.status_code == 403

    def test_director_kapsam_ici_restore_edebilir(self, db, client, task_owner, user_factory, login_as):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        # inventist director
        director = user_factory(username="sd_dir", firm="inventist", permission_level="it_director")
        login_as(director)
        r = client.post(f"/api/tasks/{tid}/restore")
        assert r.status_code == 200


class TestSoftDeleteFilter:
    """Session-level with_loader_criteria filter'ı Task için tüm SELECT'lere
    şeffaf şekilde uygulanır — session.get, Task.query.filter, get_or_404
    dahil. Bypass için execution_options={"include_deleted": True}."""

    def test_query_filter_ile_silinmis_bulunmaz(self, db, client, task_owner):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        # Task.query.filter_by ile SELECT — silinmiş bulunmamalı
        assert Task.query.filter_by(id=tid).first() is None
        assert Task.query.filter(Task.id == tid).first() is None
        # session.get de filter uygular (PK lookup SELECT'e döner)
        assert db.session.get(Task, tid) is None

    def test_bypass_ile_silinmis_gorulebilir(self, db, client, task_owner):
        tid = _create_task(client)
        client.delete(f"/api/tasks/{tid}")
        # execution_options(include_deleted=True) bypass eder → admin "Silinenler" için
        found = Task.query.execution_options(include_deleted=True).filter_by(id=tid).first()
        assert found is not None
        assert found.deleted_at is not None
        # session.get bypass ile de (restore endpoint path'i)
        found2 = db.session.get(Task, tid, execution_options={"include_deleted": True})
        assert found2 is not None
        assert found2.deleted_at is not None
