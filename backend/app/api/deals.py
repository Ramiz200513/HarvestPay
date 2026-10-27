"""Сделки и деньги: портфель, кредитная линия, шаги сделки, спутниковый мониторинг сезона.
Доступно только аналитику (тот же токен X-Analyst-Token)."""

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Application, Deal, DealStatus
from ..schemas import ApplicationOut, CreditLineOut, DealActionIn, PaymentOut, PortfolioDealOut, PortfolioOut
from ..services import monitoring
from ..services.finance import DealError, apply_action, credit_line_used, deal_economics, is_overdue
from ..services.providers import get_satellite_provider
from .deps import require_analyst
from .serializers import application_out

router = APIRouter(prefix="/api/analyst", tags=["Сделки и деньги"], dependencies=[Depends(require_analyst)])


def _deal_app(db: Session, application_id: str) -> Application:
    app = db.get(Application, application_id)
    if app is None or app.deal is None:
        raise HTTPException(status_code=404, detail="Сделка по этой заявке не найдена")
    return app


def _upcoming(deal: Deal) -> list[tuple[date, int]]:
    """Оставшиеся платежи: уже оплаченное «съедает» график с начала."""
    paid = deal.paid_amount
    left = []
    for p in deal.schedule:
        amount = p["amount"]
        covered = min(paid, amount)
        paid -= covered
        if amount - covered > 0:
            left.append((date.fromisoformat(p["date"]), amount - covered))
    return left


@router.get("/portfolio", response_model=PortfolioOut, summary="Портфель сделок и кредитная линия")
def portfolio(db: Session = Depends(get_db)) -> PortfolioOut:
    settings = get_settings()
    deals = list(db.scalars(select(Deal).order_by(Deal.created_at.desc())))
    used = credit_line_used(db)

    by_status: dict[str, int] = defaultdict(int)
    by_class: dict[str, int] = defaultdict(int)
    by_month: dict[date, int] = defaultdict(int)
    rows = []
    margin = loss = 0
    for d in deals:
        eco = deal_economics(d)
        by_status[d.status] += 1
        by_class[d.score_class] += d.goods_amount
        margin += eco.margin
        loss += eco.expected_loss
        if d.status in DealStatus.ACTIVE:
            for when, amount in _upcoming(d):
                by_month[when.replace(day=1)] += amount
        app = d.application
        rows.append(
            PortfolioDealOut(
                application_id=app.id,
                farm_name=app.farm.name,
                crop=app.field.crop,
                area_ha=app.field.area_ha,
                score_class=d.score_class,
                status=d.status,
                overdue=is_overdue(d),
                goods_amount=d.goods_amount,
                farmer_total=d.farmer_total,
                paid_amount=d.paid_amount,
                margin=eco.margin,
                monitoring_status=(d.monitoring or {}).get("status"),
            )
        )

    return PortfolioOut(
        credit_line=CreditLineOut(
            bank=settings.credit_line_bank,
            limit=settings.credit_line_limit,
            used=used,
            available=settings.credit_line_limit - used,
            rate=settings.credit_line_rate,
        ),
        deals_count=len(deals),
        goods_amount=sum(d.goods_amount for d in deals),
        supplier_payout=sum(d.supplier_payout for d in deals),
        farmer_total=sum(d.farmer_total for d in deals),
        paid_amount=sum(d.paid_amount for d in deals),
        expected_margin=margin,
        expected_loss=loss,
        by_status=dict(by_status),
        by_class=dict(by_class),
        upcoming=[PaymentOut(date=m, amount=a) for m, a in sorted(by_month.items())],
        deals=rows,
    )


@router.post("/deals/{application_id}/action", response_model=ApplicationOut, summary="Следующий шаг сделки")
def deal_action(application_id: str, body: DealActionIn, db: Session = Depends(get_db)) -> ApplicationOut:
    app = _deal_app(db, application_id)
    try:
        apply_action(app.deal, body.action, body.amount)
    except DealError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return application_out(app, full=True)


@router.post(
    "/deals/{application_id}/monitoring", response_model=ApplicationOut, summary="Обновить спутниковый мониторинг"
)
def refresh_monitoring(application_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    """В режиме GEE запрос к спутнику идёт 10–30 секунд — аналитик нажимает кнопку и ждёт.
    Если в сезоне сделки видны всходы, а товар уже отгружен, сев подтверждается автоматически."""
    app = _deal_app(db, application_id)
    deal = app.deal
    try:
        result = monitoring.run_for_deal(deal, app.field, get_satellite_provider())
    except Exception as exc:  # noqa: BLE001 — недоступен GEE и т.п.: показываем причину, сделку не трогаем
        raise HTTPException(status_code=502, detail=f"Не удалось получить снимки: {exc}") from exc
    if result["note"] is None and result["sown_on"] and deal.status == DealStatus.DELIVERED:
        apply_action(deal, "confirm_sowing")
    db.commit()
    return application_out(app, full=True)
