"""Снимки поля для просмотра на сайте: список безоблачных дат за сезон и картинка за выбранный день.

Снимки умеет отдавать только провайдер Copernicus Data Space (cdse). Ответы кэшируются в памяти процесса:
повторный просмотр той же даты не тратит квоту CDSE и открывается мгновенно.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache

from .providers import get_imagery_provider
from .satellite.cdse import image_bbox

__all__ = ["ImageryUnavailable", "field_image", "image_bbox", "season_scenes"]


class ImageryUnavailable(Exception):
    """Снимки недоступны в текущей конфигурации (демо-режим или GEE)."""


def _provider():
    provider = get_imagery_provider()
    if provider is None:
        raise ImageryUnavailable(
            "Просмотр снимков работает с Copernicus Data Space: задайте HP_SATELLITE_PROVIDER=cdse и ключи "
            "(см. README). В демо-режиме снимков нет — данные полей синтетические."
        )
    return provider


@lru_cache(maxsize=512)
def _scenes(geometry_json: str, year: int) -> tuple[dict, ...]:
    return tuple(_provider().fetch_scene_list(json.loads(geometry_json), date(year, 4, 1), date(year, 9, 30)))


@lru_cache(maxsize=256)
def _image(geometry_json: str, day: date, mode: str) -> bytes:
    return _provider().fetch_image(json.loads(geometry_json), day, mode)


def _key(geometry: dict) -> str:
    return json.dumps(geometry, sort_keys=True)


def season_scenes(geometry: dict, year: int) -> list[dict]:
    """Безоблачные снимки сезона (апрель–сентябрь): [{"date", "ndvi", "clear"}, ...]."""
    return list(_scenes(_key(geometry), year))


def field_image(geometry: dict, day: date, mode: str) -> bytes:
    return _image(_key(geometry), day, mode)
