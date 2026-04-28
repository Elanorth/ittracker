"""
Pytest fixtures — IT Tracker test altyapısı.

Önemli: Ortam değişkenleri `app` import edilmeden önce set edilmeli.
- ENABLE_SCHEDULER=0 → APScheduler test sırasında çalışmasın
- ADMIN_PASSWORD=... → init_db() RuntimeError fırlatmasın
- DATABASE_URL=sqlite:///:memory: → izole, hızlı test DB
"""
import os

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ.setdefault("ADMIN_PASSWORD", "test_admin_pwd_only")
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_EMAIL", "test_admin@example.com")
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from app import app as flask_app
from models.database import db as _db, init_db


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
    """Her test sonrası tabloları temizle — izolasyon için."""
    yield _db
    _db.session.rollback()
    for table in reversed(_db.metadata.sorted_tables):
        _db.session.execute(table.delete())
    _db.session.commit()


@pytest.fixture
def login_as(client):
    """Kullanıcıyı session'a yerleştir. Kullanım: login_as(user)"""
    def _login(user):
        with client.session_transaction() as s:
            s["user_id"] = user.id
        return user
    return _login
