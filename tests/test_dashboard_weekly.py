"""
test_dashboard_weekly.py — v5.35 — Dashboard haftalık akış trend endpoint'i.

/api/dashboard/weekly-trends: son N hafta açılan (created_at) / çözülen (completed_at)
görev sayıları; kullanıcı kapsamı; hafta kovalama.
"""

from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _noop():
    yield


def _mktask(db, user, title, created_days_ago=0, completed_days_ago=None):
    from models.database import Task

    t = Task(
        user_id=user.id, title=title, category="support", priority="orta",
        period="Tek Seferlik", firm="inventist",
        created_at=datetime.utcnow() - timedelta(days=created_days_ago),
    )
    if completed_days_ago is not None:
        t.is_done = True
        t.completed_at = datetime.utcnow() - timedelta(days=completed_days_ago)
    db.session.add(t)
    db.session.commit()
    return t


class TestWeeklyTrends:
    def test_yapi_ve_hafta_sayisi(self, db, client, user_factory, login_as):
        u = user_factory(username="wt_u", firm="inventist", permission_level="it_specialist")
        login_as(u)
        d = client.get("/api/dashboard/weekly-trends?weeks=8").get_json()
        assert len(d["labels"]) == 8 and len(d["opened"]) == 8 and len(d["resolved"]) == 8
        assert d["window"]["weeks"] == 8

    def test_acilan_ve_cozulen_sayilir(self, db, client, user_factory, login_as):
        u = user_factory(username="wt_c", firm="inventist", permission_level="it_specialist")
        login_as(u)
        _mktask(db, u, "bu hafta açık", created_days_ago=1)  # bu hafta açılan
        _mktask(db, u, "bu hafta çözülen", created_days_ago=2, completed_days_ago=1)  # açılan+çözülen
        d = client.get("/api/dashboard/weekly-trends?weeks=4").get_json()
        assert d["opened"][-1] >= 2  # son hafta en az 2 açılan
        assert d["resolved"][-1] >= 1  # son hafta en az 1 çözülen

    def test_eski_gorev_pencere_disi(self, db, client, user_factory, login_as):
        u = user_factory(username="wt_old", firm="inventist", permission_level="it_specialist")
        login_as(u)
        _mktask(db, u, "çok eski", created_days_ago=120)  # 4 haftalık pencerenin çok dışında
        d = client.get("/api/dashboard/weekly-trends?weeks=4").get_json()
        assert sum(d["opened"]) == 0  # pencereye girmez

    def test_kapsam_baska_kullanici_gorunmez(self, db, client, user_factory, login_as):
        u = user_factory(username="wt_me", firm="inventist", permission_level="junior")
        other = user_factory(username="wt_other", firm="inventist", permission_level="junior")
        _mktask(db, other, "başkasının görevi", created_days_ago=1)
        login_as(u)
        d = client.get("/api/dashboard/weekly-trends?weeks=4").get_json()
        assert sum(d["opened"]) == 0  # junior yalnız kendi görevlerini sayar

    def test_weeks_sinirlari(self, db, client, user_factory, login_as):
        u = user_factory(username="wt_lim", firm="inventist", permission_level="it_specialist")
        login_as(u)
        assert len(client.get("/api/dashboard/weekly-trends?weeks=1").get_json()["labels"]) == 2  # min 2
        assert len(client.get("/api/dashboard/weekly-trends?weeks=99").get_json()["labels"]) == 26  # max 26
