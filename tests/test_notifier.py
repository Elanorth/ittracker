"""
notifier servisinin gecikme (overdue) hesaplamasına regresyon testleri.

Tarih: 2026-05-22 — Task #89 "Gympro Geçişi" bug raporundan sonra eklendi.
Kullanıcı "deadline 19 gün sonra ama mail '3 gün gecikmeli' diyor" şikayetinde bulundu.
Kök sebep: `_days_late()` deadline yoksa `created_at`'tan geçen gün sayısını
gecikme olarak rapor ediyordu — bu yanlıştı, deadline atanmamış görev "gecikme"
değil "deadline bekliyor" durumundadır.
"""

from datetime import date, datetime, timedelta

from services.notifier import _days_late, collect_user_alerts

# ---------- _days_late() birim testleri ----------


def test_days_late_deadline_yoksa_none(task_factory, user_factory):
    """REGRESYON: Deadline atanmamış görev — kaç gün önce oluşturulsa da gecikme yok."""
    user = user_factory()
    t = task_factory(user_id=user.id, category="project")
    assert t.deadline is None  # sanity

    # 30 gün ileri sarsak bile gecikme None
    future_now = datetime.utcnow() + timedelta(days=30)
    assert _days_late(t, future_now) is None


def test_days_late_deadline_gelecekteyse_none(task_factory, user_factory, db):
    """Deadline gelecekteyse henüz gecikme değil."""
    user = user_factory()
    t = task_factory(user_id=user.id)
    t.deadline = date.today() + timedelta(days=10)
    db.session.commit()

    assert _days_late(t, datetime.utcnow()) is None


def test_days_late_deadline_bugun_none(task_factory, user_factory, db):
    """Deadline tam bugünse henüz gecikme yok (0 gün geçmiş)."""
    user = user_factory()
    t = task_factory(user_id=user.id)
    t.deadline = date.today()
    db.session.commit()

    assert _days_late(t, datetime.utcnow()) is None


def test_days_late_deadline_gecmisse_pozitif_int(task_factory, user_factory, db):
    """Deadline geçtiyse aradaki gün farkını döndürür."""
    user = user_factory()
    t = task_factory(user_id=user.id)
    t.deadline = date.today() - timedelta(days=5)
    db.session.commit()

    assert _days_late(t, datetime.utcnow()) == 5


def test_days_late_tamamlanan_gorev_none(task_factory, user_factory, db):
    """Tamamlanmış görev için gecikme kavramı uygulanmaz."""
    user = user_factory()
    t = task_factory(user_id=user.id, is_done=True)
    t.deadline = date.today() - timedelta(days=10)
    db.session.commit()

    assert _days_late(t, datetime.utcnow()) is None


# ---------- collect_user_alerts() entegrasyon testleri ----------


def test_collect_alerts_deadline_yok_overdue_listesinde_yok(task_factory, user_factory, db):
    """
    BUG #89 regresyon: Deadline'sız bir proje görevi (created_at 5 gün önce de olsa)
    overdue mail listesine düşmemeli.

    Önceki davranış: created_at + 3 gün → 'overdue' grubuna eklenip mail gönderilirdi.
    Yeni davranış: deadline atanmamış görev → hiçbir gruba düşmez.
    """
    user = user_factory()
    user.notify_overdue = True
    user.notify_daily_digest = True
    db.session.commit()

    # 5 gün önce oluşturulmuş, deadline atanmamış proje görevi
    t = task_factory(user_id=user.id, category="project")
    t.created_at = datetime.utcnow() - timedelta(days=5)
    db.session.commit()

    groups = collect_user_alerts(user)
    overdue_ids = [item["id"] for item in groups["overdue"]]
    assert t.id not in overdue_ids


def test_collect_alerts_deadline_3gun_gecmis_overdue_listesinde(task_factory, user_factory, db):
    """Deadline 3+ gün geçmiş görev overdue olarak rapor edilmeli."""
    user = user_factory()
    user.notify_overdue = True
    user.notify_daily_digest = True
    db.session.commit()

    t = task_factory(user_id=user.id, category="project")
    t.deadline = date.today() - timedelta(days=4)
    db.session.commit()

    groups = collect_user_alerts(user)
    overdue_ids = [item["id"] for item in groups["overdue"]]
    assert t.id in overdue_ids

    # days_late değeri doğru mu?
    overdue_item = next(i for i in groups["overdue"] if i["id"] == t.id)
    assert overdue_item["days_late"] == 4


def test_collect_alerts_deadline_2gun_gecmis_henuz_overdue_degil(task_factory, user_factory, db):
    """Deadline 2 gün geçmiş ama OVERDUE_DAYS eşiğinin (3) altında — mail atılmaz."""
    user = user_factory()
    user.notify_overdue = True
    user.notify_daily_digest = True
    db.session.commit()

    t = task_factory(user_id=user.id, category="project")
    t.deadline = date.today() - timedelta(days=2)
    db.session.commit()

    groups = collect_user_alerts(user)
    overdue_ids = [item["id"] for item in groups["overdue"]]
    assert t.id not in overdue_ids


def test_collect_alerts_deadline_gelecek_overdue_listesinde_yok(task_factory, user_factory, db):
    """
    Asıl Task #89 senaryosu: 4 gün önce oluşturulmuş, deadline 19 gün sonra
    olan proje görevi overdue listesine düşmemeli.
    """
    user = user_factory()
    user.notify_overdue = True
    user.notify_daily_digest = True
    db.session.commit()

    t = task_factory(user_id=user.id, category="project")
    t.created_at = datetime.utcnow() - timedelta(days=4)
    t.deadline = date.today() + timedelta(days=19)
    db.session.commit()

    groups = collect_user_alerts(user)
    overdue_ids = [item["id"] for item in groups["overdue"]]
    assert t.id not in overdue_ids
