"""
test_notification_settings_v2.py — v5.10 bildirim geliştirmeleri.

Kapsam:
1. Ayarlanabilir eşikler: notify_overdue_days / notify_sla_ratio / notify_digest_hour
   (GET/PATCH + doğrulama + collect_user_alerts davranışı).
2. SLA breach AYRI kanal: notify_sla_warning kapalıyken breach yine bildirilir;
   notify_sla_breach kapalıyken breach bildirilmez.
3. Saatlik digest filtresi: run_digest_job(digest_hour=h) yalnızca saati h olan
   kullanıcıları işler.
4. run_breach_check: yeni breach'i bildirir, bugün bildirilmişi (last_notified)
   atlar.
5. Müdür digesti: collect_manager_summary yönetilen firmaların geciken/breach
   özetini sahip adıyla döner.
"""

from datetime import date, datetime, timedelta

from services.notifier import (
    collect_manager_summary,
    collect_user_alerts,
    run_breach_check,
    run_digest_job,
)

# ---------- Ayarlar API ----------


def test_settings_get_varsayilanlar(client, user_factory, login_as):
    """GET: yeni alanlar varsayılanlarıyla döner (NULL kolonlar → efektif default)."""
    u = user_factory(username="ns_get")
    login_as(u)
    r = client.get("/api/notifications/settings")
    assert r.status_code == 200
    d = r.get_json()
    assert d["overdue_days"] == 3
    assert d["sla_warning_ratio"] == 0.25
    assert 0 <= d["digest_hour"] <= 23
    assert d["notify_sla_breach"] is True
    assert d["notify_manager_digest"] is True
    assert "timezone" in d
    assert d["is_director"] is False


def test_settings_patch_roundtrip(client, user_factory, login_as, db):
    """PATCH: eşikler ve yeni toggle'lar kaydedilir, GET aynı değerleri döner."""
    u = user_factory(username="ns_patch")
    login_as(u)
    r = client.patch(
        "/api/notifications/settings",
        json={
            "notify_overdue_days": 5,
            "notify_sla_ratio": 0.5,
            "notify_digest_hour": 14,
            "notify_sla_breach": False,
            "notify_manager_digest": False,
        },
    )
    assert r.status_code == 200
    d = r.get_json()
    assert d["overdue_days"] == 5
    assert d["sla_warning_ratio"] == 0.5
    assert d["digest_hour"] == 14
    assert d["notify_sla_breach"] is False
    g = client.get("/api/notifications/settings").get_json()
    assert g["overdue_days"] == 5
    assert g["digest_hour"] == 14


def test_settings_patch_aralik_dogrulama(client, user_factory, login_as):
    """PATCH: aralık dışı değerler 400 döner, kayıt değişmez."""
    u = user_factory(username="ns_val")
    login_as(u)
    assert client.patch("/api/notifications/settings", json={"notify_overdue_days": 0}).status_code == 400
    assert client.patch("/api/notifications/settings", json={"notify_overdue_days": 31}).status_code == 400
    assert client.patch("/api/notifications/settings", json={"notify_digest_hour": 24}).status_code == 400
    assert client.patch("/api/notifications/settings", json={"notify_sla_ratio": 0.95}).status_code == 400
    assert client.patch("/api/notifications/settings", json={"notify_overdue_days": "abc"}).status_code == 400
    # Değerler bozulmamış olmalı
    g = client.get("/api/notifications/settings").get_json()
    assert g["overdue_days"] == 3


# ---------- Kullanıcı bazlı eşikler ----------


def test_ozel_overdue_esigi_daha_erken_uyarir(user_factory, task_factory, db):
    """Eşik 1 gün olan kullanıcı, 2 gün gecikmiş görevi görür (default 3'te görünmez)."""
    u = user_factory(username="ns_thr")
    t = task_factory(user_id=u.id, category="project")
    t.deadline = date.today() - timedelta(days=2)
    db.session.commit()

    # Varsayılan eşik (3): 2 gün gecikme henüz uyarı değil
    groups = collect_user_alerts(u)
    assert all(x["id"] != t.id for x in groups["overdue"])

    # Kullanıcı eşiği 1 güne indirir → uyarılır
    u.notify_overdue_days = 1
    db.session.commit()
    groups = collect_user_alerts(u)
    assert any(x["id"] == t.id for x in groups["overdue"])


def test_ozel_sla_orani_daha_erken_uyarir(user_factory, task_factory, db):
    """Oran 0.5 olan kullanıcı, kalan %40'a düşmüş destek talebi için uyarılır."""
    u = user_factory(username="ns_ratio")
    t = task_factory(user_id=u.id, category="support", priority="orta")  # hedef 24s
    t.created_at = datetime.utcnow() - timedelta(hours=14)  # kalan ~10s = %41
    db.session.commit()

    # Varsayılan oran (0.25): kalan %41 > %25 → uyarı yok
    groups = collect_user_alerts(u)
    assert all(x["id"] != t.id for x in groups["sla_warning"])

    u.notify_sla_ratio = 0.5
    db.session.commit()
    groups = collect_user_alerts(u)
    assert any(x["id"] == t.id for x in groups["sla_warning"])


# ---------- Breach ayrı kanal ----------


def _make_breached_support(user, task_factory, db):
    t = task_factory(user_id=user.id, category="support", priority="orta")  # hedef 24s
    t.created_at = datetime.utcnow() - timedelta(hours=30)  # 6 saat aşılmış
    db.session.commit()
    return t


def test_breach_warning_kapaliyken_de_bildirilir(user_factory, task_factory, db):
    """REGRESYON: 'SLA yaklaşıyor' kapalı + breach kanalı açık → breach yine listede.

    Eski kod breach'i notify_sla_warning'e bağlıyordu; uyarıyı kapatan kullanıcı
    breach bildirimini de kaybediyordu.
    """
    u = user_factory(username="ns_br1")
    u.notify_sla_warning = False
    db.session.commit()
    t = _make_breached_support(u, task_factory, db)

    groups = collect_user_alerts(u)
    assert any(x["id"] == t.id for x in groups["sla_breached"])


def test_breach_kanali_kapaliyken_bildirilmez(user_factory, task_factory, db):
    """notify_sla_breach=False → breach listelenmez (warning açık olsa da)."""
    u = user_factory(username="ns_br2")
    u.notify_sla_breach = False
    db.session.commit()
    t = _make_breached_support(u, task_factory, db)

    groups = collect_user_alerts(u)
    assert all(x["id"] != t.id for x in groups["sla_breached"])


# ---------- Saatlik digest filtresi ----------


def test_digest_hour_filtresi(user_factory, task_factory, db):
    """digest_hour verildiğinde yalnızca o saati seçen kullanıcılar işlenir."""
    u = user_factory(username="ns_hour")
    u.notify_digest_hour = 14
    db.session.commit()
    _make_breached_support(u, task_factory, db)

    rep_wrong = run_digest_job(dry_run=True, only_user_id=u.id, digest_hour=9)
    assert all(r["user_id"] != u.id for r in rep_wrong["results"])
    assert rep_wrong["users_processed"] == 0

    rep_right = run_digest_job(dry_run=True, only_user_id=u.id, digest_hour=14)
    row = next((r for r in rep_right["results"] if r["user_id"] == u.id), None)
    assert row is not None
    assert row["sla_breached"] >= 1


def test_digest_hour_none_saat_filtresi_yok(user_factory, task_factory, db):
    """digest_hour=None (test/run-now yolu) tüm kullanıcıları işler — geriye dönük."""
    u = user_factory(username="ns_hour2")
    u.notify_digest_hour = 23
    db.session.commit()
    _make_breached_support(u, task_factory, db)

    rep = run_digest_job(dry_run=True, only_user_id=u.id)
    assert any(r["user_id"] == u.id for r in rep["results"])


# ---------- run_breach_check ----------


def test_breach_check_yeni_breachi_bulur(user_factory, task_factory, db):
    """Saatlik kontrol: bugün bildirilmemiş breach dry-run sonucuna girer."""
    u = user_factory(username="ns_bc1")
    _make_breached_support(u, task_factory, db)

    rep = run_breach_check(dry_run=True)
    row = next((r for r in rep["results"] if r["user_id"] == u.id), None)
    assert row is not None
    assert row["breached"] >= 1


def test_breach_check_bugun_bildirilmisi_atlar(user_factory, task_factory, db):
    """Anti-spam: last_notified bugünse aynı görev tekrar bildirilmez."""
    u = user_factory(username="ns_bc2")
    t = _make_breached_support(u, task_factory, db)
    t.last_notified = datetime.utcnow()
    db.session.commit()

    rep = run_breach_check(dry_run=True)
    assert all(r["user_id"] != u.id for r in rep["results"])


def test_breach_check_kanal_kapaliysa_atlar(user_factory, task_factory, db):
    """notify_sla_breach=False kullanıcı saatlik kontrolde de atlanır."""
    u = user_factory(username="ns_bc3")
    u.notify_sla_breach = False
    db.session.commit()
    _make_breached_support(u, task_factory, db)

    rep = run_breach_check(dry_run=True)
    assert all(r["user_id"] != u.id for r in rep["results"])


# ---------- Müdür digesti ----------


def test_manager_summary_yonetilen_firma_breach(user_factory, task_factory, db):
    """Director, yönettiği firmadaki başka kullanıcının breach'ini özet olarak görür."""
    director = user_factory(username="ns_dir", permission_level="it_director", firm="inventist")
    worker = user_factory(username="ns_wrk", full_name="Saha Çalışanı", firm="inventist")
    t = _make_breached_support(worker, task_factory, db)

    summary = collect_manager_summary(director)
    inv = next((s for s in summary if s["firm"] == "inventist"), None)
    assert inv is not None, "Yönetilen firmadaki breach müdür özetine girmeli"
    row = next((x for x in inv["breached"] if x["id"] == t.id), None)
    assert row is not None
    assert row["owner"] == "Saha Çalışanı"


def test_manager_summary_kapsam_disi_firma_gorunmez(user_factory, task_factory, db):
    """Director yalnızca kendi kapsamındaki firmaları görür (assos dışarıda kalır)."""
    director = user_factory(username="ns_dir2", permission_level="it_director", firm="inventist")
    other = user_factory(username="ns_oth", firm="assos")
    t = task_factory(user_id=other.id, category="support", priority="orta", firm="assos")
    t.created_at = datetime.utcnow() - timedelta(hours=30)
    db.session.commit()

    summary = collect_manager_summary(director)
    assert all(s["firm"] != "assos" for s in summary)


def test_digest_job_manager_items_dry_run(user_factory, task_factory, db):
    """Digest dry-run: director için manager_items sayısı raporlanır."""
    director = user_factory(username="ns_dir3", permission_level="it_director", firm="inventist")
    worker = user_factory(username="ns_wrk3", firm="inventist")
    _make_breached_support(worker, task_factory, db)

    rep = run_digest_job(dry_run=True, only_user_id=director.id)
    row = next((r for r in rep["results"] if r["user_id"] == director.id), None)
    assert row is not None
    assert row.get("manager_items", 0) >= 1


def test_digest_job_manager_kanali_kapali(user_factory, task_factory, db):
    """notify_manager_digest=False → müdür özeti üretilmez."""
    director = user_factory(username="ns_dir4", permission_level="it_director", firm="inventist")
    director.notify_manager_digest = False
    db.session.commit()
    worker = user_factory(username="ns_wrk4", firm="inventist")
    _make_breached_support(worker, task_factory, db)

    rep = run_digest_job(dry_run=True, only_user_id=director.id)
    row = next((r for r in rep["results"] if r["user_id"] == director.id), None)
    # Kendi görevi yok + müdür kanalı kapalı → skipped satırı (count 0) beklenir
    assert row is not None
    assert row.get("manager_items", 0) == 0 or row.get("skipped") is True
