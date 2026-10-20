"""Работа с границами поля (GeoJSON Polygon).

Фермер рисует поле на карте — сюда приходит GeoJSON вида
  {"type": "Polygon", "coordinates": [[[lon, lat], [lon, lat], ..., [lon, lat]]]}
Внимание: в GeoJSON порядок координат — сначала долгота, потом широта.

Что делаем:
  1) проверяем, что полигон корректный (замкнут, без самопересечений, внутри Казахстана);
  2) считаем площадь в гектарах на сфере (без внешних библиотек — формула та же, что в turf.js);
  3) считаем центр поля (для карты и для детерминированных демо-данных).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_378_137.0  # экваториальный радиус WGS-84

# Грубая рамка Казахстана: отсекает случайный клик по карте в другой стране.
KZ_BBOX = (46.0, 40.5, 87.5, 55.5)  # (min_lon, min_lat, max_lon, max_lat)

MIN_AREA_HA = 1.0
MAX_AREA_HA = 20_000.0


class GeometryError(ValueError):
    pass


@dataclass
class FieldGeometry:
    geojson: dict
    area_ha: float
    centroid_lat: float
    centroid_lon: float


def ring_area_m2(ring: list[list[float]]) -> float:
    """Площадь кольца на сфере (алгоритм Chamberlain & Duquette, используется в turf/geojson-area)."""
    total = 0.0
    n = len(ring)
    if n < 3:
        return 0.0
    for i in range(n):
        lon1, lat1 = ring[i]
        lon2, lat2 = ring[(i + 1) % n]
        total += math.radians(lon2 - lon1) * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(total * EARTH_RADIUS_M**2 / 2.0)


def _orientation(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """Строгое пересечение двух отрезков (касание концами не считаем)."""
    d1 = _orientation(p3, p4, p1)
    d2 = _orientation(p3, p4, p2)
    d3 = _orientation(p1, p2, p3)
    d4 = _orientation(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def has_self_intersection(ring: list[list[float]]) -> bool:
    """O(n²) проверка: для полей из десятков точек этого достаточно."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    n = len(pts)
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            # соседние рёбра делят вершину — их не сравниваем
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _segments_intersect(*edges[i], *edges[j]):
                return True
    return False


def parse_field_geometry(geojson: dict) -> FieldGeometry:
    if not isinstance(geojson, dict) or geojson.get("type") != "Polygon":
        raise GeometryError("Ожидается GeoJSON с type = 'Polygon'")
    coords = geojson.get("coordinates")
    if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
        raise GeometryError("В полигоне нет координат")

    ring = [[float(p[0]), float(p[1])] for p in coords[0]]
    if len(ring) >= 2 and ring[0] != ring[-1]:
        ring.append(list(ring[0]))  # замыкаем кольцо, если фронтенд этого не сделал
    if len(ring) < 4:
        raise GeometryError("Поле должно иметь минимум 3 точки")

    min_lon, min_lat, max_lon, max_lat = KZ_BBOX
    for lon, lat in ring:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise GeometryError("Координаты вне допустимого диапазона")
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            raise GeometryError("Поле должно находиться на территории Казахстана")

    if has_self_intersection(ring):
        raise GeometryError("Границы поля пересекают сами себя — перерисуйте контур")

    area_ha = ring_area_m2(ring) / 10_000
    if area_ha < MIN_AREA_HA:
        raise GeometryError(f"Площадь поля меньше {MIN_AREA_HA:g} га")
    if area_ha > MAX_AREA_HA:
        raise GeometryError(f"Площадь поля больше {MAX_AREA_HA:,.0f} га — разбейте на несколько полей")

    pts = ring[:-1]
    centroid_lon = sum(p[0] for p in pts) / len(pts)
    centroid_lat = sum(p[1] for p in pts) / len(pts)

    return FieldGeometry(
        geojson={"type": "Polygon", "coordinates": [ring]},
        area_ha=round(area_ha, 2),
        centroid_lat=round(centroid_lat, 6),
        centroid_lon=round(centroid_lon, 6),
    )
