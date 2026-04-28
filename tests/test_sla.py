"""
test_sla.py — SLA hesaplama kurallarının baseline testleri (v4.5).

İş kuralı:
- priority='yüksek' → 4 saat SLA hedefi
- priority='orta'   → 24 saat SLA hedefi
- priority='düşük'  → 72 saat SLA hedefi
- SLA yalnızca category='support' görevler için hesaplanır.
- Diğer kategoriler (routine, project, infra, backup, other) için sla alanı None döner.
- SLA breach: created_at + target_hours < now ise breached=True.
- Tamamlanan görev için resolution_hours ve breach durumu completed_at'e göre hesaplanır.

Kapsam:
- _sla_target_hours() fonksiyon testi (models/database.py)
- Task.to_dict() SLA sözlüğü alanları doğrulaması
- freezegun ile zaman sabitleyerek breach/remaining_hours testi
"""

import pytest
from datetime import datetime, timedelta
from freezegun import freeze_time
from models.database import _sla_target_hours, SLA_HOURS, Task, TaskCompletion


class TestSlaTargetHours:
    """_sla_target_hours() saf fonksiyon testleri."""

    def test_yuksek_priority_4_saat(self):
        """Yüksek öncelikli görev için SLA hedefi 4 saattir."""
        assert _sla_target_hours("yüksek") == 4

    def test_orta_priority_24_saat(self):
        """Orta öncelikli görev için SLA hedefi 24 saattir."""
        assert _sla_target_hours("orta") == 24

    def test_dusuk_priority_72_saat(self):
        """Düşük öncelikli görev için SLA hedefi 72 saattir."""
        assert _sla_target_hours("düşük") == 72

    def test_bos_priority_varsayilan_orta(self):
        """Boş priority değeri için varsayılan 24 saat (orta) döner."""
        assert _sla_target_hours("") == 24
        assert _sla_target_hours(None) == 24

    def test_bilinmeyen_priority_varsayilan_orta(self):
        """Tanımsız priority değeri için varsayılan 24 saat döner."""
        assert _sla_target_hours("kritik") == 24
        assert _sla_target_hours("HIGH") == 24

    def test_bosluklu_priority_normalize_edilir(self):
        """Etrafında boşluk olan priority değeri trim edilerek tanınır."""
        assert _sla_target_hours("  yüksek  ") == 4
        assert _sla_target_hours("  düşük  ") == 72

    def test_buyuk_harf_priority_normalize_edilir(self):
        """
        Büyük harfli priority lower() ile normalize edilir.
        Python Unicode lower(): 'YÜKSEK'.lower() → 'yüksek' doğru çalışır.
        Bu nedenle 'YÜKSEK' → 4 saat döner (beklenmedik olsa da doğru davranış).
        """
        assert _sla_target_hours("YÜKSEK") == 4   # Python Unicode lower() çalışır
        assert _sla_target_hours("ORTA") == 24
        assert _sla_target_hours("DÜŞÜK") == 72

    def test_sla_hours_sabiti_dogru_tanimlanmis(self):
        """SLA_HOURS sabit sözlüğü doğru key-value çiftlerini içerir."""
        assert SLA_HOURS["yüksek"] == 4
        assert SLA_HOURS["orta"] == 24
        assert SLA_HOURS["düşük"] == 72
        assert len(SLA_HOURS) == 3


class TestSlaInTaskToDict:
    """Task.to_dict() SLA alanı davranışı."""

    def test_support_gorevi_sla_alani_doner(self, db, user_factory, task_factory):
        """category='support' görev için to_dict() içinde sla sözlüğü bulunur."""
        user = user_factory(username="sla_u1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Şifre sıfırlama talebi",
            category="support",
            priority="orta",
        )
        d = task.to_dict()
        assert d["sla"] is not None, "support kategorisi için sla alanı None olmamalı"
        assert "target_hours" in d["sla"]
        assert "breached" in d["sla"]
        assert "remaining_hours" in d["sla"]

    def test_routine_gorevi_sla_none(self, db, user_factory, task_factory):
        """category='routine' görev için sla=None döner."""
        user = user_factory(username="sla_u2", firm="inventist")
        task = task_factory(user_id=user.id, category="routine", period="Aylık")
        assert task.to_dict()["sla"] is None

    def test_project_gorevi_sla_none(self, db, user_factory, task_factory):
        """category='project' görev için sla=None döner."""
        user = user_factory(username="sla_u3", firm="assos")
        task = task_factory(user_id=user.id, category="project")
        assert task.to_dict()["sla"] is None

    def test_infra_gorevi_sla_none(self, db, user_factory, task_factory):
        """category='infra' görev için sla=None döner."""
        user = user_factory(username="sla_u4", firm="assos")
        task = task_factory(user_id=user.id, category="infra")
        assert task.to_dict()["sla"] is None

    def test_other_gorevi_sla_none(self, db, user_factory, task_factory):
        """category='other' görev için sla=None döner."""
        user = user_factory(username="sla_u5", firm="inventist")
        task = task_factory(user_id=user.id, category="other")
        assert task.to_dict()["sla"] is None

    def test_support_yuksek_sla_target_4_saat(self, db, user_factory, task_factory):
        """Yüksek öncelikli destek talebinin SLA hedefi 4 saat olarak döner."""
        user = user_factory(username="sla_u6", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Kritik sunucu hatası",
            category="support",
            priority="yüksek",
        )
        d = task.to_dict()
        assert d["sla"]["target_hours"] == 4

    def test_support_orta_sla_target_24_saat(self, db, user_factory, task_factory):
        """Orta öncelikli destek talebinin SLA hedefi 24 saat olarak döner."""
        user = user_factory(username="sla_u7", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Yazıcı sorun bildirimi",
            category="support",
            priority="orta",
        )
        d = task.to_dict()
        assert d["sla"]["target_hours"] == 24

    def test_support_dusuk_sla_target_72_saat(self, db, user_factory, task_factory):
        """Düşük öncelikli destek talebinin SLA hedefi 72 saat olarak döner."""
        user = user_factory(username="sla_u8", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Genel bilgi talebi",
            category="support",
            priority="düşük",
        )
        d = task.to_dict()
        assert d["sla"]["target_hours"] == 72

    @freeze_time("2026-04-10 10:00:00")
    def test_sla_breach_olmayan_gorev_remaining_hours_pozitif(self, db, user_factory):
        """SLA süresi dolmamış açık görevde remaining_hours pozitif, breached=False."""
        user = user_factory(username="sla_u9", firm="inventist")
        # Görev 1 saat önce oluşturuldu, yüksek → 4 saat SLA → 3 saat kaldı
        created = datetime(2026, 4, 10, 9, 0, 0)  # 09:00 — 1 saat önce
        task = Task(
            user_id=user.id,
            title="Acil destek talebi",
            category="support",
            priority="yüksek",
            created_at=created,
            is_done=False,
        )
        db.session.add(task)
        db.session.commit()

        d = task.to_dict()
        assert d["sla"]["breached"] is False
        assert d["sla"]["remaining_hours"] > 0
        # 4 saat SLA, 1 saat geçmiş → ~3 saat kaldı
        assert 2.5 <= d["sla"]["remaining_hours"] <= 3.5

    @freeze_time("2026-04-10 14:00:00")
    def test_sla_breach_olan_acik_gorev(self, db, user_factory):
        """SLA süresi dolmuş açık görevde breached=True, remaining_hours negatif."""
        user = user_factory(username="sla_u10", firm="assos")
        # Görev 5 saat önce oluşturuldu, yüksek → 4 saat SLA → breach olmuş
        created = datetime(2026, 4, 10, 9, 0, 0)  # 09:00 — 5 saat önce
        task = Task(
            user_id=user.id,
            title="Çözülemeyen ağ sorunu",
            category="support",
            priority="yüksek",
            created_at=created,
            is_done=False,
        )
        db.session.add(task)
        db.session.commit()

        d = task.to_dict()
        assert d["sla"]["breached"] is True
        assert d["sla"]["remaining_hours"] < 0

    @freeze_time("2026-04-10 12:00:00")
    def test_tamamlanan_gorev_breach_tarihten_hesaplanir(self, db, user_factory):
        """
        Tamamlanan destek talebinde breach, completed_at'in SLA deadline'ını geçip
        geçmediğine göre hesaplanır (mevcut 'now'a değil).
        """
        user = user_factory(username="sla_u11", firm="inventist")
        created = datetime(2026, 4, 10, 9, 0, 0)    # 09:00
        completed = datetime(2026, 4, 10, 10, 0, 0)  # 10:00 — 1 saat sonra
        # Yüksek → 4 saat SLA, 1 saatte çözüldü → breach YOK
        task = Task(
            user_id=user.id,
            title="Hızlı çözülen destek",
            category="support",
            priority="yüksek",
            created_at=created,
            is_done=True,
            completed_at=completed,
        )
        db.session.add(task)
        db.session.commit()

        d = task.to_dict()
        assert d["sla"]["breached"] is False
        assert d["sla"]["resolution_hours"] is not None
        assert 0.9 <= d["sla"]["resolution_hours"] <= 1.1

    @freeze_time("2026-04-10 20:00:00")
    def test_tamamlanan_gorev_geç_cozumde_breach_var(self, db, user_factory):
        """Yüksek öncelikli görev 5 saatte çözüldüyse (>4h SLA) breached=True."""
        user = user_factory(username="sla_u12", firm="assos")
        created = datetime(2026, 4, 10, 9, 0, 0)    # 09:00
        completed = datetime(2026, 4, 10, 14, 0, 0)  # 14:00 — 5 saat sonra
        task = Task(
            user_id=user.id,
            title="Geç çözülen kritik sorun",
            category="support",
            priority="yüksek",
            created_at=created,
            is_done=True,
            completed_at=completed,
        )
        db.session.add(task)
        db.session.commit()

        d = task.to_dict()
        assert d["sla"]["breached"] is True
        assert d["sla"]["resolution_hours"] is not None
        assert 4.9 <= d["sla"]["resolution_hours"] <= 5.1

    @freeze_time("2026-04-10 10:00:00")
    def test_tamamlanan_gorev_remaining_hours_sifir(self, db, user_factory):
        """Tamamlanmış görevde remaining_hours=0.0 döner."""
        user = user_factory(username="sla_u13", firm="inventist")
        created = datetime(2026, 4, 10, 8, 0, 0)
        completed = datetime(2026, 4, 10, 9, 0, 0)
        task = Task(
            user_id=user.id,
            title="Kapatılmış destek talebi",
            category="support",
            priority="orta",
            created_at=created,
            is_done=True,
            completed_at=completed,
        )
        db.session.add(task)
        db.session.commit()

        d = task.to_dict()
        assert d["sla"]["remaining_hours"] == 0.0


class TestSlaStatsEndpoint:
    """GET /api/sla/stats — SLA metrikleri endpoint davranışı."""

    @freeze_time("2026-04-10 12:00:00")
    def test_sla_stats_yetkili_kullanici_200(self, db, client, user_factory, task_factory, login_as):
        """Giriş yapmış kullanıcı /api/sla/stats'a erişebilir."""
        user = user_factory(username="sla_api1", firm="inventist")
        login_as(user)
        resp = client.get("/api/sla/stats?month=4&year=2026")
        assert resp.status_code == 200

    def test_sla_stats_oturum_yok_401_veya_redirect(self, db, client, user_factory):
        """Oturum olmadan /api/sla/stats çağrısı 401 veya 302 döner."""
        resp = client.get("/api/sla/stats")
        assert resp.status_code in (401, 302)

    @freeze_time("2026-04-10 12:00:00")
    def test_sla_stats_response_alanlari(self, db, client, user_factory, task_factory, login_as):
        """SLA stats response'u beklenen alanları içerir."""
        user = user_factory(username="sla_api2", firm="assos")
        # Destek talebi oluştur
        created = datetime(2026, 4, 5, 8, 0, 0)
        task = Task(
            user_id=user.id,
            title="Ağ bağlantı sorunu — İlknur Doğan",
            category="support",
            priority="orta",
            created_at=created,
            is_done=False,
            firm="assos",
        )
        db.session.add(task)
        db.session.commit()

        login_as(user)
        resp = client.get("/api/sla/stats?month=4&year=2026")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "total" in data
        assert "open" in data
        assert "resolved" in data
        assert "breached" in data
        assert "by_priority" in data

    @freeze_time("2026-04-10 12:00:00")
    def test_sla_stats_sadece_support_sayar(self, db, client, user_factory, task_factory, login_as):
        """SLA stats yalnızca category='support' görevleri sayar."""
        user = user_factory(username="sla_api3", firm="inventist")
        # Destek görevi
        support_task = Task(
            user_id=user.id,
            title="Destek talebi",
            category="support",
            priority="orta",
            created_at=datetime(2026, 4, 5, 8, 0, 0),
            is_done=False,
            firm="inventist",
        )
        # Rutin görev — sayılmamalı
        routine_task = Task(
            user_id=user.id,
            title="Rutin görev",
            category="routine",
            priority="orta",
            created_at=datetime(2026, 4, 5, 8, 0, 0),
            is_done=False,
            firm="inventist",
        )
        db.session.add_all([support_task, routine_task])
        db.session.commit()

        login_as(user)
        resp = client.get("/api/sla/stats?month=4&year=2026")
        data = resp.get_json()

        assert data["total"] == 1, "SLA stats yalnızca support görevini saymalı"
