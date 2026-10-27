"""Тесты внешних источников без интернета: Open-Meteo (климат) и Copernicus Data Space (NDVI).
HTTP подменяется фейковым клиентом, который отдаёт заранее заготовленные ответы."""

from datetime import date, timedelta

import pytest

from app.services.satellite.base import SeasonData
from app.services.satellite.cdse import CdseSatelliteProvider, parse_scenes, season_from_scenes
from app.services.satellite.mock import MockSatelliteProvider
from app.services.satellite.openmeteo import WithOpenMeteoClimate, field_center, parse_daily

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[71.0, 51.3], [71.01435, 51.3], [71.01435, 51.309], [71.0, 51.309], [71.0, 51.3]]],
}


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class FakeClient:
    """Подмена httpx.Client: get/post возвращают ответы по очереди и запоминают запросы."""

    def __init__(self, get=None, post=None, fail=False):
        self.get_bodies, self.post_bodies, self.fail = list(get or []), list(post or []), fail
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        if self.fail:
            raise ConnectionError("нет интернета")
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(self.get_bodies.pop(0))

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(self.post_bodies.pop(0))


def open_meteo_payload(year, tmin=5.0, tmax=25.0, soil=0.3, frost_on=(), heat_on=()):
    days = [date(year, 4, 1) + timedelta(days=i) for i in range((date(year, 9, 30) - date(year, 4, 1)).days + 1)]
    return {
        "daily": {
            "time": [d.isoformat() for d in days],
            "temperature_2m_min": [-5.0 if d in frost_on else tmin for d in days],
            "temperature_2m_max": [38.0 if d in heat_on else tmax for d in days],
            "soil_moisture_0_to_7cm_mean": [soil for _ in days],
        }
    }


# --- Open-Meteo ---------------------------------------------------------------------------------


def test_parse_daily_counts_frost_and_heat_only_in_their_windows():
    frost = {date(2024, 5, 25), date(2024, 6, 2), date(2024, 8, 1)}  # 1 августа — уже не «по всходам»
    heat = {date(2024, 6, 10), date(2024, 7, 20), date(2024, 9, 1)}  # сентябрь — уже не налив
    climate = parse_daily(open_meteo_payload(2024, frost_on=frost, heat_on=heat), [2024])[2024]
    assert climate.frost_days == 2
    assert climate.heat_days == 2
    assert climate.soil_moisture == pytest.approx(0.8)  # 0,30 м³/м³ между 0,10 (сухо) и 0,35 (влажно)


def test_field_center():
    lat, lon = field_center(SQUARE)
    assert lat == pytest.approx(51.3045)
    assert lon == pytest.approx(71.007175)


def test_openmeteo_replaces_synthetic_climate_of_mock():
    payload = open_meteo_payload(2024, soil=0.1, frost_on={date(2024, 6, 1)})
    client = FakeClient(get=[payload])
    provider = WithOpenMeteoClimate(MockSatelliteProvider(), client_factory=lambda: client)
    season = provider.fetch_seasons(SQUARE, [2024])[0]
    assert provider.name == "mock"  # NDVI по-прежнему демо — так и показываем на сайте
    assert (season.frost_days, season.heat_days, season.soil_moisture) == (1, 0, 0.0)
    assert season.ndvi_peak == MockSatelliteProvider().fetch_seasons(SQUARE, [2024])[0].ndvi_peak


class RealProviderStub:
    """Как GEE: NDVI и часть климата есть, а радар не нашёл снимков — влажность None."""

    name = "gee"

    def __init__(self, soil_moisture=None):
        self.soil_moisture = soil_moisture

    def fetch_seasons(self, geometry, years):
        return [SeasonData(y, 0.7, 0.5, self.soil_moisture, 12, frost_days=4, heat_days=9) for y in years]

    def fetch_timeline(self, geometry, start, end):
        return [{"date": start.isoformat(), "ndvi": 0.3}]


def test_openmeteo_fills_only_missing_values_of_real_provider():
    client = FakeClient(get=[open_meteo_payload(2024)])
    season = WithOpenMeteoClimate(RealProviderStub(), client_factory=lambda: client).fetch_seasons(SQUARE, [2024])[0]
    assert (season.frost_days, season.heat_days) == (4, 9)  # своё у GEE не трогаем
    assert season.soil_moisture == pytest.approx(0.8)  # а пропуск дополнили


def test_openmeteo_not_called_when_real_provider_returned_everything():
    client = FakeClient()
    provider = WithOpenMeteoClimate(RealProviderStub(soil_moisture=0.4), client_factory=lambda: client)
    assert provider.fetch_seasons(SQUARE, [2024])[0].soil_moisture == 0.4
    assert client.calls == []


def test_openmeteo_failure_keeps_primary_data():
    provider = WithOpenMeteoClimate(MockSatelliteProvider(), client_factory=lambda: FakeClient(fail=True))
    assert provider.fetch_seasons(SQUARE, [2024]) == MockSatelliteProvider().fetch_seasons(SQUARE, [2024])


def test_timeline_goes_to_primary():
    provider = WithOpenMeteoClimate(RealProviderStub(), client_factory=lambda: FakeClient(fail=True))
    assert provider.fetch_timeline(SQUARE, date(2026, 4, 1), date(2026, 9, 30)) == [{"date": "2026-04-01", "ndvi": 0.3}]


# --- Copernicus Data Space ----------------------------------------------------------------------


def stats_item(day, mean, sample=1000, nodata=0):
    return {
        "interval": {"from": f"{day}T00:00:00Z", "to": "..."},
        "outputs": {"ndvi": {"bands": {"B0": {"stats": {"mean": mean, "sampleCount": sample, "noDataCount": nodata}}}}},
    }


def test_parse_scenes_drops_cloudy_and_empty_days():
    payload = {
        "data": [
            stats_item("2024-05-10", 0.31),
            stats_item("2024-06-15", 0.62, nodata=300),  # видно 70 % поля — берём
            stats_item("2024-06-20", 0.20, nodata=700),  # видно 30 % — облака, не берём
            stats_item("2024-07-01", "NaN", nodata=1000),  # поле целиком под облаком
            {"interval": {"from": "2024-07-05T00:00:00Z"}, "error": {"type": "EXECUTION_ERROR"}},
        ]
    }
    assert parse_scenes(payload) == [{"date": "2024-05-10", "ndvi": 0.31}, {"date": "2024-06-15", "ndvi": 0.62}]


def test_season_from_scenes():
    scenes = [
        {"date": f"2024-0{m}-01", "ndvi": v} for m, v in zip(range(4, 10), [0.2, 0.4, 0.7, 0.8, 0.5, 0.3], strict=True)
    ]
    s = season_from_scenes(2024, scenes)
    assert s.scenes == 6
    assert s.ndvi_mean == pytest.approx(0.483, abs=1e-3)
    assert 0.7 < s.ndvi_peak <= 0.8
    assert season_from_scenes(2024, []).ndvi_peak is None


def test_cdse_provider_gets_token_once_and_queries_each_season():
    token = {"access_token": "t-123", "expires_in": 600}
    season_body = {"data": [stats_item("2023-06-01", 0.6), stats_item("2023-07-01", 0.7)]}
    client = FakeClient(post=[token, season_body, season_body])
    provider = CdseSatelliteProvider("id", "secret", client_factory=lambda: client)

    seasons = provider.fetch_seasons(SQUARE, [2023, 2024])

    assert [s.year for s in seasons] == [2023, 2024]
    assert all(s.scenes == 2 and s.soil_moisture is None for s in seasons)
    token_calls = [c for c in client.calls if "token" in c[1]]
    stat_calls = [c for c in client.calls if "statistics" in c[1]]
    assert len(token_calls) == 1 and len(stat_calls) == 2
    assert stat_calls[0][2]["headers"] == {"Authorization": "Bearer t-123"}
    body = stat_calls[0][2]["json"]
    assert body["input"]["bounds"]["geometry"] == SQUARE
    assert body["aggregation"]["timeRange"] == {"from": "2023-04-01T00:00:00Z", "to": "2023-10-01T00:00:00Z"}
