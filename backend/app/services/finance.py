"""Деньги маркетплейса: экономика сделки, кредитная линия банка, жизненный цикл, сценарий неурожая.

Как движутся деньги (схема из бизнес-плана):

    весна  Банк-партнёр ──(цена − скидка 5–7 %)──► Поставщик ──(товар)──► Фермер
    осень  Фермер ──(цена + наценка за рассрочку)──► спецсчёт платформы ──(транш + %)──► Банк
                                                                          └─► остаток — доход платформы

  * Поставщик получает деньги сразу при отгрузке и за это уступает скидку — он не ждёт осени
    и не несёт риска невозврата.
  * Банк даёт платформе кредитную линию под её спутниковый скоринг. Линия с регрессом на платформу:
    фермер не заплатил — платформа всё равно гасит банку, поэтому первый убыток (first loss) на ней.
  * Доход платформы = скидка поставщика + наценка фермеру − проценты банку − ожидаемые потери.

Риск неурожая закрывается по очереди (crop_failure_scenario):
  1. выручка фермера с урожая — сколько он может направить на долг;
  2. страховка урожая с франшизой 30 % (условие договора, выгодоприобретатель — платформа);
  3. остаток не списывается, а переносится на следующий сезон с доплатой (реструктуризация) —
     земля и хозяйство никуда не деваются, следующий урожай обычно нормальный;
  4. то, что может не вернуться и после переноса, — ожидаемый убыток, его покрывает резерв платформы.

Все коэффициенты ниже — допущения до накопления собственной статистики, они вынесены в константы,
чтобы их было видно и легко поменять.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Application, Deal, DealStatus

# Вероятность, что фермер не рассчитается (PD), и доля потерь в этом случае (LGD) — допущения
PD = {"A": 0.02, "B": 0.05, "C": 0.10}
LGD = 0.45

SUPPLIER_PAYMENT = (4, 1)  # поставщику платим перед севом — 1 апреля года урожая (или в день одобрения, если позже)

RESTRUCTURE_FEE = 0.08  # доплата за перенос остатка долга на следующий сезон

# --- Допущения для сценария неурожая (демо, заменить данными Бюро нацстатистики) ---
# Выручка с гектара при нормальном урожае: урожайность × цена
REVENUE_PER_HA = {
    "Пшеница яровая": 1.3 * 100_000,
    "Ячмень": 1.4 * 80_000,
    "Подсолнечник": 1.0 * 200_000,
    "Рапс": 1.0 * 220_000,
    "Лён масличный": 0.8 * 250_000,
    "Овёс": 1.3 * 70_000,
}
DEFAULT_REVENUE_PER_HA = 120_000
DEBT_SERVICE_SHARE = 0.6  # какую долю выручки хозяйство может направить на долг (остальное — ГСМ, зарплаты, аренда)
INSURANCE_DEDUCTIBLE = 0.3  # страховка платит, когда потеряно больше 30 % урожая
ROLLOVER_LOSS = 0.3  # какая доля перенесённого долга, по нашей оценке, может не вернуться и в следующем году
SCENARIO_LOSSES = (0.0, 0.3, 0.5, 0.7, 0.9)


class DealError(Exception):
    """Действие невозможно в текущем статусе сделки (HTTP 409)."""


# --- Экономика сделки -------------------------------------------------------------------------


@dataclass
class Economics:
    goods_amount: int  # товар по розничной цене
    discount_income: int  # скидка поставщика — остаётся у платформы
    supplier_payout: int  # банк платит поставщикам
    fee_income: int  # наценка фермеру за рассрочку
    farmer_total: int  # фермер возвращает
    funding_days: int  # сколько дней деньги банка в работе
    funding_cost: int  # проценты банку
    expected_loss: int  # PD × LGD × долг фермера
    margin: int  # итог платформы
    margin_pct: float  # маржа к сумме товара

    def to_dict(self) -> dict:
        return asdict(self)


def weighted_discount(app: Application) -> float:
    """Средняя скидка поставщиков по корзине заявки, взвешенная по сумме позиций."""
    total = sum(i.quantity * i.price for i in app.items)
    if not total:
        return 0.0
    return sum(i.quantity * i.price * i.product.supplier.discount for i in app.items) / total


def planned_payout_date(schedule: list[dict], approved_on: date) -> date:
    harvest_year = date.fromisoformat(schedule[0]["date"]).year
    return max(approved_on, date(harvest_year, *SUPPLIER_PAYMENT))


def economics(
    goods_amount: int,
    discount_rate: float,
    farmer_total: int,
    funding_rate: float,
    payout_date: date,
    last_payment: date,
    score_class: str,
) -> Economics:
    payout = round(goods_amount * (1 - discount_rate))
    days = max((last_payment - payout_date).days, 0)
    funding_cost = round(payout * funding_rate * days / 365)
    expected_loss = round(farmer_total * PD.get(score_class, PD["C"]) * LGD)
    margin = farmer_total - payout - funding_cost - expected_loss
    return Economics(
        goods_amount=goods_amount,
        discount_income=goods_amount - payout,
        supplier_payout=payout,
        fee_income=farmer_total - goods_amount,
        farmer_total=farmer_total,
        funding_days=days,
        funding_cost=funding_cost,
        expected_loss=expected_loss,
        margin=margin,
        margin_pct=round(margin / goods_amount, 4) if goods_amount else 0.0,
    )


def deal_economics(deal: Deal) -> Economics:
    last = date.fromisoformat(deal.schedule[-1]["date"]) if deal.schedule else deal.payout_date
    return economics(
        deal.goods_amount,
        deal.discount_rate,
        deal.farmer_total,
        deal.funding_rate,
        deal.payout_date,
        last,
        deal.score_class,
    )


# --- Кредитная линия ----------------------------------------------------------------------------


def outstanding(deal: Deal) -> int:
    """Сколько денег банка «сидит» в сделке: выплата поставщику минус то, что фермер уже вернул."""
    if deal.status not in DealStatus.ACTIVE:
        return 0
    return max(deal.supplier_payout - deal.paid_amount, 0)


def credit_line_used(db: Session) -> int:
    deals = db.scalars(select(Deal).where(Deal.status.in_(DealStatus.ACTIVE)))
    return sum(outstanding(d) for d in deals)


def credit_line_available(db: Session) -> int:
    return get_settings().credit_line_limit - credit_line_used(db)


def required_payout(app: Application, amount: int) -> int:
    return round(amount * (1 - weighted_discount(app)))


# --- Жизненный цикл -----------------------------------------------------------------------------


def _event(deal: Deal, action: str, note: str, amount: int | None = None, on: date | None = None) -> None:
    deal.events = [
        *(deal.events or []),
        {"at": (on or date.today()).isoformat(), "action": action, "amount": amount, "note": note},
    ]


def open_deal(db: Session, app: Application, today: date | None = None) -> Deal:
    """Создаёт сделку по одобренной заявке и резервирует деньги в кредитной линии."""
    today = today or date.today()
    d = app.decision
    if d is None or d.approved_amount <= 0 or not d.schedule:
        raise DealError("Сделку можно открыть только по одобренной заявке")
    settings = get_settings()
    discount = weighted_discount(app)
    payout_date = planned_payout_date(d.schedule, today)
    deal = app.deal or Deal(application_id=app.id)
    deal.status = DealStatus.CONTRACTED
    deal.score_class = d.score_class
    deal.goods_amount = d.approved_amount
    deal.discount_rate = round(discount, 4)
    deal.supplier_payout = round(d.approved_amount * (1 - discount))
    deal.farmer_total = sum(p["amount"] for p in d.schedule)
    deal.fee_rate = round(deal.farmer_total / d.approved_amount - 1, 4)
    deal.funding_rate = settings.credit_line_rate
    deal.payout_date = payout_date
    deal.schedule = list(d.schedule)
    deal.paid_amount = 0
    deal.events = []
    _event(
        deal,
        "contracted",
        f"Трёхсторонний договор: фермер, поставщики, платформа. Резерв в линии {settings.credit_line_bank}",
        deal.supplier_payout,
        today,
    )
    app.deal = deal
    db.add(deal)
    return deal


def contract_number(deal: Deal) -> str:
    """Номер договора рассрочки: HP-<год>-<номер сделки>. Фермер указывает его в назначении платежа."""
    year = deal.created_at.year if deal.created_at else date.today().year
    return f"HP-{year}-{deal.id:06d}"


def payment_info(deal: Deal) -> dict:
    s = get_settings()
    number = contract_number(deal)
    return {
        "contract_number": number,
        "recipient": s.payee_name,
        "bin": s.payee_bin,
        "bank": s.payee_bank,
        "iik": s.payee_iik,
        "bik": s.payee_bik,
        "kbe": s.payee_kbe,
        "knp": s.payee_knp,
        "purpose": f"Оплата по договору рассрочки № {number} за семена и удобрения, без НДС",
        "demo": s.payee_demo,
        "fee_rate": deal.fee_rate,
        "restructure_fee": RESTRUCTURE_FEE,
        "insurance_deductible": INSURANCE_DEDUCTIBLE,
        "support_email": s.support_email,
    }


def is_overdue(deal: Deal, today: date | None = None) -> bool:
    if deal.status not in DealStatus.ACTIVE:
        return False
    today = today or date.today()
    due = sum(p["amount"] for p in deal.schedule if date.fromisoformat(p["date"]) < today)
    return deal.paid_amount < due


ACTIONS = {
    # action: (из каких статусов, в какой статус)
    "pay_supplier": ((DealStatus.CONTRACTED,), DealStatus.SUPPLIER_PAID),
    "confirm_delivery": ((DealStatus.SUPPLIER_PAID,), DealStatus.DELIVERED),
    "confirm_sowing": ((DealStatus.DELIVERED,), DealStatus.SOWING_CONFIRMED),
    "record_payment": (
        (DealStatus.DELIVERED, DealStatus.SOWING_CONFIRMED, DealStatus.RESTRUCTURED),
        None,
    ),
    "restructure": ((DealStatus.DELIVERED, DealStatus.SOWING_CONFIRMED), DealStatus.RESTRUCTURED),
}


def apply_action(deal: Deal, action: str, amount: int | None = None, today: date | None = None) -> Deal:
    today = today or date.today()
    if action not in ACTIONS:
        raise DealError(f"Неизвестное действие {action}")
    allowed, target = ACTIONS[action]
    if deal.status not in allowed:
        raise DealError(f"Действие «{action}» недоступно в статусе «{deal.status}»")

    if action == "pay_supplier":
        _event(deal, action, "Банк перечислил поставщикам оплату за товар со скидкой", deal.supplier_payout, today)
    elif action == "confirm_delivery":
        _event(deal, action, "Поставщики отгрузили товар хозяйству", deal.goods_amount, today)
    elif action == "confirm_sowing":
        _event(deal, action, "Сев подтверждён (выезд или спутник)", None, today)
    elif action == "record_payment":
        remaining = deal.farmer_total - deal.paid_amount
        if not amount or amount <= 0 or amount > remaining:
            raise DealError(f"Сумма платежа должна быть от 1 до {remaining} ₸")
        deal.paid_amount += amount
        _event(deal, action, "Платёж фермера на спецсчёт платформы", amount, today)
        if deal.paid_amount >= deal.farmer_total:
            target = DealStatus.REPAID
            _event(deal, "repaid", "Рассрочка погашена полностью, транш банку закрыт", None, today)
    elif action == "restructure":
        remaining = deal.farmer_total - deal.paid_amount
        extra = round(remaining * RESTRUCTURE_FEE)
        new_total = remaining + extra
        year = max(date.fromisoformat(deal.schedule[-1]["date"]).year, today.year) + 1
        first = new_total // 2
        # Сумма графика всегда равна farmer_total: уже оплаченное остаётся в графике одной строкой
        paid_row = [{"date": today.isoformat(), "amount": deal.paid_amount, "note": "оплачено до переноса"}]
        deal.schedule = [
            *(paid_row if deal.paid_amount else []),
            {"date": date(year, 10, 15).isoformat(), "amount": first},
            {"date": date(year, 11, 15).isoformat(), "amount": new_total - first},
        ]
        deal.farmer_total += extra
        _event(
            deal,
            action,
            f"Неурожай: остаток долга перенесён на осень {year} с доплатой {RESTRUCTURE_FEE:.0%}",
            remaining,
            today,
        )

    if target:
        deal.status = target
    return deal


# --- Сценарий неурожая --------------------------------------------------------------------------


def revenue_per_ha(crop: str) -> float:
    return REVENUE_PER_HA.get(crop, DEFAULT_REVENUE_PER_HA)


def _close_shortfall(
    rest: int, due: int, loss: float, insured: bool, deal: Deal, base_result: int
) -> tuple[int, int, int]:
    """Чем закрывается недоплата фермера rest: страховкой, затем переносом. Возвращает (страховка, перенос, итог)."""
    insurance = round(min(rest, due * max(0.0, loss - INSURANCE_DEDUCTIBLE))) if insured else 0
    rollover = rest - insurance
    # Перенос: банку платформа гасит вовремя из своих денег или продления линии — это ещё год процентов,
    # и часть перенесённого может не вернуться. Доплата за перенос частично это компенсирует.
    rollover_cost = round(rollover * deal.funding_rate) + round(rollover * ROLLOVER_LOSS)
    rollover_income = round(rollover * RESTRUCTURE_FEE)
    return insurance, rollover, base_result - rollover_cost + rollover_income


def crop_failure_scenario(deal: Deal, area_ha: float, crop: str) -> list[dict]:
    """Кто и сколько закрывает долг при разной потере урожая. Строка на каждый уровень потерь."""
    due = deal.farmer_total - deal.paid_amount
    eco = deal_economics(deal)
    # Итог «если всё прошло по плану»: маржа без статистической поправки на потери — здесь потери считаем явно
    base_result = eco.margin + eco.expected_loss
    normal_revenue = area_ha * revenue_per_ha(crop)
    rows = []
    for loss in SCENARIO_LOSSES:
        capacity = normal_revenue * (1 - loss) * DEBT_SERVICE_SHARE
        from_farmer = round(min(due, capacity))
        rest = due - from_farmer
        insurance, rollover, result_insured = _close_shortfall(rest, due, loss, True, deal, base_result)
        _, rollover_uninsured, result_uninsured = _close_shortfall(rest, due, loss, False, deal, base_result)
        rows.append(
            {
                "loss": loss,
                "from_farmer": from_farmer,
                "insurance": insurance,
                "rollover": rollover,
                "platform_result": result_insured,
                "rollover_uninsured": rollover_uninsured,
                "platform_result_uninsured": result_uninsured,
            }
        )
    return rows
