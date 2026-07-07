"""Bildirim servisi v5.10
Aktif kullanıcılar için uygun görevleri tespit eder ve digest mail atar.

Eligibility kuralları:
- overdue: kullanıcının tamamlanmamış, alarm_enabled=True görevleri;
    YALNIZCA deadline atanmış VE deadline + eşik gün (kullanıcı bazlı, default 3)
    geçmiş ise gecikme sayılır. Deadline yoksa gecikme kavramı uygulanmaz
    (önceki sürümlerde created_at fallback'i vardı — Task #89 örneği gibi yeni
    oluşturulmuş proje görevlerinin "3 gün gecikmeli" sanılmasına yol açıyordu).
- sla_warning: category=="support", tamamlanmamış, alarm_enabled=True;
    remaining_hours <= target * oran (kullanıcı bazlı, default 0.25) ve > 0.
- sla_breached: category=="support", tamamlanmamış, alarm_enabled=True;
    remaining_hours < 0. v5.10: AYRI kanal (notify_sla_breach) — "yaklaştı"
    uyarısını kapatan kullanıcı breach bildirimini kaybetmez.

v5.10 yenilikleri:
- Kullanıcı bazlı eşikler: notify_overdue_days / notify_sla_ratio / notify_digest_hour
  (NULL = aşağıdaki modül varsayılanları; effective_* helper'ları çözer).
- run_digest_job(digest_hour=h): saatlik scheduler h saatini geçirir; yalnızca digest
  saati h olan kullanıcılar işlenir (None = tümü — test/run-now yolu).
- run_breach_check(): saatlik hafif kontrol — YENİ SLA breach'lerini digest saatini
  beklemeden bildirir (4 saatlik SLA'da günlük digest çok geç kalıyordu).
- Müdür digesti: director+ kullanıcıya yönettiği firmaların geciken/breach özeti.

Anti-spam:
- Bir görev aynı gün içinde iki kere bildirilmez (last_notified tarihi bugün ise atlanır).
- Digest/breach gönderildikten sonra last_notified = utcnow().
"""

import os
from datetime import datetime, timedelta

from models.database import Firm, Task, User, _sla_target_hours, business_hours_between, db, sla_deadline
from services.mailer import send_alarm_digest, send_manager_digest

OVERDUE_DAYS = 3
SLA_WARNING_RATIO = 0.25  # kalan süre <= target * 0.25 → uyarı


def _default_digest_hour():
    """Varsayılan digest saati — NOTIFY_HOUR env (scheduler TZ'sinde), yoksa 9."""
    try:
        return int(os.environ.get("NOTIFY_HOUR", "9"))
    except ValueError:
        return 9


def effective_overdue_days(user):
    """Kullanıcının gecikme eşiği (gün). NULL/geçersiz → modül varsayılanı."""
    v = getattr(user, "notify_overdue_days", None)
    return v if isinstance(v, int) and v >= 1 else OVERDUE_DAYS


def effective_sla_ratio(user):
    """Kullanıcının SLA uyarı oranı. NULL/geçersiz → modül varsayılanı."""
    v = getattr(user, "notify_sla_ratio", None)
    return v if isinstance(v, int | float) and 0 < v < 1 else SLA_WARNING_RATIO


def effective_digest_hour(user):
    """Kullanıcının digest saati (0-23, scheduler TZ). NULL/geçersiz → NOTIFY_HOUR."""
    v = getattr(user, "notify_digest_hour", None)
    return v if isinstance(v, int) and 0 <= v <= 23 else _default_digest_hour()


def _wants_breach(user):
    """Breach kanalı açık mı? NULL (eski satır) = açık."""
    v = getattr(user, "notify_sla_breach", None)
    return True if v is None else bool(v)


def _days_late(task, now):
    """Bir görevin kaç gün gecikmiş olduğunu döndürür. Gecikme yoksa None.

    Davranış:
    - Tamamlanmış görev → None (gecikme kavramı uygulanmaz)
    - Deadline atanmamış görev → None
      (Önceki sürümlerde `created_at` fallback'i vardı; yeni oluşturulmuş ama
      deadline'sız görevler "N gün gecikmeli" sanılıyordu — bu yanlıştı.)
    - Deadline gelecekteyse → None
    - Deadline geçmişse → pozitif int (gün sayısı)
    """
    if task.is_done:
        return None
    if not task.deadline:
        return None
    delta = (now.date() - task.deadline).days
    return delta if delta > 0 else None


def _sla_state(task, now):
    """Destek görevleri için SLA durumu (v5.13 — İŞ-saati bazlı).
    Döner: (remaining_hours, breached, target_hours) veya None.
    """
    if task.category != "support" or task.is_done or not task.created_at:
        return None
    target_h = _sla_target_hours(task.priority)
    deadline_dt = sla_deadline(task.created_at, task.priority)
    breached = bool(deadline_dt and now > deadline_dt)
    remaining_h = business_hours_between(now, deadline_dt) if deadline_dt else 0.0
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

    # Kullanıcı alarmları tamamen kapattıysa boş dön (v5.10: breach kanalı dahil)
    if not (user.notify_overdue or user.notify_sla_warning or _wants_breach(user) or user.notify_daily_digest):
        return groups

    overdue_days = effective_overdue_days(user)
    sla_ratio = effective_sla_ratio(user)
    today = now.date()

    tasks = Task.query.filter_by(user_id=user.id, is_done=False).all()
    for t in tasks:
        # Alarm kapalı görevleri atla
        if t.alarm_enabled is False:
            continue
        # Bugün zaten bildirildiyse atla (anti-spam) — rutinler dahil
        if t.last_notified and t.last_notified.date() == today:
            continue

        # F2.4 — Rutin (periyodik) görevler: kanonik overdue_period_count ile
        # KAÇIRILAN periyot varsa uyar. Önceden rutinler tamamen atlanıyordu →
        # gecikmiş haftalık/aylık rutinler hiçbir bildirim üretmiyordu (v5.1'de
        # eklenen overdue_period_count() notifier'a hiç bağlanmamıştı).
        if t.category == "routine":
            if t.period != "Tek Seferlik" and user.notify_overdue:
                missed = t.overdue_period_count(today=today)
                if missed > 0:
                    groups["overdue"].append(_task_summary(t, {"overdue_periods": missed, "period": t.period}))
            continue

        # SLA (destek talepleri)
        sla_info = _sla_state(t, now)
        if sla_info is not None:
            remaining_h, breached, target_h = sla_info
            # v5.10 — breach AYRI kanal: 'yaklaştı' kapalıyken de breach bildirilir
            if breached and _wants_breach(user):
                groups["sla_breached"].append(
                    _task_summary(
                        t,
                        {
                            "sla_remaining_hours": round(remaining_h, 2),
                            "sla_target_hours": target_h,
                        },
                    )
                )
                continue
            if (not breached) and remaining_h <= target_h * sla_ratio and user.notify_sla_warning:
                groups["sla_warning"].append(
                    _task_summary(
                        t,
                        {
                            "sla_remaining_hours": round(remaining_h, 2),
                            "sla_target_hours": target_h,
                        },
                    )
                )
                continue
            # Destek talebi ama SLA uyarı eşiğinde değil → overdue kontrolüne devam

        # Overdue (eşik: kullanıcı bazlı gün sayısı, default 3)
        if user.notify_overdue:
            days_late = _days_late(t, now)
            if days_late is not None and days_late >= overdue_days:
                groups["overdue"].append(
                    _task_summary(
                        t,
                        {
                            "days_late": days_late,
                        },
                    )
                )

    return groups


def _flat_task_ids(groups):
    ids = set()
    for arr in groups.values():
        for t in arr:
            ids.add(t["id"])
    return ids


def collect_manager_summary(director, now=None):
    """v5.10 — Director+ için yönettiği firmaların geciken/breach özeti.

    Döner: [{firm, firm_name, overdue: [task_summary+owner], breached: [...]}, ...]
    Yalnızca sorunlu firmalar listelenir (boş firma satırı üretilmez).

    Kapsam: super_admin → tüm firmalar; it_director → managed_firms + kendi firma'sı
    (has_firm_scope ile aynı mantık). Görev sahibi kim olursa olsun dahil — müdür
    kendi ekibinin resmini görür. Liste firma başına 10 kayıtla sınırlanır (mail şişmesin).
    """
    now = now or datetime.utcnow()
    today = now.date()

    if director.is_super_admin:
        firms = Firm.query.order_by(Firm.name).all()
    else:
        slugs = set(director.managed_firm_slugs)
        if director.firm:
            slugs.add(director.firm)
        if not slugs:
            return []
        firms = Firm.query.filter(Firm.slug.in_(list(slugs))).order_by(Firm.name).all()

    summary = []
    for f in firms:
        tasks = Task.query.filter(Task.firm == f.slug, Task.is_done == False).all()
        overdue, breached = [], []
        for t in tasks:
            if t.alarm_enabled is False:
                continue
            owner = db.session.get(User, t.user_id) if t.user_id else None
            owner_name = owner.full_name if owner else "—"
            sla_info = _sla_state(t, now)
            if sla_info is not None and sla_info[1]:  # breached
                breached.append(_task_summary(t, {"owner": owner_name, "sla_target_hours": sla_info[2]}))
                continue
            if t.category == "routine" and t.period != "Tek Seferlik":
                missed = t.overdue_period_count(today=today)
                if missed > 0:
                    extras = {"owner": owner_name, "overdue_periods": missed, "period": t.period}
                    overdue.append(_task_summary(t, extras))
                continue
            days_late = _days_late(t, now)
            if days_late is not None and days_late >= OVERDUE_DAYS:
                overdue.append(_task_summary(t, {"owner": owner_name, "days_late": days_late}))
        if overdue or breached:
            summary.append({"firm": f.slug, "firm_name": f.name, "overdue": overdue[:10], "breached": breached[:10]})
    return summary


def run_digest_job(dry_run=False, only_user_id=None, digest_hour=None):
    """Günlük digest job'u.
    dry_run=True → mail atma, sadece kim kaça uyarı çıkmış döndür.
    only_user_id verilirse sadece o kullanıcı için çalışır (test amaçlı).
    digest_hour verilirse (saatlik scheduler yolu) yalnızca digest saati o saate
    denk gelen kullanıcılar işlenir; None = saat filtresi yok (test/run-now yolu).
    """
    results = []
    now = datetime.utcnow()

    q = User.query.filter(User.active == True)
    if only_user_id:
        q = q.filter(User.id == only_user_id)

    users = q.all()
    processed = 0
    for user in users:
        if not user.email:
            continue
        # v5.10 — kişisel digest saati filtresi (scheduler saatlik çalışır)
        if digest_hour is not None and effective_digest_hour(user) != digest_hour:
            continue
        if not user.notify_daily_digest and not (user.notify_overdue or user.notify_sla_warning or _wants_breach(user)):
            continue
        processed += 1

        groups = collect_user_alerts(user, now=now)
        total = sum(len(v) for v in groups.values())

        # v5.10 — müdür digesti: director+ ve kanal açıksa firma özeti eklenir
        mgr_summary = []
        if user.is_director_or_above and (
            user.notify_manager_digest if user.notify_manager_digest is not None else True
        ):
            mgr_summary = collect_manager_summary(user, now=now)
        mgr_total = sum(len(s["overdue"]) + len(s["breached"]) for s in mgr_summary)

        if total == 0 and mgr_total == 0:
            results.append({"user_id": user.id, "email": user.email, "count": 0, "skipped": True})
            continue

        if dry_run:
            results.append(
                {
                    "user_id": user.id,
                    "email": user.email,
                    "count": total,
                    "overdue": len(groups["overdue"]),
                    "sla_warning": len(groups["sla_warning"]),
                    "sla_breached": len(groups["sla_breached"]),
                    "manager_items": mgr_total,
                    "dry_run": True,
                }
            )
            continue

        sent_any = False
        errors = []
        if total > 0:
            resp = send_alarm_digest(user, groups)
            if resp.get("ok"):
                sent_any = True
                ids = _flat_task_ids(groups)
                if ids:
                    db.session.query(Task).filter(Task.id.in_(ids)).update(
                        {"last_notified": now}, synchronize_session=False
                    )
                    db.session.commit()
            else:
                errors.append(resp.get("error"))
        if mgr_total > 0:
            mresp = send_manager_digest(user, mgr_summary)
            if mresp.get("ok"):
                sent_any = True
            else:
                errors.append(mresp.get("error"))

        if sent_any and not errors:
            results.append(
                {"user_id": user.id, "email": user.email, "count": total, "manager_items": mgr_total, "sent": True}
            )
        else:
            results.append(
                {
                    "user_id": user.id,
                    "email": user.email,
                    "count": total,
                    "manager_items": mgr_total,
                    "sent": sent_any,
                    "error": "; ".join(e for e in errors if e) or None,
                }
            )

    return {"run_at": now.isoformat(), "users_processed": processed, "results": results}


def run_breach_check(dry_run=False):
    """v5.10 — Saatlik SLA breach kontrolü.

    Günlük digest 4 saatlik SLA için çok geç kalıyordu; bu job her saat çalışır ve
    YALNIZCA yeni breach'leri (bugün henüz bildirilmemiş) anında mail eder.
    Digest'ten farklı olarak yalnız sla_breached grubunu taşır — hafif tutulur.
    Anti-spam: last_notified bugüne damgalanır → aynı gün digest de tekrar etmez.
    """
    results = []
    now = datetime.utcnow()
    today = now.date()

    for user in User.query.filter(User.active == True).all():
        if not user.email or not _wants_breach(user):
            continue
        breached = []
        tasks = Task.query.filter_by(user_id=user.id, is_done=False, category="support").all()
        for t in tasks:
            if t.alarm_enabled is False:
                continue
            if t.last_notified and t.last_notified.date() == today:
                continue  # bugün zaten bildirildi (digest veya önceki breach check)
            sla_info = _sla_state(t, now)
            if sla_info is None:
                continue
            remaining_h, is_breached, target_h = sla_info
            if is_breached:
                breached.append(
                    _task_summary(t, {"sla_remaining_hours": round(remaining_h, 2), "sla_target_hours": target_h})
                )
        if not breached:
            continue
        if dry_run:
            results.append({"user_id": user.id, "email": user.email, "breached": len(breached), "dry_run": True})
            continue
        resp = send_alarm_digest(user, {"overdue": [], "sla_warning": [], "sla_breached": breached})
        if resp.get("ok"):
            ids = {b["id"] for b in breached}
            db.session.query(Task).filter(Task.id.in_(ids)).update({"last_notified": now}, synchronize_session=False)
            db.session.commit()
            results.append({"user_id": user.id, "email": user.email, "breached": len(breached), "sent": True})
        else:
            results.append(
                {
                    "user_id": user.id,
                    "email": user.email,
                    "breached": len(breached),
                    "sent": False,
                    "error": resp.get("error"),
                }
            )

    return {"run_at": now.isoformat(), "results": results}
