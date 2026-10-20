"""Pydantic-схемы: формат JSON, который API принимает и отдаёт.
Модели БД (models.py) и схемы API разделены специально: в БД могут быть служебные поля,
которые наружу отдавать не нужно, а API может собирать данные из нескольких таблиц."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BinRequest(BaseModel):
    bin: str = Field(min_length=12, max_length=14, examples=["150343000016"])


class FarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bin: str
    name: str | None
    legal_form: str | None
    registered_at: dt.date | None
    status: str
    reasons: list[str]
    source: str | None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    supplier: str
    unit: str
    price: int


class FieldIn(BaseModel):
    geometry: dict  # GeoJSON Polygon — подробно проверяется в services/geo.py
    crop: str = Field(min_length=2, max_length=50)


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
    area_ha: float
    centroid_lat: float
    centroid_lon: float


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


class AnalystDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    approved_amount: int | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=2000)
