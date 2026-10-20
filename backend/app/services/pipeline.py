"""Конвейер обработки заявки — то, что выполняется в фоне после нажатия «Отправить».

    pending → processing → (спутник → скоринг → лимит) → approved | review | error

Функция одна и та же для обоих режимов: её вызывает и FastAPI BackgroundTasks (режим background),
и Celery-воркер (режим celery). Поэтому логика не дублируется.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Application, ApplicationStatus, Decision, FieldSeason
from .limits import approved_amount, build_schedule, credit_limit, format_kzt
from .providers import get_satellite_provider
from .satellite.base import SeasonData, last_complete_seasons
from .scoring import score_field

log = logging.getLogger(__name__)


def _load_or_fetch_seasons(db: Session, app: Application) -> list[SeasonData]:
    """Если по этому полю уже считали нужные сезоны — берём из БД (кэш), иначе идём к спутнику."""
    settings = get_settings()
    years = last_complete_seasons(settings.seasons)
    field = app.field

    cached = {s.year: s for s in field.seasons}
    if all(y in cached for y in years):
        return [
            SeasonData(c.year, c.ndvi_peak, c.ndvi_mean, c.soil_moisture, c.scenes) for c in (cached[y] for y in years)
        ]

    provider = get_satellite_provider()
    fetched = provider.fetch_seasons(field.geometry, years)
    for s in fetched:
        row = cached.get(s.year)
        if row is None:
            row = FieldSeason(year=s.year, source=provider.name)
            field.seasons.append(row)
        row.ndvi_peak, row.ndvi_mean = s.ndvi_peak, s.ndvi_mean
        row.soil_moisture, row.scenes, row.source = s.soil_moisture, s.scenes, provider.name
    db.flush()
    return fetched


STUCK_AFTER = timedelta(minutes=10)


def _is_stuck(app: Application) -> bool:
    """«processing» дольше 10 минут — воркер упал посреди расчёта; задачу можно взять заново."""
    if app.status != ApplicationStatus.PROCESSING:
        return False
    updated = app.updated_at
    if updated.tzinfo is None:  # SQLite отдаёт время без часового пояса
        updated = updated.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated > STUCK_AFTER


def process_application(db: Session, application_id: str, today: date | None = None) -> None:
    app = db.get(Application, application_id)
    if app is None:
        log.warning("Заявка %s не найдена", application_id)
        return
    if app.status not in (ApplicationStatus.PENDING, ApplicationStatus.ERROR) and not _is_stuck(app):
        return  # уже обработана или считается прямо сейчас — защита от повторного запуска

    app.status = ApplicationStatus.PROCESSING
    app.error_message = None
    db.commit()

    try:
        seasons = _load_or_fetch_seasons(db, app)
        result = score_field(seasons)

        settings = get_settings()
        limit = credit_limit(app.field.area_ha, result.score_class, settings.limit_per_ha)
        amount = approved_amount(app.requested_amount, limit)

        reasons = list(result.reasons)
        if result.score_class == "C":
            reasons.append("Класс C: решение примет кредитный аналитик")
        elif amount < app.requested_amount:
            reasons.append(
                f"Лимит по площади и классу — {format_kzt(limit)}, это меньше запрошенного; одобрено в пределах лимита"
            )

        decision = db.scalar(select(Decision).where(Decision.application_id == app.id))
        if decision is None:
            decision = Decision(application_id=app.id)
            db.add(decision)
        decision.score = result.score
        decision.score_class = result.score_class
        decision.components = result.components
        decision.reasons = reasons
        decision.limit_amount = limit
        decision.approved_amount = amount
        decision.schedule = build_schedule(amount, result.score_class, today)
        decision.decided_by = "auto"

        if app.overlaps:
            # Пересечение с чужим полем: балл и лимит считаем, но деньги без аналитика не выдаём
            top = app.overlaps[0]
            decision.reasons = [
                *reasons,
                f"Контур пересекается с полем другого хозяйства: {top['overlap_ha']:g} га "
                f"({top['share']:.0%} участка) — нужна проверка документов на землю",
            ]
            decision.approved_amount = 0
            decision.schedule = []
            app.status = ApplicationStatus.REVIEW
        elif result.score_class == "C":
            app.status = ApplicationStatus.REVIEW
        elif amount > 0:
            app.status = ApplicationStatus.APPROVED
        else:
            app.status = ApplicationStatus.REVIEW
        db.commit()
    except Exception as exc:  # noqa: BLE001 — любую ошибку показываем в заявке, а не теряем
        db.rollback()
        log.exception("Ошибка обработки заявки %s", application_id)
        app = db.get(Application, application_id)
        if app is not None:
            app.status = ApplicationStatus.ERROR
            app.error_message = f"Не удалось получить спутниковые данные или рассчитать скоринг: {exc}"
            db.commit()
