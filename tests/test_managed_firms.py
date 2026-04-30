"""
test_managed_firms.py — v4.9 many-to-many firma yönetimi migration testleri.

Bu dosyadaki tüm testler @pytest.mark.skip ile işaretlidir.
Migration uygulandığında skip kaldırılır ve testler geçmeye başlamalıdır.

Planlanan iş kuralları (henüz implement edilmedi):
- User.managed_firms: it_director'ın yönettiği firma listesi (many-to-many).
- User.firm: kullanıcının kendi firması — string olarak KALIR, değişmez.
- it_director 2+ firma yönetebilir.
- Geriye dönük uyumluluk: migration sonrası mevcut it_director'ların
  managed_firms'ı kendi firm'lerini içerecek şekilde otomatik doldurulur.
- /api/dashboard/firm-summary: her yönetilen firma için aggregated görev özeti.
- /api/firm/users v4.9: managed_firms içindeki TÜM firmaların kullanıcılarını listeler.
"""

import pytest


class TestManagedFirmsModel:
    """User.managed_firms ilişkisi — model seviyesi testler."""

    def test_managed_firms_iliskisi_var(self, db, user_factory):
        """
        User.managed_firms özelliği mevcut ve kullanılabilir.
        Beklenen: User modelinde managed_firms çoktan-çoğa ilişki tanımlı.
        """
        user = user_factory(username="mfm_u1", firm="inventist", permission_level="it_director")
        assert hasattr(user, "managed_firms"), "User.managed_firms özelliği tanımlı olmalı"

    def test_it_director_birden_fazla_firma_yonetebilir(self, db, user_factory):
        """
        it_director 2+ firma yönetebilir (kendi firma'sı + ek olarak yönettiği firmalar).
        Beklenen: managed_firms listesi kendi firma'sı + manuel eklenen firmaları içerir.
        """
        from models.database import Firm
        director = user_factory(username="mfm_u2", firm="inventist", permission_level="it_director")
        # Auto-link: director.managed_firms zaten 'inventist' içerir.
        firm_a = Firm(name="Test Firma A", slug="test-firma-a")
        firm_b = Firm(name="Test Firma B", slug="test-firma-b")
        db.session.add_all([firm_a, firm_b])
        db.session.flush()

        director.managed_firms.append(firm_a)
        director.managed_firms.append(firm_b)
        db.session.commit()

        from models.database import User
        refreshed = User.query.get(director.id)
        slugs = {f.slug for f in refreshed.managed_firms}
        # Kendi firma'sı (auto-link) + iki ek = 3 firma yönetiyor
        assert "inventist" in slugs
        assert "test-firma-a" in slugs
        assert "test-firma-b" in slugs
        assert len(refreshed.managed_firms) >= 2

    def test_managed_firms_association_tablosu_var(self, db):
        """
        user_managed_firms association tablosu veritabanında mevcut.
        Beklenen: SQLAlchemy metadata'da tablo tanımlı.
        """
        from models.database import db as _db
        assert "user_managed_firms" in _db.metadata.tables

    def test_yeni_director_kendi_firmasini_otomatik_yonetir(self, db, user_factory):
        """
        Yeni oluşturulan it_director'ın managed_firms listesi kendi firma'sını
        otomatik içerir (after_insert event listener üzerinden auto-link).

        Bu, "yeni IT Müdürü en azından kendi firma'sını yönetir" sözleşmesini
        garanti eder — backend `_resolve_scope_uid` ve `firm_users` bu varsayım
        üzerinde çalışır.
        """
        director = user_factory(username="mfm_u3", firm="assos", permission_level="it_director")
        from models.database import User
        refreshed = User.query.get(director.id)
        slugs = [f.slug for f in refreshed.managed_firms]
        assert "assos" in slugs
        assert len(refreshed.managed_firms) == 1

    def test_director_olmayan_kullanici_auto_link_yapilmaz(self, db, user_factory):
        """
        permission_level it_director değilse auto-link tetiklenmez.
        Junior/specialist/manager kullanıcıların managed_firms'ı boş kalır.
        """
        junior = user_factory(username="mfm_u3b", firm="inventist", permission_level="junior")
        from models.database import User
        refreshed = User.query.get(junior.id)
        assert len(refreshed.managed_firms) == 0


class TestManagedFirmsMigrationBackcompat:
    """Migration geriye dönük uyumluluk — mevcut it_director'lar."""

    def test_mevcut_director_managed_firms_otomatik_doluyor(self, db, user_factory):
        """
        v4.9 migration çalıştıktan sonra, mevcut it_director'ların managed_firms
        listesi kendi firm'lerini (User.firm) içerecek şekilde doldurulmuş olmalı.
        Beklenen: migration sonrası direktörün managed_firms'ı, firm=me.firm olan
        Firm nesnesi ile dolu.
        """
        from models.database import Firm
        inv_firm = Firm.query.filter_by(slug="inventist").first()
        director = user_factory(username="mfm_bc1", firm="inventist", permission_level="it_director")

        # Migration sonrası durumu simüle et
        # Bu test migration fonksiyonunu çağırmalı ve doğrulamalı
        from models.database import User
        refreshed = User.query.get(director.id)
        firm_names = [f.name for f in refreshed.managed_firms]
        assert any("inventist" in n.lower() or "İnventist" in n for n in firm_names), (
            "Migration sonrası it_director managed_firms kendi firmasını içermeli"
        )

    def test_resolve_scope_uid_managed_firms_destekliyor(self, db, client, user_factory, login_as, task_factory):
        """
        v4.9 _resolve_scope_uid: it_director managed_firms içindeki firma kullanıcısına
        erişebilir (sadece User.firm değil).
        Beklenen: director.managed_firms içinde firma olan kullanıcıya erişim izinli.
        """
        from models.database import Firm
        director = user_factory(username="mfm_bc2", firm="inventist", permission_level="it_director")
        target_user = user_factory(username="mfm_bc2_t", firm="assos", permission_level="junior")

        # Director 'assos' firmasını da yönetiyor (managed_firms'a ekle)
        assos_firm = Firm.query.filter_by(slug="assos").first()
        if assos_firm:
            director.managed_firms.append(assos_firm)
            db.session.commit()

        task_factory(user_id=target_user.id, title="Assos görevi", category="other")
        login_as(director)

        # Artık assos kullanıcısına erişebilmeli
        resp = client.get(f"/api/tasks?user_id={target_user.id}")
        assert resp.status_code == 200, (
            "Director managed_firms içindeki firmaya erişebilmeli"
        )


class TestFirmSummaryEndpoint:
    """/api/dashboard/firm-summary endpoint testleri."""

    def test_yetkisiz_kullanici_403(self, db, client, user_factory, login_as):
        """
        it_manager veya junior /api/dashboard/firm-summary'ye 403 alır.
        Beklenen: endpoint @director_required korumalı.
        """
        manager = user_factory(username="fs_mgr", firm="inventist", permission_level="it_manager")
        login_as(manager)
        resp = client.get("/api/dashboard/firm-summary")
        assert resp.status_code == 403

    def test_it_director_sadece_kendi_yonettiklerini_gorer(self, db, client, user_factory, login_as, task_factory):
        """
        it_director /api/dashboard/firm-summary çağırırsa yalnızca
        managed_firms listesindeki firmaların özetini görür.
        Beklenen: response yalnızca director.managed_firms kapsamındaki firmalar.
        """
        director = user_factory(username="fs_dir", firm="inventist", permission_level="it_director", is_admin=True)
        inv_user = user_factory(username="fs_inv", firm="inventist", permission_level="junior")
        assos_user = user_factory(username="fs_assos", firm="assos", permission_level="junior")
        task_factory(user_id=inv_user.id, title="İnventist görevi", category="other")
        task_factory(user_id=assos_user.id, title="Assos görevi", category="other")

        login_as(director)
        resp = client.get("/api/dashboard/firm-summary")
        assert resp.status_code == 200
        data = resp.get_json()
        # data: [{"firm": "inventist", "total": N, "done": N, ...}, ...]
        firm_names = [entry["firm"] for entry in data]
        assert "inventist" in firm_names or "İnventist" in firm_names
        assert "assos" not in firm_names, "Yönetilmeyen firma görünmemeli"

    def test_super_admin_tum_firmalari_gorer(self, db, client, user_factory, login_as, task_factory):
        """
        super_admin /api/dashboard/firm-summary çağırırsa tüm firmaların özetini görür.
        Beklenen: response tüm firmalar.
        """
        admin = user_factory(username="fs_sa", firm="inventist", permission_level="super_admin", is_admin=True)
        inv_user = user_factory(username="fs_inv2", firm="inventist", permission_level="junior")
        assos_user = user_factory(username="fs_assos2", firm="assos", permission_level="junior")
        task_factory(user_id=inv_user.id, title="Görev 1", category="other")
        task_factory(user_id=assos_user.id, title="Görev 2", category="other")

        login_as(admin)
        resp = client.get("/api/dashboard/firm-summary")
        assert resp.status_code == 200
        data = resp.get_json()
        firm_names = [entry["firm"] for entry in data]
        # Her iki firma da listede olmalı
        has_inventist = any("inventist" in n.lower() for n in firm_names)
        has_assos = any("assos" in n.lower() for n in firm_names)
        assert has_inventist and has_assos

    def test_response_alanlari_eksiksiz(self, db, client, user_factory, login_as, task_factory):
        """
        /api/dashboard/firm-summary response'u her firma için gerekli alanları içerir.
        Beklenen alanlar: firm, total, done, overdue, rate, sla_breach
        """
        admin = user_factory(username="fs_fields", firm="inventist", permission_level="super_admin", is_admin=True)
        inv_user = user_factory(username="fs_inv_f", firm="inventist", permission_level="junior")
        task_factory(user_id=inv_user.id, title="Görev", category="other")

        login_as(admin)
        resp = client.get("/api/dashboard/firm-summary")
        assert resp.status_code == 200
        data = resp.get_json()
        if data:
            required_fields = {"firm", "total", "done", "overdue", "rate"}
            for entry in data:
                for field in required_fields:
                    assert field in entry, f"'{field}' alanı firma özetinde eksik"

    def test_50_firmali_performans_500ms(self, db, client, user_factory, login_as, task_factory, app):
        """
        50+ firmalı durumda /api/dashboard/firm-summary 500ms altında cevap verir.
        Bu basit bir benchmark testi.
        """
        import time
        from models.database import Firm, Team

        admin = user_factory(username="fs_perf", firm="inventist", permission_level="super_admin", is_admin=True)

        # 50 firma oluştur
        for i in range(50):
            f = Firm(name=f"Test Firma {i}", slug=f"test-firma-{i}")
            db.session.add(f)
        db.session.commit()

        login_as(admin)

        start = time.monotonic()
        resp = client.get("/api/dashboard/firm-summary")
        elapsed_ms = (time.monotonic() - start) * 1000

        assert resp.status_code == 200
        assert elapsed_ms < 500, f"Endpoint {elapsed_ms:.0f}ms aldı (hedef: <500ms)"


class TestFirmUsersV49:
    """/api/firm/users v4.9 davranışı — it_director managed_firms kapsamı."""

    def test_director_managed_firms_tum_kullanicilari_gorer(self, db, client, user_factory, login_as):
        """
        v4.9'da it_director /api/firm/users çağırırken managed_firms içindeki
        TÜM firmaların kullanıcılarını listeler (sadece User.firm değil).
        """
        from models.database import Firm
        director = user_factory(username="fuv49_dir", firm="inventist", permission_level="it_director", is_admin=True)
        assos_user = user_factory(username="fuv49_assos", firm="assos", permission_level="junior")

        # Director assos'u da yönetiyor
        assos_firm = Firm.query.filter_by(slug="assos").first()
        if assos_firm:
            director.managed_firms.append(assos_firm)
            db.session.commit()

        login_as(director)
        resp = client.get("/api/firm/users")
        assert resp.status_code == 200
        data = resp.get_json()
        ids = {d["id"] for d in data}
        assert assos_user.id in ids, "managed_firms içindeki firma kullanıcısı listede görünmeli"


class TestManagedFirmsDetailEndpoint:
    """/api/managed-firms/detail v5.0 — Yönettiğim Firmalar sayfası ana endpoint."""

    def test_yetkisiz_kullanici_403(self, db, client, user_factory, login_as):
        """junior /api/managed-firms/detail'a 403 alır."""
        junior = user_factory(username="mfd_jr", firm="inventist", permission_level="junior")
        login_as(junior)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 403

    def test_director_sadece_kendi_yonettiklerini_gorer(self, db, client, user_factory, login_as):
        """it_director sadece managed_firms + kendi firma'sının detayını görür."""
        director = user_factory(username="mfd_dir", firm="inventist", permission_level="it_director", is_admin=True)
        login_as(director)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        data = resp.get_json()
        slugs = [d["slug"] for d in data]
        assert "inventist" in slugs
        assert "assos" not in slugs, "Yönetilmeyen firma görünmemeli"

    def test_super_admin_tum_firmalari_gorer(self, db, client, user_factory, login_as):
        """super_admin tüm firmaları görür."""
        admin = user_factory(username="mfd_sa", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        slugs = [d["slug"] for d in resp.get_json()]
        assert "inventist" in slugs and "assos" in slugs

    def test_response_zorunlu_alanlar(self, db, client, user_factory, login_as, task_factory):
        """Her firma kaydı zorunlu alanları içerir."""
        admin = user_factory(username="mfd_fields", firm="inventist", permission_level="super_admin", is_admin=True)
        u = user_factory(username="mfd_u", firm="inventist", permission_level="junior")
        task_factory(user_id=u.id, title="Sunucu güncellemesi", category="other")
        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        data = resp.get_json()
        for entry in data:
            assert "slug" in entry and "name" in entry
            assert "kpi" in entry and all(k in entry["kpi"] for k in ("total", "done", "overdue", "rate"))
            assert "trend" in entry and len(entry["trend"]) == 6
            assert "category_breakdown" in entry
            assert "overdue_top3" in entry
            assert "users" in entry
            assert "sla_breach_count" in entry

    def test_geciken_sayisina_gore_sirali(self, db, client, user_factory, login_as, task_factory):
        """Sıralama: geciken sayısı azalan (en kritik üstte)."""
        from datetime import date, timedelta
        admin = user_factory(username="mfd_sort", firm="inventist", permission_level="super_admin", is_admin=True)
        u_inv = user_factory(username="mfd_sort_inv", firm="inventist", permission_level="junior")
        u_assos = user_factory(username="mfd_sort_assos", firm="assos", permission_level="junior")
        # Assos'a 2 geciken görev, İnventist'e 1 geciken görev
        old_deadline = date.today() - timedelta(days=10)
        t1 = task_factory(user_id=u_assos.id, title="Geciken 1", category="support", firm="assos")
        t1.deadline = old_deadline
        t2 = task_factory(user_id=u_assos.id, title="Geciken 2", category="support", firm="assos")
        t2.deadline = old_deadline
        t3 = task_factory(user_id=u_inv.id, title="Geciken 3", category="support", firm="inventist")
        t3.deadline = old_deadline
        from models.database import db as _db
        _db.session.commit()

        login_as(admin)
        resp = client.get("/api/managed-firms/detail")
        assert resp.status_code == 200
        data = resp.get_json()
        # İlk firma assos olmalı (2 geciken), ikinci inventist (1 geciken)
        assert data[0]["slug"] == "assos"
        assert data[0]["kpi"]["overdue"] == 2
        # İnventist daha sonra
        inv_idx = next((i for i, d in enumerate(data) if d["slug"] == "inventist"), None)
        assert inv_idx is not None and inv_idx > 0

    def test_period_parametresi_kabul_edilir(self, db, client, user_factory, login_as):
        """period=3m / 1y parametresi 200 döner (kategori dağılımı periyota göre)."""
        admin = user_factory(username="mfd_period", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        for p in ("1m", "3m", "1y", "invalid"):
            resp = client.get(f"/api/managed-firms/detail?period={p}")
            assert resp.status_code == 200, f"period={p} 200 dönmedi"
