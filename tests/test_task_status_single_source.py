"""
test_task_status_single_source.py — Görev durumu tek-kaynak refactor'ı.

Rutin görevlerin "tamamlandı/gecikti" durumu artık backend'de TEK kanonik
kaynaktan (Task.is_done_now/is_overdue_now) gelir; stats, dashboard trends ve
managed-firms/detail kendi kopya `_is_done`/`is_done` mantıklarını kullanmaz.

Bu testler, eski kopya mantıkların yol açtığı hatalara regresyon kalkanıdır:
- /api/stats overdue: rutin gecikmesi donmuş `deadline` ile DEĞİL, kanonik
  is_overdue_now ile sayılır (deadline'ı olmayan kaçmış rutin de sayılır).
- /api/managed-firms/detail kullanıcı dağılımı: rutin `is_done` flag'i hiç set
  edilmediği için eski kod hepsini "açık" sayıyordu → artık kanonik.
- /api/managed-firms/detail geciken top-3: rutinler artık kanonik is_overdue ile
  listelenir ve "N periyot atlandı" (overdue_periods) bilgisini taşır.
"""

from datetime import date, datetime

from freezegun import freeze_time

from models.database import TaskOccurrence


class TestStatsOverdueCanonical:
    """/api/stats — rutin done/overdue kanonik kaynaktan."""

    @freeze_time("2026-04-29")
    def test_kacan_aylik_rutin_deadline_yok_overdue_sayilir(self, db, client, user_factory, task_factory, login_as):
        """Deadline'ı olmayan ama önceki ayı kaçmış aylık rutin overdue'ya dahil.

        Eski kod `deadline and deadline < today` istediği için deadline=None olan
        rutinleri overdue saymıyordu — bu test onu yakalar.
        """
        u = user_factory(username="stov1", firm="inventist")
        # Kaçan aylık rutin: occurrence yok, deadline yok → is_overdue_now True
        task_factory(user_id=u.id, title="Kaçan aylık", category="routine", period="Aylık")
        # Bu ay tamamlanmış aylık rutin → done
        doner = task_factory(user_id=u.id, title="Biten aylık", category="routine", period="Aylık")
        db.session.add(TaskOccurrence(task_id=doner.id, period_key="2026-04"))
        db.session.commit()

        login_as(u)
        resp = client.get("/api/stats?month=4&year=2026")
        assert resp.status_code == 200
        d = resp.get_json()
        assert d["done"] >= 1, "Bu ay tamamlanan rutin done'a dahil olmalı"
        assert d["overdue"] >= 1, "Önceki ayı kaçmış rutin (deadline'sız) overdue'ya dahil olmalı"

    @freeze_time("2026-04-29")
    def test_onceki_ay_tamamlanmis_rutin_overdue_degil(self, db, client, user_factory, task_factory, login_as):
        """Önceki ay (Mart) tamamlanmış aylık rutin bu ay overdue sayılmaz."""
        u = user_factory(username="stov2", firm="inventist")
        t = task_factory(user_id=u.id, title="Mart biten aylık", category="routine", period="Aylık")
        db.session.add(TaskOccurrence(task_id=t.id, period_key="2026-03"))
        db.session.commit()

        login_as(u)
        resp = client.get("/api/stats?month=4&year=2026")
        assert resp.status_code == 200
        # Model seviyesinde de doğrula (izole)
        assert t.is_overdue_now(today=date(2026, 4, 29)) is False


class TestManagedFirmsUserStatsCanonical:
    """/api/managed-firms/detail — kullanıcı dağılımı rutin tamamlanmayı kanonik sayar."""

    @freeze_time("2026-04-29")
    def test_bu_ay_tamamlanan_rutin_kullanici_done(self, db, client, user_factory, task_factory, login_as):
        """Bu ay tamamlanan aylık rutin, kullanıcının done_tasks'ına yansır (open değil).

        Eski kod ham `t.is_done` okuduğu için rutini her zaman "açık" sayıyordu.
        """
        admin = user_factory(username="mfus_a", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="mfus_w", firm="inventist", permission_level="junior")
        task = task_factory(
            user_id=worker.id, title="Aylık yedek", category="routine", period="Aylık", firm="inventist"
        )
        db.session.add(TaskOccurrence(task_id=task.id, period_key="2026-04"))
        db.session.commit()

        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        inv = next((e for e in resp.get_json() if e["slug"] == "inventist"), None)
        assert inv is not None
        wrow = next((x for x in inv["users"] if x["id"] == worker.id), None)
        assert wrow is not None, "İşçi kullanıcı dağılımda görünmeli"
        assert wrow["done_tasks"] >= 1, "Bu ay tamamlanan rutin done sayılmalı"
        assert wrow["open_tasks"] == 0, "Tamamlanan rutin açık sayılmamalı"


class TestManagedFirmsOverdueTop3Canonical:
    """/api/managed-firms/detail — geciken top-3 rutinleri kanonik listeler."""

    @freeze_time("2026-04-29")
    def test_kacan_rutin_overdue_periods_ile_listelenir(self, db, client, user_factory, task_factory, login_as):
        """Kaçmış aylık rutin geciken top-3'te; overdue_periods dolu, days_overdue None.

        Eski kod yalnızca deadline'lı görevleri listeliyordu → rutinler (deadline None)
        hiç görünmüyordu.
        """
        admin = user_factory(username="mfot_a", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="mfot_w", firm="inventist", permission_level="junior")
        t = task_factory(user_id=worker.id, title="Kaçan rutin", category="routine", period="Aylık", firm="inventist")
        t.created_at = datetime(2026, 1, 1)  # Şubat+Mart kaçmış olabilir
        db.session.commit()

        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        inv = next((e for e in resp.get_json() if e["slug"] == "inventist"), None)
        assert inv is not None
        row = next((x for x in inv["overdue_top3"] if x["id"] == t.id), None)
        assert row is not None, "Kaçmış rutin geciken top-3'te olmalı"
        assert row["overdue_periods"] is not None and row["overdue_periods"] >= 1
        assert row["days_overdue"] is None, "Rutin için gün-bazlı gecikme değil periyot kullanılmalı"
        assert row["period"] == "Aylık"

    @freeze_time("2026-04-29")
    def test_deadline_bazli_gorev_days_overdue_tasir(self, db, client, user_factory, task_factory, login_as):
        """Deadline'lı (rutin olmayan) geciken görev days_overdue taşır, overdue_periods None."""
        admin = user_factory(username="mfot_b", firm="inventist", permission_level="super_admin", is_admin=True)
        worker = user_factory(username="mfot_bw", firm="inventist", permission_level="junior")
        t = task_factory(user_id=worker.id, title="Geciken destek", category="support", firm="inventist")
        t.deadline = date(2026, 4, 20)  # 9 gün önce
        db.session.commit()

        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        inv = next((e for e in resp.get_json() if e["slug"] == "inventist"), None)
        row = next((x for x in inv["overdue_top3"] if x["id"] == t.id), None)
        assert row is not None
        assert row["days_overdue"] == 9
        assert row["overdue_periods"] is None
