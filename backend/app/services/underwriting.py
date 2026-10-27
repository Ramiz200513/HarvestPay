"""Андеррайтинг: итоговый класс и лимит из всех сигналов сразу.

Скоринг поля (scoring.py) отвечает «насколько надёжно это поле». Андеррайтинг добавляет то,
чего спутник не видит, — кто хозяйство и сколько денег в одни руки можно дать:

  1. Класс A только хозяйствам старше 2 лет (HP_CLASS_A_MIN_AGE_MONTHS): у молодого нет истории
     расчётов с поставщиками, даже если поле отличное. Иначе — понижение до B.
  2. Класс A только без активных судов, где хозяйство ответчик. Иначе — понижение до B.
  3. Лимит = площадь × норма на гектар × доля класса (limits.py), но не больше потолка класса:
     A — 20 млн ₸, B — 10 млн ₸ (HP_MAX_LIMIT_A / HP_MAX_LIMIT_B). Потолок ограничивает концентрацию
     риска: одно крупное хозяйство не должно съедать заметную часть кредитной линии.

Пример из бизнес-плана: нет судов, хозяйству больше 2 лет, NDVI стабилен и высокий → класс A,
лимит до 20 млн ₸, одобрение без участия человека.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .compliance import ComplianceInfo
from .limits import credit_limit, format_kzt
from .registry import format_age, months_between


@dataclass
class UnderwritingResult:
    score_class: str  # итоговый класс
    field_class: str  # класс по одному только полю
    limit: int
    reasons: list[str] = field(default_factory=list)


def underwrite(
    field_class: str,
    area_ha: float,
    registered_at: date | None,
    compliance: ComplianceInfo,
    *,
    limit_per_ha: int,
    class_a_min_age_months: int,
    max_limit_a: int,
    max_limit_b: int,
    today: date | None = None,
) -> UnderwritingResult:
    today = today or date.today()
    result = UnderwritingResult(score_class=field_class, field_class=field_class, limit=0)

    if result.score_class == "A":
        if registered_at and months_between(registered_at, today) < class_a_min_age_months:
            result.score_class = "B"
            age = format_age(months_between(registered_at, today))
            result.reasons.append(f"Хозяйству {age} — класс A выдаём только после 2 лет работы, итоговый класс B")
        elif compliance.court_cases:
            result.score_class = "B"
            result.reasons.append("Есть активный судебный спор, где хозяйство ответчик — итоговый класс B")

    raw_limit = credit_limit(area_ha, result.score_class, limit_per_ha)
    cap = {"A": max_limit_a, "B": max_limit_b}.get(result.score_class)
    result.limit = raw_limit
    if cap is not None and raw_limit > cap:
        result.limit = cap
        result.reasons.append(
            f"Лимит по площади {format_kzt(raw_limit)} ограничен потолком класса {result.score_class} — {format_kzt(cap)}"
        )
    return result
