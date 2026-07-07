"""
test_sla_business_hours.py — v5.13 İŞ-saati bazlı SLA.

Eskiden SLA hedefi = created_at + timedelta(hours=target) → 7/24. Cuma 17:00'de
açılan 4 saatlik yüksek öncelikli talep Cuma 21:00'de "ihlal" sayılıyordu; artık
yalnız çalışma saatleri (Pzt-Cum 09:00-18:00 + tatiller) sayılır.

Birim testler cfg'yi doğrudan kurar (env'den bağımsız, deterministik). Entegrasyon
testleri env'i monkeypatch'ler (SLA_TZ=UTC).
"""

from datetime import date, datetime

import pytest
from freezegun import freeze_time

from models.database import add_business_hours, business_hours_between, sla_deadline


def _cfg(start=9, end=18, days=None, holidays=None, enabled=True, tz=None):
    return {
        "start": start,
        "end": end,
        "days": days if days is not None else {0, 1, 2, 3, 4},
        "holidays": holidays if holidays is not None else set(),
        "enabled": enabled,
        "tz": tz,
    }


# ── add_business_hours (naive, tz=None) ──
# 2026-05-04 Pazartesi ... 2026-05-08 Cuma


class TestAddBusinessHours:
    def test_gun_ici(self):
        assert add_business_hours(datetime(2026, 5, 4, 10), 3, _cfg()) == datetime(2026, 5, 4, 13)

    def test_ertesi_gune_tasar(self):
        # Pzt 16:00 + 4s → 2s Pzt (16-18) + 2s Salı (09-11)
        assert add_business_hours(datetime(2026, 5, 4, 16), 4, _cfg()) == datetime(2026, 5, 5, 11)

    def test_hafta_sonu_atlar(self):
        # Cuma 17:00 + 4s → 1s Cuma (17-18) + 3s Pzt (09-12)
        assert add_business_hours(datetime(2026, 5, 8, 17), 4, _cfg()) == datetime(2026, 5, 11, 12)

    def test_mesai_oncesi_baslar(self):
        assert add_business_hours(datetime(2026, 5, 4, 7), 2, _cfg()) == datetime(2026, 5, 4, 11)

    def test_mesai_sonrasi_ertesi_gun(self):
        assert add_business_hours(datetime(2026, 5, 4, 20), 2, _cfg()) == datetime(2026, 5, 5, 11)

    def test_tatil_atlar(self):
        # Salı 05-05 tatil → Pzt 16:00 +4s = 2s Pzt + 2s Çar (05-06)
        cfg = _cfg(holidays={date(2026, 5, 5)})
        assert add_business_hours(datetime(2026, 5, 4, 16), 4, cfg) == datetime(2026, 5, 6, 11)

    def test_disabled_724(self):
        cfg = _cfg(enabled=False)
        assert add_business_hours(datetime(2026, 5, 8, 17), 4, cfg) == datetime(2026, 5, 8, 21)

    def test_tz_istanbul(self):
        pytest.importorskip("zoneinfo")
        from zoneinfo import ZoneInfo

        cfg = _cfg(tz=ZoneInfo("Europe/Istanbul"))
        # 06:00 UTC = 09:00 TRT (mesai başı) + 4s = 13:00 TRT = 10:00 UTC
        assert add_business_hours(datetime(2026, 5, 4, 6), 4, cfg) == datetime(2026, 5, 4, 10)
        # Cuma 14:00 UTC = 17:00 TRT + 4s = 1s Cuma + 3s Pzt (09-12 TRT) = Pzt 09:00 UTC
        assert add_business_hours(datetime(2026, 5, 8, 14), 4, cfg) == datetime(2026, 5, 11, 9)


class TestBusinessHoursBetween:
    def test_gun_ici(self):
        assert business_hours_between(datetime(2026, 5, 4, 9), datetime(2026, 5, 4, 12), _cfg()) == 3.0

    def test_hafta_sonu_dahil(self):
        # Cuma 17:00 → Pzt 10:00 = 1s (Cuma) + 1s (Pzt) = 2s
        assert business_hours_between(datetime(2026, 5, 8, 17), datetime(2026, 5, 11, 10), _cfg()) == 2.0

    def test_negatif(self):
        assert business_hours_between(datetime(2026, 5, 4, 12), datetime(2026, 5, 4, 9), _cfg()) == -3.0


# ── Entegrasyon: destek talebi SLA (to_dict) + /api/sla/stats ──


class TestSlaIntegration:
    @freeze_time("2026-05-09 10:00:00")  # Cumartesi
    def test_hafta_sonu_acik_talep_breach_degil(self, db, client, user_factory, task_factory, login_as, monkeypatch):
        """Cuma 17:00 açılan yüksek öncelikli (4s) talep, Cumartesi'de İHLAL DEĞİL.

        7/24 olsaydı Cuma 21:00'de ihlal sayılırdı; iş-saatinde deadline Pzt 12:00.
        """
        monkeypatch.setenv("SLA_BUSINESS_HOURS", "1")
        monkeypatch.setenv("SLA_TZ", "UTC")  # deterministik: mesai 09-18 UTC
        u = user_factory(username="bh_u1", firm="inventist")
        t = task_factory(user_id=u.id, category="support", priority="yüksek", firm="inventist")
        t.created_at = datetime(2026, 5, 8, 17)  # Cuma 17:00
        db.session.commit()

        d = t.to_dict()
        assert d["sla"] is not None
        assert d["sla"]["breached"] is False, "Hafta sonu açık talep iş-saatinde henüz ihlal değil"
        # Deadline Pzt 12:00 civarı (Cuma'dan kalan 1s + 3s Pzt)
        assert d["sla"]["deadline"].startswith("2026-05-11")

    @freeze_time("2026-05-11 13:00:00")  # Pazartesi 13:00, deadline (12:00) geçmiş
    def test_deadline_sonrasi_breach(self, db, client, user_factory, task_factory, login_as, monkeypatch):
        monkeypatch.setenv("SLA_BUSINESS_HOURS", "1")
        monkeypatch.setenv("SLA_TZ", "UTC")
        u = user_factory(username="bh_u2", firm="inventist")
        t = task_factory(user_id=u.id, category="support", priority="yüksek", firm="inventist")
        t.created_at = datetime(2026, 5, 8, 17)  # Cuma 17:00 → deadline Pzt 12:00
        db.session.commit()
        d = t.to_dict()
        assert d["sla"]["breached"] is True

    @freeze_time("2026-05-09 10:00:00")
    def test_sla_stats_business_hours_alani(self, db, client, user_factory, task_factory, login_as, monkeypatch):
        """/api/sla/stats yanıtı iş-saati yapılandırmasını döndürür."""
        monkeypatch.setenv("SLA_BUSINESS_HOURS", "1")
        monkeypatch.setenv("SLA_TZ", "UTC")
        u = user_factory(username="bh_u3", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(u)
        r = client.get("/api/sla/stats?month=5&year=2026")
        assert r.status_code == 200
        b = r.get_json()["business_hours"]
        assert b["enabled"] is True
        assert b["work_start"] == 9 and b["work_end"] == 18
        assert b["work_days_label"] == "Pzt, Sal, Çar, Per, Cum"
