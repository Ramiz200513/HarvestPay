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

Все 7 сезонов собираются в одну FeatureCollection и запрашиваются ОДНИМ getInfo() — это
в разы быстрее, чем 14 отдельных запросов. Даже так расчёт занимает 10–60 секунд,
поэтому он выполняется в фоновой задаче (Celery), а не внутри HTTP-запроса.

Настройка доступа: см. README, раздел «Подключение Google Earth Engine».
"""

from __future__ import annotations

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

    def fetch_seasons(self, geometry: dict, years: list[int]) -> list[SeasonData]:
        ee = self.ee
        region = ee.Geometry.Polygon(geometry["coordinates"])

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

        def mean_over_field(image, band):
            stats = image.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=10, maxPixels=1e9)
            return ee.Dictionary(stats).get(band, MISSING)

        def season(year):
            y = ee.Number(year)
            s2 = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(region)
                .filterDate(ee.Date.fromYMD(y, 4, 1), ee.Date.fromYMD(y, 10, 1))
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
                .map(mask_and_ndvi)
                .map(with_clear_ratio)
                .filter(
                    ee.Filter.gte("clear_ratio", 0.5)
                )  # поле закрыто облаками больше чем наполовину — снимок не берём
            )
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
                },
            )

        info = ee.FeatureCollection(ee.List(years).map(season)).getInfo()

        def clean(value):
            if value is None or value == MISSING:
                return None
            return round(float(value), 3)

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
                )
            )
        return sorted(result, key=lambda s: s.year)
