"""
test_task_occurrence.py — v5.0 TaskOccurrence tamamlanma kaydı testleri.

Yeni kontrat: Rutin görevin tamamlanma durumu Task.is_done flag'inden DEĞİL,
TaskOccurrence.period_key kaydının varlığından okunur. PATCH toggle endpoint'i
server-side date.today() kullanır; frontend'den gelen month/year param'ları
ignore edilir (Karar 2 = B).

İş kuralları:
- category='routine' + period!='Tek Seferlik' → period_key bazlı takip.
- TaskCompletion = TaskOccurrence alias'ı geriye dönük uyumluluk için korunur.
- Aynı (task_id, period_key) için unique constraint — çift kayıt yok.
- Task silindiğinde tüm TaskOccurrence kayıtları cascade ile silinir.
"""

import pytest
from datetime import datetime, date
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError
from models.database import Task, TaskOccurrence, TaskCompletion


class TestTaskOccurrenceModel:
    """TaskOccurrence model seviyesi davranışları."""

    def test_rutin_gorev_occurrence_kaydi_olusturulabilir(self, db, user_factory, task_factory):
        """Rutin görev için period_key bazlı TaskOccurrence kaydı oluşturulabilir."""
        user = user_factory(username="to_u1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Sunucu güncellemesi gerçekleştir",
            category="routine",
            period="Aylık",
        )
        occ = TaskOccurrence(task_id=task.id, period_key="2026-03")
        db.session.add(occ)
        db.session.commit()

        fetched = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-03").first()
        assert fetched is not None

    def test_ayni_period_key_iki_kayit_unique_constraint_ihlali(self, db, user_factory, task_factory):
        """Aynı (task_id, period_key) için iki kayıt oluşturmak IntegrityError fırlatır."""
        user = user_factory(username="to_u2", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yığın yedekleme",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        db.session.commit()

        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_farkli_period_key_ayri_kayitlar_olusturulabilir(self, db, user_factory, task_factory):
        """Aynı görev için farklı period_key'ler bağımsız kayıt oluşturabilir."""
        user = user_factory(username="to_u3", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Şifre yenileme",
            category="routine",
            period="Aylık",
        )
        for m in ["2026-01", "2026-02", "2026-03", "2026-04"]:
            db.session.add(TaskOccurrence(task_id=task.id, period_key=m))
        db.session.commit()

        count = TaskOccurrence.query.filter_by(task_id=task.id).count()
        assert count == 4

    def test_task_silinince_occurrence_da_silinir_cascade(self, db, user_factory, task_factory):
        """Task silindiğinde ilişkili TaskOccurrence kayıtları cascade ile silinir."""
        user = user_factory(username="to_u5", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Bağlantı denetimi",
            category="routine",
            period="Haftalık",
        )
        task_id = task.id
        db.session.add(TaskOccurrence(task_id=task_id, period_key="2026-W10"))
        db.session.add(TaskOccurrence(task_id=task_id, period_key="2026-W11"))
        db.session.commit()

        db.session.delete(task)
        db.session.commit()

        orphan_count = TaskOccurrence.query.filter_by(task_id=task_id).count()
        assert orphan_count == 0, "Task silinince TaskOccurrence'lar da silinmeli"

    def test_occurrence_completed_at_timestamp_kaydedilir(self, db, user_factory, task_factory):
        """TaskOccurrence kaydı oluştuğunda completed_at timestamp'i otomatik set edilir."""
        user = user_factory(username="to_u6", firm="inventist")
        task = task_factory(user_id=user.id, category="routine", period="Aylık")
        before = datetime.utcnow()
        occ = TaskOccurrence(task_id=task.id, period_key="2026-05")
        db.session.add(occ)
        db.session.commit()
        after = datetime.utcnow()

        fetched = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-05").first()
        assert fetched.completed_at is not None
        assert before <= fetched.completed_at <= after

    def test_task_completion_alias_calisir(self, db, user_factory, task_factory):
        """TaskCompletion = TaskOccurrence alias'ı — eski import'lar için geriye dönük uyumluluk."""
        user = user_factory(username="to_alias", firm="inventist")
        task = task_factory(user_id=user.id, category="routine", period="Aylık")
        # TaskCompletion alias üzerinden oluştur
        occ = TaskCompletion(task_id=task.id, period_key="2026-06")
        db.session.add(occ)
        db.session.commit()
        assert TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-06").first() is not None


class TestTaskOccurrenceToDict:
    """Task.to_dict() rutin görevlerde period_key bazlı is_done davranışı."""

    def test_mart_tamamlanan_rutin_mart_done_nisan_pending(self, db, user_factory, task_factory):
        """
        Kritik iş kuralı: Rutin görev Mart'ta tamamlanırsa
        - Mart görünümünde is_done=True (period_key='2026-03')
        - Nisan görünümünde is_done=False (period_key='2026-04' kaydı yok)
        """
        user = user_factory(username="to_u7", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Sunucu güncellemesi gerçekleştir",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        db.session.commit()

        mart_dict = task.to_dict(month=3, year=2026)
        nisan_dict = task.to_dict(month=4, year=2026)

        assert mart_dict["is_done"] is True, "Mart'ta tamamlanan görev Mart görünümünde done olmalı"
        assert nisan_dict["is_done"] is False, "Mart'ta tamamlanan görev Nisan görünümünde pending olmalı"

    def test_rutin_gorev_task_is_done_flag_kullanmaz(self, db, user_factory, task_factory):
        """
        Kritik: Task.is_done=True olsa bile, rutin görev için to_dict()
        ilgili period_key'de TaskOccurrence yoksa is_done=False döner.
        """
        user = user_factory(username="to_u8", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Çağrı merkezi günlük kontrol",
            category="routine",
            period="Aylık",
            is_done=True,  # Flag True ama TaskOccurrence kaydı yok
        )

        sonuc = task.to_dict(month=4, year=2026)
        assert sonuc["is_done"] is False, (
            "Rutin görev için is_done Task.is_done flag'inden değil "
            "TaskOccurrence kaydından okunmalı"
        )

    def test_completion_olmadan_ay_bazli_is_done_false(self, db, user_factory, task_factory):
        """TaskOccurrence kaydı olmayan rutin görev her ay pending görünür."""
        user = user_factory(username="to_u9", firm="inventist")
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
        user = user_factory(username="to_u10", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Aylık rapor hazırlama",
            category="routine",
            period="Aylık",
        )
        # Ocak, Şubat, Mart tamamlandı; Nisan tamamlanmadı
        for pk in ["2026-01", "2026-02", "2026-03"]:
            db.session.add(TaskOccurrence(task_id=task.id, period_key=pk))
        db.session.commit()

        for month in [1, 2, 3]:
            assert task.to_dict(month=month, year=2026)["is_done"] is True
        assert task.to_dict(month=4, year=2026)["is_done"] is False

    def test_tek_seferlik_rutin_is_done_flag_kullanir(self, db, user_factory, task_factory):
        """period='Tek Seferlik' olan rutin görev is_done flag'ini kullanır (TaskOccurrence değil)."""
        user = user_factory(username="to_u11", firm="assos")
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
        """
        Yıllık periyot için period_key izolasyonu: 2026 ve 2027 ayrı string'ler.
        2026 yılında tamamlanan yıllık görev 2027'de pending görünür.
        """
        user = user_factory(username="to_u12", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yıl sonu sunucu denetimi",
            category="routine",
            period="Yıllık",
        )
        # 2026 yılı tamamlaması — period_key="2026"
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026"))
        db.session.commit()

        # to_dict(month=X, year=Y) ile is_done_now(date(year, month, 15)) çalışır
        # 2026 için ref_dt = date(2026, 6, 15) → _period_key("Yıllık", ...) = "2026"
        aralik_2026 = task.to_dict(month=6, year=2026)
        ocak_2027 = task.to_dict(month=1, year=2027)

        assert aralik_2026["is_done"] is True, "2026 yılında tamamlanmış, done olmalı"
        assert ocak_2027["is_done"] is False, "2027 için occurrence yok, pending olmalı"


class TestTaskOccurrenceAPIEndpoint:
    """PATCH /api/tasks/:id — yeni kontrat: server date.today() kullanır (Karar 2=B)."""

    @freeze_time("2026-04-29")
    def test_patch_is_done_true_occurrence_olusturur(self, db, client, user_factory, task_factory, login_as):
        """PATCH is_done=true → bugünün period_key ile TaskOccurrence kaydı oluşturulur."""
        user = user_factory(username="api_to1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="API testi rutin görev",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        resp = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True},
            content_type="application/json",
        )
        assert resp.status_code == 200
        # Bugün = 2026-04-29, aylık period_key = "2026-04"
        occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").first()
        assert occ is not None, "period_key='2026-04' TaskOccurrence kaydı oluşturulmuş olmalı"

    @freeze_time("2026-04-29")
    def test_patch_is_done_false_occurrence_siler(self, db, client, user_factory, task_factory, login_as):
        """PATCH is_done=false → bugünün period_key'ine ait TaskOccurrence kaydı silinir."""
        user = user_factory(username="api_to2", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Tamamlanmış rutin görev",
            category="routine",
            period="Aylık",
        )
        # Bugün = 2026-04-29 → period_key = "2026-04"
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-04", completed_by=user.id))
        db.session.commit()

        login_as(user)
        resp = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": False},
            content_type="application/json",
        )
        assert resp.status_code == 200
        occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").first()
        assert occ is None, "TaskOccurrence kaydı silinmiş olmalı"

    @freeze_time("2026-04-29")
    def test_patch_month_year_parametreleri_ignore_edilir(self, db, client, user_factory, task_factory, login_as):
        """
        Karar 2 = B doğrulaması: Frontend month=3, year=2025 göndermiş olsa bile
        server date.today() (2026-04) kullanır; Mart 2025 kaydı oluşmaz.
        """
        user = user_factory(username="api_to3", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Eski ay parametresi testi",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        resp = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True, "month": 3, "year": 2025},
            content_type="application/json",
        )
        assert resp.status_code == 200
        # Eski kontrat: month/year parametresi ile kayıt oluşurdu → artık 2026-04 olmalı
        old_key_occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2025-03").first()
        new_key_occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").first()
        assert old_key_occ is None, "Eski month/year param ignore edilmeli — 2025-03 kaydı yok"
        assert new_key_occ is not None, "Server date.today() ile 2026-04 kaydı oluşmalı"

    @freeze_time("2026-04-29")
    def test_patch_rutin_toggle_idempotent(self, db, client, user_factory, task_factory, login_as):
        """Aynı rutin görev için is_done=true iki kez çağrılırsa ikinci çağrı hata vermez."""
        user = user_factory(username="api_to4", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="İdempotent toggle testi",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        resp1 = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True},
            content_type="application/json",
        )
        resp2 = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True},
            content_type="application/json",
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        count = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").count()
        assert count == 1, "İdempotent: aynı period_key için tek kayıt olmalı"

    @freeze_time("2026-04-29")
    def test_patch_completion_completed_by_set_eder(self, db, client, user_factory, task_factory, login_as):
        """PATCH is_done=true → TaskOccurrence.completed_by = oturumdaki kullanıcı."""
        user = user_factory(username="api_to5", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Tamamlayan kullanıcı testi",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True},
            content_type="application/json",
        )

        occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").first()
        assert occ is not None
        assert occ.completed_by == user.id, "completed_by oturumdaki kullanıcı ID olmalı"

    @freeze_time("2026-04-29")
    def test_patch_rutin_tamamlama_response_is_done_true_doner(self, db, client, user_factory, task_factory, login_as):
        """Rutin görev tamamlandıktan sonra PATCH response'unda is_done=True gelir."""
        user = user_factory(username="api_to6", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Güvenlik politikası güncellemesi",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        resp = client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["is_done"] is True, "Response'da is_done=True olmalı"

    def test_patch_rutin_gorev_task_is_done_flag_degismez(self, db, client, user_factory, task_factory, login_as):
        """Rutin görev tamamlandığında Task.is_done flag'i True'ya set edilmez."""
        user = user_factory(username="api_to7", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Ağ cihazı kontrol",
            category="routine",
            period="Aylık",
        )
        login_as(user)

        client.patch(
            f"/api/tasks/{task.id}",
            json={"is_done": True},
            content_type="application/json",
        )

        from models.database import Task as TaskModel
        refreshed = db.session.get(TaskModel, task.id)
        assert refreshed.is_done is False, (
            "Rutin görevde Task.is_done flag'i güncellenmemeli; "
            "tamamlanma durumu yalnızca TaskOccurrence'dan okunur"
        )
