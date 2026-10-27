"""Общий интерфейс спутниковых провайдеров."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class SeasonData:
    """Агрегаты по полю за один вегетационный сезон (апрель–сентябрь)."""

    year: int
    ndvi_peak: float | None  # 90-й перцентиль NDVI за сезон — «насколько зелёным поле было на пике»
    ndvi_mean: float | None  # средний NDVI за сезон
    soil_moisture: float | None  # индекс влажности 0..1 (прокси по радару Sentinel-1)
    scenes: int  # сколько безоблачных снимков вошло в расчёт
    # Климат сезона по реанализу ERA5-Land (сетка ~9 км — это риск района, а не конкретного поля):
    frost_days: int | None = None  # дней с минимумом ≤ −2 °C с 20 мая по 30 июня — заморозки по всходам
    heat_days: int | None = None  # дней с максимумом ≥ 35 °C в июне–июле — «запал» зерна при наливе


class SatelliteProvider(Protocol):
    name: str

    def fetch_seasons(self, geometry: dict, years: list[int]) -> list[SeasonData]: ...

    def fetch_timeline(self, geometry: dict, start: date, end: date) -> list[dict]:
        """NDVI по безоблачным снимкам за период: [{"date": "YYYY-MM-DD", "ndvi": 0.42}, ...]."""
        ...


def last_complete_seasons(count: int, today: date | None = None) -> list[int]:
    """Последние `count` завершённых сезонов. Сезон года Y считаем завершённым с 1 октября Y."""
    today = today or date.today()
    last = today.year if today.month >= 10 else today.year - 1
    return list(range(last - count + 1, last + 1))
