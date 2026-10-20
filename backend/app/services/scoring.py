"""Скоркарта: индекс стабильности поля 0–100 и класс риска A/B/C.

Почему не нейросеть: истории дефолтов казахстанских хозяйств нет, обучать модель не на чем.
Прозрачная скоркарта честнее: каждое число можно объяснить фермеру и комиссии.

Формула (из раздела «Проектирование системы»):
    stability = 0.5 · mean_norm + 0.3 · (100 − volatility_norm) + 0.2 · trend_norm

  mean_norm       — средний пиковый NDVI за сезоны, переведённый в 0..100 (0.25 → 0, 0.75 → 100)
  volatility_norm — коэффициент вариации пиков (std / mean), 0 → 0, 0.35 → 100. Чем больше разброс, тем хуже,
                    поэтому в формулу идёт (100 − volatility_norm)
  trend_norm      — наклон линейного тренда NDVI по годам, −0.03/год → 0, +0.03/год → 100

Корректировка по влажности: если в последнем сезоне индекс влажности < 0.25, снимаем 5 баллов —
сухая почва перед новым сезоном повышает риск неурожая.

Классы: A ≥ 75, B ≥ 50, иначе C. Класс C — не отказ, а ручная проверка аналитиком.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .satellite.base import SeasonData

W_MEAN, W_STABILITY, W_TREND = 0.5, 0.3, 0.2
THRESHOLD_A, THRESHOLD_B = 75.0, 50.0
MIN_SEASONS = 4  # меньше — статистика ненадёжна
MIN_SCENES = 3  # сезон, где меньше 3 безоблачных снимков, не учитываем
DRY_SOIL = 0.25
DRY_SOIL_PENALTY = 5.0


@dataclass
class ScoreResult:
    score: float | None
    score_class: str  # "A" | "B" | "C"
    components: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    seasons_used: int = 0


def normalize(value: float, low: float, high: float) -> float:
    """Линейно переводит value из [low, high] в [0, 100] с обрезкой по краям."""
    ratio = (value - low) / (high - low)
    return max(0.0, min(1.0, ratio)) * 100.0


def linear_slope(xs: list[float], ys: list[float]) -> float:
    """Наклон прямой методом наименьших квадратов: на сколько NDVI меняется за год."""
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den else 0.0


def classify(score: float) -> str:
    if score >= THRESHOLD_A:
        return "A"
    if score >= THRESHOLD_B:
        return "B"
    return "C"


def score_field(seasons: list[SeasonData]) -> ScoreResult:
    usable = sorted(
        (s for s in seasons if s.ndvi_peak is not None and s.scenes >= MIN_SCENES),
        key=lambda s: s.year,
    )
    if len(usable) < MIN_SEASONS:
        return ScoreResult(
            score=None,
            score_class="C",
            reasons=[
                f"Надёжных сезонов {len(usable)} из {len(seasons)} (нужно минимум {MIN_SEASONS}) — "
                "заявка уходит на ручную проверку"
            ],
            seasons_used=len(usable),
        )

    years = [float(s.year) for s in usable]
    peaks = [float(s.ndvi_peak) for s in usable]  # type: ignore[arg-type]

    mean_peak = statistics.fmean(peaks)
    cv = statistics.pstdev(peaks) / mean_peak if mean_peak else 1.0
    slope = linear_slope(years, peaks)

    mean_norm = normalize(mean_peak, 0.25, 0.75)
    volatility_norm = normalize(cv, 0.0, 0.35)
    trend_norm = normalize(slope, -0.03, 0.03)

    score = W_MEAN * mean_norm + W_STABILITY * (100 - volatility_norm) + W_TREND * trend_norm
    reasons: list[str] = []

    # --- человекочитаемые объяснения: фермер должен понимать, откуда балл ---
    if mean_peak >= 0.6:
        reasons.append(f"Средний пиковый NDVI {mean_peak:.2f} — поле стабильно даёт густую растительность")
    elif mean_peak < 0.45:
        reasons.append(f"Средний пиковый NDVI {mean_peak:.2f} — растительность слабее, чем у типичного поля")
    else:
        reasons.append(f"Средний пиковый NDVI {mean_peak:.2f} — на уровне типичного поля региона")

    if cv > 0.2:
        reasons.append(f"Результат сильно скачет по годам (разброс {cv:.0%})")
    elif cv < 0.1:
        reasons.append(f"Сезоны стабильны: разброс между годами всего {cv:.0%}")

    if slope <= -0.01:
        reasons.append(f"Поле деградирует: NDVI падает примерно на {abs(slope):.3f} в год")
    elif slope >= 0.01:
        reasons.append(f"Поле улучшается: NDVI растёт примерно на {slope:.3f} в год")

    worst = min(usable, key=lambda s: s.ndvi_peak or 0)
    if (worst.ndvi_peak or 0) < mean_peak - 0.15:
        reasons.append(f"В {worst.year} году заметный провал NDVI — вероятно, засуха или неурожай")

    latest = usable[-1]
    moisture_penalty = 0.0
    if latest.soil_moisture is not None and latest.soil_moisture < DRY_SOIL:
        moisture_penalty = DRY_SOIL_PENALTY
        score -= moisture_penalty
        reasons.append(
            f"Низкая влажность почвы в {latest.year} году (индекс {latest.soil_moisture:.2f}) — −{DRY_SOIL_PENALTY:g} баллов"
        )

    score = round(max(0.0, min(100.0, score)), 1)

    return ScoreResult(
        score=score,
        score_class=classify(score),
        components={
            "mean_ndvi": round(mean_peak, 3),
            "mean_norm": round(mean_norm, 1),
            "volatility_cv": round(cv, 3),
            "volatility_norm": round(volatility_norm, 1),
            "trend_slope": round(slope, 4),
            "trend_norm": round(trend_norm, 1),
            "moisture_penalty": moisture_penalty,
            "weights": {"mean": W_MEAN, "stability": W_STABILITY, "trend": W_TREND},
        },
        reasons=reasons,
        seasons_used=len(usable),
    )
