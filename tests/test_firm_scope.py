"""
test_firm_scope.py — Mevcut firma-kapsam kurallarının baseline testleri.

İş kuralı (app.py:130-149 _resolve_scope_uid, app.py:281-296 /api/firm/users):
- it_director yalnızca kendi firmasındaki kullanıcıları görebilir/yönetebilir.
- super_admin tüm firmaları görür.
- Diğer roller (/api/firm/users çağrısında) sadece kendi kayıtlarını alır.
- it_director başka firmadaki kullanıcıya erişmeye çalışırsa 403 döner.

v4.9 many-to-many migration'ından ÖNCE bu davranışlar doğrulanıp belgelenir.
"""

import pytest
import json
from models.database import User, Task


class TestFirmUsersEndpoint:
    """GET /api/firm/users — firma bazlı kullanıcı listesi."""

    def test_super_admin_gores_tum_kullanicilari(self, db, client, user_factory, login_as):
        """super_admin tüm aktif kullanıcıları listeler (firma sınırı yok)."""
        admin = user_factory(username="sa", firm="inventist", permission_level="super_admin", is_admin=True)
        u1 = user_factory(username="inv_user", firm="inventist", permission_level="junior")
        u2 = user_factory(username="assos_user", firm="assos", permission_level="junior")

        login_as(admin)
        resp = client.get("/api/firm/users")
        assert resp.status_code == 200
        data = resp.get_json()
        ids = {d["id"] for d in data}
        assert admin.id in ids
        assert u1.id in ids
        assert u2.id in ids

    def test_it_director_sadece_kendi_firmasini_gorer(self, db, client, user_factory, login_as):
        """it_director yalnızca kendi firmasındaki kullanıcıları listeler."""
        director = user_factory(username="dir", firm="inventist", permission_level="it_director", is_admin=True)
        same_firm = user_factory(username="inv2", firm="inventist", permission_level="junior")
        other_firm = user_factory(username="assos2", firm="assos", permission_level="junior")

        login_as(director)
        resp = client.get("/api/firm/users")
        assert resp.status_code == 200
        data = resp.get_json()
        ids = {d["id"] for d in data}
        assert director.id in ids
        assert same_firm.id in ids
        assert other_firm.id not in ids, "it_director başka firmayı görmemeli"

    def test_it_director_response_firma_bilgisi_iceriyor(self, db, client, user_factory, login_as):
        """it_director listesindeki her kullanıcı kaydında 'firm' alanı vardır."""
        director = user_factory(username="dir2", firm="İnventist", permission_level="it_director", is_admin=True)
        user_factory(username="inv3", firm="İnventist", permission_level="it_specialist")

        login_as(director)
        data = client.get("/api/firm/users").get_json()
        for entry in data:
            assert "firm" in entry
            assert "id" in entry
            assert "full_name" in entry

    def test_diger_rol_sadece_kendi_kaydini_alir(self, db, client, user_factory, login_as):
        """it_manager ve altı roller /api/firm/users çağırırsa sadece kendi bilgilerini alır."""
        manager = user_factory(username="mgr", firm="inventist", permission_level="it_manager")
        user_factory(username="other_mgr", firm="inventist", permission_level="it_specialist")

        login_as(manager)
        resp = client.get("/api/firm/users")
        assert resp.status_code == 200
        data = resp.get_json()
        # Sadece bir kayıt ve o da kendisi
        assert len(data) == 1
        assert data[0]["id"] == manager.id

    def test_junior_sadece_kendi_kaydini_alir(self, db, client, user_factory, login_as):
        """junior rol da /api/firm/users çağırırsa sadece kendi kaydını görür."""
        junior = user_factory(username="jnr", firm="assos", permission_level="junior")
        user_factory(username="jnr2", firm="assos", permission_level="junior")

        login_as(junior)
        data = client.get("/api/firm/users").get_json()
        assert len(data) == 1
        assert data[0]["id"] == junior.id

    def test_oturum_acilmadan_401_veya_redirect(self, db, client, user_factory):
        """Oturum olmadan /api/firm/users çağrısı 401 veya 302 döner."""
        resp = client.get("/api/firm/users")
        assert resp.status_code in (401, 302)


class TestResolveScopeUID:
    """_resolve_scope_uid — firma kapsam çözümleyici mantığı, /api/tasks?user_id= aracılığıyla."""

    def test_director_kendi_firmasindaki_kullaniciya_erisebilir(self, db, client, user_factory, login_as, task_factory):
        """it_director kendi firmasındaki başka kullanıcının görevlerini görebilir."""
        director = user_factory(username="dir3", firm="inventist", permission_level="it_director", is_admin=True)
        target = user_factory(username="inv_target", firm="inventist", permission_level="junior")
        task_factory(user_id=target.id, title="Hedef kullanıcı görevi", category="other")

        login_as(director)
        resp = client.get(f"/api/tasks?user_id={target.id}")
        assert resp.status_code == 200
        tasks = resp.get_json()
        titles = [t["title"] for t in tasks]
        assert "Hedef kullanıcı görevi" in titles

    def test_director_baska_firmayi_reddetmeli(self, db, client, user_factory, login_as):
        """it_director başka firmadaki kullanıcıya erişmeye çalışırsa 403 alır."""
        director = user_factory(username="dir4", firm="inventist", permission_level="it_director", is_admin=True)
        foreign = user_factory(username="assos_foreign", firm="assos", permission_level="junior")

        login_as(director)
        resp = client.get(f"/api/tasks?user_id={foreign.id}")
        assert resp.status_code == 403

    def test_super_admin_baska_firmayi_gorebilir(self, db, client, user_factory, login_as, task_factory):
        """super_admin herhangi bir kullanıcının görevlerini görüntüleyebilir."""
        admin = user_factory(username="sa2", firm="inventist", permission_level="super_admin", is_admin=True)
        other = user_factory(username="assos_u2", firm="assos", permission_level="junior")
        task_factory(user_id=other.id, title="Assos görevi", category="other")

        login_as(admin)
        resp = client.get(f"/api/tasks?user_id={other.id}")
        assert resp.status_code == 200

    def test_director_var_olmayan_kullaniciya_erisemez(self, db, client, user_factory, login_as):
        """it_director var olmayan kullanıcı ID'si verirse 404 alır."""
        director = user_factory(username="dir5", firm="inventist", permission_level="it_director", is_admin=True)

        login_as(director)
        resp = client.get("/api/tasks?user_id=99999")
        assert resp.status_code in (403, 404)

    def test_director_pasif_kullaniciya_erisemez(self, db, client, user_factory, login_as):
        """it_director aktif olmayan (inactive) kullanıcıya erişmeye çalışırsa 404 alır."""
        director = user_factory(username="dir6", firm="inventist", permission_level="it_director", is_admin=True)
        inactive = user_factory(username="inv_inactive", firm="inventist", permission_level="junior", active=False)

        login_as(director)
        resp = client.get(f"/api/tasks?user_id={inactive.id}")
        assert resp.status_code == 404

    def test_junior_baska_kullanici_id_verirse_kendi_verisi_gelir(self, db, client, user_factory, login_as, task_factory):
        """junior rol başkasının user_id'sini verirse kendi verilerini görür (scope kısıtlı)."""
        junior = user_factory(username="jnr3", firm="assos", permission_level="junior")
        other = user_factory(username="assos_other", firm="assos", permission_level="junior")
        my_task = task_factory(user_id=junior.id, title="Benim görevim", category="other")
        task_factory(user_id=other.id, title="Başkasının görevi", category="other")

        login_as(junior)
        resp = client.get(f"/api/tasks?user_id={other.id}")
        # junior başkasını göremez — ya 403 ya da kendi verisi döner
        if resp.status_code == 200:
            tasks = resp.get_json()
            ids = [t["id"] for t in tasks]
            # Başkasının görevi olmamalı
            assert my_task.id in ids or len(tasks) == 0
            # Eğer veri döndüyse başkasının görevi içermemeli
            other_task_ids = [t["id"] for t in tasks if t["user_id"] == other.id]
            assert len(other_task_ids) == 0, "junior başkasının görevini görmemeli"
        else:
            assert resp.status_code == 403


class TestCrossFirmStats:
    """/api/stats endpoint'inde firma kapsam izolasyonu."""

    def test_director_stats_sadece_kendi_firmasini_kapsıyor(self, db, client, user_factory, login_as, task_factory):
        """it_director /api/stats çağırırken başka firmanın görevi sayılmaz."""
        director = user_factory(username="dir7", firm="inventist", permission_level="it_director", is_admin=True)
        other = user_factory(username="assos_st", firm="assos", permission_level="junior")
        task_factory(user_id=other.id, title="Assos istatistik görevi", category="other")

        login_as(director)
        resp = client.get(f"/api/stats?user_id={other.id}")
        assert resp.status_code == 403
