"""Окружение Alembic: откуда брать адрес БД и описание таблиц."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401 — импорт регистрирует все таблицы в Base.metadata
from app.config import get_settings
from app.db import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Адрес БД — из настроек приложения, чтобы не дублировать его в alembic.ini
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata

# Объекты, которых нет в models.py, но они есть в БД намеренно: служебная таблица PostGIS
# и индексы, которые миграция 0002 создаёт по-разному для PostgreSQL и SQLite.
# Без этого фильтра `alembic revision --autogenerate` предлагал бы их удалить.
IGNORED = {"spatial_ref_sys", "ix_fields_geom", "ix_fields_bbox"}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    return name not in IGNORED


def run_migrations_offline() -> None:
    """Режим «только SQL»: alembic upgrade head --sql печатает SQL вместо выполнения."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is None:
        connectable = engine_from_config(config.get_section(config.config_ini_section, {}), poolclass=pool.NullPool)
        with connectable.connect() as connection:
            _run(connection)
    else:
        _run(connectable)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        # SQLite не умеет ALTER TABLE в полном объёме — batch-режим пересоздаёт таблицу за нас
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
