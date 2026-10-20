"""Настройки приложения. Все значения можно переопределить переменными окружения с префиксом HP_
(например HP_DATABASE_URL) или файлом backend/.env. Пример — в .env.example в корне проекта."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HP_", extra="ignore", env_ignore_empty=True)

    # По умолчанию SQLite-файл — чтобы проект запускался без установки PostgreSQL.
    # В docker-compose подставляется PostgreSQL.
    database_url: str = "sqlite:///./harvestpay.db"

    # "background" — расчёт в фоне внутри процесса API (не нужен Redis, удобно для разработки);
    # "celery"     — расчёт в отдельном воркере через очередь Redis (как в архитектуре проекта).
    task_mode: Literal["background", "celery"] = "background"
    redis_url: str = "redis://localhost:6379/0"

    satellite_provider: Literal["mock", "gee"] = "mock"
    gee_project: str | None = None
    gee_service_account: str | None = None
    gee_key_file: str | None = None
    seasons: int = 7

    registry_provider: Literal["mock", "statgov"] = "mock"
    statgov_url: str = "https://old.stat.gov.kz/api/juridical/counter/api/"
    min_company_age_months: int = 12

    limit_per_ha: int = 60_000  # ₸ на гектар — базовая норма лимита

    analyst_token: str = "analyst-demo-token"  # обязательно смените в продакшене
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
