"""Подключение к базе данных через SQLAlchemy 2.0."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Базовый класс для всех моделей (таблиц)."""


def make_engine(url: str):
    # SQLite по умолчанию запрещает использовать соединение из другого потока,
    # а фоновые задачи FastAPI работают в отдельном потоке — снимаем ограничение.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: открывает сессию на время запроса и гарантированно закрывает её."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
