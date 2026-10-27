"""Демо-провайдер: правдоподобные, но синтетические данные.

Зачем он нужен: доступ к Google Earth Engine выдают не мгновенно, а разрабатывать и показывать
продукт надо уже сейчас. Данные детерминированы — генератор случайных чисел инициализируется
координатами центра поля, поэтому одно и то же поле всегда получает одну и ту же «историю».
Разные поля получают разные истории: хорошие, средние и проблемные — удобно для демонстрации.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta

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

        # Климат — отдельным генератором, чтобы не сдвинуть NDVI полей, посчитанных раньше.
        # Север (Костанай, СКО) — чаще поздние заморозки, юг и запад — чаще жара.
        ring = geometry["coordinates"][0][:-1]
        lat = sum(p[1] for p in ring) / len(ring)
        climate = random.Random(_seed_from_geometry(geometry) ^ 0xC11A7E)
        frost_rate = (1.4 if lat >= 52.5 else 0.7 if lat >= 50.5 else 0.25) * climate.uniform(0.5, 1.6)
        heat_rate = (2.5 if lat >= 51 else 6.0 if lat >= 48 else 11.0) * climate.uniform(0.6, 1.5)

        def events(rate: float) -> int:
            # число событий за сезон «примерно по Пуассону» со средним rate
            return sum(climate.random() < rate / 30 for _ in range(30))

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
                    frost_days=events(frost_rate),
                    heat_days=events(heat_rate * (1.8 if year == drought_year else 1.0)),
                )
            )
        return seasons

    def fetch_timeline(self, geometry: dict, start: date, end: date) -> list[dict]:
        """Синтетический сезон: голая почва → всходы → пик в июле → уборка. Пик берётся из той же
        «истории», что и fetch_seasons, поэтому прошлый сезон на графике совпадает с таблицей сезонов.
        У части полей сезон проблемный (засуха) или поле вовсе не засеяно — чтобы было что показать."""
        year = start.year
        history = self.fetch_seasons(geometry, list(range(year - 6, year + 1)))
        peak = history[-1].ndvi_peak or 0.6
        rng = random.Random(_seed_from_geometry(geometry) ^ (year * 7919))
        outcome = rng.random()
        if outcome < 0.07:
            kind = "not_sown"
        elif outcome < 0.2:
            kind = "stress"
            peak *= rng.uniform(0.5, 0.68)
        else:
            kind = "normal"
        sowing = date(year, 5, 12) + timedelta(days=rng.randint(0, 22))
        growth_mid = sowing + timedelta(days=38)
        decline, harvest = date(year, 7, 28), date(year, 9, 12)

        points = []
        day = start
        while day <= end:
            if rng.random() > 0.35:  # примерно треть снимков закрыта облаками
                if kind == "not_sown":
                    ndvi = rng.uniform(0.12, 0.24)  # сорняки и стерня
                elif day <= decline:
                    t = (day - growth_mid).days
                    ndvi = 0.15 + (peak - 0.15) / (1 + math.exp(-t / 7))
                elif day <= harvest:
                    ndvi = peak - (peak - 0.22) * (day - decline).days / (harvest - decline).days
                else:
                    ndvi = 0.2
                ndvi += rng.gauss(0, 0.02)
                points.append({"date": day.isoformat(), "ndvi": round(min(max(ndvi, 0.05), 0.95), 3)})
            day += timedelta(days=5)
        return points
