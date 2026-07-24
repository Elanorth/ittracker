"""
Pytest fixtures — IT Tracker test altyapısı.

Önemli: Ortam değişkenleri `app` import edilmeden önce set edilmeli.
- ENABLE_SCHEDULER=0 → APScheduler test sırasında çalışmasın
- ADMIN_PASSWORD=... → init_db() RuntimeError fırlatmasın
- DATABASE_URL=sqlite:///:memory: → izole, hızlı test DB
"""

import os

# ⚠️ KRİTİK — testler ASLA gerçek e-posta göndermemeli.
# Sebep: app.py import'ta load_dotenv() ile yerel .env'i okur; geliştirici
# makinesinde .env GERÇEK SMTP creds içerebilir (ör. SMTP_USER=info@..., geçerli
# şifre). MAIL_SUPPRESS zorlanmazsa portal testleri (/portal/api/cases +
# ahmet@inventist.com.tr) send_case_ack ile GERÇEK mail atıp bounce üretir
# (2026-07 olayı: info@ gelen kutusuna çok sayıda NDR). setdefault DEĞİL, force (=):
# ortamda MAIL_SUPPRESS=0 olsa bile testler susturulur. load_dotenv override=False
# olduğu ve .env'de MAIL_SUPPRESS bulunmadığı için bu değer test boyunca korunur.
os.environ["MAIL_SUPPRESS"] = "1"

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ.setdefault("ADMIN_PASSWORD", "test_admin_pwd_only")
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_EMAIL", "test_admin@example.com")
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
# Test client HTTP üzerinden çalışır; Secure çerez gönderilmezse oturum kaybolur.
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")
# v5.13 — SLA testlerinin çoğu 7/24 varsayımıyla yazıldı (created_at - N saat = breach).
# İş-saati takvimi bu varsayımı bozar; testlerde varsayılan KAPALI, business-hours
# davranışı yalnız test_sla_business_hours.py'de açıkça (SLA_BUSINESS_HOURS=1) test edilir.
os.environ.setdefault("SLA_BUSINESS_HOURS", "0")

import pytest

from app import app as flask_app
from models.database import AuditLog, Firm, Task, TaskCompletion, Team, User, init_db
from models.database import db as _db


@pytest.fixture(scope="session")
def app():
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
    )
    with flask_app.app_context():
        _db.create_all()
        init_db()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    """Her test sonrası tabloları temizle, sonra seed datayı yeniden kur.

    session.remove() → session.close() eşdeğeri: session'ı döndürür ve
    bir sonraki işlemde yeni session açılır. Böylece testtler arası
    SQLAlchemy identity map'indeki stale/detached instance problemi önlenir.

    init_db() yeniden çağrılır: firms (İnventist, Assos), teams ve admin
    kullanıcısı yeniden seed edilir. v4.9'da firma şeridi testleri Firm
    satırlarının var olmasına dayanır.
    """
    yield _db
    _db.session.rollback()
    for table in reversed(_db.metadata.sorted_tables):
        _db.session.execute(table.delete())
    _db.session.commit()
    _db.session.remove()
    # Seed datayı geri getir — sonraki test bunlara güvenebilsin
    init_db()


@pytest.fixture
def login_as(client):
    """Kullanıcıyı session'a yerleştir. Kullanım: login_as(user)"""

    def _login(user):
        with client.session_transaction() as s:
            s["user_id"] = user.id
        return user

    return _login


@pytest.fixture
def user_factory(db):
    """
    Kullanıcı fabrikası: her test için bağımsız kullanıcı oluşturur.

    Kullanım:
        user = user_factory(username="cagla", full_name="Çağla Öztürk",
                            firm="inventist", permission_level="junior")
    """
    created = []

    def _make(
        username="test_user",
        full_name="Test Kullanıcı",
        email=None,
        firm="inventist",
        permission_level="junior",
        is_admin=False,
        password="test_pw_123",
        active=True,
        can_access_board=False,
    ):
        # Aynı username ile tekrar çağrılırsa unique suffix ekle
        if email is None:
            email = f"{username}_{len(created)}@example.com"
        u = User(
            username=f"{username}_{len(created)}",
            full_name=full_name,
            email=email,
            firm=firm,
            permission_level=permission_level,
            is_admin=is_admin,
            active=active,
            can_access_board=can_access_board,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        created.append(u)
        return u

    return _make


@pytest.fixture
def task_factory(db):
    """
    Görev fabrikası.

    Kullanım:
        task = task_factory(user_id=user.id, title="Sunucu yedeği", category="routine")
    """

    def _make(
        user_id,
        title="Test Görevi",
        category="other",
        priority="orta",
        period="Tek Seferlik",
        firm="inventist",
        is_done=False,
    ):
        from datetime import datetime

        t = Task(
            user_id=user_id,
            title=title,
            category=category,
            priority=priority,
            period=period,
            firm=firm,
            is_done=is_done,
            created_at=datetime.utcnow(),
        )
        db.session.add(t)
        db.session.commit()
        return t

    return _make
