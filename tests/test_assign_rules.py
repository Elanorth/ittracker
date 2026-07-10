"""
test_assign_rules.py — v5.19 Havuz D2 — Portal case otomatik-atama kural motoru.

- Master toggle (portal_auto_assign) kapalıyken kural olsa da case havuza düşer.
- Toggle açıkken: firma + kategori + keyword eşleşen ilk kural (priority) atar.
- Eşleşme yoksa / hedef kapsam dışı / pasif kural → havuz.
- CRUD: super_admin kural ekler-siler; director kapsam kontrolü; toggle super_admin.
"""

import pytest

import app as app_module
from models.database import AssignRule, Task, db, set_setting


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    app_module._PORTAL_HITS.clear()
    yield
    app_module._PORTAL_HITS.clear()


def _enable(on=True):
    set_setting("portal_auto_assign", "1" if on else "0")
    db.session.commit()


def _rule(target, firm="inventist", category="", keyword="", priority=100, enabled=True):
    r = AssignRule(
        firm=firm,
        category=category,
        keyword=keyword,
        target_user_id=target.id,
        priority=priority,
        enabled=enabled,
    )
    db.session.add(r)
    db.session.commit()
    return r


def _open(client, firm="inventist", subject="Yazıcı arızası", category="support"):
    return client.post(
        "/portal/api/cases",
        json={
            "firm": firm,
            "name": "Ali Veli",
            "email": "ali@x.com",
            "subject": subject,
            "category": category,
            "description": "Otomatik atama testi için en az altmış karakter olması gereken uzun açıklama metni.",
        },
    ).get_json()["case_code"]


def _task(code):
    return Task.query.filter_by(case_code=code).first()


class TestMatcher:
    def test_toggle_kapali_havuza(self, db, client, user_factory):
        u = user_factory(username="aa_off", firm="inventist", permission_level="it_specialist")
        _rule(u, keyword="yazıcı")
        _enable(False)
        code = _open(client, subject="Yazıcı arızası")
        assert _task(code).user_id is None  # toggle kapalı → havuz

    def test_keyword_eslesme_atar(self, db, client, user_factory):
        u = user_factory(username="aa_kw", firm="inventist", permission_level="it_specialist")
        _rule(u, keyword="yazıcı")
        _enable(True)
        code = _open(client, subject="Yazıcı çalışmıyor")
        assert _task(code).user_id == u.id

    def test_keyword_tr_buyuk_i(self, db, client, user_factory):
        # "İnternet" konusu, kural keyword'ü "internet" (küçük) — TR-lower eşleşmeli
        u = user_factory(username="aa_tr", firm="inventist", permission_level="it_specialist")
        _rule(u, keyword="internet")
        _enable(True)
        code = _open(client, subject="İNTERNET yok")
        assert _task(code).user_id == u.id

    def test_keyword_yok_havuza(self, db, client, user_factory):
        u = user_factory(username="aa_nm", firm="inventist", permission_level="it_specialist")
        _rule(u, keyword="vpn")
        _enable(True)
        code = _open(client, subject="Yazıcı arızası")
        assert _task(code).user_id is None  # keyword yok → havuz

    def test_priority_kucuk_kazanir(self, db, client, user_factory):
        a = user_factory(username="aa_p1", firm="inventist", permission_level="it_specialist")
        b = user_factory(username="aa_p2", firm="inventist", permission_level="it_specialist")
        _rule(b, keyword="", priority=200)  # geniş kural, düşük öncelik
        _rule(a, keyword="", priority=10)  # geniş kural, yüksek öncelik
        _enable(True)
        code = _open(client)
        assert _task(code).user_id == a.id  # priority 10 < 200

    def test_firma_disi_kural_atlanir(self, db, client, user_factory):
        # kural firm=assos; case inventist → eşleşmez → havuz
        u = user_factory(username="aa_fs", firm="assos", permission_level="it_specialist")
        _rule(u, firm="assos", keyword="")
        _enable(True)
        code = _open(client, firm="inventist")
        assert _task(code).user_id is None

    def test_pasif_kural_atlanir(self, db, client, user_factory):
        u = user_factory(username="aa_dis", firm="inventist", permission_level="it_specialist")
        _rule(u, keyword="", enabled=False)
        _enable(True)
        code = _open(client)
        assert _task(code).user_id is None

    def test_hedef_kapsam_disi_atlanir(self, db, client, user_factory):
        # hedef kullanıcı assos'ta ama kural global (firm=""); case inventist →
        # has_firm_scope(inventist) False → atlanır → havuz
        u = user_factory(username="aa_scope", firm="assos", permission_level="junior")
        _rule(u, firm="", keyword="")
        _enable(True)
        code = _open(client, firm="inventist")
        assert _task(code).user_id is None

    def test_kategori_filtresi(self, db, client, user_factory):
        u = user_factory(username="aa_cat", firm="inventist", permission_level="it_specialist")
        _rule(u, category="infra", keyword="")
        _enable(True)
        # support kategorili case → infra kuralı eşleşmez
        assert _task(_open(client, category="support")).user_id is None
        # infra kategorili case → eşleşir
        assert _task(_open(client, category="infra")).user_id == u.id


class TestToggleEndpoint:
    def test_super_admin_acar(self, db, client, user_factory, login_as):
        sa = user_factory(username="tg_sa", permission_level="super_admin", is_admin=True)
        login_as(sa)
        assert client.get("/api/settings/auto-assign").get_json()["enabled"] is False
        r = client.post("/api/settings/auto-assign", json={"enabled": True})
        assert r.status_code == 200 and r.get_json()["enabled"] is True
        assert client.get("/api/settings/auto-assign").get_json()["enabled"] is True

    def test_director_403(self, db, client, user_factory, login_as):
        d = user_factory(username="tg_dir", firm="inventist", permission_level="it_director")
        login_as(d)
        assert client.post("/api/settings/auto-assign", json={"enabled": True}).status_code == 403


class TestRuleCRUD:
    def test_super_admin_ekler_listeler_siler(self, db, client, user_factory, login_as):
        sa = user_factory(username="cr_sa", permission_level="super_admin", is_admin=True)
        tgt = user_factory(username="cr_tgt", firm="inventist", permission_level="it_specialist")
        login_as(sa)
        r = client.post(
            "/api/assign-rules",
            json={"firm": "inventist", "keyword": "vpn", "target_user_id": tgt.id, "priority": 5},
        )
        assert r.status_code == 201
        rid = r.get_json()["id"]
        lst = client.get("/api/assign-rules").get_json()
        assert any(x["id"] == rid and x["keyword"] == "vpn" for x in lst)
        assert client.delete(f"/api/assign-rules/{rid}").status_code == 200
        assert all(x["id"] != rid for x in client.get("/api/assign-rules").get_json())

    def test_patch_toggle_enabled(self, db, client, user_factory, login_as):
        sa = user_factory(username="pt_sa", permission_level="super_admin", is_admin=True)
        tgt = user_factory(username="pt_t", firm="inventist", permission_level="it_specialist")
        login_as(sa)
        rid = client.post("/api/assign-rules", json={"firm": "inventist", "target_user_id": tgt.id}).get_json()["id"]
        r = client.patch(f"/api/assign-rules/{rid}", json={"enabled": False})
        assert r.status_code == 200 and r.get_json()["enabled"] is False

    def test_director_global_kural_403(self, db, client, user_factory, login_as):
        d = user_factory(username="dg_dir", firm="inventist", permission_level="it_director")
        tgt = user_factory(username="dg_t", firm="inventist", permission_level="it_specialist")
        login_as(d)
        # firm boş = global → director yasak
        r = client.post("/api/assign-rules", json={"firm": "", "target_user_id": tgt.id})
        assert r.status_code == 403

    def test_director_kapsam_disi_firma_403(self, db, client, user_factory, login_as):
        d = user_factory(username="ds_dir", firm="inventist", permission_level="it_director")
        tgt = user_factory(username="ds_t", firm="assos", permission_level="it_specialist")
        login_as(d)
        r = client.post("/api/assign-rules", json={"firm": "assos", "target_user_id": tgt.id})
        assert r.status_code == 403

    def test_hedef_zorunlu_400(self, db, client, user_factory, login_as):
        sa = user_factory(username="hz_sa", permission_level="super_admin", is_admin=True)
        login_as(sa)
        assert client.post("/api/assign-rules", json={"firm": "inventist"}).status_code == 400
