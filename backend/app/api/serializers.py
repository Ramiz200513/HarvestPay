"""Сборка ответов API из моделей БД. Вынесено отдельно, чтобы фермерский и аналитический
эндпоинты отдавали заявку в одинаковом формате."""

from datetime import date, datetime, timedelta, timezone

from ..config import get_settings
from ..models import Application, Deal, Farm, Product
from ..schemas import (
    ApplicationListItem,
    ApplicationOut,
    DealOut,
    DecisionOut,
    FarmOut,
    FieldOut,
    FlowStepOut,
    ItemOut,
    OverlapOut,
    ProductOut,
    SeasonOut,
)
from ..services.finance import crop_failure_scenario, deal_economics, is_overdue
from ..services.registry import FarmVerification


def _utc(value: datetime) -> datetime:
    """SQLite возвращает время без часового пояса — помечаем его как UTC, иначе браузер решит, что это местное."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def farm_out(farm: Farm | FarmVerification) -> FarmOut:
    if isinstance(farm, FarmVerification):
        return FarmOut(
            bin=farm.bin,
            name=farm.name,
            legal_form=farm.legal_form,
            registered_at=farm.registered_at,
            status=farm.status,
            reasons=farm.reasons,
            source=farm.source,
            checks=farm.checks,
        )
    return FarmOut(
        bin=farm.bin,
        name=farm.name,
        legal_form=farm.legal_form,
        registered_at=farm.registered_at,
        status=farm.verification_status,
        reasons=list(farm.verification_reasons or []),
        source=farm.registry_source,
        checks=list(farm.checks or []),
    )


def product_out(p: Product) -> ProductOut:
    return ProductOut(id=p.id, name=p.name, category=p.category, supplier=p.supplier.name, unit=p.unit, price=p.price)


def _flow(app: Application, deal: Deal) -> list[FlowStepOut]:
    """Как движутся деньги и товар по сделке — по шагам, с датами и суммами."""
    eco = deal_economics(deal)
    bank = get_settings().credit_line_bank
    suppliers = ", ".join(sorted({i.product.supplier.name for i in app.items}))
    farm = app.farm.name or app.farm.bin
    last = date.fromisoformat(deal.schedule[-1]["date"]) if deal.schedule else deal.payout_date
    steps = [
        FlowStepOut(
            when=deal.payout_date,
            source=bank,
            target=suppliers,
            amount=eco.supplier_payout,
            kind="money",
            note=f"Оплата товара со скидкой {deal.discount_rate:.1%} — поставщик не ждёт осени и не несёт риска",
        ),
        FlowStepOut(
            when=deal.payout_date + timedelta(days=7),
            source=suppliers,
            target=farm,
            amount=deal.goods_amount,
            kind="goods",
            note="Отгрузка семян и удобрений по розничной цене",
        ),
    ]
    for p in deal.schedule:
        if p.get("note"):
            continue  # строка «оплачено до переноса» — это уже прошедшие платежи
        steps.append(
            FlowStepOut(
                when=date.fromisoformat(p["date"]),
                source=farm,
                target="Спецсчёт платформы",
                amount=p["amount"],
                kind="money",
                note="Платёж по рассрочке после уборки",
            )
        )
    steps.append(
        FlowStepOut(
            when=last,
            source="Спецсчёт платформы",
            target=bank,
            amount=eco.supplier_payout + eco.funding_cost,
            kind="money",
            note=f"Погашение транша и процентов ({deal.funding_rate:.0%} годовых за {eco.funding_days} дн.)",
        )
    )
    return steps


def deal_out(app: Application, full: bool) -> DealOut | None:
    deal = app.deal
    if deal is None:
        return None
    out = DealOut(
        status=deal.status,
        overdue=is_overdue(deal),
        score_class=deal.score_class,
        goods_amount=deal.goods_amount,
        farmer_total=deal.farmer_total,
        paid_amount=deal.paid_amount,
        schedule=deal.schedule or [],
        payout_date=deal.payout_date,
        events=deal.events or [],
    )
    if full:
        out.economics = deal_economics(deal).to_dict()
        out.discount_rate = deal.discount_rate
        out.fee_rate = deal.fee_rate
        out.funding_rate = deal.funding_rate
        out.flow = _flow(app, deal)
        out.scenario = crop_failure_scenario(deal, app.field.area_ha, app.field.crop)
        out.monitoring = deal.monitoring
    return out


def overlap_out(raw: dict, full: bool) -> OverlapOut:
    out = OverlapOut(overlap_ha=raw["overlap_ha"], share=raw["share"], other_area_ha=raw["other_area_ha"])
    if full:  # аналитику — кто владелец и где именно поле
        out.farm_name, out.farm_bin, out.geometry = raw.get("farm_name"), raw.get("farm_bin"), raw.get("geometry")
    return out


def application_out(app: Application, full: bool = False) -> ApplicationOut:
    """full=True — ответ для аналитика (с данными о чужих полях), False — для фермера."""
    d = app.decision
    return ApplicationOut(
        id=app.id,
        status=app.status,
        error_message=app.error_message,
        created_at=_utc(app.created_at),
        updated_at=_utc(app.updated_at),
        requested_amount=app.requested_amount,
        farm=farm_out(app.farm),
        field=FieldOut(
            geometry=app.field.geometry,
            crop=app.field.crop,
            cadastral_number=app.field.cadastral_number,
            area_ha=app.field.area_ha,
            centroid_lat=app.field.centroid_lat,
            centroid_lon=app.field.centroid_lon,
        ),
        items=[
            ItemOut(
                product_id=i.product_id,
                name=i.product.name,
                unit=i.product.unit,
                quantity=i.quantity,
                price=i.price,
                total=i.quantity * i.price,
            )
            for i in app.items
        ],
        seasons=[SeasonOut.model_validate(s) for s in app.field.seasons],
        decision=None
        if d is None
        else DecisionOut(
            score=d.score,
            score_class=d.score_class,
            components=d.components or {},
            reasons=d.reasons or [],
            limit_amount=d.limit_amount,
            approved_amount=d.approved_amount,
            schedule=d.schedule or [],
            decided_by=d.decided_by,
            analyst_comment=d.analyst_comment,
        ),
        overlaps=[overlap_out(o, full) for o in (app.overlaps or [])],
        deal=deal_out(app, full),
    )


def application_list_item(app: Application) -> ApplicationListItem:
    d = app.decision
    return ApplicationListItem(
        id=app.id,
        status=app.status,
        created_at=_utc(app.created_at),
        farm_name=app.farm.name,
        bin=app.farm.bin,
        area_ha=app.field.area_ha,
        crop=app.field.crop,
        requested_amount=app.requested_amount,
        score=d.score if d else None,
        score_class=d.score_class if d else None,
        has_overlaps=bool(app.overlaps),
        deal_status=app.deal.status if app.deal else None,
    )
