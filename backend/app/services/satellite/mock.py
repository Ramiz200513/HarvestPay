"""Демо-провайдер: правдоподобные, но синтетические данные.

Зачем он нужен: доступ к Google Earth Engine выдают не мгновенно, а разрабатывать и показывать
продукт надо уже сейчас. Данные детерминированы — генератор случайных чисел инициализируется
координатами центра поля, поэтому одно и то же поле всегда получает одну и ту же «историю».
Разные поля получают разные истории: хорошие, средние и проблемные — удобно для демонстрации.
"""

from __future__ import annotations

import hashlib
import random

from .base import SeasonData


def _seed_from_geometry(geometry: dict) -> int:
    ring = geometry["coordinates"][0][:-1]
    lon = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    key = f"{lat:.3f}:{lon:.3f}".encode()  # округление ~100 м: чуть сдвинутый контур = то же поле
    return int(hashlib.sha256(key).hexdigest()[:16], 16)


class MockSatelliteProvider:
    name = "mock"

    def fetch_seasons(self, geometry: dict, years: list[int]) -> list[SeasonData]:
        rng = random.Random(_seed_from_geometry(geometry))

        base = rng.uniform(0.38, 0.82)  # «качество» поля
        trend = rng.uniform(-0.025, 0.02)  # улучшается или деградирует год к году
        noise = rng.uniform(0.02, 0.12)  # насколько урожайность скачет
        drought_year = rng.choice(years + [None, None])  # иногда бывает засушливый год
        moisture_base = rng.uniform(0.3, 0.65)

        seasons: list[SeasonData] = []
        for i, year in enumerate(years):
            peak = base + trend * i + rng.gauss(0, noise)
            moisture = moisture_base + rng.gauss(0, 0.06)
            if year == drought_year:
                peak -= rng.uniform(0.12, 0.25)
                moisture -= 0.2
            peak = min(max(peak, 0.08), 0.92)
            moisture = min(max(moisture, 0.05), 0.95)
            seasons.append(
                SeasonData(
                    year=year,
                    ndvi_peak=round(peak, 3),
                    ndvi_mean=round(peak * rng.uniform(0.62, 0.74), 3),
                    soil_moisture=round(moisture, 3),
                    scenes=rng.randint(9, 26),
                )
            )
        return seasons
