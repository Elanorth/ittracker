"""
test_sla_no_deadline.py — v5.37

İş kuralı: Destek talepleri (category='support') için manuel bitiş tarihi
(deadline) TUTULMAZ. Bitiş, önceliğe göre SLA'dan otomatik hesaplanır ve
gecikme (is_overdue_now / GECİKEN KPI) TEK KAYNAK olarak SLA breach'e bağlıdır.

Kapsam:
- create_task: category=support + deadline gönderilse bile task.deadline None
- update_task: support'a çevrilen / support olan görevde deadline temizlenir
- Task.is_overdue_now: support için SLA breach = gecikme (manuel deadline yok sayılır)
"""

from datetime import datetime

from freezegun import freeze_time

from models.database import Task


class TestCreateSupportNoDeadline:
    def test_deadline_gonderilse_bile_none(self, db, client, user_factory, login_as):
        u = user_factory(username="snd_c", firm="inventist", permission_level="it_specialist")
        login_as(u)
        r = client.post(
            "/api/tasks",
            json={
                "title": "Yazıcı arızası",
                "category": "support",
                "priority": "yüksek",
                "firm": "inventist",
                "deadline": "2030-01-01",  # UI artık göndermez ama gelse bile yok sayılmalı
            },
        )
        assert r.status_code in (200, 201)
        t = Task.query.filter_by(title="Yazıcı arızası").first()
        assert t is not None
        assert t.deadline is None  # SLA otomatik; manuel deadline saklanmaz

    def test_diger_kategori_deadline_korunur(self, db, client, user_factory, login_as):
        # Regresyon: support DIŞINDAKİ kategoriler manuel deadline'ı korumalı
        u = user_factory(username="snd_o", firm="inventist", permission_level="it_specialist")
        login_as(u)
        client.post(
            "/api/tasks",
            json={"title": "Sunucu bakımı", "category": "infra", "firm": "inventist", "deadline": "2030-01-01"},
        )
        t = Task.query.filter_by(title="Sunucu bakımı").first()
        assert t.deadline is not None and t.deadline.isoformat() == "2030-01-01"


class TestUpdateSupportClearsDeadline:
    def test_support_a_cevrilince_deadline_temizlenir(self, db, client, user_factory, login_as):
        u = user_factory(username="snd_u", firm="inventist", permission_level="it_specialist")
        login_as(u)
        # infra (deadline'lı) oluştur, sonra support'a çevir
        client.post(
            "/api/tasks",
            json={"title": "Dönüştürülecek", "category": "infra", "firm": "inventist", "deadline": "2030-05-05"},
        )
        t = Task.query.filter_by(title="Dönüştürülecek").first()
        assert t.deadline is not None
        r = client.patch(f"/api/tasks/{t.id}", json={"category": "support", "priority": "orta"})
        assert r.status_code == 200
        db.session.refresh(t)
        assert t.category == "support"
        assert t.deadline is None  # kategori support olunca temizlenir


class TestSupportOverdueFromSla:
    def _mk_support(self, db, u, priority, created_at, is_done=False, completed_at=None):
        t = Task(
            user_id=u.id,
            title="case",
            category="support",
            priority=priority,
            period="Tek Seferlik",
            firm="inventist",
            created_at=created_at,
            is_done=is_done,
            completed_at=completed_at,
        )
        db.session.add(t)
        db.session.commit()
        return t

    @freeze_time("2026-08-14 12:00:00")
    def test_acik_sla_asilmis_overdue(self, db, user_factory):
        u = user_factory(username="snd_ov1", firm="inventist", permission_level="it_specialist")
        # yüksek = 4s SLA; 3 gün önce açılmış açık case → kesinlikle aşılmış
        t = self._mk_support(db, u, "yüksek", datetime(2026, 8, 11, 9, 0, 0))
        assert t.is_overdue_now() is True

    @freeze_time("2026-08-14 12:00:00")
    def test_acik_sla_icinde_overdue_degil(self, db, user_factory):
        u = user_factory(username="snd_ov2", firm="inventist", permission_level="it_specialist")
        # düşük = 72s SLA; 10 dk önce açılmış → SLA içinde
        t = self._mk_support(db, u, "düşük", datetime(2026, 8, 14, 11, 50, 0))
        assert t.is_overdue_now() is False

    @freeze_time("2026-08-14 12:00:00")
    def test_tamamlanmis_overdue_degil(self, db, user_factory):
        u = user_factory(username="snd_ov3", firm="inventist", permission_level="it_specialist")
        # Geç kapatılmış bile olsa "şu anda geciken" değildir (breach geçmişi SLA statste)
        t = self._mk_support(
            db,
            u,
            "yüksek",
            datetime(2026, 8, 1, 9, 0, 0),
            is_done=True,
            completed_at=datetime(2026, 8, 5, 9, 0, 0),
        )
        assert t.is_overdue_now() is False

    @freeze_time("2026-08-14 12:00:00")
    def test_manuel_deadline_yok_sayilir(self, db, user_factory):
        # Eski veri: support case'de stray manuel deadline gelecekte olsa bile,
        # SLA aşıldıysa overdue olmalı (manuel deadline artık yol sinyali değil)
        u = user_factory(username="snd_ov4", firm="inventist", permission_level="it_specialist")
        t = self._mk_support(db, u, "yüksek", datetime(2026, 8, 11, 9, 0, 0))
        t.deadline = (datetime(2030, 1, 1)).date()  # ileri tarihli stray deadline
        db.session.commit()
        assert t.is_overdue_now() is True  # SLA aşımı belirleyici
