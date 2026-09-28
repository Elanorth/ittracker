"""
test_case_notifications.py — v5.22 — Portal case 'IT ilgisi bekliyor' (it_unread)
bayrağı + bildirim zili new_cases grubu.

- Yeni case açılınca it_unread=True.
- IT case mesajlarını GÖRÜNTÜLEYİNCE it_unread=False.
- Reporter yanıt yazınca tekrar True.
- IT yanıt/iç not yazınca False.
- /api/notifications/preview new_cases: atanan bana + havuz (firma kapsamı) görünür,
  kapsam dışı havuz görünmez.
"""

import pytest

import app as app_module
from models.database import Task, db


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


def _open(client, firm="inventist", subject="Yazıcı arızası"):
    return client.post(
        "/portal/api/cases",
        json={
            "firm": firm,
            "name": "Ali Veli",
            "email": "ali@x.com",
            "subject": subject,
            "category": "support",
            "description": "Bildirim testi için en az altmış karakter olması gereken uzunca bir açıklama metni.",
        },
    ).get_json()["case_code"]


def _task(code):
    return Task.query.filter_by(case_code=code).first()


class TestUnreadLifecycle:
    def test_yeni_case_unread(self, db, client):
        t = _task(_open(client))
        assert t.it_unread is True

    def test_it_goruntuleyince_temizlenir(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_a", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        r = client.get(f"/api/tasks/{task.id}/messages")
        assert r.status_code == 200
        assert db.session.get(Task, task.id).it_unread is False

    def test_reporter_yaniti_tekrar_unread(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_b", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.get(f"/api/tasks/{task.id}/messages")  # temizle
        # reporter yanıt (login yok)
        client.post("/portal/api/case/reply", json={"case_code": code, "email": "ali@x.com", "body": "Devam ediyor"})
        assert db.session.get(Task, task.id).it_unread is True

    def test_it_yaniti_temizler(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_c", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "it", "body": "Bakıyoruz"})
        assert db.session.get(Task, task.id).it_unread is False

    def test_ic_not_da_temizler(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cn_d", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.post(f"/api/tasks/{task.id}/messages", json={"sender_type": "internal", "body": "iç not"})
        assert db.session.get(Task, task.id).it_unread is False


class TestCaseClosure:
    def test_kapat_resolved_ve_temizler(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cl_a", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        r = client.patch(f"/api/tasks/{task.id}", json={"is_done": True})
        assert r.status_code == 200
        t2 = db.session.get(Task, task.id)
        assert t2.is_done is True
        assert t2.it_unread is False  # kapanınca ilgi bayrağı düşer
        # Portal takip: status resolved
        pub = client.post("/portal/api/lookup", json={"case_code": code, "email": "ali@x.com"}).get_json()
        assert pub["status"] == "resolved"

    def test_yeniden_ac(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        admin = user_factory(username="cl_b", firm="inventist", permission_level="super_admin", is_admin=True)
        login_as(admin)
        client.patch(f"/api/tasks/{task.id}", json={"is_done": True})
        client.patch(f"/api/tasks/{task.id}", json={"is_done": False})
        pub = client.post("/portal/api/lookup", json={"case_code": code, "email": "ali@x.com"}).get_json()
        assert pub["status"] in ("received", "in_progress")  # resolved değil


class TestNotificationPreview:
    def test_havuz_kapsam_ici_gorunur(self, db, client, user_factory, login_as):
        _open(client, "inventist")
        u = user_factory(username="np_u", firm="inventist", permission_level="it_specialist")
        login_as(u)
        d = client.get("/api/notifications/preview").get_json()
        assert any(c["kind"] == "new" and c["pooled"] for c in d["new_cases"])
        assert d["total"] >= 1

    def test_kapsam_disi_havuz_gorunmez(self, db, client, user_factory, login_as):
        _open(client, "assos")  # assos havuzu
        u = user_factory(username="np_scope", firm="inventist", permission_level="junior")
        login_as(u)
        d = client.get("/api/notifications/preview").get_json()
        assert d["new_cases"] == []

    def test_super_admin_tum_havuz(self, db, client, user_factory, login_as):
        _open(client, "inventist")
        _open(client, "assos")
        sa = user_factory(username="np_sa", permission_level="super_admin", is_admin=True)
        login_as(sa)
        firms = {c["firm"] for c in client.get("/api/notifications/preview").get_json()["new_cases"]}
        assert "inventist" in firms and "assos" in firms

    def test_it_gorunce_zilden_duser(self, db, client, user_factory, login_as):
        code = _open(client, "inventist")
        task = _task(code)
        u = user_factory(username="np_seen", firm="inventist", permission_level="it_specialist")
        login_as(u)
        assert len(client.get("/api/notifications/preview").get_json()["new_cases"]) >= 1
        client.get(f"/api/tasks/{task.id}/messages")  # görüntüle → temizle
        assert client.get("/api/notifications/preview").get_json()["new_cases"] == []


class TestPoolEmailRecipients:
    """v5.97 — Havuza düşen portal case'i için send_case_new_to_it çağrısının
    firma kapsamındaki TÜM aktif IT çalışanlarına gitmesi gerekir (junior dahil),
    sadece director+super_admin değil. Aksi halde alt kademe havuzu görmez ve
    üstlenme gecikir.
    """

    def _capture(self, monkeypatch):
        calls = []

        def _fake(email, case_code, subject, firm, reporter_name, assigned):
            calls.append({"email": email, "assigned": assigned, "case_code": case_code})

        import services.mailer as mailer_mod

        monkeypatch.setattr(mailer_mod, "send_case_new_to_it", _fake)
        return calls

    def test_havuz_tum_it_calisanlarina_mail(self, db, client, user_factory, monkeypatch):
        # inventist firmasında farklı seviyelerde IT çalışanları
        junior = user_factory(username="pool_j", firm="inventist", permission_level="junior")
        specialist = user_factory(username="pool_s", firm="inventist", permission_level="it_specialist")
        manager = user_factory(username="pool_m", firm="inventist", permission_level="it_manager")
        director = user_factory(username="pool_d", firm="inventist", permission_level="it_director")
        calls = self._capture(monkeypatch)
        _open(client, "inventist")
        emails = {c["email"] for c in calls}
        # Havuz → hepsi bildirim almalı
        assert junior.email in emails, "junior havuz bildirimini almalı"
        assert specialist.email in emails, "it_specialist havuz bildirimini almalı"
        assert manager.email in emails, "it_manager havuz bildirimini almalı"
        assert director.email in emails, "it_director havuz bildirimini almalı"
        assert all(c["assigned"] is False for c in calls), "havuz bildirimi assigned=False olmalı"

    def test_havuz_kapsam_disi_it_mail_almaz(self, db, client, user_factory, monkeypatch):
        # assos firmasındaki bir junior; case inventist havuzunda → mail almamalı
        assos_junior = user_factory(username="pool_ax", firm="assos", permission_level="junior")
        inv_junior = user_factory(username="pool_ix", firm="inventist", permission_level="junior")
        calls = self._capture(monkeypatch)
        _open(client, "inventist")
        emails = {c["email"] for c in calls}
        assert inv_junior.email in emails
        assert assos_junior.email not in emails, "kapsam dışı firma juniorı bildirim almamalı"

    def test_pasif_kullanici_mail_almaz(self, db, client, user_factory, monkeypatch):
        active = user_factory(username="pool_act", firm="inventist", permission_level="junior")
        inactive = user_factory(username="pool_ina", firm="inventist", permission_level="junior", active=False)
        calls = self._capture(monkeypatch)
        _open(client, "inventist")
        emails = {c["email"] for c in calls}
        assert active.email in emails
        assert inactive.email not in emails, "pasif kullanıcı bildirim almamalı"


class TestReporterReplyRecipients:
    """v5.97 — Reporter portal'dan yanıt yazınca: case atanmışsa yalnız
    sahibine, havuzdaysa firma kapsamındaki tüm aktif IT'ye mail atılmalı.
    Önceki davranış: havuzdaki case'e yanıt gelince kimseye mail düşmüyordu.
    """

    def _capture(self, monkeypatch):
        calls = []

        def _fake(email, case_code, subject, reporter_name):
            calls.append({"email": email, "case_code": case_code})

        import services.mailer as mailer_mod

        monkeypatch.setattr(mailer_mod, "send_case_user_replied", _fake)
        return calls

    def test_havuzdaki_case_yanit_tum_kapsam_ici_it(self, db, client, user_factory, monkeypatch):
        junior = user_factory(username="rr_j", firm="inventist", permission_level="junior")
        specialist = user_factory(username="rr_s", firm="inventist", permission_level="it_specialist")
        assos_junior = user_factory(username="rr_a", firm="assos", permission_level="junior")
        code = _open(client, "inventist")
        task = _task(code)
        assert task.user_id is None, "havuzda beklenir"

        calls = self._capture(monkeypatch)
        r = client.post(
            "/portal/api/case/reply",
            json={"case_code": code, "email": "ali@x.com", "body": "Ek bilgi paylaşıyorum, hâlâ sorun sürüyor."},
        )
        assert r.status_code == 201
        emails = {c["email"] for c in calls}
        assert junior.email in emails
        assert specialist.email in emails
        assert assos_junior.email not in emails, "kapsam dışı IT mail almamalı"

    def test_atanmis_case_yanit_yalniz_sahibine(self, db, client, user_factory, monkeypatch, login_as):
        owner = user_factory(username="rr_own", firm="inventist", permission_level="it_specialist")
        other = user_factory(username="rr_oth", firm="inventist", permission_level="junior")
        code = _open(client, "inventist")
        task = _task(code)
        # havuzdan üstlen → atanmış
        login_as(owner)
        r = client.post(f"/api/tasks/{task.id}/claim")
        assert r.status_code == 200
        # oturumu kapat ki portal endpoint anon çalışsın
        with client.session_transaction() as s:
            s.clear()

        calls = self._capture(monkeypatch)
        r = client.post(
            "/portal/api/case/reply",
            json={"case_code": code, "email": "ali@x.com", "body": "Yanıt teşekkürler, denemeye devam ediyorum."},
        )
        assert r.status_code == 201
        emails = {c["email"] for c in calls}
        assert owner.email in emails
        assert other.email not in emails, "atanmış case'te yalnız sahibi mail almalı"
