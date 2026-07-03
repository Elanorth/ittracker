"""
test_security_hardening_v2.py — v5.11 güvenlik sertleştirmeleri.

Kapsam:
1. Config backup upload uzantı whitelist'i (storage.ALLOWED_EXTENSIONS) gerçekten
   uygulanıyor mu — izinsiz uzantı ValueError; endpoint 400.
2. /login brute-force koruması — (ip, username) başına eşik aşımında 429.
3. Temel güvenlik başlıkları (after_request).
"""

import io

import app as app_module
from services.storage import ALLOWED_EXTENSIONS, save_backup_file


class _FakeUpload:
    """save_backup_file'ın beklediği minimum arayüz (filename + save)."""

    def __init__(self, filename):
        self.filename = filename
        self.saved_to = None

    def save(self, path):
        self.saved_to = path


class TestUploadExtensionWhitelist:
    def test_izinsiz_uzanti_valueerror(self, tmp_path, monkeypatch):
        """.exe gibi izinsiz uzantı ValueError fırlatır, dosya diske YAZILMAZ."""
        monkeypatch.setattr("services.storage.BACKUP_DIR", str(tmp_path))
        up = _FakeUpload("malware.exe")
        try:
            save_backup_file(up, 1, 1)
            raise AssertionError("İzinsiz uzantı için ValueError beklenirdi")
        except ValueError:
            pass
        assert up.saved_to is None

    def test_izinli_uzanti_kaydeder(self, tmp_path, monkeypatch):
        """İzinli uzantı (.cfg) sorunsuz kaydedilir."""
        assert ".cfg" in ALLOWED_EXTENSIONS
        monkeypatch.setattr("services.storage.BACKUP_DIR", str(tmp_path))
        up = _FakeUpload("router.cfg")
        path = save_backup_file(up, 5, 9)
        assert path.endswith(".cfg")
        assert up.saved_to == path

    def test_api_izinsiz_uzanti_400(self, db, client, user_factory, login_as):
        """POST /api/tasks (backup + .exe) → 400, görev de oluşmaz."""
        admin = user_factory(username="sec_up", permission_level="super_admin", is_admin=True)
        login_as(admin)
        data = {
            "title": "Config yedek",
            "category": "backup",
            "firm": "inventist",
            "backup_file": (io.BytesIO(b"MZ..."), "payload.exe"),
        }
        resp = client.post("/api/tasks", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert "izin veril" in resp.get_json()["error"].lower()


class TestLoginRateLimit:
    def test_esik_asiminda_429(self, db, client):
        """Aynı kullanıcı adına 5 başarısız denemeden sonra 429 döner."""
        app_module._LOGIN_FAILS.clear()
        payload = {"username": "bruteforce_hedef", "password": "yanlis"}
        for _ in range(app_module._LOGIN_MAX_FAILS):
            r = client.post("/login", json=payload)
            assert r.status_code in (401, 403)  # başarısız ama henüz limitli değil
        blocked = client.post("/login", json=payload)
        assert blocked.status_code == 429
        assert "deneme" in blocked.get_json()["error"].lower()
        app_module._LOGIN_FAILS.clear()


class TestSecurityHeaders:
    def test_temel_basliklar(self, client):
        """after_request temel güvenlik başlıklarını ekler."""
        r = client.get("/login")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("Referrer-Policy") == "same-origin"
