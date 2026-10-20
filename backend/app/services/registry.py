"""Проверка хозяйства по реестру юрлиц.

Два «провайдера» с одинаковым интерфейсом:
  * MockRegistry   — детерминированные демо-данные, работает без интернета (для разработки и защиты);
  * StatGovRegistry — запрос к открытому API Бюро нацстатистики (stat.gov.kz). Экспериментальный:
    формат ответа у госсервисов иногда меняется, поэтому разбор написан «защитно».

Остальной код зависит только от метода lookup(), поэтому провайдер переключается одной
переменной окружения HP_REGISTRY_PROVIDER, без правки бизнес-логики.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from .bin_check import check_bin


class RegistryUnavailable(Exception):
    """Реестр не ответил — это не отказ фермеру, а временная ошибка (HTTP 503)."""


@dataclass
class RegistryInfo:
    found: bool
    name: str | None = None
    registered_at: date | None = None
    active: bool = True
    legal_form: str | None = None
    source: str = "mock"


class Registry(Protocol):
    def lookup(self, bin_value: str) -> RegistryInfo: ...


# --- Демо-реестр --------------------------------------------------------------------------

# Демо-БИН для показа разных сценариев (контрольные цифры у всех валидные):
#   150343000016 — КХ, зарегистрировано в 2015 → проходит
#   180240000011 — ТОО, 2018 → проходит
#   260440000016 — ТОО, апрель 2026 → отказ «слишком молодое»
#   080740000019 — ликвидировано → отказ
#   150340000015 — нет в реестре → отказ
# Любой другой валидный БИН в демо-режиме тоже «находится» — с названием, выбранным по хешу.
DEMO_LIQUIDATED = {"080740000019"}
DEMO_NOT_FOUND = {"150340000015"}

_DEMO_NAMES = [
    "Агро-Есиль",
    "Береке",
    "Нива Сарыарки",
    "Дала Астык",
    "Колос Акмолы",
    "Жасыл Дала",
    "Степной Хлеб",
    "Тобол Агро",
    "Ак Бидай",
    "Нур Егін",
]


class MockRegistry:
    def lookup(self, bin_value: str) -> RegistryInfo:
        if bin_value in DEMO_NOT_FOUND:
            return RegistryInfo(found=False, source="mock")

        parsed = check_bin(bin_value)
        # Имя выбираем по хешу БИН: один и тот же БИН всегда даёт одно и то же название.
        idx = int(hashlib.sha256(bin_value.encode()).hexdigest(), 16) % len(_DEMO_NAMES)
        is_farm = parsed.attribute == "крестьянское (фермерское) хозяйство"
        prefix = "КХ" if is_farm else "ТОО"
        registered = None
        if parsed.reg_year and parsed.reg_month:
            registered = date(parsed.reg_year, parsed.reg_month, 15)
        return RegistryInfo(
            found=True,
            name=f"{prefix} «{_DEMO_NAMES[idx]}»",
            registered_at=registered,
            active=bin_value not in DEMO_LIQUIDATED,
            legal_form="Крестьянское хозяйство" if is_farm else "Товарищество с ограниченной ответственностью",
            source="mock",
        )


# --- Реальный реестр (stat.gov.kz) ----------------------------------------------------------


class StatGovRegistry:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout

    def lookup(self, bin_value: str) -> RegistryInfo:
        import httpx  # импорт внутри: в mock-режиме библиотека не нужна

        try:
            resp = httpx.get(self.url, params={"bin": bin_value, "lang": "ru"}, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # сеть, таймаут, не-JSON — всё это «реестр недоступен»
            raise RegistryUnavailable(f"Реестр stat.gov.kz не ответил: {exc}") from exc

        obj = payload.get("obj") if isinstance(payload, dict) else None
        if not payload.get("success") or not obj:
            return RegistryInfo(found=False, source="stat.gov.kz")

        registered = None
        raw_date = str(obj.get("registerDate") or "")[:10]  # '2005-09-26T00:00...' -> '2005-09-26'
        try:
            registered = date.fromisoformat(raw_date)
        except ValueError:
            pass

        return RegistryInfo(
            found=True,
            name=obj.get("name"),
            registered_at=registered,
            # В открытом ответе нет явного статуса ликвидации — считаем активным, если запись отдана.
            active=True,
            legal_form=obj.get("krpName") or obj.get("okedName"),
            source="stat.gov.kz",
        )


# --- Правила допуска хозяйства ----------------------------------------------------------------


@dataclass
class FarmVerification:
    bin: str
    status: str  # "verified" | "rejected"
    name: str | None = None
    registered_at: date | None = None
    legal_form: str | None = None
    source: str | None = None
    reasons: list[str] = field(default_factory=list)


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def verify_farm(bin_value: str, registry: Registry, min_age_months: int, today: date | None = None) -> FarmVerification:
    """Первый шаг скоринга (ромб «Проверка юрлица» на блок-схеме)."""
    today = today or date.today()
    parsed = check_bin(bin_value)
    if not parsed.valid:
        return FarmVerification(bin=parsed.bin, status="rejected", reasons=parsed.errors)

    info = registry.lookup(parsed.bin)  # может бросить RegistryUnavailable — это обрабатывает API
    result = FarmVerification(
        bin=parsed.bin,
        status="verified",
        name=info.name,
        registered_at=info.registered_at,
        legal_form=info.legal_form,
        source=info.source,
    )

    if not info.found:
        result.status = "rejected"
        result.reasons.append("Организация с таким БИН не найдена в реестре")
        return result
    if not info.active:
        result.status = "rejected"
        result.reasons.append("Организация ликвидирована или деятельность приостановлена")
    if info.registered_at and months_between(info.registered_at, today) < min_age_months:
        result.status = "rejected"
        result.reasons.append(
            f"Хозяйство зарегистрировано меньше {min_age_months} мес. назад — пока нет истории для оценки"
        )
    return result
