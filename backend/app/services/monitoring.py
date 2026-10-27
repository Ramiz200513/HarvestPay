"""Мониторинг поля после продажи: засеяно ли поле и не отстаёт ли посев от своей нормы.

Зачем: деньги уже у поставщика, товар у фермера. Спутник отвечает на два вопроса, которые раньше
требовали выезда агронома:
  1. Семена действительно посеяны на этом поле? (NDVI поднимается выше 0,3 после голой почвы — всходы.)
     Это аргумент для поставщиков и банка: товар ушёл в землю, а не перепродан.
  2. Как идёт сезон? Сравниваем NDVI с «нормой» этого же поля — средним пиком за прошлые сезоны.
     Сильное отставание в июле — ранний сигнал неурожая: аналитик заранее готовит страховой случай
     или перенос платежа, а не узнаёт о проблеме в ноябре.

NDVI — не урожай: оценка потерь грубая (1 − факт/норма) и служит сигналом, а не расчётом выплаты.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

SOWN_NDVI = 0.3  # выше — на поле есть всходы
STRESS_RATIO = 0.75  # пик ниже 75 % нормы — риск неурожая
SEASON_START = (4, 15)
SEASON_END = (9, 30)
SOIL_NDVI = 0.15


def expected_ndvi(day: date, norm_peak: float) -> float:
    """Типичная кривая яровых на севере Казахстана: сев в конце мая, пик в середине июля, уборка в сентябре."""
    y = day.year
    rise_mid = date(y, 6, 25)
    decline_start, harvest = date(y, 7, 31), date(y, 9, 15)
    if day <= decline_start:
        t = (day - rise_mid).days
        return round(SOIL_NDVI + (norm_peak - SOIL_NDVI) / (1 + math.exp(-t / 7)), 3)
    if day <= harvest:
        share = (day - decline_start).days / (harvest - decline_start).days
        return round(norm_peak - (norm_peak - 0.22) * share, 3)
    return 0.22


def season_for(deal_season: int, today: date) -> tuple[int, str | None]:
    """Какой сезон показывать: сезон сделки, а если он ещё не начался — прошлый, с пояснением."""
    if today < date(deal_season, *SEASON_START):
        return deal_season - 1, (
            f"Сезон {deal_season} ещё не начался (сев в мае). Показан сезон {deal_season - 1}: "
            "по нему видно, что поле действительно обрабатывается."
        )
    return deal_season, None


def analyze(points: list[dict], season: int, norm_peak: float, today: date) -> dict:
    """points: [{"date": "YYYY-MM-DD", "ndvi": 0.42}, ...] — безоблачные наблюдения сезона."""
    end = min(today, date(season, *SEASON_END))
    expected = []
    d = date(season, *SEASON_START)
    while d <= date(season, *SEASON_END):
        expected.append({"date": d.isoformat(), "ndvi": expected_ndvi(d, norm_peak)})
        d += timedelta(days=10)

    result: dict = {
        "season": season,
        "norm_peak": round(norm_peak, 3),
        "points": points,
        "expected": expected,
        "sown_on": None,
        "peak": None,
        "ratio": None,
        "estimated_loss": None,
    }
    if not points:
        result.update(status="no_data", message="Безоблачных снимков пока нет — проверим позже")
        return result

    sown = next((p for p in points if p["ndvi"] >= SOWN_NDVI), None)
    peak = max(p["ndvi"] for p in points)
    result["peak"] = round(peak, 3)
    result["sown_on"] = sown["date"] if sown else None

    if sown is None:
        if end >= date(season, 6, 25):
            result.update(
                status="not_sown",
                message="К концу июня всходов не видно — поле, похоже, не засеяно. Нужен выезд или звонок фермеру",
            )
        else:
            result.update(status="waiting", message="Всходов пока нет — для конца весны это нормально")
        return result

    # Сравниваем с нормой на ту же дату: максимум факта против максимума ожидаемой кривой к этой дате
    expected_so_far = max(expected_ndvi(date.fromisoformat(p["date"]), norm_peak) for p in points)
    ratio = peak / expected_so_far if expected_so_far else 1.0
    result["ratio"] = round(ratio, 2)
    if end < date(season, 6, 20):
        result.update(status="growing", message=f"Всходы замечены {_ru(sown['date'])} — сев подтверждён")
    elif ratio < STRESS_RATIO:
        result["estimated_loss"] = round(min(max(1 - ratio, 0.0), 1.0), 2)
        result.update(
            status="stress",
            message=(
                f"Посев отстаёт от нормы поля: NDVI {peak:.2f} против {expected_so_far:.2f} "
                f"({ratio:.0%}). Риск неурожая — подготовить страховой случай или перенос платежа"
            ),
        )
    else:
        result.update(
            status="normal", message=f"Сев подтверждён {_ru(sown['date'])}, посев развивается в норме ({ratio:.0%})"
        )
    return result


def run_for_deal(deal, field, provider, today: date | None = None) -> dict:
    """Запрашивает снимки сезона сделки, анализирует и сохраняет результат в deal.monitoring.
    deal — models.Deal, field — models.Field, provider — спутниковый провайдер."""
    today = today or date.today()
    season, note = season_for(deal.payout_date.year, today)
    history = [s.ndvi_peak for s in field.seasons if s.ndvi_peak is not None and s.year != season]
    norm_peak = sum(history) / len(history) if history else 0.6
    end = min(today, date(season, *SEASON_END))
    points = provider.fetch_timeline(field.geometry, date(season, *SEASON_START), end)
    result = analyze(points, season, norm_peak, today)
    result["note"] = note
    result["checked_at"] = today.isoformat()
    result["source"] = provider.name
    deal.monitoring = result
    return result


def _ru(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"
