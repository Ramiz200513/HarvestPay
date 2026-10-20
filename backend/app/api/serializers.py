"""Сборка ответов API из моделей БД. Вынесено отдельно, чтобы фермерский и аналитический
эндпоинты отдавали заявку в одинаковом формате."""

from datetime import datetime, timezone

from ..models import Application, Farm
from ..schemas import (
    ApplicationListItem,
    ApplicationOut,
    DecisionOut,
    FarmOut,
    FieldOut,
    ItemOut,
    SeasonOut,
)
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
        )
    return FarmOut(
        bin=farm.bin,
        name=farm.name,
        legal_form=farm.legal_form,
        registered_at=farm.registered_at,
        status=farm.verification_status,
        reasons=list(farm.verification_reasons or []),
        source=farm.registry_source,
    )


def application_out(app: Application) -> ApplicationOut:
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
    )
