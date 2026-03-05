"""Veritabanı Modelleri v3 — TaskCompletion + project_status"""
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    full_name     = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    role          = db.Column(db.String(50), default="IT Yardımcısı")
    firm          = db.Column(db.String(50), default="")
    is_admin      = db.Column(db.Boolean, default=False)
    active        = db.Column(db.Boolean, default=True)
    o365_id       = db.Column(db.String(100), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    tasks         = db.relationship("Task", backref="user", lazy=True)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)
    def to_dict(self):
        return {"id":self.id,"username":self.username,"full_name":self.full_name,"email":self.email,
                "role":self.role,"firm":self.firm,"is_admin":self.is_admin,"active":self.active,
                "o365_linked":bool(self.o365_id),"created_at":self.created_at.isoformat()}

import json as _json
from datetime import timedelta, date as _date

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
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    backups        = db.relationship("ConfigBackup", backref="task", lazy=True)
    completions    = db.relationship("TaskCompletion", backref="task", lazy=True,
                                     cascade="all, delete-orphan")

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

        is_done      = self.is_done
        completed_at = self.completed_at.isoformat() if self.completed_at else None

        if self.category == "routine" and self.period != "Tek Seferlik" and month and year:
            comp = TaskCompletion.query.filter_by(
                task_id=self.id, year=year, month=month
            ).first()
            is_done      = comp is not None
            completed_at = comp.completed_at.isoformat() if comp else None

        return {
            "id": self.id, "user_id": self.user_id, "title": self.title,
            "category": self.category, "period": self.period,
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
        }


class TaskCompletion(db.Model):
    """Rutin görevlerin aylık tamamlanma kaydı."""
    __tablename__ = "task_completions"
    id           = db.Column(db.Integer, primary_key=True)
    task_id      = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    year         = db.Column(db.Integer, nullable=False)
    month        = db.Column(db.Integer, nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    __table_args__ = (db.UniqueConstraint("task_id", "year", "month", name="uq_task_month"),)


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
                     role="IT Sorumlusu", firm="inventist", is_admin=True)
        admin.set_password(admin_password)
        db.session.add(admin)
    db.session.commit()
    admin_user = User.query.filter_by(is_admin=True).first()
    uname = admin_user.username if admin_user else admin_username
    print(f"✅ DB hazır. Admin kullanıcı: {uname}")
