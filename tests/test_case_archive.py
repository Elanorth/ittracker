"""
test_case_archive.py — v5.27 — Case Arşivi (ay-bağımsız destek talebi arama).

- Arama: Case No / başlık / bildiren e-postası-adı.
- Ay bağımsız: eski aylardaki case'ler de bulunur (get_tasks ay filtreli, arşiv değil).
- Firma kapsamı: junior yalnız kendi firması; super_admin tümü.
- Durum filtresi (open/resolved) + sayfalama.
"""

from datetime import datetime, timedelta

import pytest

import app as app_module
from models.database import Task, db


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


def _case(code="INV-ARC001", title="Yazıcı arızası", firm="inventist", done=False, months_ago=0, email="a@x.com"):
    t = Task(
        user_id=None,
        title=title,
        category="support",
        priority="orta",
        period="Tek Seferlik",
        firm=firm,
        source="portal",
        case_code=code,
        reporter_email=email,
        reporter_name="Ali Veli",
        is_done=done,
    )
    if months_ago:
        t.created_at = datetime.utcnow() - timedelta(days=30 * months_ago)
    db.session.add(t)
    db.session.commit()
    return t


class TestArchiveSearch:
    def test_case_no_ile_bulunur(self, db, client, user_factory, login_as):
        _case("INV-ARC111")
        login_as(user_factory(username="ar_a", firm="inventist", permission_level="it_specialist"))
        d = client.get("/api/archive?q=ARC111").get_json()
        assert d["total"] == 1 and d["items"][0]["case_code"] == "INV-ARC111"

    def test_baslik_ve_eposta_ile_bulunur(self, db, client, user_factory, login_as):
        _case("INV-ARC112", title="VPN kopuyor", email="mehmet@inventist.com.tr")
        login_as(user_factory(username="ar_b", firm="inventist", permission_level="it_specialist"))
        assert client.get("/api/archive?q=VPN").get_json()["total"] == 1
        assert client.get("/api/archive?q=mehmet@").get_json()["total"] == 1

    def test_ay_bagimsiz_eski_case_bulunur(self, db, client, user_factory, login_as):
        _case("INV-ARC113", months_ago=5, done=True)  # 5 ay önce, kapalı
        login_as(user_factory(username="ar_c", firm="inventist", permission_level="it_specialist"))
        d = client.get("/api/archive?q=ARC113").get_json()
        assert d["total"] == 1 and d["items"][0]["status"] == "resolved"

    def test_durum_filtresi(self, db, client, user_factory, login_as):
        _case("INV-ARC114", done=False)
        _case("INV-ARC115", done=True)
        login_as(user_factory(username="ar_d", firm="inventist", permission_level="it_specialist"))
        assert client.get("/api/archive?status=open&q=ARC11").get_json()["total"] == 1
        assert client.get("/api/archive?status=resolved&q=ARC11").get_json()["total"] == 1
        assert client.get("/api/archive?q=ARC11").get_json()["total"] == 2


class TestArchiveScope:
    def test_junior_yalniz_kendi_firmasi(self, db, client, user_factory, login_as):
        _case("INV-ARC116", firm="inventist")
        _case("ASS-ARC117", firm="assos")
        login_as(user_factory(username="ar_jr", firm="inventist", permission_level="junior"))
        d = client.get("/api/archive").get_json()
        firms = {i["firm"] for i in d["items"]}
        assert firms == {"inventist"}

    def test_super_admin_tum_firmalar(self, db, client, user_factory, login_as):
        _case("INV-ARC118", firm="inventist")
        _case("ASS-ARC119", firm="assos")
        login_as(user_factory(username="ar_sa", permission_level="super_admin", is_admin=True))
        firms = {i["firm"] for i in client.get("/api/archive").get_json()["items"]}
        assert "inventist" in firms and "assos" in firms


class TestArchivePagination:
    def test_sayfalama(self, db, client, user_factory, login_as):
        for i in range(30):
            _case(f"INV-ARCP{i:02d}")
        login_as(user_factory(username="ar_pg", firm="inventist", permission_level="it_specialist"))
        d1 = client.get("/api/archive?page=1").get_json()
        assert len(d1["items"]) == 25 and d1["total"] == 30 and d1["pages"] == 2
        d2 = client.get("/api/archive?page=2").get_json()
        assert len(d2["items"]) == 5
