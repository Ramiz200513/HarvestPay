"""Кабинет кредитного аналитика: очередь заявок класса C и ручное решение."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationStatus, Decision
from ..schemas import AnalystDecisionIn, ApplicationListItem, ApplicationOut
from ..services.limits import build_schedule
from ..tasks import enqueue_application
from .deps import require_analyst
from .serializers import application_list_item, application_out

router = APIRouter(prefix="/api/analyst", tags=["Аналитик"], dependencies=[Depends(require_analyst)])


def _get(db: Session, application_id: str) -> Application:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return app


@router.get("/applications", response_model=list[ApplicationListItem])
def list_applications(status: str | None = None, db: Session = Depends(get_db)) -> list[ApplicationListItem]:
    query = select(Application).order_by(Application.created_at.desc()).limit(200)
    if status:
        query = query.where(Application.status == status)
    return [application_list_item(a) for a in db.scalars(query)]


@router.get("/applications/{application_id}", response_model=ApplicationOut)
def get_application(application_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    return application_out(_get(db, application_id), full=True)


@router.post("/applications/{application_id}/decision", response_model=ApplicationOut)
def decide(application_id: str, body: AnalystDecisionIn, db: Session = Depends(get_db)) -> ApplicationOut:
    app = _get(db, application_id)
    if app.status != ApplicationStatus.REVIEW:
        raise HTTPException(status_code=409, detail="Вручную решаются только заявки в статусе «на проверке»")

    decision = app.decision
    if decision is None:
        decision = Decision(score_class="C")
        app.decision = decision

    if body.action == "approve":
        amount = body.approved_amount if body.approved_amount is not None else app.requested_amount
        if not 0 < amount <= app.requested_amount:
            raise HTTPException(status_code=422, detail="Сумма должна быть больше 0 и не больше запрошенной")
        decision.approved_amount = amount
        decision.limit_amount = max(decision.limit_amount or 0, amount)
        decision.schedule = build_schedule(amount, decision.score_class)
        app.status = ApplicationStatus.APPROVED
    else:
        decision.approved_amount = 0
        decision.schedule = []
        app.status = ApplicationStatus.REJECTED

    decision.decided_by = "analyst"
    decision.analyst_comment = body.comment
    db.commit()
    return application_out(app, full=True)


@router.post("/applications/{application_id}/retry", response_model=ApplicationOut)
def retry(application_id: str, background: BackgroundTasks, db: Session = Depends(get_db)) -> ApplicationOut:
    """Перезапуск после технической ошибки (например, GEE был недоступен)."""
    app = _get(db, application_id)
    if app.status != ApplicationStatus.ERROR:
        raise HTTPException(status_code=409, detail="Перезапуск возможен только для заявок с ошибкой")
    enqueue_application(app.id, background)
    return application_out(app, full=True)
