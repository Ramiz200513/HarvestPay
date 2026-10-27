"""Модели БД — 7 сущностей из ER-диаграммы:
Хозяйство → Поле → РасчётПоля, Хозяйство → Заявка → Решение, Заявка → ПозицияЗаявки ← Товар.
С версии 0.3 добавлены Поставщик (Товар → Поставщик) и Сделка (Заявка → Сделка): маркетплейс
платит поставщику со скидкой из кредитной линии банка, а фермер рассчитывается осенью.

Отличие от первой версии ER-диаграммы: у Заявки есть field_id — заявка подаётся под конкретное поле,
иначе непонятно, какое поле оценивать.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# В PostgreSQL храним JSON как JSONB (быстрее и индексируется), в SQLite — как обычный JSON.
JsonType = JSON().with_variant(JSONB(), "postgresql")

# Контур поля для пространственных запросов. В PostgreSQL — настоящая геометрия PostGIS
# (с GIST-индексом, см. миграцию 0002), в SQLite — просто текст WKT: там пересечения
# считаются в Python (services/overlap.py). spatial_index=False — индекс создаёт миграция.
GeomType = Text().with_variant(Geometry("POLYGON", srid=4326, spatial_index=False), "postgresql")


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
    # Налоги, аресты, суды, субсидии (services/compliance.py) и чек-лист проверки для экрана
    compliance: Mapped[dict] = mapped_column(JsonType, default=dict)
    checks: Mapped[list] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fields: Mapped[list[Field]] = relationship(back_populates="farm")
    applications: Mapped[list[Application]] = relationship(back_populates="farm")


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    geometry: Mapped[dict] = mapped_column(JsonType)  # GeoJSON Polygon
    crop: Mapped[str] = mapped_column(String(50))
    # Кадастровый номер со слов фермера — сверку с ГосКадастром пока делает аналитик вручную
    cadastral_number: Mapped[str | None] = mapped_column(String(32))
    area_ha: Mapped[float] = mapped_column(Float)
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    # PostGIS-копия контура (EWKT при записи) и рамка (bbox) — для быстрого поиска пересечений
    geom: Mapped[str | None] = mapped_column(GeomType)
    min_lon: Mapped[float | None] = mapped_column(Float)
    min_lat: Mapped[float | None] = mapped_column(Float)
    max_lon: Mapped[float | None] = mapped_column(Float)
    max_lat: Mapped[float | None] = mapped_column(Float)
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
    # Климат сезона (ERA5-Land): дни заморозков после сева и дни жары ≥ 35 °C в июне–июле
    frost_days: Mapped[int | None] = mapped_column(Integer)
    heat_days: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20))  # mock | gee | cdse

    field: Mapped[Field] = relationship(back_populates="seasons")


class Supplier(Base):
    """Дистрибьютор семян/удобрений. Получает оплату сразу при отгрузке, а за это даёт скидку
    маркетплейсу (discount) — из неё и складывается часть дохода платформы."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    discount: Mapped[float] = mapped_column(Float)  # 0.06 = скидка 6 % от розничной цены

    products: Mapped[list[Product]] = relationship(back_populates="supplier")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))  # seeds | fertilizer | protection
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    unit: Mapped[str] = mapped_column(String(20))
    price: Mapped[int] = mapped_column(Integer)  # ₸ за единицу — розничная цена для фермера

    supplier: Mapped[Supplier] = relationship(back_populates="products")


class Application(Base):
    __tablename__ = "applications"

    # UUID вместо 1, 2, 3...: ссылку на заявку нельзя подобрать перебором.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"))
    status: Mapped[str] = mapped_column(String(20), default=ApplicationStatus.PENDING, index=True)
    requested_amount: Mapped[int] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Пересечения с полями других хозяйств на момент подачи (см. services/overlap.py)
    overlaps: Mapped[list] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    farm: Mapped[Farm] = relationship(back_populates="applications")
    field: Mapped[Field] = relationship()
    items: Mapped[list[ApplicationItem]] = relationship(back_populates="application", cascade="all, delete-orphan")
    decision: Mapped[Decision | None] = relationship(back_populates="application", uselist=False)
    deal: Mapped[Deal | None] = relationship(back_populates="application", uselist=False)


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


class DealStatus:
    """Жизненный цикл сделки после одобрения (services/finance.py)."""

    CONTRACTED = "contracted"  # трёхсторонний договор подписан, деньги зарезервированы в кредитной линии
    SUPPLIER_PAID = "supplier_paid"  # банк перечислил поставщику цену со скидкой
    DELIVERED = "delivered"  # товар отгружен фермеру
    SOWING_CONFIRMED = "sowing_confirmed"  # спутник видит всходы на поле
    RESTRUCTURED = "restructured"  # неурожай: остаток долга перенесён на следующий сезон
    REPAID = "repaid"  # фермер рассчитался полностью

    ACTIVE = (CONTRACTED, SUPPLIER_PAID, DELIVERED, SOWING_CONFIRMED, RESTRUCTURED)


class Deal(Base):
    """«Сделка»: деньги по одобренной заявке. Суммы фиксируются в момент одобрения,
    чтобы смена скидки поставщика или ставки банка не меняла уже заключённые договоры."""

    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default=DealStatus.CONTRACTED, index=True)
    score_class: Mapped[str] = mapped_column(String(1))
    goods_amount: Mapped[int] = mapped_column(Integer)  # товар по розничной цене = тело рассрочки
    discount_rate: Mapped[float] = mapped_column(Float)  # средневзвешенная скидка поставщиков
    supplier_payout: Mapped[int] = mapped_column(Integer)  # сколько банк платит поставщикам
    fee_rate: Mapped[float] = mapped_column(Float)  # наценка за рассрочку для фермера
    farmer_total: Mapped[int] = mapped_column(Integer)  # сколько фермер вернёт осенью
    funding_rate: Mapped[float] = mapped_column(Float)  # годовая ставка кредитной линии
    payout_date: Mapped[date] = mapped_column(Date)  # плановая оплата поставщику (перед севом)
    schedule: Mapped[list] = mapped_column(JsonType, default=list)  # текущий график (меняется при реструктуризации)
    paid_amount: Mapped[int] = mapped_column(Integer, default=0)
    events: Mapped[list] = mapped_column(JsonType, default=list)  # журнал: [{at, action, amount, note}]
    monitoring: Mapped[dict | None] = mapped_column(JsonType)  # последний спутниковый мониторинг сезона
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    application: Mapped[Application] = relationship(back_populates="deal")
