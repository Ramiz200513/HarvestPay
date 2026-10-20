"""Точка входа API.

Запуск для разработки (из папки backend):
    uvicorn app.main:app --reload
Документация API (Swagger) откроется на http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import analyst, applications, farms
from .config import get_settings
from .db import Base, SessionLocal, engine
from .seed import seed_products

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Создаём таблицы, если их нет, и заполняем каталог. Для учебного MVP этого достаточно;
    # когда схема начнёт меняться на живых данных — подключаем миграции Alembic.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_products(db)
    yield


settings = get_settings()
app = FastAPI(title="Harvest Pay API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(farms.router)
app.include_router(applications.router)
app.include_router(analyst.router)


@app.get("/api/health", tags=["Служебное"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config", tags=["Служебное"])
def public_config() -> dict:
    """Какие источники данных включены — фронтенд честно показывает плашку «демо-данные»."""
    return {
        "satellite_provider": settings.satellite_provider,
        "registry_provider": settings.registry_provider,
        "seasons": settings.seasons,
        "limit_per_ha": settings.limit_per_ha,
    }
