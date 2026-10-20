"""Расчёт кредитного лимита и графика платежей.

Лимит привязан к площади поля: базовая норма (по умолчанию 60 000 ₸ на гектар — примерно стоимость
семян + удобрений на 1 га пшеницы) умножается на долю по классу риска:
    A — 100 %, B — 60 %, C — 0 % (сумму назначает аналитик вручную).

Одобренная сумма = min(запрошенная сумма, лимит).

Рассрочка «до осени»: два платежа после уборки — 15 октября и 15 ноября.
Комиссия за сезон зависит от класса: A — 6 %, B — 10 %, C — 14 %.
Если заявка подана после 1 августа, платежи переносятся на осень следующего года
(под этот урожай деньги уже не успеют сработать).
"""

from __future__ import annotations

from datetime import date

CLASS_SHARE = {"A": 1.0, "B": 0.6, "C": 0.0}
CLASS_FEE = {"A": 0.06, "B": 0.10, "C": 0.14}


def credit_limit(area_ha: float, score_class: str, limit_per_ha: int) -> int:
    raw = area_ha * limit_per_ha * CLASS_SHARE[score_class]
    return int(round(raw / 1000.0)) * 1000  # округляем до тысячи тенге


def approved_amount(requested: int, limit: int) -> int:
    return max(0, min(requested, limit))


def build_schedule(amount: int, score_class: str, today: date | None = None) -> list[dict]:
    if amount <= 0:
        return []
    today = today or date.today()
    harvest_year = today.year if today.month < 8 else today.year + 1
    fee = CLASS_FEE[score_class]
    total = int(round(amount * (1 + fee)))
    first = total // 2
    second = total - first  # остаток от деления уходит во второй платёж — сумма сходится до тенге
    return [
        {"date": date(harvest_year, 10, 15).isoformat(), "amount": first},
        {"date": date(harvest_year, 11, 15).isoformat(), "amount": second},
    ]


def format_kzt(amount: int) -> str:
    """12345678 -> '12 345 678 ₸' (неразрывные пробелы между разрядами)."""
    return f"{amount:,}".replace(",", "\u00a0") + "\u00a0₸"
