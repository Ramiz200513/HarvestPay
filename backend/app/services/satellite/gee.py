"""Реальный провайдер: Google Earth Engine.

Что считаем для каждого сезона (1 апреля – 30 сентября):
  * Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED), разрешение 10 м.
    Маска облаков по слою SCL: оставляем только пиксели «растительность» (4) и «открытая почва» (5).
    Без маски облако даёт ложный провал NDVI — и честное хозяйство получило бы плохой балл.
  * NDVI = (B8 − B4) / (B8 + B4): ближний ИК минус красный — чем больше, тем гуще живая растительность.
  * ndvi_peak — 90-й перцентиль NDVI по каждому пикселю за сезон, усреднённый по полю.
  * ndvi_mean — средний NDVI за сезон.
  * Влажность — прокси по радару Sentinel-1 (канал VV, апрель–июнь). Радар видит сквозь облака;
    обратное рассеяние растёт с влажностью почвы. Переводим dB в индекс 0..1: −20 dB → 0, −5 dB → 1.
  * Климат — реанализ ERA5-Land (ECMWF/ERA5_LAND/DAILY_AGGR), ячейка ~9 км, берём ту, где центр поля:
    frost_days — дней с минимумом ≤ −2 °C с 20 мая по 30 июня (заморозки по всходам),
    heat_days  — дней с максимумом ≥ 35 °C в июне–июле (жара при цветении и наливе зерна).

Все 7 сезонов собираются в одну FeatureCollection и запрашиваются ОДНИМ getInfo() — это
в разы быстрее, чем 14 отдельных запросов. Даже так расчёт занимает 10–60 секунд,
поэтому он выполняется в фоновой задаче (Celery), а не внутри HTTP-запроса.

Настройка доступа: см. README, раздел «Подключение Google Earth Engine».
"""

from __future__ import annotations

from datetime import date, timedelta

from .base import SeasonData

MISSING = -999  # маркер «нет данных» (Earth Engine не умеет вернуть None из Dictionary.get)


def vv_db_to_index(vv_db: float | None) -> float | None:
    if vv_db is None or vv_db == MISSING:
        return None
    return round(min(max((vv_db + 20.0) / 15.0, 0.0), 1.0), 3)


class GeeSatelliteProvider:
    name = "gee"

    def __init__(self, project: str, service_account: str | None = None, key_file: str | None = None) -> None:
        import ee  # тяжёлая библиотека — импортируем только когда реально выбран GEE

        if service_account and key_file:
            credentials = ee.ServiceAccountCredentials(service_account, key_file)
            ee.Initialize(credentials=credentials, project=project)
        else:
            # Локальная разработка: заранее выполнить `earthengine authenticate`
            ee.Initialize(project=project)
        self.ee = ee

    def _clear_ndvi(self, region, start, end):
        """Снимки Sentinel-2 с NDVI, где поле видно без облаков хотя бы на 50 %."""
        ee = self.ee

        def mask_and_ndvi(img):
            scl = img.select("SCL")
            clear = scl.eq(4).Or(scl.eq(5))
            ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
            return ee.Image(ndvi.updateMask(clear).copyProperties(img, ["system:time_start"]))

        # сколько 20-метровых пикселей в поле вообще — для доли «видимой» площади на снимке
        total_px = ee.Number(
            ee.Image(1)
            .reduceRegion(reducer=ee.Reducer.count(), geometry=region, scale=20, maxPixels=1e9)
            .get("constant")
        )

        def with_clear_ratio(img):
            valid = (
                img.select("NDVI")
                .reduceRegion(reducer=ee.Reducer.count(), geometry=region, scale=20, maxPixels=1e9)
                .get("NDVI")
            )
            return img.set("clear_ratio", ee.Number(valid).divide(total_px.max(1)))

        return (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(region)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
            .map(mask_and_ndvi)
            .map(with_clear_ratio)
            .filter(ee.Filter.gte("clear_ratio", 0.5))  # поле закрыто облаками больше чем наполовину — не берём
        )

    def _mean_over_field(self, region, image, band):
        ee = self.ee
        stats = image.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=10, maxPixels=1e9)
        return ee.Dictionary(stats).get(band, MISSING)

    def fetch_timeline(self, geometry: dict, start: date, end: date) -> list[dict]:
        """NDVI поля по каждому безоблачному снимку за период — для мониторинга сезона."""
        ee = self.ee
        region = ee.Geometry.Polygon(geometry["coordinates"])
        col = self._clear_ndvi(region, start.isoformat(), (end + timedelta(days=1)).isoformat())

        def per_image(img):
            return ee.Feature(
                None, {"date": img.date().format("YYYY-MM-dd"), "ndvi": self._mean_over_field(region, img, "NDVI")}
            )

        info = ee.FeatureCollection(col.map(per_image)).getInfo()
        by_day: dict[str, float] = {}
        for feature in info["features"]:
            p = feature["properties"]
            if p.get("ndvi") not in (None, MISSING):
                by_day[p["date"]] = round(float(p["ndvi"]), 3)  # два снимка за день (соседние тайлы) — один
        return [{"date": d, "ndvi": v} for d, v in sorted(by_day.items())]

    def fetch_seasons(self, geometry: dict, years: list[int]) -> list[SeasonData]:
        ee = self.ee
        region = ee.Geometry.Polygon(geometry["coordinates"])
        center = region.centroid(maxError=1)
        era5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")

        def count_days(start, end, band, test):
            days = era5.filterDate(start, end).select(band).map(lambda img: test(img).rename("days")).sum()
            stats = days.reduceRegion(reducer=ee.Reducer.first(), geometry=center, scale=11132)
            return ee.Dictionary(stats).get("days", MISSING)

        def mean_over_field(image, band):
            return self._mean_over_field(region, image, band)

        def season(year):
            y = ee.Number(year)
            s2 = self._clear_ndvi(region, ee.Date.fromYMD(y, 4, 1), ee.Date.fromYMD(y, 10, 1))
            s1 = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(region)
                .filterDate(ee.Date.fromYMD(y, 4, 15), ee.Date.fromYMD(y, 7, 1))
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                .select("VV")
            )
            return ee.Feature(
                None,
                {
                    "year": y,
                    "scenes": s2.size(),  # только снимки, где поле видно хотя бы на 50%
                    "ndvi_peak": mean_over_field(s2.reduce(ee.Reducer.percentile([90])), "NDVI_p90"),
                    "ndvi_mean": mean_over_field(s2.mean(), "NDVI"),
                    "vv": mean_over_field(s1.mean(), "VV"),
                    "frost_days": count_days(
                        ee.Date.fromYMD(y, 5, 20),
                        ee.Date.fromYMD(y, 7, 1),
                        "temperature_2m_min",
                        lambda t: t.lte(271.15),  # −2 °C в кельвинах
                    ),
                    "heat_days": count_days(
                        ee.Date.fromYMD(y, 6, 1),
                        ee.Date.fromYMD(y, 8, 1),
                        "temperature_2m_max",
                        lambda t: t.gte(308.15),  # 35 °C
                    ),
                },
            )

        info = ee.FeatureCollection(ee.List(years).map(season)).getInfo()

        def clean(value):
            if value is None or value == MISSING:
                return None
            return round(float(value), 3)

        def days(value):
            return None if value is None or value == MISSING else int(round(float(value)))

        result = []
        for feature in info["features"]:
            p = feature["properties"]
            result.append(
                SeasonData(
                    year=int(p["year"]),
                    ndvi_peak=clean(p.get("ndvi_peak")),
                    ndvi_mean=clean(p.get("ndvi_mean")),
                    soil_moisture=vv_db_to_index(p.get("vv")),
                    scenes=int(p.get("scenes") or 0),
                    frost_days=days(p.get("frost_days")),
                    heat_days=days(p.get("heat_days")),
                )
            )
        return sorted(result, key=lambda s: s.year)
