"""Точка входа API.

Запуск для разработки (из папки backend):
    uvicorn app.main:app --reload
Документация API (Swagger) откроется на http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import analyst, applications, deals, farms
from .config import get_settings
from .db import SessionLocal, engine
from .migrate import run_migrations
from .seed import seed_products

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Приводим схему БД к последней версии (миграции Alembic) и заполняем каталог товаров.
    run_migrations(engine)
    with SessionLocal() as db:
        seed_products(db)
    yield


settings = get_settings()
app = FastAPI(title="Harvest Pay API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(farms.router)
app.include_router(applications.router)
app.include_router(analyst.router)
app.include_router(deals.router)


@app.get("/api/health", tags=["Служебное"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config", tags=["Служебное"])
def public_config() -> dict:
    """Какие источники данных включены — фронтенд честно показывает плашку «демо-данные»."""
    return {
        "satellite_provider": settings.satellite_provider,
        "climate_provider": settings.climate_provider,
        "registry_provider": settings.registry_provider,
        "seasons": settings.seasons,
        "limit_per_ha": settings.limit_per_ha,
        "max_limit_a": settings.max_limit_a,
        "max_limit_b": settings.max_limit_b,
    }
