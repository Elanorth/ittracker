"""Bildirim servisi v4.6
Aktif kullanıcılar için uygun görevleri tespit eder ve digest mail atar.

Eligibility kuralları:
- overdue: kullanıcının tamamlanmamış, alarm_enabled=True görevleri;
    deadline varsa deadline + 3 gün geçmiş;
    deadline yoksa created_at üzerinden 3+ gün geçmiş (rutin ve proje dışı).
- sla_warning: category=="support", tamamlanmamış, alarm_enabled=True;
    remaining_hours <= target * 0.25 ve remaining_hours > 0.
- sla_breached: category=="support", tamamlanmamış, alarm_enabled=True;
    remaining_hours < 0.

Anti-spam:
- Bir görev aynı gün içinde iki kere bildirilmez (last_notified tarihi bugün ise atlanır).
- Digest gönderildikten sonra last_notified = utcnow().
"""
from datetime import datetime, timedelta, date
from models.database import db, User, Task, SLA_HOURS, _sla_target_hours
from services.mailer import send_alarm_digest


OVERDUE_DAYS = 3
SLA_WARNING_RATIO = 0.25  # kalan süre <= target * 0.25 → uyarı


def _days_late(task, now):
    """Bir görevin kaç gün gecikmiş olduğunu döndürür. Uygun değilse None."""
    if task.is_done:
        return None
    if task.deadline:
        delta = (now.date() - task.deadline).days
        return delta if delta > 0 else 0
    # deadline yoksa created_at'tan geçen gün
    if task.created_at:
        return (now.date() - task.created_at.date()).days
    return 0


def _sla_state(task, now):
    """Destek görevleri için SLA durumu.
    Döner: (remaining_hours, breached, target_hours) veya None.
    """
    if task.category != "support" or task.is_done or not task.created_at:
        return None
    target_h = _sla_target_hours(task.priority)
    deadline_dt = task.created_at + timedelta(hours=target_h)
    remaining_sec = (deadline_dt - now).total_seconds()
    remaining_h = remaining_sec / 3600.0
    breached = remaining_sec < 0
    return remaining_h, breached, target_h


def _task_summary(task, extras):
    base = {
        "id": task.id,
        "title": task.title,
        "firm": task.firm or "",
        "team": task.team or "",
        "priority": task.priority or "orta",
        "category": task.category,
    }
    base.update(extras or {})
    return base


def collect_user_alerts(user, now=None):
    """Tek kullanıcı için uyarı görevlerini toplar. Dict döner."""
    now = now or datetime.utcnow()
    groups = {"overdue": [], "sla_warning": [], "sla_breached": []}

    # Kullanıcı alarmları tamamen kapattıysa boş dön
    if not (user.notify_overdue or user.notify_sla_warning or user.notify_daily_digest):
        return groups

    today = now.date()

    tasks = Task.query.filter_by(user_id=user.id, is_done=False).all()
    for t in tasks:
        # Alarm kapalı görevleri atla
        if t.alarm_enabled is False:
            continue
        # Rutin görevler ayrı tamamlama mantığıyla çalışıyor → atla
        if t.category == "routine":
            continue
        # Bugün zaten bildirildiyse atla (anti-spam)
        if t.last_notified and t.last_notified.date() == today:
            continue

        # SLA (destek talepleri)
        sla_info = _sla_state(t, now)
        if sla_info is not None:
            remaining_h, breached, target_h = sla_info
            if breached and user.notify_sla_warning:
                groups["sla_breached"].append(_task_summary(t, {
                    "sla_remaining_hours": round(remaining_h, 2),
                    "sla_target_hours": target_h,
                }))
                continue
            if (not breached) and remaining_h <= target_h * SLA_WARNING_RATIO and user.notify_sla_warning:
                groups["sla_warning"].append(_task_summary(t, {
                    "sla_remaining_hours": round(remaining_h, 2),
                    "sla_target_hours": target_h,
                }))
                continue
            # Destek talebi ama SLA uyarı eşiğinde değil → overdue kontrolüne devam

        # Overdue (3+ gün gecikme)
        if user.notify_overdue:
            days_late = _days_late(t, now)
            if days_late is not None and days_late >= OVERDUE_DAYS:
                # Proje görevleri için deadline varsa kullan; yoksa created_at'tan
                groups["overdue"].append(_task_summary(t, {
                    "days_late": days_late,
                }))

    return groups


def _flat_task_ids(groups):
    ids = set()
    for arr in groups.values():
        for t in arr:
            ids.add(t["id"])
    return ids


def run_digest_job(dry_run=False, only_user_id=None):
    """Günlük digest job'u.
    dry_run=True → mail atma, sadece kim kaça uyarı çıkmış döndür.
    only_user_id verilirse sadece o kullanıcı için çalışır (test amaçlı).
    """
    results = []
    now = datetime.utcnow()

    q = User.query.filter(User.active == True)
    if only_user_id:
        q = q.filter(User.id == only_user_id)

    users = q.all()
    for user in users:
        if not user.email:
            continue
        if not user.notify_daily_digest and not (user.notify_overdue or user.notify_sla_warning):
            continue

        groups = collect_user_alerts(user, now=now)
        total = sum(len(v) for v in groups.values())

        if total == 0:
            results.append({"user_id": user.id, "email": user.email, "count": 0, "skipped": True})
            continue

        if dry_run:
            results.append({
                "user_id": user.id, "email": user.email, "count": total,
                "overdue": len(groups["overdue"]),
                "sla_warning": len(groups["sla_warning"]),
                "sla_breached": len(groups["sla_breached"]),
                "dry_run": True,
            })
            continue

        resp = send_alarm_digest(user, groups)
        if resp.get("ok"):
            # last_notified damgala
            ids = _flat_task_ids(groups)
            if ids:
                db.session.query(Task).filter(Task.id.in_(ids)).update(
                    {"last_notified": now}, synchronize_session=False
                )
                db.session.commit()
            results.append({"user_id": user.id, "email": user.email, "count": total, "sent": True})
        else:
            results.append({"user_id": user.id, "email": user.email, "count": total,
                            "sent": False, "error": resp.get("error")})

    return {"run_at": now.isoformat(), "users_processed": len(users), "results": results}
