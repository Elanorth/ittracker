"""Firma dashboard N+1 önleme — yardımcıların model metoduyla eşdeğerliği.

dashboard_firm_summary / managed_firms_detail her görev için is_done_now /
is_overdue_now çağırıp TaskOccurrence sorguluyordu (firma×görev, trend'de ×6).
Artık _preload_routine_occurrences ile firma başına tek sorgu + bellekte
_task_done_at / _task_overdue_at. Bu testler refactor'ın DAVRANIŞ KORUYUCU
olduğunu (aynı sonuç) kanıtlar.
"""

from datetime import date, datetime, timedelta

from app import _preload_routine_occurrences, _task_done_at, _task_overdue_at
from models.database import TaskOccurrence, _period_key


def test_helpers_match_model_methods(db, user_factory, task_factory):
    u = user_factory(username="perf_eq", firm="inventist")
    today = date.today()

    weekly_done = task_factory(user_id=u.id, category="routine", period="Haftalık")
    db.session.add(TaskOccurrence(task_id=weekly_done.id, period_key=_period_key("Haftalık", today)))

    weekly_overdue = task_factory(user_id=u.id, category="routine", period="Haftalık")
    weekly_overdue.created_at = datetime.utcnow() - timedelta(days=120)

    monthly = task_factory(user_id=u.id, category="routine", period="Aylık")
    nonroutine_done = task_factory(user_id=u.id, category="support", is_done=True)
    nonroutine_overdue = task_factory(user_id=u.id, category="other")
    nonroutine_overdue.deadline = today - timedelta(days=3)
    db.session.commit()

    tasks = [weekly_done, weekly_overdue, monthly, nonroutine_done, nonroutine_overdue]
    occ_map = _preload_routine_occurrences(tasks)
    for t in tasks:
        assert _task_done_at(t, today, occ_map) == t.is_done_now(today=today), f"done mismatch task {t.id}"
        assert _task_overdue_at(t, today, occ_map) == t.is_overdue_now(today=today), f"overdue mismatch task {t.id}"


def test_preload_shape(db, user_factory, task_factory):
    u = user_factory(username="perf_shape", firm="inventist")
    r = task_factory(user_id=u.id, category="routine", period="Aylık")
    db.session.add(TaskOccurrence(task_id=r.id, period_key="2026-05"))
    db.session.add(TaskOccurrence(task_id=r.id, period_key="2026-06"))
    db.session.commit()
    occ_map = _preload_routine_occurrences([r])
    assert occ_map[r.id] == {"2026-05", "2026-06"}


def test_firm_summary_endpoint_smoke(db, client, login_as, user_factory, task_factory):
    director = user_factory(username="perf_dir", firm="inventist", permission_level="it_director", is_admin=True)
    task_factory(user_id=director.id, category="routine", period="Aylık")
    login_as(director)
    resp = client.get("/api/dashboard/firm-summary")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)
