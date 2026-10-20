"""Применение миграций Alembic при старте API — чтобы студенту не нужно было помнить
про отдельную команду. Вручную то же самое делает `alembic upgrade head` из папки backend."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

BACKEND_DIR = Path(__file__).resolve().parent.parent


def run_migrations(engine: Engine) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False  # не перенастраиваем логирование uvicorn
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        inspector = inspect(connection)
        if inspector.has_table("farms") and not inspector.has_table("alembic_version"):
            # База создана версией 0.1 через create_all — её схема совпадает с миграцией 0001.
            # Помечаем её как 0001, чтобы применились только новые миграции.
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
