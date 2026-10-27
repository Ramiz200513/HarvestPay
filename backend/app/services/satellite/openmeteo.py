"""Климат и влажность почвы из Open-Meteo — бесплатно и без ключа.

Open-Meteo отдаёт реанализ ERA5 / ERA5-Land (тот же, что в Google Earth Engine) по координатам точки
через обычный HTTP-запрос: https://open-meteo.com/en/docs/historical-weather-api
Для учебного и некоммерческого использования ключ не нужен; для коммерческого у них есть платный тариф.

Что берём для каждого сезона (по центру поля, сетка ~9–11 км — это риск района, а не конкретного поля):
  frost_days    — дней с минимумом ≤ −2 °C с 20 мая по 30 июня (заморозки по всходам);
  heat_days     — дней с максимумом ≥ 35 °C в июне–июле (жара при наливе зерна);
  soil_moisture — средняя влажность верхних 7 см почвы с 15 апреля по 30 июня, переведённая в индекс 0..1:
                  0,10 м³/м³ (почти сухо) → 0, 0,35 м³/м³ (полная влагоёмкость суглинка) → 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

log = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FROST_C, HEAT_C = -2.0, 35.0
DRY_SM, WET_SM = 0.10, 0.35


@dataclass
class SeasonClimate:
    frost_days: int | None
    heat_days: int | None
    soil_moisture: float | None  # индекс 0..1, как у радара Sentinel-1 в GEE-провайдере


def moisture_index(sm: float | None) -> float | None:
    if sm is None:
        return None
    return round(min(max((sm - DRY_SM) / (WET_SM - DRY_SM), 0.0), 1.0), 3)


def parse_daily(payload: dict, years: list[int]) -> dict[int, SeasonClimate]:
    """Раскладывает суточный ответ Open-Meteo по сезонам."""
    daily = payload.get("daily") or {}
    days = [date.fromisoformat(d) for d in daily.get("time", [])]
    tmin = daily.get("temperature_2m_min", [])
    tmax = daily.get("temperature_2m_max", [])
    soil = daily.get("soil_moisture_0_to_7cm_mean", [])

    result = {}
    for year in years:
        frost = heat = 0
        frost_seen = heat_seen = False
        sm_values = []
        for i, d in enumerate(days):
            if d.year != year:
                continue
            if date(year, 5, 20) <= d <= date(year, 6, 30) and i < len(tmin) and tmin[i] is not None:
                frost_seen = True
                frost += tmin[i] <= FROST_C
            if date(year, 6, 1) <= d <= date(year, 7, 31) and i < len(tmax) and tmax[i] is not None:
                heat_seen = True
                heat += tmax[i] >= HEAT_C
            if date(year, 4, 15) <= d <= date(year, 6, 30) and i < len(soil) and soil[i] is not None:
                sm_values.append(soil[i])
        result[year] = SeasonClimate(
            frost_days=frost if frost_seen else None,
            heat_days=heat if heat_seen else None,
            soil_moisture=moisture_index(sum(sm_values) / len(sm_values)) if sm_values else None,
        )
    return result


def fetch_climate(lat: float, lon: float, years: list[int], client, timeout: float = 30.0) -> dict[int, SeasonClimate]:
    """Один запрос на все сезоны сразу. client — httpx.Client (в тестах подменяется)."""
    resp = client.get(
        ARCHIVE_URL,
        params={
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "start_date": f"{min(years)}-04-01",
            "end_date": f"{max(years)}-09-30",
            "daily": "temperature_2m_min,temperature_2m_max,soil_moisture_0_to_7cm_mean",
            "timezone": "UTC",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_daily(resp.json(), years)


def field_center(geometry: dict) -> tuple[float, float]:
    """Центр поля (lat, lon) — среднее вершин контура; для сетки 9–11 км точнее не нужно."""
    ring = geometry["coordinates"][0][:-1]
    return sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)


class WithOpenMeteoClimate:
    """Обёртка над спутниковым провайдером: климат и влажность почвы берём из Open-Meteo.

    * Демо-провайдер (mock) — его климат синтетический, поэтому заменяем его настоящим.
    * Настоящий провайдер (gee, cdse) — дополняем только то, чего он не вернул (None):
      например, у GEE не нашлось снимков радара, а CDSE-провайдер климат не считает вовсе.
    Если Open-Meteo недоступен, заявка не падает: остаются данные основного провайдера.
    NDVI обёртка не трогает — его даёт только спутник.
    """

    def __init__(self, primary, client_factory=None, timeout: float = 60.0) -> None:  # первый запрос бывает до 40 с
        self.primary = primary
        self.name = primary.name  # источник NDVI — по нему видно, демо это или настоящий спутник
        self.override = primary.name == "mock"
        self.timeout = timeout
        self._client_factory = client_factory

    def _client(self):
        if self._client_factory is not None:
            return self._client_factory()
        import httpx

        return httpx.Client()

    def fetch_seasons(self, geometry: dict, years: list[int]):
        seasons = self.primary.fetch_seasons(geometry, years)
        if not self.override and all(
            s.frost_days is not None and s.heat_days is not None and s.soil_moisture is not None for s in seasons
        ):
            return seasons  # основной провайдер вернул всё сам — лишний запрос не нужен
        try:
            with self._client() as client:
                climate = fetch_climate(*field_center(geometry), years, client, timeout=self.timeout)
        except Exception:  # noqa: BLE001 — без климата скоринг всё равно работает, штраф просто не начисляется
            log.warning("Open-Meteo недоступен — климат остаётся от провайдера %s", self.primary.name, exc_info=True)
            return seasons
        for s in seasons:
            c = climate.get(s.year)
            if c is None:
                continue
            for attr in ("frost_days", "heat_days", "soil_moisture"):
                value = getattr(c, attr)
                if value is not None and (self.override or getattr(s, attr) is None):
                    setattr(s, attr, value)
        return seasons

    def fetch_timeline(self, geometry: dict, start: date, end: date) -> list[dict]:
        return self.primary.fetch_timeline(geometry, start, end)
