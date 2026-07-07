"""
test_csv_export.py — v5.14 CSV (Excel) dışa aktarım.

/api/tasks/export ve /api/audit/export — UTF-8 BOM + ';' ayraç (TR Excel uyumlu),
ekrandaki ay/filtre kümesiyle aynı veriyi döndürür.
"""

from datetime import datetime


def _lines(resp):
    """CSV gövdesini BOM'suz satırlara ayır."""
    text = resp.get_data(as_text=True)
    assert text.startswith("﻿"), "UTF-8 BOM bekleniyordu (Excel Türkçe uyumu)"
    return text.lstrip("﻿").strip().split("\r\n")


class TestTasksExport:
    def test_csv_temel(self, db, client, user_factory, task_factory, login_as):
        u = user_factory(username="csv_u1", firm="inventist")
        task_factory(user_id=u.id, title="Sunucu <bakım>", category="support", priority="yüksek", firm="inventist")
        login_as(u)
        now = datetime.utcnow()
        resp = client.get(f"/api/tasks/export?month={now.month}&year={now.year}")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["Content-Type"]
        assert "attachment" in resp.headers["Content-Disposition"]
        assert ".csv" in resp.headers["Content-Disposition"]
        lines = _lines(resp)
        assert lines[0].startswith("ID;Başlık;Kategori")  # ';' ayraç
        # Başlık ham yazılır (CSV; HTML değil) — XSS escape gerektirmez ama title korunur
        assert any("Sunucu <bakım>" in ln for ln in lines[1:])

    def test_bos_ay(self, db, client, user_factory, login_as):
        u = user_factory(username="csv_u2", firm="inventist")
        login_as(u)
        resp = client.get("/api/tasks/export?month=1&year=2020")
        assert resp.status_code == 200
        lines = _lines(resp)
        assert lines[0].startswith("ID;")
        assert len(lines) == 1  # yalnız başlık satırı

    def test_yetki_kapsami(self, db, client, user_factory, task_factory, login_as):
        """Junior başkasının görevini export edemez (scope kendi id'sine düşer)."""
        owner = user_factory(username="csv_owner", firm="inventist")
        other = user_factory(username="csv_other", firm="inventist")
        task_factory(user_id=owner.id, title="Gizli", category="support", firm="inventist")
        login_as(other)
        now = datetime.utcnow()
        resp = client.get(f"/api/tasks/export?month={now.month}&year={now.year}&user_id={owner.id}")
        # _resolve_scope_uid junior için 403 döner
        assert resp.status_code == 403


class TestAuditExport:
    def test_csv_director(self, db, client, user_factory, task_factory, login_as):
        admin = user_factory(username="csv_adm", firm="inventist", permission_level="super_admin", is_admin=True)
        # Bir audit kaydı üretmek için görev oluştur (API üzerinden)
        login_as(admin)
        client.post("/api/tasks", json={"title": "Denetlenen görev", "category": "support", "firm": "inventist"})
        resp = client.get("/api/audit/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["Content-Type"]
        lines = _lines(resp)
        assert lines[0] == "Tarih;İşlem;Aktör;Hedef;Firma;Özet"
        assert any("Görev Oluşturma" in ln for ln in lines[1:])

    def test_junior_403(self, db, client, user_factory, login_as):
        u = user_factory(username="csv_jr", firm="inventist", permission_level="junior")
        login_as(u)
        assert client.get("/api/audit/export").status_code == 403

    def test_gecersiz_tarih_400(self, db, client, user_factory, login_as):
        admin = user_factory(username="csv_adm2", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        assert client.get("/api/audit/export?start=bozuk").status_code == 400
