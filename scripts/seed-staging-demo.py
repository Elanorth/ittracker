#!/usr/bin/env python3
"""
Staging için demo veri seed script'i.

Amaç: PR test ve UI doğrulama için her kategoriden, her durumdan görev içeren
gerçekçi bir veri seti — manuel kayıt açma derdi olmadan.

Kullanım (staging container içinden):
    docker compose -p ittracker-staging exec web python scripts/seed-staging-demo.py
    docker compose -p ittracker-staging exec web python scripts/seed-staging-demo.py --wipe

Güvenlik:
- Tüm demo kayıtlar `demo_` prefix'li username ve `[DEMO]` prefix'li title taşır.
- Mevcut gerçek kullanıcı/görev verilerine DOKUNULMAZ.
- İdempotent: re-run her seferinde demo veriyi sıfırlayıp yeniden kurar.
- PRODUCTION'da çalıştırılmamalı — script `APP_ENV` kontrolü yapar.
"""
import os
import sys
from datetime import datetime, timedelta, date

# Script app context dışında çalıştırılırsa Flask app'i yükle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from models.database import (
    db, User, Task, TaskOccurrence, Firm, Team,
    _period_key,
)


DEMO_USER_PREFIX = "demo_"
DEMO_TASK_PREFIX = "[DEMO]"


# ---------- Veri tanımları ----------

DEMO_USERS = [
    # (username, full_name, email, firm, permission_level, password)
    ("demo_director_inv", "DEMO Direktör İnventist", "demo_director_inv@demo.local",
     "inventist", "it_director", "Demo2026!"),
    ("demo_director_assos", "DEMO Direktör Assos", "demo_director_assos@demo.local",
     "assos", "it_director", "Demo2026!"),
    ("demo_specialist_inv", "DEMO Uzman İnventist", "demo_specialist_inv@demo.local",
     "inventist", "it_specialist", "Demo2026!"),
    ("demo_specialist_assos", "DEMO Uzman Assos", "demo_specialist_assos@demo.local",
     "assos", "it_specialist", "Demo2026!"),
    ("demo_junior_inv", "DEMO Junior İnventist", "demo_junior_inv@demo.local",
     "inventist", "junior", "Demo2026!"),
    ("demo_junior_assos", "DEMO Junior Assos", "demo_junior_assos@demo.local",
     "assos", "junior", "Demo2026!"),
]


def _today():
    return date.today()


def _build_task_scenarios(today):
    """
    Her kullanıcı için uygulanacak senaryo tanımları.

    Her senaryo dict: {title, category, priority, period, deadline_offset_days,
                       created_offset_days, is_done, alarm_enabled}
    deadline_offset_days: bugüne göre, None = deadline yok
    created_offset_days: negatif = geçmiş (kaç gün önce oluşturuldu)
    """
    return [
        # === Anlık görevler ===
        {"title": "Yeni laptop kurulumu", "category": "task", "priority": "orta",
         "period": "Tek Seferlik", "deadline_offset_days": 7, "created_offset_days": -2,
         "is_done": False, "alarm_enabled": True},
        {"title": "Office365 lisans atama", "category": "task", "priority": "düşük",
         "period": "Tek Seferlik", "deadline_offset_days": -5, "created_offset_days": -15,
         "is_done": False, "alarm_enabled": True},  # GECİKEN 5 gün
        {"title": "Yazıcı sürücü güncellemesi", "category": "task", "priority": "düşük",
         "period": "Tek Seferlik", "deadline_offset_days": None, "created_offset_days": -3,
         "is_done": True, "alarm_enabled": True},  # TAMAMLANDI

        # === Proje görevleri ===
        {"title": "VPN altyapı modernizasyonu", "category": "project", "priority": "yüksek",
         "period": "Tek Seferlik", "deadline_offset_days": 30, "created_offset_days": -10,
         "is_done": False, "alarm_enabled": True},
        {"title": "Active Directory göç planı", "category": "project", "priority": "yüksek",
         "period": "Tek Seferlik", "deadline_offset_days": -2, "created_offset_days": -45,
         "is_done": False, "alarm_enabled": True},  # GECİKEN proje
        {"title": "Backup sistem refactor", "category": "project", "priority": "orta",
         "period": "Tek Seferlik", "deadline_offset_days": None, "created_offset_days": -7,
         "is_done": False, "alarm_enabled": True},  # deadline yok — overdue OLMAMALI (bug fix testi)

        # === Rutin görevler ===
        {"title": "Sunucu sağlık kontrolü", "category": "routine", "priority": "orta",
         "period": "Haftalık", "deadline_offset_days": None, "created_offset_days": -60,
         "is_done": False, "alarm_enabled": True, "completed_periods": ["last_week"]},
        {"title": "Aylık güvenlik taraması", "category": "routine", "priority": "yüksek",
         "period": "Aylık", "deadline_offset_days": None, "created_offset_days": -120,
         "is_done": False, "alarm_enabled": True, "completed_periods": ["last_month"]},
        {"title": "Günlük log incelemesi", "category": "routine", "priority": "düşük",
         "period": "Günlük", "deadline_offset_days": None, "created_offset_days": -30,
         "is_done": False, "alarm_enabled": True, "completed_periods": ["yesterday"]},

        # === Destek talepleri (SLA) ===
        {"title": "Mail erişim sorunu", "category": "support", "priority": "yüksek",
         "period": "Tek Seferlik", "deadline_offset_days": None, "created_offset_days_h": -3.5,
         "is_done": False, "alarm_enabled": True},  # SLA 4s, kalan 0.5s → BREACH yakın
        {"title": "Yazıcıdan çıktı alamıyorum", "category": "support", "priority": "orta",
         "period": "Tek Seferlik", "deadline_offset_days": None, "created_offset_days_h": -2,
         "is_done": False, "alarm_enabled": True},  # SLA 24s, kalan 22s — sağlıklı
        {"title": "Slack bildirimleri gelmiyor", "category": "support", "priority": "düşük",
         "period": "Tek Seferlik", "deadline_offset_days": None, "created_offset_days_h": -100,
         "is_done": False, "alarm_enabled": True},  # SLA 72s, BREACHED 28s

        # === Diğer kategoriler ===
        {"title": "Switch firmware yedeği", "category": "backup", "priority": "düşük",
         "period": "Aylık", "deadline_offset_days": None, "created_offset_days": -20,
         "is_done": False, "alarm_enabled": True},
        {"title": "Network kabin yenileme", "category": "infra", "priority": "orta",
         "period": "Tek Seferlik", "deadline_offset_days": 15, "created_offset_days": -5,
         "is_done": False, "alarm_enabled": True},
        {"title": "Test ortamı hazırlığı", "category": "other", "priority": "düşük",
         "period": "Tek Seferlik", "deadline_offset_days": None, "created_offset_days": -4,
         "is_done": True, "alarm_enabled": True},
    ]


def _is_demo_user(u):
    return u.username and u.username.startswith(DEMO_USER_PREFIX)


def _is_demo_task(t):
    return t.title and t.title.startswith(DEMO_TASK_PREFIX)


# ---------- Wipe ----------

def wipe_demo_data():
    """Demo prefix'li tüm User ve Task'ları (ve TaskOccurrence cascade) sil."""
    print("→ Demo veri siliniyor...")
    demo_users = User.query.filter(User.username.like(f"{DEMO_USER_PREFIX}%")).all()
    user_ids = [u.id for u in demo_users]

    # Önce demo kullanıcıların tüm görevlerini sil (TaskOccurrence cascade ile gider)
    deleted_tasks = 0
    if user_ids:
        deleted_tasks = Task.query.filter(Task.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )

    # Sonra demo title'lı orphan tasks (varsa)
    orphan = Task.query.filter(Task.title.like(f"{DEMO_TASK_PREFIX}%")).delete(
        synchronize_session=False
    )
    deleted_tasks += orphan

    # Demo kullanıcıları sil
    deleted_users = 0
    for u in demo_users:
        db.session.delete(u)
        deleted_users += 1

    db.session.commit()
    print(f"  ✓ {deleted_users} kullanıcı, {deleted_tasks} görev silindi")
    return deleted_users, deleted_tasks


# ---------- Seed ----------

def _create_user(username, full_name, email, firm, permission_level, password):
    u = User(
        username=username,
        full_name=full_name,
        email=email,
        firm=firm,
        permission_level=permission_level,
        active=True,
        notify_overdue=True,
        notify_sla_warning=True,
        notify_daily_digest=True,
    )
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    return u


def _create_task(user, scenario, today):
    title = f"{DEMO_TASK_PREFIX} {scenario['title']}"

    # created_at hesabı
    if "created_offset_days_h" in scenario:
        created_at = datetime.utcnow() + timedelta(hours=scenario["created_offset_days_h"])
    else:
        offset = scenario.get("created_offset_days", 0)
        created_at = datetime.utcnow() + timedelta(days=offset)

    # deadline hesabı
    deadline = None
    if scenario.get("deadline_offset_days") is not None:
        deadline = today + timedelta(days=scenario["deadline_offset_days"])

    t = Task(
        user_id=user.id,
        title=title,
        category=scenario["category"],
        priority=scenario["priority"],
        period=scenario["period"],
        firm=user.firm,
        deadline=deadline,
        is_done=scenario.get("is_done", False),
        alarm_enabled=scenario.get("alarm_enabled", True),
        created_at=created_at,
    )
    if scenario.get("is_done"):
        t.completed_at = datetime.utcnow() - timedelta(days=1)
    db.session.add(t)
    db.session.flush()
    return t


def _create_occurrences(task, completed_periods, today):
    """Rutin görevler için geçmiş tamamlama kayıtları."""
    for marker in completed_periods:
        if marker == "yesterday":
            target_date = today - timedelta(days=1)
        elif marker == "last_week":
            target_date = today - timedelta(days=7)
        elif marker == "last_month":
            target_date = today.replace(day=1) - timedelta(days=1)
        else:
            continue

        key = _period_key(task.period, target_date)
        if not key:
            continue

        exists = TaskOccurrence.query.filter_by(task_id=task.id, period_key=key).first()
        if exists:
            continue

        occ = TaskOccurrence(
            task_id=task.id,
            period_key=key,
            completed_at=datetime.combine(target_date, datetime.min.time()) + timedelta(hours=10),
        )
        db.session.add(occ)


def seed_demo_data():
    today = _today()
    print(f"→ Demo veri seed başlıyor (bugün: {today})")

    # Önce wipe (idempotent)
    wipe_demo_data()

    # Kullanıcıları oluştur
    print("→ Kullanıcılar oluşturuluyor...")
    users = []
    for u_def in DEMO_USERS:
        u = _create_user(*u_def)
        users.append(u)
        print(f"  ✓ {u.username} ({u.permission_level}, {u.firm})")

    # Director'ların yönettiği firmaları doldur (after_insert event auto-link yapar zaten,
    # ama burada explicit eklenebilir — Inventist director'ı her iki firmayı da yönetsin örnek için)
    inv_firm = Firm.query.filter_by(slug="inventist").first()
    assos_firm = Firm.query.filter_by(slug="assos").first()
    if inv_firm and assos_firm:
        # demo_director_inv → her iki firmayı yönetsin (super-director simülasyonu)
        director_inv = next(u for u in users if u.username == "demo_director_inv")
        if assos_firm not in director_inv.managed_firms:
            director_inv.managed_firms.append(assos_firm)

    # Görevleri oluştur
    print("→ Görevler oluşturuluyor...")
    scenarios = _build_task_scenarios(today)
    total_tasks = 0
    total_occurrences = 0

    for user in users:
        for scenario in scenarios:
            t = _create_task(user, scenario, today)
            total_tasks += 1
            if "completed_periods" in scenario:
                before = TaskOccurrence.query.count()
                _create_occurrences(t, scenario["completed_periods"], today)
                db.session.flush()
                total_occurrences += TaskOccurrence.query.count() - before

    db.session.commit()

    print(f"\n=== TAMAMLANDI ===")
    print(f"  Kullanıcılar: {len(users)}")
    print(f"  Görevler:     {total_tasks}")
    print(f"  Tamamlamalar: {total_occurrences}")
    print(f"\nDemo şifreleri: Demo2026! (tüm demo kullanıcılar)")
    print(f"Tekrar yüklemek için: python scripts/seed-staging-demo.py")
    print(f"Temizlemek için:      python scripts/seed-staging-demo.py --wipe")


# ---------- CLI ----------

def main():
    # Güvenlik: prod'da çalıştırılmasın
    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env == "production":
        print("HATA: APP_ENV=production. Demo seed prod'da çalıştırılamaz.")
        print("Bu script yalnızca staging/development içindir.")
        sys.exit(2)

    with app.app_context():
        if "--wipe" in sys.argv:
            wipe_demo_data()
        else:
            seed_demo_data()


if __name__ == "__main__":
    main()
