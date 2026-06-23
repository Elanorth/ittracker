"""Çoklu firma (v4.9) yetki tutarlılığı — F2.3.

Bug: görüntüleme/oluşturma `has_firm_scope` (çoklu firma) kullanırken;
düzenleme/silme/alarm/audit eski tek-firma `owner.firm == me.firm` kontrolünü
kullanıyordu. Sonuç: çoklu firma yöneten it_director ikinci firmayı görür/oluşturur
ama düzenleyemez/silemez/audit'ini göremezdi.

Bu testler: director YÖNETTİĞİ firmadaki görevleri düzenleyebilmeli; yönetmediği
firmada hâlâ engellenmeli (regresyon); it_manager başkasının görevini düzenleyememeli
(yetki genişlemesi olmamalı).
"""

from models.database import AuditLog, Firm


def _director_managing_assos(user_factory, db, username):
    """inventist'li ama assos'u da yöneten it_director döndürür."""
    director = user_factory(username=username, firm="inventist", permission_level="it_director", is_admin=True)
    assos = Firm.query.filter_by(slug="assos").first()
    if assos not in director.managed_firms:
        director.managed_firms.append(assos)
        db.session.commit()
    return director


# ── Düzenleme / silme / alarm — yönetilen firmada İZİN ───────────────────────
def test_director_can_edit_task_in_managed_firm(db, client, login_as, user_factory, task_factory):
    director = _director_managing_assos(user_factory, db, "mfp_dir_edit")
    owner = user_factory(username="mfp_owner1", firm="assos", permission_level="junior")
    task = task_factory(user_id=owner.id, title="Assos görevi", firm="assos")
    login_as(director)
    resp = client.patch(f"/api/tasks/{task.id}", json={"title": "Director düzenledi"})
    assert resp.status_code == 200, "Yönettiği firmadaki görevi düzenleyebilmeli (F2.3)"
    assert resp.get_json()["title"] == "Director düzenledi"


def test_director_can_delete_task_in_managed_firm(db, client, login_as, user_factory, task_factory):
    director = _director_managing_assos(user_factory, db, "mfp_dir_del")
    owner = user_factory(username="mfp_owner2", firm="assos", permission_level="junior")
    task = task_factory(user_id=owner.id, title="Silinecek assos görevi", firm="assos")
    login_as(director)
    resp = client.delete(f"/api/tasks/{task.id}")
    assert resp.status_code == 200


def test_director_can_toggle_alarm_in_managed_firm(db, client, login_as, user_factory, task_factory):
    director = _director_managing_assos(user_factory, db, "mfp_dir_alarm")
    owner = user_factory(username="mfp_owner3", firm="assos", permission_level="junior")
    task = task_factory(user_id=owner.id, title="Alarm görevi", firm="assos")
    login_as(director)
    resp = client.patch(f"/api/tasks/{task.id}/alarm", json={"alarm_enabled": False})
    assert resp.status_code == 200
    assert resp.get_json()["alarm_enabled"] is False


# ── Regresyon: yönetilmeyen firma + yetki genişlemesi yok ────────────────────
def test_director_cannot_edit_unmanaged_firm_task(db, client, login_as, user_factory, task_factory):
    """Yalnızca kendi firma'sını (inventist) yöneten director, assos görevini düzenleyemez."""
    director = user_factory(username="mfp_dir_no", firm="inventist", permission_level="it_director", is_admin=True)
    owner = user_factory(username="mfp_owner4", firm="assos", permission_level="junior")
    task = task_factory(user_id=owner.id, title="Yönetilmeyen assos görevi", firm="assos")
    login_as(director)
    resp = client.patch(f"/api/tasks/{task.id}", json={"title": "olmaz"})
    assert resp.status_code == 403


def test_manager_cannot_edit_other_users_task(db, client, login_as, user_factory, task_factory):
    """it_manager başkasının görevini düzenleyemez — yetki genişlemesi olmamalı."""
    mgr = user_factory(username="mfp_mgr", firm="inventist", permission_level="it_manager", is_admin=True)
    owner = user_factory(username="mfp_owner5", firm="inventist", permission_level="junior")
    task = task_factory(user_id=owner.id, title="Inventist görevi", firm="inventist")
    login_as(mgr)
    resp = client.patch(f"/api/tasks/{task.id}", json={"title": "olmaz"})
    assert resp.status_code == 403


# ── Audit kapsamı ────────────────────────────────────────────────────────────
def test_director_sees_managed_firm_audit(db, client, login_as, user_factory):
    director = _director_managing_assos(user_factory, db, "mfp_dir_audit")
    db.session.add(AuditLog(action="task.create", firm="assos", actor_name="x", summary="assos log"))
    db.session.add(AuditLog(action="task.create", firm="inventist", actor_name="y", summary="inv log"))
    db.session.commit()
    login_as(director)
    resp = client.get("/api/audit")
    assert resp.status_code == 200
    firms = {r["firm"] for r in resp.get_json()["rows"]}
    assert "assos" in firms and "inventist" in firms


def test_director_audit_excludes_unmanaged_firm(db, client, login_as, user_factory):
    director = _director_managing_assos(user_factory, db, "mfp_dir_audit2")
    db.session.add(AuditLog(action="task.create", firm="ghostfirm", actor_name="z", summary="ghost log"))
    db.session.commit()
    login_as(director)
    resp = client.get("/api/audit")
    assert resp.status_code == 200
    firms = {r["firm"] for r in resp.get_json()["rows"]}
    assert "ghostfirm" not in firms
