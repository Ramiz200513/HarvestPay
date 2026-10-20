from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationItem, Farm, Field, Product
from ..schemas import (
    ApplicationCreate,
    ApplicationCreated,
    ApplicationOut,
    OverlapCheckIn,
    OverlapCheckOut,
    ProductOut,
)
from ..services.geo import GeometryError, parse_field_geometry
from ..services.overlap import find_overlaps
from ..tasks import enqueue_application
from .farms import verify_and_store
from .serializers import application_out, overlap_out

router = APIRouter(prefix="/api", tags=["Заявки"])


@router.get("/products", response_model=list[ProductOut], summary="Каталог товаров для рассрочки")
def list_products(db: Session = Depends(get_db)) -> list[Product]:
    return list(db.scalars(select(Product).order_by(Product.category, Product.name)))


@router.post("/applications", response_model=ApplicationCreated, status_code=201, summary="Подать заявку")
def create_application(
    body: ApplicationCreate, background: BackgroundTasks, db: Session = Depends(get_db)
) -> ApplicationCreated:
    # 1. Хозяйство: проверяем БИН ещё раз на сервере — фронтенду доверять нельзя.
    verification, farm = verify_and_store(db, body.bin)
    if farm is None:
        raise HTTPException(
            status_code=422,
            detail={"message": "Хозяйство не прошло проверку", "reasons": verification.reasons},
        )

    # 2. Поле: валидный полигон в Казахстане, считаем площадь.
    try:
        geom = parse_field_geometry(body.field.geometry)
    except GeometryError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc), "reasons": []}) from exc

    # 3. Товары: все id должны существовать; цену берём из БД, а не из запроса.
    ids = {i.product_id for i in body.items}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    missing = ids - products.keys()
    if missing:
        raise HTTPException(status_code=422, detail={"message": f"Нет товаров с id {sorted(missing)}", "reasons": []})

    # 4. Антифрод: не заявляло ли этот участок другое хозяйство (PostGIS / shapely).
    overlaps = find_overlaps(db, geom, exclude_farm_id=farm.id)

    min_lon, min_lat, max_lon, max_lat = geom.bbox
    field = Field(
        farm_id=farm.id,
        geometry=geom.geojson,
        geom=geom.ewkt,
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        crop=body.field.crop.strip(),
        area_ha=geom.area_ha,
        centroid_lat=geom.centroid_lat,
        centroid_lon=geom.centroid_lon,
    )
    items = [
        ApplicationItem(product_id=i.product_id, quantity=i.quantity, price=products[i.product_id].price)
        for i in body.items
    ]
    app = Application(
        farm_id=farm.id,
        field=field,
        items=items,
        requested_amount=sum(i.quantity * i.price for i in items),
        overlaps=[o.to_dict() for o in overlaps],
    )
    db.add(app)
    db.commit()

    # 5. Ставим в очередь: спутник + скоринг выполнятся в фоне, ответ уходит сразу.
    enqueue_application(app.id, background)
    return ApplicationCreated(id=app.id, status=app.status)


@router.post("/fields/check", response_model=OverlapCheckOut, summary="Проверить контур поля до подачи заявки")
def check_field(body: OverlapCheckIn, db: Session = Depends(get_db)) -> OverlapCheckOut:
    """Фронтенд вызывает это, пока фермер рисует поле: площадь по версии сервера + пересечения.
    Чьё именно поле пересекается, фермеру не сообщаем — только площадь и долю."""
    try:
        geom = parse_field_geometry(body.geometry)
    except GeometryError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc), "reasons": []}) from exc
    farm_id = None
    if body.bin:
        farm_id = db.scalar(select(Farm.id).where(Farm.bin == body.bin.strip()))
    overlaps = find_overlaps(db, geom, exclude_farm_id=farm_id)
    return OverlapCheckOut(area_ha=geom.area_ha, overlaps=[overlap_out(o.to_dict(), full=False) for o in overlaps])


@router.get("/applications/{application_id}", response_model=ApplicationOut, summary="Статус и решение по заявке")
def get_application(application_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return application_out(app)
