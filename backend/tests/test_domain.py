"""Тесты «чистой» бизнес-логики: БИН, геометрия, скоринг, лимиты, демо-спутник.
Не требуют БД и веб-сервера — запускаются за доли секунды: `pytest` из папки backend."""

from datetime import date

import pytest

from app.services.bin_check import check_bin
from app.services.geo import GeometryError, parse_field_geometry, ring_area_m2
from app.services.limits import build_schedule, credit_limit
from app.services.registry import MockRegistry, verify_farm
from app.services.satellite.base import SeasonData, last_complete_seasons
from app.services.satellite.mock import MockSatelliteProvider
from app.services.scoring import classify, score_field

# Квадрат ~1×1 км под Астаной (≈100 га)
SQUARE = {
    "type": "Polygon",
    "coordinates": [[[71.0, 51.3], [71.01435, 51.3], [71.01435, 51.309], [71.0, 51.309], [71.0, 51.3]]],
}


# --- БИН ---------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["150343000016", "180240000011", "080740000019"])
def test_valid_bins(value):
    assert check_bin(value).valid


def test_bin_wrong_checksum():
    result = check_bin("150343000017")
    assert not result.valid
    assert any("Контрольная" in e for e in result.errors)


def test_bin_rejects_iin_of_person():
    # 5-я цифра 0–3 — это ИИН физлица
    assert not check_bin("900101300017").valid


def test_bin_wrong_length():
    assert not check_bin("12345").valid


def test_farm_parsed_attributes():
    result = check_bin("150343000016")
    assert result.reg_year == 2015 and result.reg_month == 3
    assert result.attribute == "крестьянское (фермерское) хозяйство"


# --- Проверка хозяйства --------------------------------------------------------------------


def test_verify_ok():
    v = verify_farm("150343000016", MockRegistry(), 12, today=date(2026, 10, 1))
    assert v.status == "verified" and v.name.startswith("КХ")


@pytest.mark.parametrize(
    "value,fragment",
    [("080740000019", "ликвидирована"), ("150340000015", "не найдена"), ("260440000016", "меньше 12")],
)
def test_verify_rejections(value, fragment):
    v = verify_farm(value, MockRegistry(), 12, today=date(2026, 10, 1))
    assert v.status == "rejected"
    assert any(fragment in r for r in v.reasons)


# --- Геометрия -----------------------------------------------------------------------------


def test_area_of_square_about_100_ha():
    area_ha = ring_area_m2(SQUARE["coordinates"][0]) / 10_000
    assert 98 < area_ha < 102


def test_parse_closes_ring_and_computes_centroid():
    open_ring = {"type": "Polygon", "coordinates": [SQUARE["coordinates"][0][:-1]]}
    g = parse_field_geometry(open_ring)
    assert g.geojson["coordinates"][0][0] == g.geojson["coordinates"][0][-1]
    assert abs(g.centroid_lat - 51.3045) < 1e-3


def test_self_intersection_rejected():
    bow_tie = {"type": "Polygon", "coordinates": [[[71.0, 51.3], [71.02, 51.31], [71.02, 51.3], [71.0, 51.31]]]}
    with pytest.raises(GeometryError, match="пересекают"):
        parse_field_geometry(bow_tie)


def test_outside_kazakhstan_rejected():
    moscow = {"type": "Polygon", "coordinates": [[[37.6, 55.7], [37.62, 55.7], [37.62, 55.71], [37.6, 55.71]]]}
    with pytest.raises(GeometryError, match="Казахстана"):
        parse_field_geometry(moscow)


def test_too_small_rejected():
    tiny = {"type": "Polygon", "coordinates": [[[71.0, 51.3], [71.0005, 51.3], [71.0005, 51.3003], [71.0, 51.3003]]]}
    with pytest.raises(GeometryError, match="меньше"):
        parse_field_geometry(tiny)


# --- Скоринг -------------------------------------------------------------------------------


def seasons(peaks, moisture=0.5, start=2020):
    return [SeasonData(start + i, p, p * 0.7, moisture, 15) for i, p in enumerate(peaks)]


def test_good_stable_field_is_class_a():
    r = score_field(seasons([0.72, 0.74, 0.71, 0.75, 0.73, 0.74, 0.76]))
    assert r.score_class == "A" and r.score >= 75


def test_volatile_degrading_field_is_class_c():
    r = score_field(seasons([0.65, 0.40, 0.55, 0.30, 0.45, 0.28, 0.33]))
    assert r.score_class == "C"
    assert any("деградирует" in x for x in r.reasons)


def test_few_seasons_go_to_review():
    data = seasons([0.7, 0.7, 0.7])
    r = score_field(data)
    assert r.score is None and r.score_class == "C"


def test_cloudy_seasons_are_skipped():
    data = seasons([0.7] * 7)
    for s in data[:4]:
        s.scenes = 1  # мало снимков — сезон не учитывается
    assert score_field(data).seasons_used == 3


def test_dry_soil_penalty():
    base = score_field(seasons([0.7] * 7, moisture=0.5)).score
    dry = score_field(seasons([0.7] * 7, moisture=0.1)).score
    assert base - dry == pytest.approx(5.0)


def test_classify_thresholds():
    assert classify(75) == "A" and classify(74.9) == "B" and classify(50) == "B" and classify(49.9) == "C"


# --- Лимиты и график ----------------------------------------------------------------------


def test_limit_by_class():
    assert credit_limit(100, "A", 60_000) == 6_000_000
    assert credit_limit(100, "B", 60_000) == 3_600_000
    assert credit_limit(100, "C", 60_000) == 0


def test_schedule_sums_with_fee():
    sched = build_schedule(1_000_001, "A", today=date(2026, 3, 1))
    assert [p["date"] for p in sched] == ["2026-10-15", "2026-11-15"]
    assert sum(p["amount"] for p in sched) == round(1_000_001 * 1.06)


def test_schedule_after_august_moves_to_next_year():
    sched = build_schedule(100_000, "B", today=date(2026, 10, 20))
    assert sched[0]["date"].startswith("2027")


# --- Демо-спутник --------------------------------------------------------------------------


def test_mock_provider_is_deterministic():
    years = last_complete_seasons(7, today=date(2026, 10, 20))
    assert years == list(range(2020, 2027))
    a = MockSatelliteProvider().fetch_seasons(SQUARE, years)
    b = MockSatelliteProvider().fetch_seasons(SQUARE, years)
    assert a == b and len(a) == 7
    assert all(0 < s.ndvi_peak < 1 for s in a)


def test_seasons_before_october_exclude_current_year():
    assert last_complete_seasons(7, today=date(2026, 9, 30))[-1] == 2025
