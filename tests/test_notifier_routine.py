"""F2.4 — Notifier gecikmiş rutinleri de uyarmalı.

Bug: collect_user_alerts rutin görevleri tamamen atlıyordu (`continue`), bu yüzden
3 haftadır yapılmamış haftalık bir yedek görevi hiçbir bildirim üretmiyordu —
oysa v5.1'de tam bu iş için `overdue_period_count()` eklenmişti ama notifier'a
hiç bağlanmamıştı.
"""

from datetime import date, datetime, timedelta

from models.database import TaskOccurrence, _period_key
from services.notifier import collect_user_alerts


def _old_routine(db, task_factory, user_id, period="Haftalık", days_ago=120):
    r = task_factory(user_id=user_id, title=f"{period} rutin", category="routine", period=period)
    r.created_at = datetime.utcnow() - timedelta(days=days_ago)
    db.session.commit()
    return r


def test_overdue_routine_appears_in_alerts(db, user_factory, task_factory):
    u = user_factory(username="nrt_basic")  # notify_overdue default True
    r = _old_routine(db, task_factory, u.id, "Haftalık")
    groups = collect_user_alerts(u)
    entry = next((t for t in groups["overdue"] if t["id"] == r.id), None)
    assert entry is not None, "Gecikmiş rutin overdue uyarılarında olmalı (F2.4)"
    assert entry["overdue_periods"] >= 1
    assert entry["period"] == "Haftalık"


def test_completed_routine_not_alerted(db, user_factory, task_factory):
    """Önceki periyodu tamamlanmış rutin gecikmiş sayılmaz → uyarı yok."""
    u = user_factory(username="nrt_done")
    r = _old_routine(db, task_factory, u.id, "Haftalık")
    last_week = date.today() - timedelta(days=7)
    db.session.add(TaskOccurrence(task_id=r.id, period_key=_period_key("Haftalık", last_week)))
    db.session.commit()
    assert r.id not in [t["id"] for t in collect_user_alerts(u)["overdue"]]


def test_alarm_disabled_routine_not_alerted(db, user_factory, task_factory):
    u = user_factory(username="nrt_alarm")
    r = _old_routine(db, task_factory, u.id, "Haftalık")
    r.alarm_enabled = False
    db.session.commit()
    assert r.id not in [t["id"] for t in collect_user_alerts(u)["overdue"]]


def test_notify_overdue_off_skips_routine(db, user_factory, task_factory):
    u = user_factory(username="nrt_off")
    u.notify_overdue = False  # diğer flag'ler açık → erken return olmaz
    db.session.commit()
    r = _old_routine(db, task_factory, u.id, "Haftalık")
    assert r.id not in [t["id"] for t in collect_user_alerts(u)["overdue"]]


def test_routine_antispam_last_notified_today(db, user_factory, task_factory):
    u = user_factory(username="nrt_spam")
    r = _old_routine(db, task_factory, u.id, "Haftalık")
    r.last_notified = datetime.utcnow()  # bugün bildirildi
    db.session.commit()
    assert r.id not in [t["id"] for t in collect_user_alerts(u)["overdue"]]


def test_monthly_routine_overdue_periods(db, user_factory, task_factory):
    """Aylık rutin de doğru periyot tipiyle raporlanmalı."""
    u = user_factory(username="nrt_monthly")
    r = _old_routine(db, task_factory, u.id, "Aylık", days_ago=200)
    entry = next((t for t in collect_user_alerts(u)["overdue"] if t["id"] == r.id), None)
    assert entry is not None
    assert entry["period"] == "Aylık"
    assert entry["overdue_periods"] >= 1
