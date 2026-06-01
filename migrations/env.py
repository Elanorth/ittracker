"""Alembic env config — Flask-Migrate uyumlu.

Standart Flask-Migrate env.py template'i. Şunları yapar:
1. Flask app context'i kurar
2. SQLAlchemy URL'ini app.config'den okur
3. db.metadata'yı autogenerate kaynağı olarak kullanır
4. SQLite için batch mode aktif (ALTER TABLE limitations workaround)
"""
import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

# Alembic Config object
config = context.config

# Logging
fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def get_engine():
    try:
        # Flask-SQLAlchemy 3.x
        return current_app.extensions["migrate"].db.engine
    except (TypeError, AttributeError):
        # Flask-SQLAlchemy 2.x (eski fallback)
        return current_app.extensions["migrate"].db.get_engine()


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace("%", "%%")
    except AttributeError:
        return str(get_engine().url).replace("%", "%%")


config.set_main_option("sqlalchemy.url", get_engine_url())
target_db = current_app.extensions["migrate"].db


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Alembic'i offline modda çalıştır — SQL output'u dosyaya yazılır."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=get_metadata(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Alembic'i online modda çalıştır — DB'ye bağlanır, migration'ları uygular."""

    def process_revision_directives(context, revision, directives):
        # Boş migration'lar üretilmesin (autogenerate hiçbir değişiklik bulamadıysa)
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("Autogenerate sonucu boş — revision oluşturulmadı")

    conf_args = current_app.extensions["migrate"].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()
    with connectable.connect() as connection:
        # render_as_batch app.py'de Migrate(..., render_as_batch=True) ile set edildi
        # ve `conf_args` içinden gelir. Burada doğrudan parametre olarak geçilmez —
        # aksi halde TypeError: multiple values for keyword argument 'render_as_batch'.
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
