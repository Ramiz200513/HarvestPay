"""Стартовый каталог товаров. Цены, поставщики и их скидки — демонстрационные (порядок цен реалистичный).

Скидка — то, что поставщик уступает маркетплейсу за оплату сразу при отгрузке вместо ожидания до осени
(в бизнес-плане 5–7 %). Фермер видит розничную цену, скидку видит только аналитик."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Product, Supplier

DEMO_SUPPLIERS = {
    # name: discount
    "Агрохолдинг Север (демо)": 0.06,
    "СемКорм (демо)": 0.07,
    "АгроХим КЗ (демо)": 0.05,
    "ЗащитаПолей (демо)": 0.07,
}

DEMO_PRODUCTS = [
    # name, category, supplier, unit, price ₸
    ("Пшеница яровая «Астана», элита", "seeds", "Агрохолдинг Север (демо)", "т", 210_000),
    ("Пшеница яровая «Шортандинская 95», репродукция 1", "seeds", "Агрохолдинг Север (демо)", "т", 185_000),
    ("Ячмень «Астана 2000»", "seeds", "СемКорм (демо)", "т", 160_000),
    ("Подсолнечник гибрид F1", "seeds", "СемКорм (демо)", "п.е.", 95_000),
    ("Аммофос 12:52", "fertilizer", "АгроХим КЗ (демо)", "т", 320_000),
    ("Карбамид (мочевина) 46%", "fertilizer", "АгроХим КЗ (демо)", "т", 240_000),
    ("Аммиачная селитра 34,4%", "fertilizer", "АгроХим КЗ (демо)", "т", 175_000),
    ("Гербицид на основе глифосата 360 г/л", "protection", "ЗащитаПолей (демо)", "л", 3_200),
    ("Протравитель семян, 1 л", "protection", "ЗащитаПолей (демо)", "л", 14_500),
    ("Фунгицид системный, 5 л", "protection", "ЗащитаПолей (демо)", "канистра", 62_000),
]


def seed_products(db: Session) -> None:
    if db.scalar(select(Product.id).limit(1)) is not None:
        return  # каталог уже заполнен — ничего не делаем
    suppliers = {s.name: s for s in db.scalars(select(Supplier))}
    for name, discount in DEMO_SUPPLIERS.items():
        if name not in suppliers:
            suppliers[name] = Supplier(name=name, discount=discount)
            db.add(suppliers[name])
    for name, category, supplier, unit, price in DEMO_PRODUCTS:
        db.add(Product(name=name, category=category, supplier=suppliers[supplier], unit=unit, price=price))
    db.commit()
