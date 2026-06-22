"""Rapor (PDF) görev kapsamı ve tamamlanma kaynağı testleri.

Doğrulanan bulgular:
- F2.1: Aylık rapor, önceki aylarda açılan rutinleri de içermeli (ekrandaki
  liste ile aynı görev kümesi). Eski kod yalnızca `created_at` o ay olanları
  alıyordu → rutinler rapora hiç girmiyordu.
- F2.2: Rapor rutin tamamlanmayı KANONİK kaynaktan (TaskOccurrence/period_key)
  saymalı, eski `last_completed` proxy'sinden değil.
"""

from datetime import date, datetime, timedelta

from app import _collect_tasks_for_month
from models.database import TaskOccurrence, _period_key
from services.report import task_done_for_report


def _backdate(db, task, days):
    task.created_at = datetime.utcnow() - timedelta(days=days)
    db.session.commit()


# ── F2.1 — kapsam ───────────────────────────────────────────────────────────
def test_report_includes_routine_created_in_prior_month(db, user_factory, task_factory):
    """100 gün önce açılmış aylık rutin, BU AY raporunda görünmeli."""
    u = user_factory(username="rep_scope", firm="inventist")
    r = task_factory(user_id=u.id, title="Aylık güvenlik taraması", category="routine", period="Aylık")
    _backdate(db, r, 100)
    today = date.today()
    ids = [t.id for t in _collect_tasks_for_month(u.id, today.month, today.year)]
    assert r.id in ids, "Önceki ayda açılan rutin bu ay raporunda olmalı (F2.1)"


def test_report_scope_includes_all_period_routines(db, user_factory, task_factory):
    """Günlük/Haftalık/Aylık/Yıllık rutinlerin hepsi, eski tarihte açılsa bile dahil."""
    u = user_factory(username="rep_periods", firm="inventist")
    made = []
    for period in ("Günlük", "Haftalık", "Aylık", "Yıllık"):
        t = task_factory(user_id=u.id, title=f"{period} rutin", category="routine", period=period)
        _backdate(db, t, 200)
        made.append(t.id)
    today = date.today()
    ids = [t.id for t in _collect_tasks_for_month(u.id, today.month, today.year)]
    for tid in made:
        assert tid in ids


def test_report_scope_carryover_open_task_from_prior_month(db, user_factory, task_factory):
    """Önceki ayda açılmış, hâlâ açık destek talebi carry-over ile dahil olmalı."""
    u = user_factory(username="rep_carry", firm="inventist")
    s = task_factory(user_id=u.id, title="Eski açık talep", category="support", is_done=False)
    _backdate(db, s, 60)
    today = date.today()
    ids = [t.id for t in _collect_tasks_for_month(u.id, today.month, today.year)]
    assert s.id in ids


# ── F2.2 — tamamlanma kaynağı ────────────────────────────────────────────────
def test_report_done_ignores_stale_last_completed(db, user_factory, task_factory):
    """last_completed bu ay olsa bile TaskOccurrence yoksa rapor 'tamamlanmadı' demeli.

    (Eski proxy bunu yanlışlıkla 'tamamlandı' sayıyordu — un-toggle senaryosu.)
    """
    u = user_factory(username="rep_stale")
    r = task_factory(user_id=u.id, title="Aylık", category="routine", period="Aylık")
    r.last_completed = datetime.utcnow()  # bu ay, ama occurrence YOK
    db.session.commit()
    today = date.today()
    assert task_done_for_report(r, today.year, today.month) is False


def test_report_done_uses_taskoccurrence(db, user_factory, task_factory):
    """Bu ay için TaskOccurrence varsa rapor 'tamamlandı' demeli."""
    u = user_factory(username="rep_canon")
    r = task_factory(user_id=u.id, title="Aylık", category="routine", period="Aylık")
    today = date.today()
    db.session.add(TaskOccurrence(task_id=r.id, period_key=_period_key("Aylık", today)))
    db.session.commit()
    assert task_done_for_report(r, today.year, today.month) is True


def test_report_done_nonroutine_uses_is_done_flag(db, user_factory, task_factory):
    """Rutin olmayan görevler hâlâ is_done flag'ini kullanır."""
    u = user_factory(username="rep_nonroutine")
    done = task_factory(user_id=u.id, category="support", is_done=True)
    open_ = task_factory(user_id=u.id, category="support", is_done=False)
    today = date.today()
    assert task_done_for_report(done, today.year, today.month) is True
    assert task_done_for_report(open_, today.year, today.month) is False


# ── Uçtan uca — endpoint çökmesin, rutinleri içeren PDF üretsin ──────────────
def test_report_pdf_endpoint_smoke(db, client, login_as, user_factory, task_factory):
    mgr = user_factory(username="rep_mgr", permission_level="super_admin", is_admin=True)
    r = task_factory(user_id=mgr.id, title="Aylık rutin", category="routine", period="Aylık")
    _backdate(db, r, 90)  # önceki ayda açıldı → eski kodda PDF'te YOKTU
    login_as(mgr)
    today = date.today()
    resp = client.get(f"/api/report/pdf?month={today.month}&year={today.year}")
    assert resp.status_code == 200
    assert resp.data[:4] == b"%PDF"
