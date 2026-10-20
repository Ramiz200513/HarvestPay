from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationItem, Field, Product
from ..schemas import ApplicationCreate, ApplicationCreated, ApplicationOut, ProductOut
from ..services.geo import GeometryError, parse_field_geometry
from ..tasks import enqueue_application
from .farms import verify_and_store
from .serializers import application_out

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

    field = Field(
        farm_id=farm.id,
        geometry=geom.geojson,
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
    )
    db.add(app)
    db.commit()

    # 4. Ставим в очередь: спутник + скоринг выполнятся в фоне, ответ уходит сразу.
    enqueue_application(app.id, background)
    return ApplicationCreated(id=app.id, status=app.status)


@router.get("/applications/{application_id}", response_model=ApplicationOut, summary="Статус и решение по заявке")
def get_application(application_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return application_out(app)
