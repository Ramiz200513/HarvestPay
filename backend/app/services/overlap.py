"""Антифрод: не заявлял ли этот участок кто-то другой.

Типичная схема мошенничества в агрокредитовании — обвести на карте чужое хорошее поле:
у него отличная история NDVI, и скоринг даст класс A. Поэтому при подаче заявки ищем
поля ДРУГИХ хозяйств, которые пересекаются с новым контуром. Если пересечение заметное,
заявка не одобряется автоматически, а уходит аналитику — проверить документы на землю.

Два способа поиска, результат одинаковый:
  * PostgreSQL + PostGIS — один SQL-запрос. ST_Intersects использует GIST-индекс, поэтому даже
    при сотнях тысяч полей база проверяет только тех, чья рамка задевает наш контур.
    ST_Area(...::geography) считает площадь пересечения в квадратных метрах на сфере.
  * SQLite (разработка без PostGIS) — сначала отбираем кандидатов по рамке (bbox) обычным
    WHERE, потом точное пересечение считает библиотека shapely.

Свои поля хозяйства не считаются: фермер каждый год подаёт заявку на те же поля.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Farm, Field
from .geo import FieldGeometry, polygon_area_ha

# Пересечение меньше 10% меньшего из двух полей игнорируем: соседи рисуют общую границу
# кликами по снимку, и контуры неизбежно немного залезают друг на друга.
MIN_SHARE = 0.10


@dataclass
class Overlap:
    field_id: int
    farm_id: int
    farm_name: str | None
    farm_bin: str
    other_area_ha: float
    overlap_ha: float
    share: float  # доля от меньшего из двух полей, 0..1
    geometry: dict  # контур чужого поля — аналитик увидит его на карте

    def to_dict(self) -> dict:
        return asdict(self)


def _postgis_candidates(db: Session, geom: FieldGeometry, exclude_farm_id: int) -> list[tuple[int, float]]:
    rows = db.execute(
        text(
            """
            SELECT f.id,
                   ST_Area(ST_Intersection(f.geom, g.geom)::geography) / 10000 AS overlap_ha
            FROM fields AS f,
                 (SELECT ST_GeomFromEWKT(:ewkt) AS geom) AS g
            WHERE f.farm_id <> :farm_id
              AND ST_Intersects(f.geom, g.geom)
            """
        ),
        {"ewkt": geom.ewkt, "farm_id": exclude_farm_id},
    )
    return [(row.id, float(row.overlap_ha)) for row in rows]


def _python_candidates(db: Session, geom: FieldGeometry, exclude_farm_id: int) -> list[tuple[int, float]]:
    from shapely.geometry import shape

    min_lon, min_lat, max_lon, max_lat = geom.bbox
    # Две рамки пересекаются, если ни одна не лежит целиком левее/правее/выше/ниже другой
    candidates = db.scalars(
        select(Field).where(
            Field.farm_id != exclude_farm_id,
            Field.min_lon <= max_lon,
            Field.max_lon >= min_lon,
            Field.min_lat <= max_lat,
            Field.max_lat >= min_lat,
        )
    )
    new_shape = shape(geom.geojson)
    result = []
    for field in candidates:
        intersection = new_shape.intersection(shape(field.geometry))
        if intersection.is_empty:
            continue
        # Пересечение может распасться на несколько кусков (MultiPolygon) — складываем площади
        parts = getattr(intersection, "geoms", [intersection])
        area = sum(
            polygon_area_ha([list(p.exterior.coords), *[list(r.coords) for r in p.interiors]])
            for p in parts
            if p.geom_type == "Polygon"
        )
        result.append((field.id, area))
    return result


def find_overlaps(db: Session, geom: FieldGeometry, exclude_farm_id: int | None) -> list[Overlap]:
    exclude = exclude_farm_id if exclude_farm_id is not None else -1
    if db.get_bind().dialect.name == "postgresql":
        raw = _postgis_candidates(db, geom, exclude)
    else:
        raw = _python_candidates(db, geom, exclude)

    overlaps = []
    for field_id, overlap_ha in raw:
        field = db.get(Field, field_id)
        if field is None or overlap_ha <= 0:
            continue
        smaller = min(geom.area_ha, field.area_ha)
        # PostGIS считает площадь на эллипсоиде, а наша формула — на сфере: расхождение ~0.3%.
        # Чтобы не показывать «пересечение больше самого поля», обрезаем по меньшему полю.
        overlap_ha = min(overlap_ha, smaller)
        share = overlap_ha / smaller
        if share < MIN_SHARE:
            continue
        farm: Farm = field.farm
        overlaps.append(
            Overlap(
                field_id=field.id,
                farm_id=farm.id,
                farm_name=farm.name,
                farm_bin=farm.bin,
                other_area_ha=round(field.area_ha, 2),
                overlap_ha=round(overlap_ha, 2),
                share=round(min(share, 1.0), 3),
                geometry=field.geometry,
            )
        )
    # Одно хозяйство могло подавать заявки на этот участок несколько раз (каждая заявка хранит
    # свой контур) — оставляем по одному, самому большому пересечению на хозяйство.
    best: dict[int, Overlap] = {}
    for o in overlaps:
        if o.farm_id not in best or o.overlap_ha > best[o.farm_id].overlap_ha:
            best[o.farm_id] = o
    return sorted(best.values(), key=lambda o: o.overlap_ha, reverse=True)
