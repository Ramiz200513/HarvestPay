"""Модели БД — 7 сущностей из ER-диаграммы:
Хозяйство → Поле → РасчётПоля, Хозяйство → Заявка → Решение, Заявка → ПозицияЗаявки ← Товар.

Отличие от первой версии ER-диаграммы: у Заявки есть field_id — заявка подаётся под конкретное поле,
иначе непонятно, какое поле оценивать.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# В PostgreSQL храним JSON как JSONB (быстрее и индексируется), в SQLite — как обычный JSON.
JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationStatus:
    PENDING = "pending"  # создана, ждёт очереди
    PROCESSING = "processing"  # идёт запрос к спутнику и расчёт
    APPROVED = "approved"  # одобрена (автоматически или аналитиком)
    REVIEW = "review"  # класс C — ждёт аналитика
    REJECTED = "rejected"  # отказ
    ERROR = "error"  # техническая ошибка (например, недоступен GEE)


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(primary_key=True)
    bin: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    legal_form: Mapped[str | None] = mapped_column(String(255))
    registered_at: Mapped[date | None] = mapped_column(Date)
    verification_status: Mapped[str] = mapped_column(String(20))  # verified | rejected
    verification_reasons: Mapped[list] = mapped_column(JsonType, default=list)
    registry_source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fields: Mapped[list[Field]] = relationship(back_populates="farm")
    applications: Mapped[list[Application]] = relationship(back_populates="farm")


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    geometry: Mapped[dict] = mapped_column(JsonType)  # GeoJSON Polygon
    crop: Mapped[str] = mapped_column(String(50))
    area_ha: Mapped[float] = mapped_column(Float)
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    farm: Mapped[Farm] = relationship(back_populates="fields")
    seasons: Mapped[list[FieldSeason]] = relationship(
        back_populates="field", order_by="FieldSeason.year", cascade="all, delete-orphan"
    )


class FieldSeason(Base):
    """«РасчётПоля»: спутниковые агрегаты за один сезон."""

    __tablename__ = "field_seasons"
    __table_args__ = (UniqueConstraint("field_id", "year", name="uq_field_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    ndvi_peak: Mapped[float | None] = mapped_column(Float)
    ndvi_mean: Mapped[float | None] = mapped_column(Float)
    soil_moisture: Mapped[float | None] = mapped_column(Float)
    scenes: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20))  # mock | gee

    field: Mapped[Field] = relationship(back_populates="seasons")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))  # seeds | fertilizer | protection
    supplier: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(20))
    price: Mapped[int] = mapped_column(Integer)  # ₸ за единицу


class Application(Base):
    __tablename__ = "applications"

    # UUID вместо 1, 2, 3...: ссылку на заявку нельзя подобрать перебором.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"))
    status: Mapped[str] = mapped_column(String(20), default=ApplicationStatus.PENDING, index=True)
    requested_amount: Mapped[int] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    farm: Mapped[Farm] = relationship(back_populates="applications")
    field: Mapped[Field] = relationship()
    items: Mapped[list[ApplicationItem]] = relationship(back_populates="application", cascade="all, delete-orphan")
    decision: Mapped[Decision | None] = relationship(back_populates="application", uselist=False)


class ApplicationItem(Base):
    """«ПозицияЗаявки»: какой товар и сколько. Цена копируется на момент заявки —
    если поставщик поменяет прайс, старая заявка не «поплывёт»."""

    __tablename__ = "application_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)

    application: Mapped[Application] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), unique=True)
    score: Mapped[float | None] = mapped_column(Float)
    score_class: Mapped[str] = mapped_column(String(1))  # A | B | C
    components: Mapped[dict] = mapped_column(JsonType, default=dict)
    reasons: Mapped[list] = mapped_column(JsonType, default=list)
    limit_amount: Mapped[int] = mapped_column(Integer, default=0)
    approved_amount: Mapped[int] = mapped_column(Integer, default=0)
    schedule: Mapped[list] = mapped_column(JsonType, default=list)
    decided_by: Mapped[str] = mapped_column(String(20), default="auto")  # auto | analyst
    analyst_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    application: Mapped[Application] = relationship(back_populates="decision")
