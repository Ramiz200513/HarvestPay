"""Настройки приложения. Все значения можно переопределить переменными окружения с префиксом HP_
(например HP_DATABASE_URL) или файлом .env: в корне проекта (его же читает Docker) или backend/.env —
он важнее корневого. Пример — в .env.example в корне проекта."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_prefix="HP_", extra="ignore", env_ignore_empty=True
    )

    # По умолчанию SQLite-файл — чтобы проект запускался без установки PostgreSQL.
    # В docker-compose подставляется PostgreSQL.
    database_url: str = "sqlite:///./harvestpay.db"

    # "background" — расчёт в фоне внутри процесса API (не нужен Redis, удобно для разработки);
    # "celery"     — расчёт в отдельном воркере через очередь Redis (как в архитектуре проекта).
    task_mode: Literal["background", "celery"] = "background"
    redis_url: str = "redis://localhost:6379/0"

    # mock — демо; gee — Google Earth Engine; cdse — Copernicus Data Space (бесплатно, без Google)
    satellite_provider: Literal["mock", "gee", "cdse"] = "mock"
    gee_project: str | None = None
    gee_service_account: str | None = None
    gee_key_file: str | None = None
    cdse_client_id: str | None = None
    cdse_client_secret: str | None = None
    # Климат и влажность почвы из Open-Meteo (бесплатно, без ключа): заменяет синтетический климат демо-режима
    # и дополняет то, чего не вернул спутниковый провайдер. off — не ходить в интернет за климатом.
    climate_provider: Literal["openmeteo", "off"] = "openmeteo"
    seasons: int = 7

    registry_provider: Literal["mock", "statgov"] = "mock"
    statgov_url: str = "https://old.stat.gov.kz/api/juridical/counter/api/"
    min_company_age_months: int = 12
    # Налоговый долг до этой суммы — предупреждение (часто это пеня за просрочку на пару дней), больше — отказ
    max_tax_debt: int = 100_000

    limit_per_ha: int = 60_000  # ₸ на гектар — базовая норма лимита

    # --- Андеррайтинг: правила поверх спутникового балла (services/underwriting.py) ---
    class_a_min_age_months: int = 24  # класс A — только хозяйствам старше 2 лет
    max_limit_a: int = 20_000_000  # потолок лимита на одну заявку для класса A
    max_limit_b: int = 10_000_000  # и для класса B

    # --- Фондирование: кредитная линия банка-партнёра (services/finance.py) ---
    credit_line_bank: str = "Банк-партнёр (демо)"
    credit_line_limit: int = 500_000_000
    credit_line_rate: float = 0.17  # годовая ставка, под которую банк даёт линию

    # --- Реквизиты для оплаты рассрочки фермером: спецсчёт платформы в банке-партнёре ---
    # По умолчанию — демо-значения (на сайте помечены «демо»). В продакшене — настоящие из договора с банком.
    payee_name: str = "ТОО «Harvest Pay»"
    payee_bin: str = "240840012345"
    payee_bank: str = "Банк-партнёр (демо)"
    payee_iik: str = "KZ00000D000000000000"
    payee_bik: str = "DEMOKZKA"
    payee_kbe: str = "17"  # код бенефициара: юрлицо-резидент, негосударственное
    payee_knp: str = "710"  # код назначения платежа: оплата за товары
    payee_demo: bool = True  # показывать пометку «демо-реквизиты»
    support_email: str = "support@harvestpay.example"

    analyst_token: str = "analyst-demo-token"  # обязательно смените в продакшене
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
