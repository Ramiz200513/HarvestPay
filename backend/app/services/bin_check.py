"""Проверка формата БИН (бизнес-идентификационный номер Казахстана).

БИН — 12 цифр:
  1–2  год регистрации (последние две цифры)
  3–4  месяц регистрации (01–12)
  5    тип: 4 — юрлицо-резидент, 5 — юрлицо-нерезидент, 6 — ИП (совместное)
  6    признак: 0 — головная организация, 1 — филиал, 2 — представительство,
       3 — крестьянское (фермерское) хозяйство на совместном предпринимательстве
  7–11 порядковый номер
  12   контрольная цифра

Контрольная цифра считается так же, как у ИИН: сумма цифр с весами 1..11 по модулю 11.
Если получилось 10 — пересчитываем с весами 3..11,1,2. Если снова 10 — номер невалиден.

Модуль «чистый»: не зависит от БД и веб-фреймворка, поэтому легко тестируется.
"""

from __future__ import annotations

from dataclasses import dataclass, field

WEIGHTS_1 = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
WEIGHTS_2 = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)

ENTITY_TYPES = {
    "4": "юридическое лицо (резидент)",
    "5": "юридическое лицо (нерезидент)",
    "6": "ИП (совместное предпринимательство)",
}

ATTRIBUTES = {
    "0": "головная организация",
    "1": "филиал",
    "2": "представительство",
    "3": "крестьянское (фермерское) хозяйство",
}


def control_digit(first_11: str) -> int | None:
    """Считает контрольную (12-ю) цифру по первым 11. None — если номер не может быть валидным."""
    digits = [int(c) for c in first_11]
    total = sum(d * w for d, w in zip(digits, WEIGHTS_1, strict=True)) % 11
    if total == 10:
        total = sum(d * w for d, w in zip(digits, WEIGHTS_2, strict=True)) % 11
        if total == 10:
            return None
    return total


@dataclass
class BinCheck:
    bin: str
    valid: bool
    entity_type: str | None = None
    attribute: str | None = None
    reg_year: int | None = None
    reg_month: int | None = None
    errors: list[str] = field(default_factory=list)


def check_bin(raw: str) -> BinCheck:
    """Проверяет формат БИН и раскладывает его на части. Не обращается к внешним реестрам."""
    value = (raw or "").strip().replace(" ", "")
    result = BinCheck(bin=value, valid=False)

    if len(value) != 12 or not value.isdigit():
        result.errors.append("БИН должен состоять ровно из 12 цифр")
        return result

    month = int(value[2:4])
    if not 1 <= month <= 12:
        result.errors.append("В 3–4 позиции БИН должен быть месяц регистрации (01–12)")

    type_digit = value[4]
    if type_digit not in ENTITY_TYPES:
        result.errors.append(
            "5-я цифра указывает, что это ИИН физлица, а не БИН организации — "
            "рассрочка выдаётся только юрлицам и хозяйствам"
        )

    expected = control_digit(value[:11])
    if expected is None or expected != int(value[11]):
        result.errors.append("Контрольная цифра не совпадает — проверьте, нет ли опечатки")

    yy = int(value[0:2])
    # БИН появились в 2000-х; год 00–79 считаем 2000+, остальное — 1900+ (организации, перерегистрированные со старым годом).
    result.reg_year = 2000 + yy if yy < 80 else 1900 + yy
    result.reg_month = month if 1 <= month <= 12 else None
    result.entity_type = ENTITY_TYPES.get(type_digit)
    result.attribute = ATTRIBUTES.get(value[5])
    result.valid = not result.errors
    return result


def make_valid_bin(first_11: str) -> str:
    """Достраивает контрольную цифру. Нужен для генерации демо-БИН в тестах и сидах."""
    digit = control_digit(first_11)
    if digit is None:
        raise ValueError("Для этих 11 цифр валидной контрольной цифры не существует")
    return first_11 + str(digit)
