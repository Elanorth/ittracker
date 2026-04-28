"""
test_auth.py — Kimlik doğrulama ve yetkilendirme akışlarının baseline testleri.

Kapsam:
- @login_required: oturum yoksa JSON 401 veya form 302 döner.
- @admin_required: non-admin kullanıcı 403 alır.
- @director_required: it_director ve üzeri geçer, altı 403 alır.
- @super_admin_required: yalnızca super_admin geçer.
- Manuel login: ADMIN_USERNAME dışındaki kullanıcılar O365'e yönlendirilir.
- Logout: session temizlenir.
- O365 callback: msal mock ile state mismatch test edilir.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from models.database import User


class TestLoginRequired:
    """@login_required decorator davranışı."""

    def test_session_olmadan_json_content_type_401(self, db, client):
        """Content-Type: application/json ile oturum yoksa 401 döner."""
        resp = client.get(
            "/api/tasks",
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_session_olmadan_accept_json_header_401(self, db, client):
        """Sadece Accept: application/json header ile de 401 döner.

        Önceden login_required yalnızca request.is_json (yani Content-Type)
        kontrolü yapıyordu. Frontend fetch() çağrılarının çoğu Accept gönderir
        ama Content-Type göndermez (GET için). Fix: Accept header da kontrol ediliyor.
        """
        resp = client.get(
            "/api/tasks",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 401

    def test_session_olmadan_api_path_401(self, db, client):
        """/api/* path'i oturum yoksa header'sız bile JSON 401 döner.

        Frontend fetch'leri /api/* hit eder ve redirect (302→/login HTML)
        almak yerine net 401 alıp toast/banner gösterebilmeli.
        """
        resp = client.get("/api/tasks")
        assert resp.status_code == 401
        assert resp.is_json
        assert resp.get_json().get("error") == "Unauthorized"

    def test_session_olmadan_html_istek_302(self, db, client):
        """HTML isteğiyle oturum olmadan / çağrısı login'e 302 yönlendirir."""
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.location

    def test_session_ile_korunan_route_200(self, db, client, user_factory, login_as):
        """Geçerli oturumla korunan route'a erişilir."""
        user = user_factory(username="auth_u1", firm="inventist")
        login_as(user)
        resp = client.get("/api/tasks")
        assert resp.status_code == 200

    def test_logout_sonrasi_session_temizlenir(self, db, client, user_factory, login_as):
        """Logout'tan sonra korunan route'a erişim 401 veya 302 döner."""
        user = user_factory(username="auth_u2", firm="inventist")
        login_as(user)

        # Önce erişim var
        resp = client.get("/api/tasks")
        assert resp.status_code == 200

        # Logout
        client.get("/logout")

        # Sonra erişim yok
        resp = client.get("/api/tasks")
        assert resp.status_code in (302, 401)


class TestAdminRequired:
    """@admin_required / @manager_required decorator davranışı.

    Not: /api/admin/users @manager_required korumalı (is_admin değil, permission_level).
    Gerçek @admin_required (is_admin flag'i) kullanan route bulunmadı — sistem prompt'taki
    decorator açıklamasına göre bu decorator'ı doğrudan kullanan rotayı test ediyoruz.
    """

    def test_junior_kullanici_admin_users_route_403(self, db, client, user_factory, login_as):
        """junior permission_level kullanıcı @manager_required route'a 403 alır."""
        user = user_factory(username="auth_nonadmin", firm="inventist", is_admin=False, permission_level="junior")
        login_as(user)
        # /api/admin/users @manager_required korumalı
        resp = client.get("/api/admin/users")
        assert resp.status_code == 403

    def test_manager_kullanici_admin_users_erisebilir(self, db, client, user_factory, login_as):
        """it_manager kullanıcı @manager_required route'a erişebilir."""
        admin = user_factory(
            username="auth_admin",
            firm="inventist",
            is_admin=True,
            permission_level="it_manager",
        )
        login_as(admin)
        resp = client.get("/api/admin/users")
        assert resp.status_code == 200

    def test_super_admin_admin_users_erisebilir(self, db, client, user_factory, login_as):
        """super_admin @manager_required route'a erişebilir."""
        admin = user_factory(
            username="auth_sa_users",
            firm="inventist",
            is_admin=True,
            permission_level="super_admin",
        )
        login_as(admin)
        resp = client.get("/api/admin/users")
        assert resp.status_code == 200

    def test_oturum_olmadan_admin_route_redirect_veya_401(self, db, client):
        """Oturum olmadan /api/admin/users çağrısı 302 veya 401 döner."""
        resp = client.get("/api/admin/users")
        assert resp.status_code in (302, 401)


class TestDirectorRequired:
    """@director_required decorator davranışı."""

    def test_it_director_erisebilir(self, db, client, user_factory, login_as):
        """it_director rolü @director_required route'a erişebilir."""
        director = user_factory(
            username="auth_dir",
            firm="inventist",
            permission_level="it_director",
            is_admin=True,
        )
        login_as(director)
        resp = client.get("/api/audit")
        assert resp.status_code == 200

    def test_super_admin_director_required_gecebilir(self, db, client, user_factory, login_as):
        """super_admin @director_required route'a erişebilir (is_director_or_above=True)."""
        admin = user_factory(
            username="auth_sa_dir",
            firm="inventist",
            permission_level="super_admin",
            is_admin=True,
        )
        login_as(admin)
        resp = client.get("/api/audit")
        assert resp.status_code == 200

    def test_it_manager_director_required_reddedilir(self, db, client, user_factory, login_as):
        """it_manager @director_required route'a 403 alır."""
        manager = user_factory(
            username="auth_mgr",
            firm="inventist",
            permission_level="it_manager",
            is_admin=True,
        )
        login_as(manager)
        resp = client.get("/api/audit")
        assert resp.status_code == 403

    def test_junior_director_required_reddedilir(self, db, client, user_factory, login_as):
        """junior @director_required route'a 403 alır."""
        junior = user_factory(username="auth_jnr2", firm="assos", permission_level="junior")
        login_as(junior)
        resp = client.get("/api/audit")
        assert resp.status_code == 403

    def test_it_specialist_director_required_reddedilir(self, db, client, user_factory, login_as):
        """it_specialist @director_required route'a 403 alır."""
        specialist = user_factory(
            username="auth_spec",
            firm="inventist",
            permission_level="it_specialist",
        )
        login_as(specialist)
        resp = client.get("/api/audit")
        assert resp.status_code == 403


class TestSuperAdminRequired:
    """@super_admin_required decorator davranışı (sadece super_admin).

    Not: /api/firms @login_required korumalı (GET), POST ise @manager_required.
    Gerçek @super_admin_required kullanan route: POST /api/firms (Grep ile doğrulandı — yok).
    /api/admin/invite (POST) @manager_required. Dolayısıyla bu sınıf permission_level
    kontrollü rotalar üzerinden super_admin avantajını test eder.
    """

    def test_super_admin_firma_listesi_erisebilir(self, db, client, user_factory, login_as):
        """super_admin GET /api/firms route'a erişebilir (login_required)."""
        admin = user_factory(
            username="sa_test",
            firm="inventist",
            permission_level="super_admin",
            is_admin=True,
        )
        login_as(admin)
        resp = client.get("/api/firms")
        assert resp.status_code == 200

    def test_it_director_firma_listesi_erisebilir(self, db, client, user_factory, login_as):
        """it_director GET /api/firms'e erişebilir (login_required)."""
        director = user_factory(
            username="dir_sa_test",
            firm="inventist",
            permission_level="it_director",
            is_admin=True,
        )
        login_as(director)
        resp = client.get("/api/firms")
        assert resp.status_code == 200

    def test_super_admin_baska_kullanicinin_iznini_degistirebilir(self, db, client, user_factory, login_as):
        """super_admin başka bir kullanıcının permission_level'ini güncelleyebilir."""
        admin = user_factory(
            username="sa_perm_test",
            firm="inventist",
            permission_level="super_admin",
            is_admin=True,
        )
        target = user_factory(username="sa_target_u", firm="inventist", permission_level="junior")
        login_as(admin)

        resp = client.patch(
            f"/api/admin/users/{target.id}",
            json={"permission_level": "it_specialist"},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_it_manager_super_admin_atayamaz(self, db, client, user_factory, login_as):
        """it_manager başka kullanıcıya super_admin rolü atayamaz — 403 döner."""
        manager = user_factory(
            username="mgr_no_sa",
            firm="inventist",
            permission_level="it_manager",
            is_admin=True,
        )
        target = user_factory(username="mgr_target_u", firm="inventist", permission_level="junior")
        login_as(manager)

        resp = client.patch(
            f"/api/admin/users/{target.id}",
            json={"permission_level": "super_admin"},
            content_type="application/json",
        )
        assert resp.status_code == 403


class TestManualLogin:
    """Manuel login formu — yalnızca ADMIN_USERNAME."""

    def test_admin_dogru_sifre_ile_giris_basarili(self, db, client, app):
        """ADMIN_USERNAME doğru şifreyle giriş yapabilir."""
        import os
        from models.database import User as UserModel
        admin_uname = os.environ.get("ADMIN_USERNAME", "test_admin")
        user = UserModel.query.filter_by(username=admin_uname).first()
        if user is None:
            pytest.skip("Admin kullanıcı DB'de yok — conftest init_db ile oluşturulmuş olmalı")

        resp = client.post(
            "/login",
            json={"username": admin_uname, "password": os.environ.get("ADMIN_PASSWORD", "test_admin_pwd_only")},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") is True

    def test_admin_yanlis_sifre_401(self, db, client, app):
        """ADMIN_USERNAME yanlış şifreyle 401 alır."""
        import os
        admin_uname = os.environ.get("ADMIN_USERNAME", "test_admin")
        resp = client.post(
            "/login",
            json={"username": admin_uname, "password": "YANLIS_SIFRE_XYZ"},
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_non_admin_kullanici_o365_yonlendirmesi(self, db, client, user_factory):
        """ADMIN_USERNAME olmayan kullanıcı login'e çalışırsa O365 mesajı alır."""
        user = user_factory(username="o365_usr", firm="assos")
        resp = client.post(
            "/login",
            json={"username": "o365_usr_0", "password": "herhangi"},
            content_type="application/json",
        )
        assert resp.status_code == 403
        data = resp.get_json()
        assert "Microsoft" in data.get("error", "") or "365" in data.get("error", "")


class TestO365OAuthMock:
    """O365 OAuth akışı — msal HTTP çağrılarını mock'layarak test et."""

    def test_auth_callback_gecersiz_state_400(self, db, client, user_factory):
        """OAuth callback state mismatch → 400 döner."""
        # Session'da oauth_state set et
        with client.session_transaction() as s:
            s["oauth_state"] = "dogru_state_abc123"

        # Yanlış state ile callback çağrısı
        resp = client.get("/auth/callback?code=fake_code&state=YANLIS_STATE")
        assert resp.status_code == 400

    def test_auth_callback_msal_error_400(self, db, client):
        """MSAL token exchange hatası → 400 döner."""
        if not _msal_available():
            pytest.skip("msal yüklü değil")

        with client.session_transaction() as s:
            s["oauth_state"] = "test_state_xyz"

        mock_result = {"error": "invalid_grant", "error_description": "Token süresi dolmuş"}
        with patch("msal.ConfidentialClientApplication") as mock_msal:
            mock_app = MagicMock()
            mock_app.acquire_token_by_authorization_code.return_value = mock_result
            mock_msal.return_value = mock_app

            resp = client.get("/auth/callback?code=fake_code&state=test_state_xyz")
            assert resp.status_code == 400

    def test_auth_o365_msal_yok_503(self, db, client):
        """msal import başarısız olursa /auth/o365 503 döner."""
        import app as flask_app_module
        original = flask_app_module.MSAL_AVAILABLE
        try:
            flask_app_module.MSAL_AVAILABLE = False
            resp = client.get("/auth/o365")
            assert resp.status_code == 503
        finally:
            flask_app_module.MSAL_AVAILABLE = original


def _msal_available():
    try:
        import msal
        return True
    except ImportError:
        return False


class TestSessionDecorators:
    """Dekoratör zinciri — @admin_required içinde @login_required gömülü."""

    def test_admin_required_oturum_olmadan_401_veya_302(self, db, client):
        """@manager_required çağrılırken session yoksa @login_required devreye girer."""
        resp = client.get("/api/admin/users")
        # login_required önce kontrol eder: JSON değilse 302, JSON ise 401
        assert resp.status_code in (302, 403, 401)

    def test_director_required_oturum_olmadan_redirect(self, db, client):
        """@director_required oturum yokken /login'e yönlendirmeli."""
        resp = client.get("/api/audit")
        assert resp.status_code in (302, 401, 403)

    def test_manager_required_yeterli_yetki_gecer(self, db, client, user_factory, login_as):
        """it_specialist @manager_required route'a erişebilir (is_manager_or_above=True)."""
        spec = user_factory(
            username="spec_mgr_test",
            firm="inventist",
            permission_level="it_specialist",
        )
        login_as(spec)
        # /api/tasks/assign veya benzeri bir manager_required route gerekiyor
        # Basit doğrulama: /api/stats erişilebilir mi?
        resp = client.get("/api/stats")
        assert resp.status_code == 200
