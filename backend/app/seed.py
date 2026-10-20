"""Стартовый каталог товаров. Цены и поставщики — демонстрационные (порядок цен реалистичный)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Product

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
    for name, category, supplier, unit, price in DEMO_PRODUCTS:
        db.add(Product(name=name, category=category, supplier=supplier, unit=unit, price=price))
    db.commit()
