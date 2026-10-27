from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Farm
from ..schemas import BinRequest, FarmOut
from ..services.providers import get_compliance, get_registry
from ..services.registry import FarmVerification, RegistryUnavailable, verify_farm
from .serializers import farm_out

router = APIRouter(prefix="/api/farms", tags=["Хозяйства"])


def verify_and_store(db: Session, bin_value: str) -> tuple[FarmVerification, Farm | None]:
    """Проверяет БИН и сохраняет хозяйство, если оно прошло проверку.
    Отклонённые не сохраняем: в БД попадают только реальные клиенты."""
    settings = get_settings()
    try:
        result = verify_farm(
            bin_value,
            get_registry(),
            settings.min_company_age_months,
            compliance=get_compliance(),
            max_tax_debt=settings.max_tax_debt,
            class_a_min_age_months=settings.class_a_min_age_months,
        )
    except RegistryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if result.status != "verified":
        return result, None

    farm = db.scalar(select(Farm).where(Farm.bin == result.bin))
    if farm is None:
        farm = Farm(bin=result.bin)
        db.add(farm)
    farm.name = result.name
    farm.legal_form = result.legal_form
    farm.registered_at = result.registered_at
    farm.verification_status = result.status
    farm.verification_reasons = result.reasons
    farm.registry_source = result.source
    farm.compliance = result.compliance.to_dict() if result.compliance else {}
    farm.checks = result.checks
    db.commit()
    return result, farm


@router.post("/verify", response_model=FarmOut, summary="Шаг 1: проверка хозяйства по БИН")
def verify(body: BinRequest, db: Session = Depends(get_db)) -> FarmOut:
    result, _ = verify_and_store(db, body.bin)
    return farm_out(result)
