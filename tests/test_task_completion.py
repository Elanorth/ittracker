"""
test_task_completion.py — Rutin görev aylık tamamlanma mantığının baseline testleri.

En kritik iş kuralı: Rutin görevin (category='routine') is_done durumu
Task.is_done flag'inden DEĞİL, TaskCompletion(task_id, year, month) kaydının
varlığından okunur. Her ay bağımsız bir tamamlanma kaydıdır.

Kapsam:
- Rutin görev Mart'ta tamamlanırsa Mart'ta done, Nisan'da pending.
- Aynı (task_id, year, month) için iki kayıt oluşturulamaz (unique constraint).
- Aralık → Ocak yıl geçişinde ay/yıl doğru ayrışır.
- PATCH /api/tasks/:id is_done=true → TaskCompletion kaydı oluşur.
- PATCH /api/tasks/:id is_done=false → TaskCompletion kaydı silinir.
- Task.is_done flag'i rutin görevler için güncellenmez (flag kullanılmaz).
- Tek seferlik rutin görev (period='Tek Seferlik') is_done flag'ini kullanır.
"""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from models.database import Task, TaskCompletion


class TestTaskCompletionModel:
    """TaskCompletion model seviyesi davranışları."""

    def test_rutin_gorev_completion_kaydi_olusturulabilir(self, db, user_factory, task_factory):
        """Rutin görev için TaskCompletion kaydı oluşturulabilir."""
        user = user_factory(username="tc_user1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Sunucu güncellemesi gerçekleştir",
            category="routine",
            period="Aylık",
        )
        comp = TaskCompletion(task_id=task.id, year=2026, month=3)
        db.session.add(comp)
        db.session.commit()

        fetched = TaskCompletion.query.filter_by(task_id=task.id, year=2026, month=3).first()
        assert fetched is not None

    def test_ayni_ay_iki_kayit_unique_constraint_ihlali(self, db, user_factory, task_factory):
        """Aynı (task_id, year, month) için iki kayıt oluşturmak IntegrityError fırlatır."""
        user = user_factory(username="tc_user2", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yığın yedekleme",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskCompletion(task_id=task.id, year=2026, month=3))
        db.session.commit()

        db.session.add(TaskCompletion(task_id=task.id, year=2026, month=3))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_farkli_ay_ayri_kayitlar_olusturulabilir(self, db, user_factory, task_factory):
        """Aynı görev için farklı aylar bağımsız kayıt oluşturabilir."""
        user = user_factory(username="tc_user3", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Şifre yenileme",
            category="routine",
            period="Aylık",
        )
        for month in [1, 2, 3, 4]:
            db.session.add(TaskCompletion(task_id=task.id, year=2026, month=month))
        db.session.commit()

        count = TaskCompletion.query.filter_by(task_id=task.id, year=2026).count()
        assert count == 4

    def test_aralik_ocak_yil_gecisi_ayri_kayitlar(self, db, user_factory, task_factory):
        """Aralık 2026 ve Ocak 2027 tamamlanmaları ayrı kayıtlar olarak izoledir."""
        user = user_factory(username="tc_user4", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yıllık sunucu denetimi",
            category="routine",
            period="Yıllık",
        )
        db.session.add(TaskCompletion(task_id=task.id, year=2026, month=12))
        db.session.add(TaskCompletion(task_id=task.id, year=2027, month=1))
        db.session.commit()

        dec_comp = TaskCompletion.query.filter_by(task_id=task.id, year=2026, month=12).first()
        jan_comp = TaskCompletion.query.filter_by(task_id=task.id, year=2027, month=1).first()
        assert dec_comp is not None
        assert jan_comp is not None
        assert dec_comp.id != jan_comp.id

    def test_task_silinince_completion_da_silinir_cascade(self, db, user_factory, task_factory):
        """Task silindiğinde ilişkili TaskCompletion kayıtları cascade ile silinir."""
        user = user_factory(username="tc_user5", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Bağlantı denetimi",
            category="routine",
            period="Haftalık",
        )
        task_id = task.id
        db.session.add(TaskCompletion(task_id=task_id, year=2026, month=3))
        db.session.add(TaskCompletion(task_id=task_id, year=2026, month=4))
        db.session.commit()

        db.session.delete(task)
        db.session.commit()

        orphan_count = TaskCompletion.query.filter_by(task_id=task_id).count()
        assert orphan_count == 0, "Task silinince TaskCompletion'lar da silinmeli"

    def test_completion_completed_at_timestamp_kaydedilir(self, db, user_factory, task_factory):
        """TaskCompletion kaydı oluştuğunda completed_at timestamp'i otomatik set edilir."""
        user = user_factory(username="tc_user6", firm="inventist")
        task = task_factory(user_id=user.id, category="routine", period="Aylık")
        before = datetime.utcnow()
        comp = TaskCompletion(task_id=task.id, year=2026, month=5)
        db.session.add(comp)
        db.session.commit()
        after = datetime.utcnow()

        fetched = TaskCompletion.query.filter_by(task_id=task.id, year=2026, month=5).first()
        assert fetched.completed_at is not None
        assert before <= fetched.completed_at <= after


class TestTaskCompletionToDict:
    """Task.to_dict() rutin görevlerde ay bazlı is_done davranışı."""

    def test_mart_tamamlanan_rutin_mart_done_nisan_pending(self, db, user_factory, task_factory):
        """
        Kritik iş kuralı: Rutin görev Mart'ta tamamlanırsa
        - Mart görünümünde is_done=True
        - Nisan görünümünde is_done=False
        """
        user = user_factory(username="tc_user7", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Sunucu güncellemesi gerçekleştir",
            category="routine",
            period="Aylık",
        )
        # Mart tamamlaması
        db.session.add(TaskCompletion(task_id=task.id, year=2026, month=3))
        db.session.commit()

        mart_dict = task.to_dict(month=3, year=2026)
        nisan_dict = task.to_dict(month=4, year=2026)

        assert mart_dict["is_done"] is True, "Mart'ta tamamlanan görev Mart görünümünde done olmalı"
        assert nisan_dict["is_done"] is False, "Mart'ta tamamlanan görev Nisan görünümünde pending olmalı"

    def test_rutin_gorev_task_is_done_flag_kullanmaz(self, db, user_factory, task_factory):
        """
        Kritik: Task.is_done=True olsa bile, rutin görev için to_dict()
        ilgili ayda TaskCompletion kaydı yoksa is_done=False döner.
        """
        user = user_factory(username="tc_user8", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Çağrı merkezi günlük kontrol",
            category="routine",
            period="Aylık",
            is_done=True,  # Flag True ama TaskCompletion kaydı yok
        )

        sonuc = task.to_dict(month=4, year=2026)
        assert sonuc["is_done"] is False, (
            "Rutin görev için is_done Task.is_done flag'inden değil "
            "TaskCompletion kaydından okunmalı"
        )

    def test_completion_olmadan_ay_bazli_is_done_false(self, db, user_factory, task_factory):
        """TaskCompletion kaydı olmayan rutin görev her ay pending görünür."""
        user = user_factory(username="tc_user9", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Haftalık yedekleme denetimi",
            category="routine",
            period="Haftalık",
        )
        for month in range(1, 13):
            sonuc = task.to_dict(month=month, year=2026)
            assert sonuc["is_done"] is False, f"Ay {month}'de is_done False olmalı"

    def test_birden_fazla_ay_ayri_ayri_tamamlanabilir(self, db, user_factory, task_factory):
        """Rutin görev birden fazla ayda bağımsız olarak tamamlanabilir."""
        user = user_factory(username="tc_user10", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Aylık rapor hazırlama",
            category="routine",
            period="Aylık",
        )
        # Ocak, Şubat, Mart tamamlandı; Nisan tamamlanmadı
        for month in [1, 2, 3]:
            db.session.add(TaskCompletion(task_id=task.id, year=2026, month=month))
        db.session.commit()

        for month in [1, 2, 3]:
            assert task.to_dict(month=month, year=2026)["is_done"] is True
        assert task.to_dict(month=4, year=2026)["is_done"] is False

    def test_tek_seferlik_rutin_is_done_flag_kullanir(self, db, user_factory, task_factory):
        """period='Tek Seferlik' olan rutin görev is_done flag'ini kullanır (TaskCompletion değil)."""
        user = user_factory(username="tc_user11", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Tek seferlik sistem kurulumu",
            category="routine",
            period="Tek Seferlik",
            is_done=True,
        )
        sonuc = task.to_dict(month=4, year=2026)
        assert sonuc["is_done"] is True, "Tek Seferlik rutin görev Task.is_done flag'ini kullanmalı"

    def test_aralik_2026_ocak_2027_gecis_izolasyonu(self, db, user_factory, task_factory):
        """Aralık 2026'da tamamlanan rutin görev Ocak 2027'de pending görünür."""
        user = user_factory(username="tc_user12", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yıl sonu sunucu denetimi",
            category="routine",
            period="Yıllık",
        )
        db.session.add(TaskCompletion(task_id=task.id, year=2026, month=12))
        db.session.commit()

        aralik = task.to_dict(month=12, year=2026)
        ocak = task.to_dict(month=1, year=2027)

        assert aralik["is_done"] is True, "Aralık 2026'da tamamlanmış, done olmalı"
        assert ocak["is_done"] is False, "Ocak 2027'de completion yok, pending olmalı"


class TestTaskCompletionAPIEndpoint:
    """PATCH /api/tasks/:id — TaskCompletion oluşturma/silme endpoint davranışı."""

    def test_patch_is_done_true_completion_olusturur(self, db, client, user_factory, task_factory, login_as):
        """PATCH is_done=true → TaskCompletion kaydı oluşturulur."""
        user = user_factory(username="api_tc1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="API testi rutin görev",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        resp = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True, "month": 3, "year": 2026},
            content_type="application/json",
        )
        assert resp.status_code == 200
        comp = TaskCompletion.query.filter_by(task_id=task.id, year=2026, month=3).first()
        assert comp is not None, "TaskCompletion kaydı oluşturulmuş olmalı"

    def test_patch_is_done_false_completion_siler(self, db, client, user_factory, task_factory, login_as):
        """PATCH is_done=false → mevcut TaskCompletion kaydı silinir."""
        user = user_factory(username="api_tc2", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Tamamlanmış rutin görev",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskCompletion(task_id=task.id, year=2026, month=3, completed_by=user.id))
        db.session.commit()

        login_as(user)
        resp = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": False, "month": 3, "year": 2026},
            content_type="application/json",
        )
        assert resp.status_code == 200
        comp = TaskCompletion.query.filter_by(task_id=task.id, year=2026, month=3).first()
        assert comp is None, "TaskCompletion kaydı silinmiş olmalı"

    def test_patch_rutin_gorev_task_is_done_flag_degismez(self, db, client, user_factory, task_factory, login_as):
        """Rutin görev tamamlandığında Task.is_done flag'i True'ya set edilmez."""
        user = user_factory(username="api_tc3", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Ağ cihazı kontrol",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True, "month": 3, "year": 2026},
            content_type="application/json",
        )

        from models.database import Task as TaskModel
        refreshed = db.session.get(TaskModel, task.id)
        assert refreshed.is_done is False, (
            "Rutin görevde Task.is_done flag'i güncellenmemeli; "
            "tamamlanma durumu yalnızca TaskCompletion'dan okunur"
        )

    def test_patch_rutin_tamamlama_response_is_done_true_doner(self, db, client, user_factory, task_factory, login_as):
        """Rutin görev tamamlandıktan sonra PATCH response'unda is_done=True gelir."""
        user = user_factory(username="api_tc4", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Güvenlik politikası güncellemesi",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        resp = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True, "month": 4, "year": 2026},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["is_done"] is True, "Response'da is_done=True olmalı"

    def test_farkli_aylar_bagimsiz_patch_cagrilabilir(self, db, client, user_factory, task_factory, login_as):
        """Aynı görev farklı aylar için bağımsız olarak tamamlanabilir/açılabilir."""
        user = user_factory(username="api_tc5", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Aylık yedekleme kontrolü",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        # Mart tamamla
        client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True, "month": 3, "year": 2026},
            content_type="application/json",
        )
        # Nisan tamamla
        client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True, "month": 4, "year": 2026},
            content_type="application/json",
        )

        mart = TaskCompletion.query.filter_by(task_id=task.id, year=2026, month=3).first()
        nisan = TaskCompletion.query.filter_by(task_id=task.id, year=2026, month=4).first()
        assert mart is not None
        assert nisan is not None
        assert mart.id != nisan.id
