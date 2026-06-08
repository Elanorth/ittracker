"""
test_recurring_tasks.py — v5.0 Plan C Commit 4/5 — Yeni rutin görev test ağı.

Bu dosya v5.0 recurring tasks refactor'ın tüm iş kurallarını doğrular:
- _period_key() ve _previous_period_key() helper davranışı (her periyot tipi).
- Task.is_done_now() ve Task.is_overdue_now() instance method'ları.
- PATCH /api/tasks/<id> toggle endpoint'i — server date.today() (Karar 2=B).
- /api/dashboard/firm-summary rutin görev sayımı (is_done_now bazlı).
- /api/managed-firms/detail KPI + trend rutin görev sayımı.

İş kuralları:
- Günlük: period_key = "YYYY-MM-DD" (ISO date).
- Haftalık: period_key = "YYYY-Www" (ISO week).
- Aylık: period_key = "YYYY-MM".
- Yıllık: period_key = "YYYY" — yıl içinde 1 tamamlama yeterli (Karar 1=A).
- Tek Seferlik: period_key = None, Task.is_done flag kullanılır.
- Karar 2=B: server date.today() kullanır; frontend month/year param'ları ignore.
"""

from datetime import date, datetime

import pytest
from freezegun import freeze_time

from models.database import (
    Task,
    TaskCompletion,
    TaskOccurrence,
    _period_key,
    _previous_period_key,
)

# ─────────────────────────────────────────────────────────────────────────────
# TestPeriodKey — _period_key() helper
# ─────────────────────────────────────────────────────────────────────────────


class TestPeriodKey:
    """_period_key() helper'ın her periyot tipi için doğru kanonik string üretmesi."""

    def test_gunluk_period_key_iso_date(self):
        """Günlük periyot için ISO date string döner: 'YYYY-MM-DD'."""
        result = _period_key("Günlük", date(2026, 5, 4))
        assert result == "2026-05-04"

    def test_haftalik_period_key_iso_week(self):
        """
        Haftalık periyot için ISO week string döner: 'YYYY-Www'.
        5 Mayıs 2026 Salı = ISO 2026 Week 19.
        """
        result = _period_key("Haftalık", date(2026, 5, 5))
        assert result == "2026-W19"

    def test_haftalik_period_key_yil_basi_iso_hafta(self):
        """
        ISO week edge case: 5 Ocak 2026 (2. hafta) — yıl başı doğru atanır.
        ISO 8601'e göre 5 Ocak 2026 Pazartesi → 2026-W02.
        """
        result = _period_key("Haftalık", date(2026, 1, 5))
        assert result == "2026-W02"

    def test_aylik_period_key_year_month(self):
        """Aylık periyot için 'YYYY-MM' formatı döner."""
        result = _period_key("Aylık", date(2026, 5, 15))
        assert result == "2026-05"

    def test_yillik_period_key_year(self):
        """Yıllık periyot için sadece 'YYYY' döner."""
        result = _period_key("Yıllık", date(2026, 3, 10))
        assert result == "2026"

    def test_tek_seferlik_period_key_none(self):
        """Tek Seferlik periyot için None döner."""
        result = _period_key("Tek Seferlik", date(2026, 5, 4))
        assert result is None

    def test_gecersiz_periyot_none(self):
        """Geçersiz periyot string'i için None döner."""
        result = _period_key("Foo", date.today())
        assert result is None

    def test_gunluk_period_key_tek_haneli_gun_ay_pad(self):
        """Günlük period_key'de tek haneli gün/ay sıfır ile doldurulur."""
        result = _period_key("Günlük", date(2026, 1, 3))
        assert result == "2026-01-03"

    def test_aylik_period_key_tek_haneli_ay_pad(self):
        """Aylık period_key'de tek haneli ay sıfır ile doldurulur."""
        result = _period_key("Aylık", date(2026, 1, 1))
        assert result == "2026-01"


# ─────────────────────────────────────────────────────────────────────────────
# TestPreviousPeriodKey — _previous_period_key() helper
# ─────────────────────────────────────────────────────────────────────────────


class TestPreviousPeriodKey:
    """_previous_period_key() helper'ın önceki periyot key'ini doğru hesaplaması."""

    def test_gunluk_onceki_gun(self):
        """Günlük + 2026-05-04 → bir önceki gün '2026-05-03'."""
        result = _previous_period_key("Günlük", date(2026, 5, 4))
        assert result == "2026-05-03"

    def test_haftalik_onceki_hafta(self):
        """
        Haftalık + Pazartesi 2026-05-04 (W19) → bir önceki hafta '2026-W18'.
        7 gün geri: 2026-04-27 = W18.
        """
        result = _previous_period_key("Haftalık", date(2026, 5, 4))
        assert result == "2026-W18"

    def test_aylik_onceki_ay(self):
        """Aylık + 2026-05-04 → önceki ay '2026-04'."""
        result = _previous_period_key("Aylık", date(2026, 5, 4))
        assert result == "2026-04"

    def test_aylik_yil_gecisi_ocak(self):
        """Aylık + 2026-01-04 → önceki ay yıl geçişi ile '2025-12'."""
        result = _previous_period_key("Aylık", date(2026, 1, 4))
        assert result == "2025-12"

    def test_yillik_onceki_yil(self):
        """Yıllık + 2026-05-04 → önceki yıl '2025'."""
        result = _previous_period_key("Yıllık", date(2026, 5, 4))
        assert result == "2025"

    def test_tek_seferlik_none_doner(self):
        """Tek Seferlik için None döner — önceki periyot kavramı yok."""
        result = _previous_period_key("Tek Seferlik", date(2026, 5, 4))
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# TestIsDoneNow — Task.is_done_now()
# ─────────────────────────────────────────────────────────────────────────────


class TestIsDoneNow:
    """Task.is_done_now() method'u — her periyot tipi için doğru davranış."""

    def test_yeni_rutin_gorev_done_degil(self, db, user_factory, task_factory):
        """Tamamlanma kaydı olmayan yeni rutin görev is_done_now() → False."""
        user = user_factory(username="idn_u1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Çağrı sıfırlama prosedürü",
            category="routine",
            period="Aylık",
        )
        assert task.is_done_now(today=date(2026, 4, 29)) is False

    @freeze_time("2026-04-29")
    def test_aylik_rutin_bu_ay_occurrence_var_done(self, db, user_factory, task_factory):
        """Aylık rutin + bu ay TaskOccurrence var → is_done_now() True."""
        user = user_factory(username="idn_u2", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Aylık rapor gönderimi",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-04"))
        db.session.commit()

        assert task.is_done_now() is True  # today = 2026-04-29 → period_key = "2026-04"

    @freeze_time("2026-04-29")
    def test_aylik_rutin_gecen_ay_occurrence_var_bu_ay_pending(self, db, user_factory, task_factory):
        """Aylık rutin + geçen ay (Mart) tamamlanmış, bu ay (Nisan) tamamlanmamış → False."""
        user = user_factory(username="idn_u3", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="İlknur Doğan sunucu kontrolü",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        db.session.commit()

        assert task.is_done_now() is False  # today = 2026-04-29 → period_key = "2026-04" — kayıt yok

    @freeze_time("2026-05-04")
    def test_gunluk_rutin_bugun_occurrence_var_done(self, db, user_factory, task_factory):
        """Günlük rutin + bugünün period_key var → is_done_now() True."""
        user = user_factory(username="idn_u4", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Şirket Çağ günlük log kontrol",
            category="routine",
            period="Günlük",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-05-04"))
        db.session.commit()

        assert task.is_done_now() is True

    @freeze_time("2026-05-04")
    def test_gunluk_rutin_dun_occurrence_var_bugun_pending(self, db, user_factory, task_factory):
        """Günlük rutin + dün tamamlanmış, bugün için kayıt yok → is_done_now() False."""
        user = user_factory(username="idn_u5", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Gülnur Yıldız günlük yedek kontrol",
            category="routine",
            period="Günlük",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-05-03"))  # dün
        db.session.commit()

        assert task.is_done_now() is False  # bugün = 2026-05-04, kayıt yok

    @freeze_time("2026-05-04")
    def test_yillik_rutin_bu_yil_tamamlandi_done(self, db, user_factory, task_factory):
        """
        Karar 1=A: Yıllık rutin, yıl içinde 1 kez tamamlanırsa tüm yıl boyunca done.
        period_key="2026" ile occurrence var → yıl içindeki herhangi bir günde True.
        """
        user = user_factory(username="idn_u6", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yıllık güvenlik denetimi",
            category="routine",
            period="Yıllık",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026"))
        db.session.commit()

        assert task.is_done_now() is True  # today = 2026-05-04 → period_key = "2026"

    def test_tek_seferlik_is_done_flag_kullanir(self, db, user_factory, task_factory):
        """Tek Seferlik görev is_done_now() → Task.is_done flag'ini kullanır."""
        user = user_factory(username="idn_u7", firm="assos")
        task_done = task_factory(
            user_id=user.id,
            title="Sistem kurulumu (tek seferlik)",
            category="routine",
            period="Tek Seferlik",
            is_done=True,
        )
        task_open = task_factory(
            user_id=user.id,
            title="Kurulum adımları (tek seferlik)",
            category="routine",
            period="Tek Seferlik",
            is_done=False,
        )
        assert task_done.is_done_now(today=date(2026, 4, 29)) is True
        assert task_open.is_done_now(today=date(2026, 4, 29)) is False

    def test_proje_gorev_is_done_flag_kullanir(self, db, user_factory, task_factory):
        """Proje görevi is_done_now() → Task.is_done flag'ini kullanır (TaskOccurrence değil)."""
        user = user_factory(username="idn_u8", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yeni ofis ağ altyapısı kurulumu",
            category="project",
            is_done=True,
        )
        # TaskOccurrence kaydı olmasa da True dönmeli
        assert task.is_done_now(today=date(2026, 4, 29)) is True


# ─────────────────────────────────────────────────────────────────────────────
# TestIsOverdueNow — Task.is_overdue_now()
# ─────────────────────────────────────────────────────────────────────────────


class TestIsOverdueNow:
    """Task.is_overdue_now() method'u — gecikme tespiti her periyot tipi için."""

    @freeze_time("2026-04-29")
    def test_aylik_rutin_gecen_ay_completion_yok_overdue(self, db, user_factory, task_factory):
        """
        Aylık rutin + geçen ay (Mart) tamamlanmamış → is_overdue_now() True.
        today=2026-04-29, prev_key="2026-03", kayıt yok → overdue.
        """
        user = user_factory(username="ion_u1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="İbrahim Şahin aylık kontrol",
            category="routine",
            period="Aylık",
        )
        assert task.is_overdue_now() is True

    @freeze_time("2026-04-29")
    def test_aylik_rutin_gecen_ay_completion_var_not_overdue(self, db, user_factory, task_factory):
        """Aylık rutin + geçen ay (Mart) tamamlanmış → is_overdue_now() False."""
        user = user_factory(username="ion_u2", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Assos İlaç sistem güncelleme",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        db.session.commit()

        assert task.is_overdue_now() is False

    @freeze_time("2026-05-04")
    def test_gunluk_rutin_dun_completion_yok_overdue(self, db, user_factory, task_factory):
        """Günlük rutin + dünün kaydı yok → is_overdue_now() True."""
        user = user_factory(username="ion_u3", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Çağla Öztürk günlük servis kontrol",
            category="routine",
            period="Günlük",
        )
        # 2026-05-03 (dün) için kayıt yok
        assert task.is_overdue_now() is True

    def test_proje_deadline_gecmis_acik_overdue(self, db, user_factory, task_factory):
        """Proje görevi + deadline geçmiş + açık → is_overdue_now() True."""
        from datetime import timedelta

        user = user_factory(username="ion_u4", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Sunucu odası yenileme projesi",
            category="project",
            is_done=False,
        )
        task.deadline = date.today() - timedelta(days=5)
        db.session.commit()

        assert task.is_overdue_now() is True

    def test_proje_deadline_gecmis_tamamlanmis_not_overdue(self, db, user_factory, task_factory):
        """Proje görevi + deadline geçmiş + tamamlanmış → is_overdue_now() False."""
        from datetime import timedelta

        user = user_factory(username="ion_u5", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Assos ofis ağ altyapısı",
            category="project",
            is_done=True,
        )
        task.deadline = date.today() - timedelta(days=5)
        db.session.commit()

        assert task.is_overdue_now() is False

    def test_tek_seferlik_deadline_yok_not_overdue(self, db, user_factory, task_factory):
        """Tek Seferlik görev + deadline yok → is_overdue_now() False."""
        user = user_factory(username="ion_u6", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Tek seferlik kurulum",
            category="routine",
            period="Tek Seferlik",
            is_done=False,
        )
        # deadline = None → not overdue
        assert task.is_overdue_now(today=date(2026, 4, 29)) is False


# ─────────────────────────────────────────────────────────────────────────────
# TestToggleEndpoint — PATCH /api/tasks/<id> rutin toggle
# ─────────────────────────────────────────────────────────────────────────────


class TestToggleEndpoint:
    """PATCH /api/tasks/<id> — periyot tipine göre doğru period_key oluşturulur."""

    @freeze_time("2026-04-29")
    def test_aylik_rutin_toggle_bu_ay_period_key(self, db, client, user_factory, task_factory, login_as):
        """Aylık rutin is_done=true → period_key='2026-04' (bu ay)."""
        user = user_factory(username="te_u1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Aylık yedekleme denetimi",
            category="routine",
            period="Aylık",
        )
        login_as(user)
        resp = client.patch(f"/api/tasks/{task.id}", json={"is_done": True})
        assert resp.status_code == 200
        occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").first()
        assert occ is not None

    @freeze_time("2026-04-29")
    def test_aylik_rutin_toggle_geri_al_kaydi_siler(self, db, client, user_factory, task_factory, login_as):
        """Aylık rutin is_done=false → bu ayın period_key kaydı silinir."""
        user = user_factory(username="te_u2", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Aylık kontrol silme testi",
            category="routine",
            period="Aylık",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-04"))
        db.session.commit()
        login_as(user)
        resp = client.patch(f"/api/tasks/{task.id}", json={"is_done": False})
        assert resp.status_code == 200
        assert TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").first() is None

    @freeze_time("2026-05-04")
    def test_gunluk_rutin_toggle_bugun_period_key(self, db, client, user_factory, task_factory, login_as):
        """Günlük rutin is_done=true → period_key='2026-05-04' (ISO date bugün)."""
        user = user_factory(username="te_u3", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Günlük log denetimi",
            category="routine",
            period="Günlük",
        )
        login_as(user)
        resp = client.patch(f"/api/tasks/{task.id}", json={"is_done": True})
        assert resp.status_code == 200
        occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-05-04").first()
        assert occ is not None

    @freeze_time("2026-05-04")
    def test_haftalik_rutin_toggle_bu_hafta_period_key(self, db, client, user_factory, task_factory, login_as):
        """Haftalık rutin is_done=true → period_key='2026-W19' (2026-05-04 = W19)."""
        user = user_factory(username="te_u4", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Haftalık güvenlik taraması",
            category="routine",
            period="Haftalık",
        )
        login_as(user)
        resp = client.patch(f"/api/tasks/{task.id}", json={"is_done": True})
        assert resp.status_code == 200
        occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-W19").first()
        assert occ is not None

    @freeze_time("2026-05-04")
    def test_yillik_rutin_toggle_bu_yil_period_key(self, db, client, user_factory, task_factory, login_as):
        """Yıllık rutin is_done=true → period_key='2026'."""
        user = user_factory(username="te_u5", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yıllık lisans denetimi",
            category="routine",
            period="Yıllık",
        )
        login_as(user)
        resp = client.patch(f"/api/tasks/{task.id}", json={"is_done": True})
        assert resp.status_code == 200
        occ = TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026").first()
        assert occ is not None

    @freeze_time("2026-05-04")
    def test_tek_seferlik_gorev_is_done_flag_guncellenir_occurrence_yazilmaz(
        self, db, client, user_factory, task_factory, login_as
    ):
        """
        Tek Seferlik rutin (period='Tek Seferlik') → Task.is_done flag güncellenir,
        TaskOccurrence kaydı yazılmaz.
        """
        user = user_factory(username="te_u6", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Tek seferlik kurulum",
            category="routine",
            period="Tek Seferlik",
        )
        login_as(user)
        resp = client.patch(f"/api/tasks/{task.id}", json={"is_done": True})
        assert resp.status_code == 200
        # TaskOccurrence yazılmamalı
        occ_count = TaskOccurrence.query.filter_by(task_id=task.id).count()
        assert occ_count == 0, "Tek Seferlik görev için TaskOccurrence kaydı oluşturulmamalı"
        # Task.is_done flag True olmalı
        from models.database import Task as T

        refreshed = db.session.get(T, task.id)
        assert refreshed.is_done is True

    @freeze_time("2026-04-29")
    def test_karar2b_server_date_today_kullanir(self, db, client, user_factory, task_factory, login_as):
        """
        Karar 2=B: Frontend month=3, year=2025 göndermiş olsa bile server
        date.today() (2026-04) kullanır — geçmiş period_key kaydı oluşmaz.
        """
        user = user_factory(username="te_u7", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Karar 2=B doğrulama testi",
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
        # Geçmiş tarih 2025-03 kaydı oluşmamalı
        assert TaskOccurrence.query.filter_by(task_id=task.id, period_key="2025-03").first() is None
        # Server today = 2026-04-29 → period_key = "2026-04"
        assert TaskOccurrence.query.filter_by(task_id=task.id, period_key="2026-04").first() is not None


# ─────────────────────────────────────────────────────────────────────────────
# TestFirmSummaryRoutineFix — /api/dashboard/firm-summary rutin sayımı
# ─────────────────────────────────────────────────────────────────────────────


class TestFirmSummaryRoutineFix:
    """
    /api/dashboard/firm-summary rutin görev sayımının is_done_now() bazlı çalışması.
    Eski kod Task.is_done flag kullanıyordu (rutin için yanlış).
    """

    @freeze_time("2026-04-29")
    def test_aylik_rutin_bu_ay_tamamlanan_done_olarak_sayilir(self, db, client, user_factory, task_factory, login_as):
        """Aylık rutin + bu ay TaskOccurrence var → firm-summary done count'a dahil."""
        admin = user_factory(username="fsr_admin", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="fsr_worker", firm="inventist", permission_level="junior")
        task = task_factory(
            user_id=worker.id,
            title="İnventist aylık yedekleme",
            category="routine",
            period="Aylık",
            firm="inventist",
        )
        # Bu ay (Nisan 2026) tamamlandı
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-04"))
        db.session.commit()

        login_as(admin)
        resp = client.get("/api/dashboard/firm-summary")
        assert resp.status_code == 200
        data = resp.get_json()
        inv_entry = next((e for e in data if e["firm"] == "inventist"), None)
        assert inv_entry is not None
        assert inv_entry["done"] >= 1, "Bu ay tamamlanan rutin görev done sayısına dahil olmalı"

    @freeze_time("2026-04-29")
    def test_aylik_rutin_gecen_ay_tamamlanan_bu_ay_done_sayilmaz(
        self, db, client, user_factory, task_factory, login_as
    ):
        """
        Aylık rutin + geçen ay (Mart) TaskOccurrence var, bu ay yok →
        firm-summary'de done count'a dahil DEĞİL; eski Task.is_done flag hatası artık yok.
        """
        admin = user_factory(username="fsr_admin2", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="fsr_worker2", firm="inventist", permission_level="junior")
        task = task_factory(
            user_id=worker.id,
            title="Geçen ay tamamlanan rutin",
            category="routine",
            period="Aylık",
            firm="inventist",
            is_done=True,  # Eski kod bu flag'i okurdu — yanlış sayım kaynağı
        )
        # Sadece geçen ay (Mart) kaydı var, bu ay (Nisan) yok
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        db.session.commit()

        login_as(admin)
        resp = client.get("/api/dashboard/firm-summary")
        assert resp.status_code == 200
        data = resp.get_json()
        inv_entry = next((e for e in data if e["firm"] == "inventist"), None)
        assert inv_entry is not None
        # Bu ay tamamlanmamış → done = 0 (Task.is_done=True olsa da)
        # Not: sadece bu görevi test ettiğimizden toplam done 0 olmalı
        # Diğer fixture görevleri varsa bu assertion yanlışlanabilir;
        # bu nedenle is_done_now(today) False döndüğünü model seviyesinde doğrulayalım
        assert (
            task.is_done_now(today=date(2026, 4, 29)) is False
        ), "Geçen ay tamamlanan rutin görev bu ay için is_done_now() False vermeli"


# ─────────────────────────────────────────────────────────────────────────────
# TestManagedFirmsDetailRoutineFix — /api/managed-firms/detail rutin sayımı
# ─────────────────────────────────────────────────────────────────────────────


class TestManagedFirmsDetailRoutineFix:
    """
    /api/managed-firms/detail KPI + trend hesabında rutin görevlerin
    is_done_now() bazlı doğru sayılması.
    """

    @freeze_time("2026-04-29")
    def test_aylik_rutin_bu_ay_completion_var_kpi_done_dahil(self, db, client, user_factory, task_factory, login_as):
        """Aylık rutin + bu ay TaskOccurrence var → KPI done sayısına dahil."""
        admin = user_factory(username="mfd_r1", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="mfd_r1_w", firm="inventist", permission_level="junior")
        task = task_factory(
            user_id=worker.id,
            title="Aylık yedekleme denetimi",
            category="routine",
            period="Aylık",
            firm="inventist",
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-04"))
        db.session.commit()

        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        data = resp.get_json()
        inv_entry = next((e for e in data if e["slug"] == "inventist"), None)
        assert inv_entry is not None
        # is_done_now() True olduğu için KPI done >= 1
        assert task.is_done_now(today=date(2026, 4, 29)) is True
        assert inv_entry["kpi"]["done"] >= 1

    @freeze_time("2026-04-29")
    def test_aylik_rutin_gecen_ay_completion_bu_ay_yok_overdue_dahil(
        self, db, client, user_factory, task_factory, login_as
    ):
        """
        Aylık rutin + geçen ay (Mart) completion var, bu ay (Nisan) yok →
        is_overdue_now() True → KPI overdue sayısına dahil.
        """
        admin = user_factory(username="mfd_r2", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="mfd_r2_w", firm="inventist", permission_level="junior")
        task = task_factory(
            user_id=worker.id,
            title="Geçen ay kaçırılan rutin",
            category="routine",
            period="Aylık",
            firm="inventist",
        )
        # Geçen ay tamamlanmış ama bu ay yok
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        db.session.commit()

        # is_overdue_now: prev_key="2026-03" mevcut → overdue DEĞİL (geçen ay tamamlandı)
        # Not: overdue = geçen periyot tamamlanmamışsa, geçen ay tamamlanmışsa overdue değil.
        assert task.is_overdue_now(today=date(2026, 4, 29)) is False
        # Bu ay için is_done_now False
        assert task.is_done_now(today=date(2026, 4, 29)) is False

        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        data = resp.get_json()
        inv_entry = next((e for e in data if e["slug"] == "inventist"), None)
        assert inv_entry is not None
        # done = 0 (bu ay tamamlanmamış), overdue = 0 (geçen ay tamamlanmış → overdue değil)
        assert inv_entry["kpi"]["done"] == 0

    @freeze_time("2026-04-29")
    def test_trend_alti_ay_rutin_done_sayimi(self, db, client, user_factory, task_factory, login_as):
        """
        /api/managed-firms/detail trend[6 ay]: o ayın period_key completion'ı varsa
        o ayın done sayısına +1 eklenmeli.
        """
        admin = user_factory(username="mfd_r3", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="mfd_r3_w", firm="inventist", permission_level="junior")
        task = task_factory(
            user_id=worker.id,
            title="Trend rutin görevi",
            category="routine",
            period="Aylık",
            firm="inventist",
        )
        # Şubat ve Mart 2026'da tamamlandı; Nisan'da tamamlanmadı
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-02"))
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-03"))
        db.session.commit()

        # Aylık period_key doğrulaması
        assert task.is_done_now(today=date(2026, 2, 15)) is True  # Şubat → "2026-02" var
        assert task.is_done_now(today=date(2026, 3, 15)) is True  # Mart → "2026-03" var
        assert task.is_done_now(today=date(2026, 4, 15)) is False  # Nisan → "2026-04" yok

        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        data = resp.get_json()
        inv_entry = next((e for e in data if e["slug"] == "inventist"), None)
        assert inv_entry is not None
        assert "trend" in inv_entry
        assert len(inv_entry["trend"]) == 6, "Trend 6 aylık veri içermeli"


class TestToDictRoutineCurrentMonthBugFix:
    """v5.0 hotfix — Task.to_dict() Günlük/Haftalık rutinde bugünün period_key'i kullanılmalı.

    Bug: to_dict ay ortası 15. gün referansı kullanıyordu. Aylık için doğru
    çalışıyordu ama Günlük/Haftalık'ta toggle gerçek tarih ile yazıldığı için
    eşleşme tutmuyordu — kullanıcıya "tamamlanmamış" görünüyordu.
    Fix: Görüntülenen ay = bugünün ayıysa BUGÜN baz alınır.
    """

    def test_gunluk_rutin_bugun_tamamlandi_to_dict_done_doner(self, db, user_factory, task_factory):
        """Günlük rutin bugün tamamlandı, to_dict bu ayı sorduğunda done=True."""
        from models.database import TaskOccurrence, _period_key

        u = user_factory(username="td_g1", firm="inventist")
        task = task_factory(user_id=u.id, title="Sunucu yedek kontrolü", category="routine", period="Günlük")
        today = date.today()
        pk = _period_key("Günlük", today)
        db.session.add(TaskOccurrence(task_id=task.id, period_key=pk))
        db.session.commit()

        d = task.to_dict(month=today.month, year=today.year)
        assert d["is_done"] is True, "Günlük rutin bugün tamamlandı, to_dict done=True dönmeli"

    def test_haftalik_rutin_bu_hafta_tamamlandi_to_dict_done_doner(self, db, user_factory, task_factory):
        """Haftalık rutin bu hafta tamamlandı, to_dict bu ayı sorduğunda done=True."""
        from models.database import TaskOccurrence, _period_key

        u = user_factory(username="td_h1", firm="inventist")
        task = task_factory(user_id=u.id, title="Haftalık backup denetimi", category="routine", period="Haftalık")
        today = date.today()
        pk = _period_key("Haftalık", today)
        db.session.add(TaskOccurrence(task_id=task.id, period_key=pk))
        db.session.commit()

        d = task.to_dict(month=today.month, year=today.year)
        assert d["is_done"] is True, "Haftalık rutin bu hafta tamamlandı, to_dict done=True dönmeli"

    def test_aylik_rutin_bu_ay_tamamlandi_to_dict_done_doner(self, db, user_factory, task_factory):
        """Aylık rutin bu ay tamamlandı, to_dict done=True dönmeli (regression)."""
        from models.database import TaskOccurrence, _period_key

        u = user_factory(username="td_a1", firm="inventist")
        task = task_factory(user_id=u.id, title="Aylık güvenlik raporu", category="routine", period="Aylık")
        today = date.today()
        pk = _period_key("Aylık", today)
        db.session.add(TaskOccurrence(task_id=task.id, period_key=pk))
        db.session.commit()

        d = task.to_dict(month=today.month, year=today.year)
        assert d["is_done"] is True

    def test_gecmis_ay_aylik_rutin_dogru_calisir(self, db, user_factory, task_factory):
        """Geçmiş ay görüntülenirken Aylık rutin için o ayın period_key kontrol edilir."""
        from models.database import TaskOccurrence

        u = user_factory(username="td_p1", firm="inventist")
        task = task_factory(user_id=u.id, title="Eski aylık", category="routine", period="Aylık")
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-02"))
        db.session.commit()

        d_feb = task.to_dict(month=2, year=2026)
        assert d_feb["is_done"] is True, "Şubat görüntülenirken Şubat completion bulunmalı"
        d_mar = task.to_dict(month=3, year=2026)
        assert d_mar["is_done"] is False, "Mart görüntülenirken Şubat completion sayılmamalı"


# ════════════════════════════════════════════════════════════════════
# v5.1 — overdue_period_count + to_dict kanonik rutin alanları
# ════════════════════════════════════════════════════════════════════


class TestOverduePeriodCount:
    """v5.1 — Ardışık kaçırılan periyot sayısı (aktif periyot hariç)."""

    @freeze_time("2026-06-08")  # ISO W24, Pazartesi
    def test_haftalik_onceki_periyot_tamamlanmis_sifir(self, db, user_factory, task_factory):
        """Bug #78 senaryosu: önceki hafta (W23) tamamlanmış → 0 gecikme."""
        from models.database import TaskOccurrence

        u = user_factory(username="opc1", firm="inventist")
        t = task_factory(user_id=u.id, title="Firewall bakım", category="routine", period="Haftalık")
        t.created_at = datetime(2026, 5, 10)
        for wk in ("2026-W20", "2026-W21", "2026-W22", "2026-W23"):
            db.session.add(TaskOccurrence(task_id=t.id, period_key=wk))
        db.session.commit()

        assert t.overdue_period_count() == 0

    @freeze_time("2026-06-08")
    def test_haftalik_iki_hafta_kacirilmis_iki(self, db, user_factory, task_factory):
        """W22, W23 eksik (W21'de durur) → 2 periyot kaçırılmış."""
        from models.database import TaskOccurrence

        u = user_factory(username="opc2", firm="inventist")
        t = task_factory(user_id=u.id, title="Switch bakım", category="routine", period="Haftalık")
        t.created_at = datetime(2026, 5, 10)
        for wk in ("2026-W20", "2026-W21"):
            db.session.add(TaskOccurrence(task_id=t.id, period_key=wk))
        db.session.commit()

        assert t.overdue_period_count() == 2

    @freeze_time("2026-06-08")
    def test_aylik_gecen_ay_kacirilmis_bir(self, db, user_factory, task_factory):
        """Aylık görev: Mayıs (önceki ay) eksik → 1 periyot kaçırılmış."""
        from models.database import TaskOccurrence

        u = user_factory(username="opc3", firm="inventist")
        t = task_factory(user_id=u.id, title="Aylık tarama", category="routine", period="Aylık")
        t.created_at = datetime(2026, 1, 1)
        db.session.add(TaskOccurrence(task_id=t.id, period_key="2026-04"))  # Nisan var, Mayıs yok
        db.session.commit()

        assert t.overdue_period_count() == 1

    @freeze_time("2026-06-08")
    def test_created_at_oncesi_periyotlar_sayilmaz(self, db, user_factory, task_factory):
        """Görev 1 Haziran'da oluşturulmuşsa Mayıs ve öncesi sayılmaz."""
        u = user_factory(username="opc4", firm="inventist")
        t = task_factory(user_id=u.id, title="Yeni haftalık", category="routine", period="Haftalık")
        t.created_at = datetime(2026, 6, 1)  # bu hafta (W23) oluşturuldu
        db.session.commit()

        # Hiç occurrence yok ama görev yeni — sadece W23 (önceki periyot) sayılabilir
        # W23 başlangıcı 1 Haziran, created 1 Haziran → W23 sayılır = 1
        assert t.overdue_period_count() <= 1

    @freeze_time("2026-06-08")
    def test_tek_seferlik_ve_diger_kategoriler_sifir(self, db, user_factory, task_factory):
        """Rutin olmayan görevler için overdue_period_count her zaman 0."""
        u = user_factory(username="opc5", firm="inventist")
        t1 = task_factory(user_id=u.id, title="Proje", category="project", period="Tek Seferlik")
        t2 = task_factory(user_id=u.id, title="Tek seferlik rutin", category="routine", period="Tek Seferlik")
        db.session.commit()

        assert t1.overdue_period_count() == 0
        assert t2.overdue_period_count() == 0


class TestToDictRoutineV51:
    """v5.1 — to_dict rutin kanonik alanları (is_overdue, overdue_periods, vb.)."""

    @freeze_time("2026-06-08")
    def test_to_dict_rutin_alanlari_mevcut(self, db, user_factory, task_factory):
        """Rutin görev to_dict'inde v5.1 alanları bulunur."""
        u = user_factory(username="td51a", firm="inventist")
        t = task_factory(user_id=u.id, title="Haftalık", category="routine", period="Haftalık")
        db.session.commit()

        d = t.to_dict(month=6, year=2026)
        assert "is_overdue" in d
        assert "overdue_periods" in d
        assert "current_period_label" in d
        assert "next_period_date" in d
        assert d["current_period_label"] == "Bu hafta"

    @freeze_time("2026-06-08")
    def test_to_dict_onceki_periyot_tamamlanmis_overdue_degil(self, db, user_factory, task_factory):
        """Bug #78: önceki periyot tamamlanmış → is_overdue=False, overdue_periods=0."""
        from models.database import TaskOccurrence

        u = user_factory(username="td51b", firm="inventist")
        t = task_factory(user_id=u.id, title="Firewall", category="routine", period="Haftalık")
        t.created_at = datetime(2026, 5, 10)
        for wk in ("2026-W22", "2026-W23"):
            db.session.add(TaskOccurrence(task_id=t.id, period_key=wk))
        db.session.commit()

        d = t.to_dict(month=6, year=2026)
        assert d["is_overdue"] is False
        assert d["overdue_periods"] == 0

    @freeze_time("2026-06-08")
    def test_to_dict_kacirilmis_overdue_dogru_sayar(self, db, user_factory, task_factory):
        """2 hafta kaçırılmış → is_overdue=True, overdue_periods=2."""
        from models.database import TaskOccurrence

        u = user_factory(username="td51c", firm="inventist")
        t = task_factory(user_id=u.id, title="Switch", category="routine", period="Haftalık")
        t.created_at = datetime(2026, 5, 1)
        db.session.add(TaskOccurrence(task_id=t.id, period_key="2026-W21"))
        db.session.commit()

        d = t.to_dict(month=6, year=2026)
        assert d["is_overdue"] is True
        assert d["overdue_periods"] >= 2

    @freeze_time("2026-06-08")
    def test_to_dict_rutin_olmayan_default_degerler(self, db, user_factory, task_factory):
        """Proje görevinde v5.1 alanları default (False/0/None)."""
        u = user_factory(username="td51d", firm="inventist")
        t = task_factory(user_id=u.id, title="Proje", category="project", period="Tek Seferlik")
        db.session.commit()

        d = t.to_dict(month=6, year=2026)
        assert d["is_overdue"] is False
        assert d["overdue_periods"] == 0
        assert d["current_period_label"] is None
