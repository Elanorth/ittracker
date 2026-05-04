"""Veritabanı Modelleri v3 — TaskCompletion + project_status"""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

# v4.9 — IT Müdürü çoklu firma yönetimi için many-to-many ilişki tablosu.
# User.firm (kendi firması) tek string olarak kalır; managed_firms ise
# yönetim kapsamı (super_admin gibi geniş ama firmaya kısıtlı erişim).
user_managed_firms = db.Table(
    "user_managed_firms",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    db.Column("firm_id", db.Integer, db.ForeignKey("firms.id", ondelete="CASCADE"), primary_key=True),
)


class User(db.Model):
    __tablename__ = "users"
    id               = db.Column(db.Integer, primary_key=True)
    username         = db.Column(db.String(50), unique=True, nullable=False)
    full_name        = db.Column(db.String(100), nullable=False)
    email            = db.Column(db.String(150), unique=True, nullable=False)
    role             = db.Column(db.String(50), default="IT Yardımcısı")
    # firm: tek string. "Boş firma" semantiği = "" (boş string).
    # @validates ile None → "" coerce edilir, böylece kod her yerde tutarlı
    # olarak `if not user.firm` veya `user.firm == ""` kontrolü kullanabilir.
    firm             = db.Column(db.String(50), nullable=False, default="")
    is_admin         = db.Column(db.Boolean, default=False)
    permission_level  = db.Column(db.String(20), default="junior")  # super_admin | it_director | it_manager | it_specialist | junior
    can_access_board  = db.Column(db.Boolean, default=False)
    active            = db.Column(db.Boolean, default=True)
    o365_id          = db.Column(db.String(100), unique=True, nullable=True)
    password_hash    = db.Column(db.String(256), nullable=False)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    # v4.6 — Bildirim tercihleri
    notify_overdue      = db.Column(db.Boolean, default=True)   # 3+ gün geciken görevler
    notify_sla_warning  = db.Column(db.Boolean, default=True)   # SLA %75 eşiğine yaklaşan destek talepleri
    notify_daily_digest = db.Column(db.Boolean, default=True)   # günlük özet maili
    # v4.3 — Task'ta iki FK var (user_id sahip, assigned_by atayan). Sahip ilişkisini belirt.
    tasks            = db.relationship("Task", backref="user", lazy=True,
                                        foreign_keys="Task.user_id")
    assigned_tasks   = db.relationship("Task", lazy=True,
                                        foreign_keys="Task.assigned_by")
    # v4.9 — IT Müdürü'nün yönettiği firmalar (many-to-many)
    managed_firms    = db.relationship("Firm", secondary=user_managed_firms,
                                        lazy="select", backref="managers")

    @validates("firm")
    def _validate_firm(self, key, value):
        """firm=None gönderilse de "" olarak saklanır.

        Sebep: v4.9 öncesi `firm` string'di ve `default=""` olarak tanımlıydı,
        ama `User(firm=None)` çağrısında SQLAlchemy default'u uygulamıyordu —
        sonuç olarak NULL ile "" arasında semantik karışıklık oluşuyordu.
        Tek doğru "boş firma" temsili: "" (boş string).
        """
        return value if value is not None else ""

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

    @property
    def is_super_admin(self):
        return self.permission_level == "super_admin"

    @property
    def is_director_or_above(self):
        """IT Müdürü ve üstü — firma bazlı geniş erişim"""
        return self.permission_level in ("super_admin", "it_director")

    @property
    def is_manager_or_above(self):
        return self.permission_level in ("super_admin", "it_director", "it_manager", "it_specialist")

    @property
    def managed_firm_slugs(self):
        """v4.9 — yönetilen firmaların slug listesi (önbelleksiz, lazy)."""
        return [f.slug for f in (self.managed_firms or [])]

    def has_firm_scope(self, firm_value):
        """v4.9 — verilen firm slug değeri yönetim kapsamımda mı?

        super_admin için her zaman True.
        it_director için: managed_firms slug listesinde VEYA kendi firm'i (geriye dönük).
        Diğer roller için: yalnızca kendi firm'i ile eşleşirse True.
        """
        if not firm_value:
            return False
        if self.is_super_admin:
            return True
        if self.permission_level == "it_director":
            if firm_value in self.managed_firm_slugs:
                return True
        # Geriye dönük: kendi firması ile eşleşirse evet
        return firm_value == self.firm

    def to_dict(self):
        return {"id":self.id,"username":self.username,"full_name":self.full_name,"email":self.email,
                "role":self.role,"firm":self.firm,"is_admin":self.is_admin,"active":self.active,
                "permission_level":self.permission_level or "junior",
                "can_access_board":bool(self.can_access_board),
                "managed_firm_slugs": self.managed_firm_slugs,  # v4.9 — IT Müdürü dashboard şeridi için
                "notify_overdue":bool(self.notify_overdue) if self.notify_overdue is not None else True,
                "notify_sla_warning":bool(self.notify_sla_warning) if self.notify_sla_warning is not None else True,
                "notify_daily_digest":bool(self.notify_daily_digest) if self.notify_daily_digest is not None else True,
                "o365_linked":bool(self.o365_id),"created_at":self.created_at.isoformat()}

import json as _json
from datetime import timedelta, date as _date

# v4.5 — SLA hedef süreleri (Jira service-desk varsayılanlarına paralel).
# Destek talepleri (category=="support") için uygulanır.
SLA_HOURS = {"yüksek": 4, "orta": 24, "düşük": 72}
def _sla_target_hours(priority):
    return SLA_HOURS.get((priority or "orta").strip().lower(), 24)

def _period_key(period: str, dt) -> str | None:
    """v5.0 — Verilen tarih için periyota karşılık gelen kanonik string key.

    Kullanım: TaskOccurrence.period_key alanı. Aynı periyotta birden fazla
    completion oluşmasın diye UNIQUE(task_id, period_key) ile birlikte çalışır.

    - "Günlük"      → "YYYY-MM-DD" (ISO date)
    - "Haftalık"    → "YYYY-Www" (ISO week, ör. "2026-W18")
    - "Aylık"       → "YYYY-MM"
    - "Yıllık"      → "YYYY"
    - "Tek Seferlik" veya geçersiz periyot → None
    """
    if dt is None:
        return None
    if period == "Günlük":
        return dt.isoformat()
    if period == "Haftalık":
        iso = dt.isocalendar()  # (iso_year, iso_week, iso_weekday)
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    if period == "Aylık":
        return f"{dt.year:04d}-{dt.month:02d}"
    if period == "Yıllık":
        return f"{dt.year:04d}"
    return None


def _previous_period_key(period: str, today) -> str | None:
    """v5.0 — Bugünden bir önceki periyot için key. Overdue tespiti için."""
    if today is None or period == "Tek Seferlik":
        return None
    if period == "Günlük":
        return _period_key("Günlük", today - timedelta(days=1))
    if period == "Haftalık":
        return _period_key("Haftalık", today - timedelta(days=7))
    if period == "Aylık":
        if today.month == 1:
            prev = _date(today.year - 1, 12, 1)
        else:
            prev = _date(today.year, today.month - 1, 1)
        return _period_key("Aylık", prev)
    if period == "Yıllık":
        return _period_key("Yıllık", _date(today.year - 1, 1, 1))
    return None


def _next_due_date(period: str, from_date=None) -> _date:
    """Periyota göre bir sonraki deadline tarihini hesapla (gösterim amaçlı)."""
    base = from_date or _date.today()
    if period == "Günlük":
        return base + timedelta(days=1)
    if period == "Haftalık":
        days_ahead = 7 - base.weekday()
        if days_ahead == 0: days_ahead = 7
        return base + timedelta(days=days_ahead)
    if period == "Aylık":
        if base.month == 12:
            return _date(base.year + 1, 1, 1)
        return _date(base.year, base.month + 1, 1)
    if period == "Yıllık":
        return _date(base.year + 1, 1, 1)
    return None  # Tek Seferlik


class Task(db.Model):
    __tablename__ = "tasks"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title          = db.Column(db.String(300), nullable=False)
    category       = db.Column(db.String(50), default="other")
    priority       = db.Column(db.String(10), default="orta")  # support talepleri için: düşük/orta/yüksek
    period         = db.Column(db.String(50), default="Tek Seferlik")
    firm           = db.Column(db.String(50), default="")
    team           = db.Column(db.String(100), default="")
    notes          = db.Column(db.Text, default="")
    deadline       = db.Column(db.Date, nullable=True)
    is_done        = db.Column(db.Boolean, default=False)
    completed_at   = db.Column(db.DateTime, nullable=True)
    last_completed = db.Column(db.DateTime, nullable=True)
    next_due       = db.Column(db.Date, nullable=True)
    checklist      = db.Column(db.Text, default="[]")
    checklist_done = db.Column(db.Text, default="[]")
    project_status = db.Column(db.Text, default="")   # Proje durum notu
    manager_note   = db.Column(db.Text, default="")   # v4.3 — IT Müdürü notu (kırmızı font)
    assigned_by    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # v4.3 — görevi atayan yönetici
    # v4.6 — Bildirim/alarm
    alarm_enabled  = db.Column(db.Boolean, default=True)   # bu görev için bildirim/alarm aktif mi
    last_notified  = db.Column(db.DateTime, nullable=True) # son bildirim maili atılan zaman (anti-spam)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    backups        = db.relationship("ConfigBackup", backref="task", lazy=True,
                                     cascade="all, delete-orphan")
    completions    = db.relationship("TaskOccurrence", backref="task", lazy=True,
                                     cascade="all, delete-orphan")

    def is_done_now(self, today=None):
        """v5.0 — Bu görev şu anda (bugün için) tamamlanmış mı?

        Rutin görevler: aktif periyot için TaskOccurrence kaydı var mı?
        Diğer kategoriler: Task.is_done flag.
        """
        if self.category == "routine" and self.period != "Tek Seferlik":
            key = _period_key(self.period, today or _date.today())
            if not key:
                return False
            return TaskOccurrence.query.filter_by(task_id=self.id, period_key=key).first() is not None
        return bool(self.is_done)

    def is_overdue_now(self, today=None):
        """v5.0 — Bu görev şu anda gecikmiş mi?

        Rutin görevler: önceki periyot için TaskOccurrence yoksa overdue.
        Diğer kategoriler: deadline geçmiş ve tamamlanmamışsa overdue.
        """
        today = today or _date.today()
        if self.category == "routine" and self.period != "Tek Seferlik":
            prev_key = _previous_period_key(self.period, today)
            if not prev_key:
                return False
            return TaskOccurrence.query.filter_by(task_id=self.id, period_key=prev_key).first() is None
        return (not self.is_done) and (self.deadline is not None) and (self.deadline < today)

    def get_checklist(self):
        try: return _json.loads(self.checklist or "[]")
        except: return []

    def get_checklist_done(self):
        try: return _json.loads(self.checklist_done or "[]")
        except: return []

    def to_dict(self, month=None, year=None):
        cl  = self.get_checklist()
        cld = self.get_checklist_done()
        while len(cld) < len(cl): cld.append(False)

        # Rutin görevlerde is_done, o aya ait TaskCompletion kaydından gelir
        is_done      = self.is_done
        completed_at = self.completed_at.isoformat() if self.completed_at else None

        if self.category == "routine" and self.period != "Tek Seferlik" and month and year:
            comp = TaskCompletion.query.filter_by(
                task_id=self.id, year=year, month=month
            ).first()
            is_done      = comp is not None
            completed_at = comp.completed_at.isoformat() if comp else None

        # Önceki aylardan taşınan tamamlanmamış görev kontrolü
        from_previous_month = False
        if month and year and self.category not in ("routine", "project") and not self.is_done:
            from_previous_month = (
                self.created_at.year < year or
                (self.created_at.year == year and self.created_at.month < month)
            )

        # v4.5 — SLA hesaplamaları (destek talepleri için)
        sla = None
        if self.category == "support":
            target_h = _sla_target_hours(self.priority)
            deadline_dt = self.created_at + timedelta(hours=target_h) if self.created_at else None
            now = datetime.utcnow()
            if is_done and self.completed_at:
                resolution_h = (self.completed_at - self.created_at).total_seconds() / 3600.0
                breached = (self.completed_at > deadline_dt) if deadline_dt else False
                remaining_h = 0.0
            else:
                resolution_h = None
                remaining_seconds = (deadline_dt - now).total_seconds() if deadline_dt else 0
                remaining_h = remaining_seconds / 3600.0
                breached = remaining_seconds < 0
            sla = {
                "target_hours": target_h,
                "deadline": deadline_dt.isoformat() if deadline_dt else None,
                "remaining_hours": round(remaining_h, 2),
                "resolution_hours": round(resolution_h, 2) if resolution_h is not None else None,
                "breached": bool(breached),
            }

        return {
            "id": self.id, "user_id": self.user_id, "title": self.title,
            "category": self.category, "period": self.period,
            "priority": (self.priority or "orta"),
            "firm": self.firm, "team": self.team, "notes": self.notes,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "next_due": self.next_due.isoformat() if self.next_due else None,
            "last_completed": self.last_completed.isoformat() if self.last_completed else None,
            "is_done": is_done,
            "completed_at": completed_at,
            "created_at": self.created_at.isoformat(),
            "has_backup": len(self.backups) > 0,
            "checklist": cl,
            "checklist_done": cld,
            "project_status": self.project_status or "",
            "manager_note": self.manager_note or "",
            "assigned_by": self.assigned_by,
            "from_previous_month": from_previous_month,
            "sla": sla,
            "alarm_enabled": bool(self.alarm_enabled) if self.alarm_enabled is not None else True,
            "last_notified": self.last_notified.isoformat() if self.last_notified else None,
        }


class TaskOccurrence(db.Model):
    """v5.0 — Rutin görevlerin periyot bazlı tamamlanma kaydı.

    Önceki TaskCompletion (yıl+ay) yerine geçer. period_key string'i
    Günlük/Haftalık/Aylık/Yıllık periyotların hepsini tek alanda kanonik
    olarak temsil eder (bkz. _period_key).

    Geriye dönük uyumluluk: dosya sonunda `TaskCompletion = TaskOccurrence`
    alias'ı tanımlı; eski import'lar (services/, app.py, tests/) çalışmaya
    devam eder.
    """
    __tablename__ = "task_occurrences"
    id           = db.Column(db.Integer, primary_key=True)
    task_id      = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    period_key   = db.Column(db.String(20), nullable=False, index=True)
    # v5.0 — Geriye dönük uyumluluk: eski kod (services/, app.py, tests/) hâlâ
    # year/month ile sorgu yapıyor. Bu kolonlar deprecated; sonraki commit'te
    # tüm endpoint'ler period_key'e geçirildiğinde kaldırılacak.
    year         = db.Column(db.Integer, nullable=True)
    month        = db.Column(db.Integer, nullable=True)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    __table_args__ = (db.UniqueConstraint("task_id", "period_key", name="uq_task_period"),)

    def __init__(self, **kwargs):
        """Backward-compat: year+month verilirse period_key otomatik üretilir.

        Yeni kod period_key'i doğrudan vermeli; year/month sadece eski kod
        (TaskCompletion(task_id=, year=, month=)) için bridge.
        """
        if "period_key" not in kwargs and "year" in kwargs and "month" in kwargs:
            y = kwargs["year"]
            m = kwargs["month"]
            if y is not None and m is not None:
                kwargs["period_key"] = f"{int(y):04d}-{int(m):02d}"
        super().__init__(**kwargs)


class ConfigBackup(db.Model):
    """Firmware/güncelleme öncesi yüklenen config dosyaları"""
    __tablename__ = "config_backups"
    id          = db.Column(db.Integer, primary_key=True)
    task_id     = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename    = db.Column(db.String(255), nullable=False)
    file_path   = db.Column(db.String(512), nullable=False)
    device      = db.Column(db.String(200), default="")
    file_size   = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    def to_dict(self):
        task = db.session.get(Task, self.task_id)
        return {
            "id":          self.id,
            "task_id":     self.task_id,
            "task_title":  task.title if task else "—",
            "firm":        task.firm  if task else "",
            "team":        task.team  if task else "",
            "filename":    self.filename,
            "device":      self.device,
            "file_size":   self.file_size,
            "file_size_kb": round(self.file_size/1024, 1),
            "uploaded_at": self.uploaded_at.isoformat(),
        }

class Firm(db.Model):
    __tablename__ = "firms"
    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(100), unique=True, nullable=False)
    slug  = db.Column(db.String(100), unique=True, nullable=False)
    teams = db.relationship("Team", backref="firm", lazy=True, cascade="all, delete-orphan")
    def to_dict(self): return {"id":self.id,"name":self.name,"slug":self.slug,"teams":[t.to_dict() for t in self.teams]}

class Team(db.Model):
    __tablename__ = "teams"
    id      = db.Column(db.Integer, primary_key=True)
    firm_id = db.Column(db.Integer, db.ForeignKey("firms.id"), nullable=False)
    name    = db.Column(db.String(100), nullable=False)
    def to_dict(self): return {"id":self.id,"firm_id":self.firm_id,"name":self.name}

class Invitation(db.Model):
    __tablename__ = "invitations"
    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), nullable=False)
    full_name  = db.Column(db.String(100), default="")
    role       = db.Column(db.String(50), default="IT Yardımcısı")
    firm       = db.Column(db.String(50), default="")
    token      = db.Column(db.String(64), unique=True, nullable=False)
    used       = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    invited_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def to_dict(self): return {"id":self.id,"email":self.email,"full_name":self.full_name,
                               "role":self.role,"firm":self.firm,"used":self.used,"expires_at":self.expires_at.isoformat()}

class BoardCard(db.Model):
    """Ortak Alan — Trello tarzı kanban kartı"""
    __tablename__ = "board_cards"
    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(300), nullable=False)
    description    = db.Column(db.Text, default="")
    column         = db.Column(db.String(20), default="todo")  # todo/in_progress/review/done
    position       = db.Column(db.Integer, default=0)
    color          = db.Column(db.String(20), default="yellow")  # yellow/green/blue/pink/orange
    checklist      = db.Column(db.Text, default="[]")
    checklist_done = db.Column(db.Text, default="[]")
    created_by     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_to    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    firm           = db.Column(db.String(50), default="")
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    comments       = db.relationship("BoardComment", backref="card", lazy=True, cascade="all, delete-orphan")
    creator        = db.relationship("User", foreign_keys=[created_by])
    assignee       = db.relationship("User", foreign_keys=[assigned_to])

    def get_checklist(self):
        try: return _json.loads(self.checklist or "[]")
        except: return []

    def get_checklist_done(self):
        try: return _json.loads(self.checklist_done or "[]")
        except: return []

    def to_dict(self):
        cl  = self.get_checklist()
        cld = self.get_checklist_done()
        while len(cld) < len(cl): cld.append(False)
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "column": self.column, "position": self.position, "color": self.color,
            "checklist": cl, "checklist_done": cld,
            "created_by": self.created_by,
            "creator_name": self.creator.full_name if self.creator else "",
            "assigned_to": self.assigned_to,
            "assignee_name": self.assignee.full_name if self.assignee else "",
            "firm": self.firm,
            "comment_count": len(self.comments),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BoardComment(db.Model):
    """Ortak Alan kart yorumu"""
    __tablename__ = "board_comments"
    id         = db.Column(db.Integer, primary_key=True)
    card_id    = db.Column(db.Integer, db.ForeignKey("board_cards.id", ondelete="CASCADE"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author     = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        return {
            "id": self.id, "card_id": self.card_id,
            "user_id": self.user_id,
            "author_name": self.author.full_name if self.author else "",
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


class AuditLog(db.Model):
    """v4.4 — Denetim kaydı. Kim, ne zaman, ne yaptı."""
    __tablename__ = "audit_logs"
    id             = db.Column(db.Integer, primary_key=True)
    actor_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_name     = db.Column(db.String(150), default="")  # snapshot (kullanıcı silinirse korunur)
    action         = db.Column(db.String(60), nullable=False)   # task.create, task.update, task.delete, task.assign, task.manager_note, user.invite, user.update, user.delete, user.permission
    entity_type    = db.Column(db.String(40), default="")        # task / user / invitation / firm / team
    entity_id      = db.Column(db.Integer, nullable=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    target_name    = db.Column(db.String(150), default="")
    firm           = db.Column(db.String(50), default="")
    summary        = db.Column(db.String(500), default="")        # kısa insan-okunabilir özet
    details        = db.Column(db.Text, default="")               # JSON string — ek detaylar
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name or "",
            "action": self.action,
            "entity_type": self.entity_type or "",
            "entity_id": self.entity_id,
            "target_user_id": self.target_user_id,
            "target_name": self.target_name or "",
            "firm": self.firm or "",
            "summary": self.summary or "",
            "details": self.details or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# v4.9 — IT Müdürü kullanıcısı insert edildikten sonra kendi firma'sı otomatik
# olarak managed_firms'a eklensin. `after_insert` mapper event'i raw SQL ile
# user_managed_firms tablosuna bağlantı satırı ekler — ORM relationship
# lazy-load taraması yapmaz, böylece flush sırasındaki recursion riski yok.
@event.listens_for(User, "after_insert")
def _auto_link_director_to_own_firm(mapper, connection, target):
    """it_director eklendikten sonra kendi firma'sı managed_firms'a eklenir.

    Çalışma anı: User INSERT'inden hemen sonra (target.id artık dolu).
    Yöntem: `firms` tablosunda slug eşleşmesi varsa user_managed_firms tablosuna
    raw INSERT. Mevcut bağlantı varsa idempotent (UNIQUE primary_key sayesinde).
    """
    if target.permission_level != "it_director" or not target.firm:
        return
    from sqlalchemy import text as _text
    firm_row = connection.execute(
        _text("SELECT id FROM firms WHERE slug = :s"),
        {"s": target.firm}
    ).first()
    if not firm_row:
        return
    # Çift eklemeyi önle
    existing = connection.execute(
        _text("SELECT 1 FROM user_managed_firms WHERE user_id=:u AND firm_id=:f"),
        {"u": target.id, "f": firm_row[0]}
    ).first()
    if existing:
        return
    connection.execute(
        user_managed_firms.insert().values(user_id=target.id, firm_id=firm_row[0])
    )


def init_db():
    import os
    from sqlalchemy import inspect, text
    db.create_all()

    # Migration: mevcut tasks tablosuna project_status sütunu ekle
    inspector = inspect(db.engine)
    cols = [c["name"] for c in inspector.get_columns("tasks")]
    if "project_status" not in cols:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN project_status TEXT DEFAULT ''"))
        db.session.commit()
        print("✅ Migration: project_status sütunu eklendi")

    # Migration: mevcut tasks tablosuna priority sütunu ekle (support talepleri için)
    # SQLite: ALTER TABLE ile kolon eklenir; mevcut satırlar NULL kalabilir, onları "orta" yapıyoruz.
    cols = [c["name"] for c in inspector.get_columns("tasks")]
    if "priority" not in cols:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'orta'"))
        db.session.execute(text("UPDATE tasks SET priority = 'orta' WHERE priority IS NULL OR priority = ''"))
        db.session.commit()
        print("✅ Migration: priority sütunu eklendi")

    # Migration: v4.3 — manager_note sütunu ekle
    cols = [c["name"] for c in inspector.get_columns("tasks")]
    if "manager_note" not in cols:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN manager_note TEXT DEFAULT ''"))
        db.session.commit()
        print("Migration: manager_note sutunu eklendi")

    # Migration: v4.3 — assigned_by sütunu ekle
    cols = [c["name"] for c in inspector.get_columns("tasks")]
    if "assigned_by" not in cols:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN assigned_by INTEGER"))
        db.session.commit()
        print("Migration: assigned_by sutunu eklendi")

    # Migration: v4.6 — alarm_enabled sütunu ekle
    cols = [c["name"] for c in inspector.get_columns("tasks")]
    if "alarm_enabled" not in cols:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN alarm_enabled BOOLEAN DEFAULT 1"))
        db.session.execute(text("UPDATE tasks SET alarm_enabled = 1 WHERE alarm_enabled IS NULL"))
        db.session.commit()
        print("Migration: alarm_enabled sutunu eklendi")

    # Migration: v4.6 — last_notified sütunu ekle
    cols = [c["name"] for c in inspector.get_columns("tasks")]
    if "last_notified" not in cols:
        db.session.execute(text("ALTER TABLE tasks ADD COLUMN last_notified DATETIME"))
        db.session.commit()
        print("Migration: last_notified sutunu eklendi")

    # Migration: permission_level sütunu ekle
    user_cols = [c["name"] for c in inspector.get_columns("users")]
    if "permission_level" not in user_cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN permission_level TEXT DEFAULT 'junior'"))
        # Mevcut kullanıcıları dönüştür
        db.session.execute(text("""
            UPDATE users SET permission_level = CASE
                WHEN is_admin = 1 AND (o365_id IS NULL OR o365_id = '') THEN 'super_admin'
                WHEN is_admin = 1 THEN 'it_manager'
                ELSE 'junior'
            END
        """))
        db.session.commit()
        print("Migration: permission_level sutunu eklendi")

    # Migration: can_access_board sütunu ekle
    user_cols = [c["name"] for c in inspector.get_columns("users")]
    if "can_access_board" not in user_cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN can_access_board BOOLEAN DEFAULT 0"))
        # Super admin'lere otomatik erişim ver
        db.session.execute(text("UPDATE users SET can_access_board = 1 WHERE permission_level = 'super_admin'"))
        db.session.commit()
        print("Migration: can_access_board sutunu eklendi")

    # Migration: v4.6 — bildirim tercihleri
    user_cols = [c["name"] for c in inspector.get_columns("users")]
    for col_name in ("notify_overdue", "notify_sla_warning", "notify_daily_digest"):
        if col_name not in user_cols:
            db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} BOOLEAN DEFAULT 1"))
            db.session.execute(text(f"UPDATE users SET {col_name} = 1 WHERE {col_name} IS NULL"))
            db.session.commit()
            print(f"Migration: {col_name} sutunu eklendi")

    # Migration: ADMIN_USERNAME kullanıcısı her zaman super_admin olmalı
    admin_uname = os.environ.get("ADMIN_USERNAME", "levent.can")
    admin_fix = User.query.filter_by(username=admin_uname).first()
    if admin_fix and admin_fix.permission_level != "super_admin":
        admin_fix.permission_level = "super_admin"
        admin_fix.is_admin = True
        db.session.commit()
        print(f"Migration: {admin_uname} super_admin yapildi")

    # v4.9 Migration — Mevcut it_director'lar için managed_firms backfill.
    # Yeni kayıtlar `before_flush` event listener ile zaten otomatik link'lenir;
    # bu blok prod'daki ESKİ direktörler için tek seferlik geriye dönük doldurma.
    directors = User.query.filter_by(permission_level="it_director").all()
    backfilled = 0
    for d in directors:
        if not d.firm:
            continue
        if any(f.slug == d.firm for f in d.managed_firms):
            continue
        f = Firm.query.filter_by(slug=d.firm).first()
        if f and f not in d.managed_firms:
            d.managed_firms.append(f)
            backfilled += 1
    if backfilled:
        db.session.commit()
        print(f"v4.9 Migration: {backfilled} it_director için managed_firms backfill edildi")

    if not Firm.query.first():
        inv = Firm(name="İnventist", slug="inventist")
        ass = Firm(name="Assos",     slug="assos")
        db.session.add_all([inv, ass]); db.session.flush()
        for n in ["Teknik Ekip","Misafir İlişkileri","F&B","Akademi Yönetimi","Otel ve Ön Büro","Housekeeping","İnsan Kaynakları","Genel"]:
            db.session.add(Team(firm_id=inv.id, name=n))
        for n in ["Resepsiyon","Teknik Servis","Yiyecek-İçecek","İdare","Animasyon","Genel"]:
            db.session.add(Team(firm_id=ass.id, name=n))
    admin_username = os.environ.get("ADMIN_USERNAME", "levent.can")
    admin_email    = os.environ.get("ADMIN_EMAIL",    "levent.can@inventist.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    admin_exists = (
        User.query.filter_by(username=admin_username).first() or
        User.query.filter_by(email=admin_email).first() or
        User.query.filter_by(is_admin=True).first()
    )
    if not admin_exists:
        if not admin_password:
            raise RuntimeError("ADMIN_PASSWORD ortam değişkeni ayarlanmamış! .env dosyasını kontrol edin.")
        admin = User(username=admin_username, full_name="Levent Mahir Can",
                     email=admin_email,
                     role="IT Sorumlusu", firm="inventist", is_admin=True,
                     permission_level="super_admin")
        admin.set_password(admin_password)
        db.session.add(admin)
    db.session.commit()
    admin_user = User.query.filter_by(is_admin=True).first()
    uname = admin_user.username if admin_user else admin_username
    print(f"✅ DB hazır. Admin kullanıcı: {uname}")


# v5.0 — Geriye dönük uyumluluk alias'ı.
# services/, app.py, tests/ ve diğer modüller hâlâ `TaskCompletion` import ediyor.
# Sonraki commit'lerde bu modüller TaskOccurrence + period_key API'sine geçirilecek;
# bu commit kapsamı dar (sadece model katmanı), bu yüzden alias şeffaf çalışsın.
TaskCompletion = TaskOccurrence
