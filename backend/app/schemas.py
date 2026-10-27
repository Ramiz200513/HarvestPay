"""Pydantic-схемы: формат JSON, который API принимает и отдаёт.
Модели БД (models.py) и схемы API разделены специально: в БД могут быть служебные поля,
которые наружу отдавать не нужно, а API может собирать данные из нескольких таблиц."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BinRequest(BaseModel):
    bin: str = Field(min_length=12, max_length=14, examples=["150343000016"])


class CheckOut(BaseModel):
    """Строка чек-листа проверки хозяйства: реестр, возраст, налоги, аресты, суды, субсидии."""

    label: str
    status: Literal["ok", "warn", "fail", "info"]
    detail: str


class FarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bin: str
    name: str | None
    legal_form: str | None
    registered_at: dt.date | None
    status: str
    reasons: list[str]
    source: str | None
    checks: list[CheckOut] = []


class ProductOut(BaseModel):
    id: int
    name: str
    category: str
    supplier: str
    unit: str
    price: int


class FieldIn(BaseModel):
    geometry: dict  # GeoJSON Polygon — подробно проверяется в services/geo.py
    crop: str = Field(min_length=2, max_length=50)
    # Кадастровый номер участка, например 01:011:002:345 — необязательный, проверяет аналитик
    cadastral_number: str | None = Field(default=None, max_length=32, pattern=r"^\d[\d:\-\s]{4,31}$")


class ItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100_000)


class ApplicationCreate(BaseModel):
    bin: str
    field: FieldIn
    items: list[ItemIn] = Field(min_length=1)


class ApplicationCreated(BaseModel):
    id: str
    status: str


class SeasonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    ndvi_peak: float | None
    ndvi_mean: float | None
    soil_moisture: float | None
    scenes: int
    frost_days: int | None = None
    heat_days: int | None = None
    source: str | None = None  # mock | cdse | gee — откуда NDVI


class ItemOut(BaseModel):
    product_id: int
    name: str
    unit: str
    quantity: int
    price: int
    total: int


class PaymentOut(BaseModel):
    date: dt.date
    amount: int
    note: str | None = None


class DecisionOut(BaseModel):
    score: float | None
    score_class: str
    components: dict
    reasons: list[str]
    limit_amount: int
    approved_amount: int
    schedule: list[PaymentOut]
    decided_by: str
    analyst_comment: str | None


class FieldOut(BaseModel):
    geometry: dict
    crop: str
    cadastral_number: str | None = None
    area_ha: float
    centroid_lat: float
    centroid_lon: float


class OverlapOut(BaseModel):
    """Пересечение с чужим полем. Фермеру показываем только площадь и долю —
    чьё это поле, видит лишь аналитик (farm_name, farm_bin, geometry = None в публичном ответе)."""

    overlap_ha: float
    share: float
    other_area_ha: float
    farm_name: str | None = None
    farm_bin: str | None = None
    geometry: dict | None = None


class OverlapCheckIn(BaseModel):
    bin: str | None = None
    geometry: dict


class OverlapCheckOut(BaseModel):
    area_ha: float
    overlaps: list[OverlapOut]


class DealEventOut(BaseModel):
    at: dt.date
    action: str
    amount: int | None
    note: str


class FlowStepOut(BaseModel):
    """Шаг движения денег/товара по сделке — для схемы на экране аналитика."""

    when: dt.date
    source: str
    target: str
    amount: int
    kind: Literal["money", "goods"]
    note: str


class PaymentInfoOut(BaseModel):
    """Как фермеру оплатить рассрочку: реквизиты спецсчёта платформы и условия договора."""

    contract_number: str
    recipient: str
    bin: str
    bank: str
    iik: str
    bik: str
    kbe: str
    knp: str
    purpose: str  # назначение платежа — с номером договора, чтобы платёж зачли автоматически
    demo: bool
    fee_rate: float  # наценка за рассрочку, которую фермер видит в договоре
    restructure_fee: float  # доплата за перенос остатка на следующий сезон при неурожае
    insurance_deductible: float  # франшиза страховки урожая
    support_email: str


class DealOut(BaseModel):
    """Сделка по одобренной заявке. Фермер видит свою часть (что и когда платить);
    поля ниже «только аналитику» в ответе фермеру равны None."""

    status: str
    overdue: bool
    score_class: str
    goods_amount: int
    farmer_total: int
    paid_amount: int
    schedule: list[PaymentOut]
    payout_date: dt.date
    events: list[DealEventOut]
    payment: PaymentInfoOut | None = None
    # --- только аналитику ---
    economics: dict | None = None
    discount_rate: float | None = None
    fee_rate: float | None = None
    funding_rate: float | None = None
    flow: list[FlowStepOut] | None = None
    scenario: list[dict] | None = None
    monitoring: dict | None = None


class ApplicationOut(BaseModel):
    id: str
    status: str
    error_message: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    requested_amount: int
    farm: FarmOut
    field: FieldOut
    items: list[ItemOut]
    seasons: list[SeasonOut]
    decision: DecisionOut | None
    overlaps: list[OverlapOut]
    deal: DealOut | None = None


class ApplicationListItem(BaseModel):
    id: str
    status: str
    created_at: dt.datetime
    farm_name: str | None
    bin: str
    area_ha: float
    crop: str
    requested_amount: int
    score: float | None
    score_class: str | None
    has_overlaps: bool
    deal_status: str | None = None


class AnalystDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    approved_amount: int | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=2000)


class DealActionIn(BaseModel):
    action: Literal["pay_supplier", "confirm_delivery", "confirm_sowing", "record_payment", "restructure"]
    amount: int | None = Field(default=None, gt=0)


class CreditLineOut(BaseModel):
    bank: str
    limit: int
    used: int
    available: int
    rate: float


class PortfolioDealOut(BaseModel):
    application_id: str
    farm_name: str | None
    crop: str
    area_ha: float
    score_class: str
    status: str
    overdue: bool
    goods_amount: int
    farmer_total: int
    paid_amount: int
    margin: int
    monitoring_status: str | None


class PortfolioOut(BaseModel):
    credit_line: CreditLineOut
    deals_count: int
    goods_amount: int  # товар отгружен/законтрактован по розничной цене
    supplier_payout: int  # из них заплачено/будет заплачено поставщикам
    farmer_total: int  # ожидаем от фермеров
    paid_amount: int  # уже вернули
    expected_margin: int
    expected_loss: int
    by_status: dict[str, int]
    by_class: dict[str, int]  # сумма товара по классам
    upcoming: list[PaymentOut]  # ожидаемые поступления по месяцам (дата = 1-е число)
    deals: list[PortfolioDealOut]
