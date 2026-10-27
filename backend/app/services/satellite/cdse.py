"""Реальный провайдер без Google: Copernicus Data Space Ecosystem (CDSE), Statistical API.

CDSE — официальный портал снимков Sentinel от Еврокомиссии и ESA. Бесплатный аккаунт:
https://dataspace.copernicus.eu → «Register». Месячной бесплатной квоты с запасом хватает на учебный проект.
Ключ получают так: https://shapps.dataspace.copernicus.eu/dashboard → «User settings» → «OAuth clients» → «Create».
Подробно — README, раздел «Copernicus Data Space (бесплатная замена GEE)».

Что считаем — то же, что в GEE-провайдере, но без тяжёлых библиотек, обычными HTTP-запросами:
  * Sentinel-2 L2A, маска облаков по слою SCL: только «растительность» (4) и «открытая почва» (5).
  * NDVI = (B08 − B04) / (B08 + B04) — среднее по полю на каждый день, когда был снимок.
  * Снимок берём, если поле видно без облаков хотя бы на 50 %: считаем относительно самого чистого
    снимка того же сезона (у него видно всё поле).
  * ndvi_peak — 90-й перцентиль средних NDVI по снимкам сезона, ndvi_mean — среднее по снимкам.
    В GEE перцентиль считается по каждому пикселю, здесь — по среднему поля: значения близки, но не равны.
  * Влажность и климат CDSE-провайдер не считает — их добавляет Open-Meteo (openmeteo.WithOpenMeteoClimate).

Один запрос на сезон: 7 сезонов — 7 запросов по 2–10 секунд, поэтому расчёт идёт в фоне, как и с GEE.
"""

from __future__ import annotations

import math
import statistics
import time
from collections.abc import Callable
from datetime import date, timedelta

from .base import SeasonData

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
MIN_CLEAR_RATIO = 0.5
RES_DEG = 0.0001  # ~10 м: разрешение каналов B04/B08, в градусах — геометрию передаём в WGS84

EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [{ id: "ndvi", bands: 1, sampleType: "FLOAT32" }, { id: "dataMask", bands: 1 }],
  };
}
function evaluatePixel(s) {
  const clear = s.SCL == 4 || s.SCL == 5;
  const sum = s.B08 + s.B04;
  const ok = s.dataMask == 1 && clear && sum > 0;
  return { ndvi: [ok ? (s.B08 - s.B04) / sum : 0], dataMask: [ok ? 1 : 0] };
}
"""


def stats_request(geometry: dict, start: date, end: date) -> dict:
    """Тело запроса Statistical API: среднее NDVI по полю за каждые сутки периода [start, end]."""
    return {
        "input": {
            "bounds": {
                "geometry": geometry,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"maxCloudCoverage": 60}}],
        },
        "aggregation": {
            "timeRange": {
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z",
            },
            "aggregationInterval": {"of": "P1D"},
            "evalscript": EVALSCRIPT,
            "resx": RES_DEG,
            "resy": RES_DEG,
        },
    }


def parse_scenes(payload: dict) -> list[dict]:
    """Ответ Statistical API → безоблачные снимки [{"date": "YYYY-MM-DD", "ndvi": 0.42}, ...]."""
    raw = []
    for item in payload.get("data", []):
        if "error" in item:
            continue  # отдельный день не посчитался — остальные дни это не портит
        stats = item.get("outputs", {}).get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})
        valid = (stats.get("sampleCount") or 0) - (stats.get("noDataCount") or 0)
        try:
            mean = float(stats.get("mean"))
        except (TypeError, ValueError):
            continue
        if valid <= 0 or math.isnan(mean):
            continue
        raw.append((item["interval"]["from"][:10], mean, valid))

    best = max((v for _, _, v in raw), default=0)
    by_day = {d: round(m, 3) for d, m, v in raw if v >= MIN_CLEAR_RATIO * best}
    return [{"date": d, "ndvi": v} for d, v in sorted(by_day.items())]


def season_from_scenes(year: int, scenes: list[dict]) -> SeasonData:
    values = [s["ndvi"] for s in scenes]
    if not values:
        return SeasonData(year=year, ndvi_peak=None, ndvi_mean=None, soil_moisture=None, scenes=0)
    peak = statistics.quantiles(values, n=10, method="inclusive")[8] if len(values) > 1 else values[0]
    return SeasonData(
        year=year,
        ndvi_peak=round(peak, 3),
        ndvi_mean=round(statistics.fmean(values), 3),
        soil_moisture=None,
        scenes=len(values),
    )


class CdseSatelliteProvider:
    name = "cdse"

    def __init__(
        self, client_id: str, client_secret: str, client_factory: Callable | None = None, timeout: float = 60.0
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._client_factory = client_factory
        self._token: str | None = None
        self._token_expires = 0.0

    def _client(self):
        if self._client_factory is not None:
            return self._client_factory()
        import httpx

        return httpx.Client()

    def _auth_header(self, client) -> dict:
        if self._token is None or time.monotonic() > self._token_expires:
            resp = client.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            body = resp.json()
            self._token = body["access_token"]
            self._token_expires = time.monotonic() + int(body.get("expires_in", 600)) - 60  # с запасом в минуту
        return {"Authorization": f"Bearer {self._token}"}

    def _scenes(self, client, geometry: dict, start: date, end: date) -> list[dict]:
        resp = client.post(
            STATS_URL, json=stats_request(geometry, start, end), headers=self._auth_header(client), timeout=self.timeout
        )
        resp.raise_for_status()
        return parse_scenes(resp.json())

    def fetch_seasons(self, geometry: dict, years: list[int]) -> list[SeasonData]:
        with self._client() as client:
            return [season_from_scenes(y, self._scenes(client, geometry, date(y, 4, 1), date(y, 9, 30))) for y in years]

    def fetch_timeline(self, geometry: dict, start: date, end: date) -> list[dict]:
        with self._client() as client:
            return self._scenes(client, geometry, start, end)
