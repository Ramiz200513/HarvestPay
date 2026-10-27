"""Выбор провайдеров по настройкам. Один раз создаём объект и переиспользуем
(инициализация Earth Engine небыстрая — не нужно делать её на каждую заявку)."""

from functools import lru_cache

from ..config import get_settings
from .compliance import Compliance, MockCompliance
from .registry import MockRegistry, Registry, StatGovRegistry
from .satellite.base import SatelliteProvider
from .satellite.mock import MockSatelliteProvider


@lru_cache
def get_registry() -> Registry:
    s = get_settings()
    if s.registry_provider == "statgov":
        return StatGovRegistry(s.statgov_url)
    return MockRegistry()


@lru_cache
def get_compliance() -> Compliance:
    # Налоги, аресты, суды: в продакшене — API агрегатора госбаз (adata.kz / Kompra) по договору
    return MockCompliance()


@lru_cache
def get_satellite_provider() -> SatelliteProvider:
    s = get_settings()
    if s.satellite_provider == "gee":
        if not s.gee_project:
            raise RuntimeError("Для HP_SATELLITE_PROVIDER=gee нужно задать HP_GEE_PROJECT")
        from .satellite.gee import GeeSatelliteProvider

        return GeeSatelliteProvider(s.gee_project, s.gee_service_account, s.gee_key_file)
    return MockSatelliteProvider()
