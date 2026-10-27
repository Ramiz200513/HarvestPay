"""Тесты версии 0.3: проверка юрлица (налоги, аресты, суды), климат, андеррайтинг, деньги сделки,
сценарий неурожая и мониторинг сезона. Чистая логика — без БД и HTTP."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.services import monitoring
from app.services.compliance import ComplianceInfo, MockCompliance
from app.services.finance import (
    DealError,
    apply_action,
    crop_failure_scenario,
    economics,
    is_overdue,
    planned_payout_date,
)
from app.services.registry import MockRegistry, verify_farm
from app.services.satellite.base import SeasonData
from app.services.satellite.mock import MockSatelliteProvider
from app.services.scoring import score_field
from app.services.underwriting import underwrite

TODAY = date(2026, 10, 21)
SQUARE = {
    "type": "Polygon",
    "coordinates": [[[71.0, 51.3], [71.01435, 51.3], [71.01435, 51.309], [71.0, 51.309], [71.0, 51.3]]],
}


def verify(bin_value):
    return verify_farm(bin_value, MockRegistry(), 12, today=TODAY, compliance=MockCompliance())


# --- Проверка юрлица ---------------------------------------------------------------------------


def test_clean_farm_has_full_checklist():
    v = verify("150343000016")
    assert v.status == "verified"
    labels = {c["label"]: c["status"] for c in v.checks}
    assert labels["Налоги"] == "ok" and labels["Аресты и запреты"] == "ok" and labels["Суды"] == "ok"
    assert labels["Возраст хозяйства"] == "ok"


@pytest.mark.parametrize("value,fragment", [("170343000014", "Налоговая задолженность"), ("160540000019", "Арест")])
def test_tax_debt_and_arrest_reject(value, fragment):
    v = verify(value)
    assert v.status == "rejected"
    assert any(fragment in r for r in v.reasons)


def test_small_tax_debt_is_only_warning():
    class SmallDebt:
        def lookup(self, bin_value):
            return ComplianceInfo(tax_debt=12_000)

    v = verify_farm("150343000016", MockRegistry(), 12, today=TODAY, compliance=SmallDebt())
    assert v.status == "verified"
    assert any(c["label"] == "Налоги" and c["status"] == "warn" for c in v.checks)


def test_court_case_and_young_farm_are_warnings():
    assert verify("190340000017").status == "verified"
    young = verify("250643000018")
    assert young.status == "verified"
    assert any(c["label"] == "Возраст хозяйства" and c["status"] == "warn" for c in young.checks)


# --- Климат в скоринге ---------------------------------------------------------------------------


def seasons(frost=0, heat=0, peak=0.72):
    return [SeasonData(2020 + i, peak, peak * 0.7, 0.5, 15, frost, heat) for i in range(7)]


def test_climate_penalties():
    base = score_field(seasons()).score
    assert base - score_field(seasons(frost=1)).score == pytest.approx(2.0)
    assert base - score_field(seasons(frost=3)).score == pytest.approx(4.0)
    assert base - score_field(seasons(heat=12)).score == pytest.approx(4.0)
    both = score_field(seasons(frost=3, heat=6))
    assert base - both.score == pytest.approx(6.0)
    assert any("заморозки" in r for r in both.reasons) and any("Жара" in r for r in both.reasons)


def test_climate_unknown_means_no_penalty():
    # сезоны, посчитанные до версии 0.3, без климата — штрафа нет
    plain = [SeasonData(2020 + i, 0.72, 0.5, 0.5, 15) for i in range(7)]
    assert score_field(plain).components["climate_penalty"] == 0


def test_mock_climate_north_has_more_frost_than_south():
    years = list(range(2020, 2027))

    def avg_frost(lat):
        total = 0
        for k in range(20):
            lon = 66 + k * 0.3
            geom = {
                "type": "Polygon",
                "coordinates": [[[lon, lat], [lon + 0.01, lat], [lon + 0.01, lat + 0.01], [lon, lat]]],
            }
            total += sum(s.frost_days for s in MockSatelliteProvider().fetch_seasons(geom, years))
        return total

    assert avg_frost(53.5) > avg_frost(45.0)


# --- Андеррайтинг ---------------------------------------------------------------------------------

UW = dict(limit_per_ha=60_000, class_a_min_age_months=24, max_limit_a=20_000_000, max_limit_b=10_000_000, today=TODAY)


def test_class_a_ok_for_mature_clean_farm():
    r = underwrite("A", 100, date(2015, 3, 15), ComplianceInfo(), **UW)
    assert r.score_class == "A" and r.limit == 6_000_000 and not r.reasons


def test_young_farm_capped_to_b():
    r = underwrite("A", 100, date(2025, 6, 15), ComplianceInfo(), **UW)
    assert r.score_class == "B" and r.field_class == "A"
    assert r.limit == 3_600_000


def test_court_case_capped_to_b():
    assert underwrite("A", 100, date(2015, 3, 15), ComplianceInfo(court_cases=1), **UW).score_class == "B"


def test_limit_ceiling_per_class():
    big = underwrite("A", 1000, date(2015, 3, 15), ComplianceInfo(), **UW)  # 60 млн по площади
    assert big.limit == 20_000_000 and any("потолком" in r for r in big.reasons)
    assert underwrite("B", 1000, date(2015, 3, 15), ComplianceInfo(), **UW).limit == 10_000_000


# --- Экономика сделки ------------------------------------------------------------------------------


def test_economics_adds_up():
    e = economics(1_000_000, 0.06, 1_060_000, 0.17, date(2027, 4, 1), date(2027, 11, 15), "A")
    assert e.supplier_payout == 940_000 and e.discount_income == 60_000 and e.fee_income == 60_000
    assert e.funding_days == 228
    assert e.funding_cost == round(940_000 * 0.17 * 228 / 365)
    assert e.margin == 1_060_000 - 940_000 - e.funding_cost - e.expected_loss


def test_supplier_paid_before_sowing():
    schedule = [{"date": "2027-10-15", "amount": 1}, {"date": "2027-11-15", "amount": 1}]
    assert planned_payout_date(schedule, date(2026, 10, 21)) == date(2027, 4, 1)
    assert planned_payout_date(schedule, date(2027, 5, 10)) == date(2027, 5, 10)


def make_deal(**kw):
    defaults = dict(
        status="contracted",
        score_class="A",
        goods_amount=1_000_000,
        discount_rate=0.06,
        supplier_payout=940_000,
        fee_rate=0.06,
        farmer_total=1_060_000,
        funding_rate=0.17,
        payout_date=date(2027, 4, 1),
        schedule=[{"date": "2027-10-15", "amount": 530_000}, {"date": "2027-11-15", "amount": 530_000}],
        paid_amount=0,
        events=[],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_deal_lifecycle_to_repaid():
    d = make_deal()
    for action in ("pay_supplier", "confirm_delivery", "confirm_sowing"):
        apply_action(d, action, today=date(2027, 6, 1))
    assert d.status == "sowing_confirmed"
    apply_action(d, "record_payment", 530_000, today=date(2027, 10, 15))
    assert d.status == "sowing_confirmed" and d.paid_amount == 530_000
    apply_action(d, "record_payment", 530_000, today=date(2027, 11, 15))
    assert d.status == "repaid"
    assert [e["action"] for e in d.events][-1] == "repaid"


def test_actions_out_of_order_are_refused():
    with pytest.raises(DealError):
        apply_action(make_deal(), "confirm_delivery")
    with pytest.raises(DealError):
        apply_action(make_deal(status="delivered"), "record_payment", 2_000_000)  # больше долга


def test_restructure_moves_rest_to_next_year():
    d = make_deal(status="sowing_confirmed", paid_amount=300_000)
    apply_action(d, "restructure", today=date(2027, 11, 20))
    assert d.status == "restructured"
    extra = round(760_000 * 0.08)
    assert d.farmer_total == 1_060_000 + extra
    assert sum(p["amount"] for p in d.schedule) == d.farmer_total
    assert d.schedule[-1]["date"] == "2028-11-15"


def test_overdue():
    d = make_deal(status="sowing_confirmed", paid_amount=0)
    assert not is_overdue(d, today=date(2027, 10, 15))
    assert is_overdue(d, today=date(2027, 10, 16))
    d.paid_amount = 530_000
    assert not is_overdue(d, today=date(2027, 10, 16))


def test_crop_failure_waterfall():
    d = make_deal(status="sowing_confirmed")
    rows = {r["loss"]: r for r in crop_failure_scenario(d, area_ha=20, crop="Пшеница яровая")}
    # нормальный год: 20 га × 130 000 × 60 % = 1,56 млн > долга — фермер платит всё сам
    assert rows[0.0]["from_farmer"] == 1_060_000 and rows[0.0]["rollover"] == 0
    bad = rows[0.7]
    assert bad["from_farmer"] + bad["insurance"] + bad["rollover"] == 1_060_000
    assert bad["insurance"] > 0
    # страховка уменьшает перенос и улучшает итог платформы
    assert bad["rollover"] < bad["rollover_uninsured"]
    assert bad["platform_result"] > bad["platform_result_uninsured"]
    # чем сильнее неурожай, тем хуже итог
    results = [r["platform_result_uninsured"] for r in crop_failure_scenario(d, 20, "Пшеница яровая")]
    assert results == sorted(results, reverse=True)


# --- Мониторинг сезона -----------------------------------------------------------------------------


def curve(peak, start=date(2027, 4, 15), end=date(2027, 9, 30)):
    points, d = [], start
    while d <= end:
        points.append({"date": d.isoformat(), "ndvi": monitoring.expected_ndvi(d, peak)})
        d = date.fromordinal(d.toordinal() + 10)
    return points


def test_monitoring_normal_season():
    r = monitoring.analyze(curve(0.7), 2027, 0.7, today=date(2027, 10, 1))
    assert r["status"] == "normal" and r["sown_on"] is not None


def test_monitoring_detects_stress():
    r = monitoring.analyze(curve(0.4), 2027, 0.7, today=date(2027, 10, 1))
    assert r["status"] == "stress" and r["estimated_loss"] > 0.3


def test_monitoring_detects_not_sown():
    flat = [{"date": f"2027-{m:02d}-10", "ndvi": 0.18} for m in (5, 6, 7)]
    assert monitoring.analyze(flat, 2027, 0.7, today=date(2027, 7, 15))["status"] == "not_sown"


def test_monitoring_shows_previous_season_before_spring():
    season, note = monitoring.season_for(2027, date(2026, 10, 21))
    assert season == 2026 and "ещё не начался" in note
    assert monitoring.season_for(2027, date(2027, 6, 1)) == (2027, None)


def test_mock_timeline_is_deterministic_and_bounded():
    p = MockSatelliteProvider()
    a = p.fetch_timeline(SQUARE, date(2026, 4, 15), date(2026, 9, 30))
    assert a == p.fetch_timeline(SQUARE, date(2026, 4, 15), date(2026, 9, 30))
    assert a and all(0 < x["ndvi"] < 1 for x in a)
