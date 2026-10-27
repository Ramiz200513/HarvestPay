"""Проверка «чистоты» хозяйства: налоговый долг, аресты, суды, история субсидий.

Реестр юрлиц (registry.py) отвечает на вопрос «существует ли хозяйство». Этот модуль — на вопрос
«не опасно ли с ним работать». В продакшене данные берутся у агрегаторов госбаз (adata.kz, Kompra):
у них платный API по договору, поэтому здесь пока только демо-провайдер с тем же интерфейсом —
настоящий подключается так же, как StatGovRegistry, без правки правил.

Правила (verify_farm в registry.py):
  * арест счетов или имущества         → отказ: деньги за урожай могут списать в пользу взыскателя;
  * налоговый долг > HP_MAX_TAX_DEBT   → отказ; меньше — только предупреждение;
  * активные суды, где хозяйство ответчик → не отказ, но класс не выше B (underwriting.py);
  * субсидии в прошлые годы            → плюс к доверию: хозяйство реально сеет и отчитывается перед МСХ.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Protocol


@dataclass
class ComplianceInfo:
    tax_debt: int = 0  # ₸
    arrests: list[str] = field(default_factory=list)  # аресты счетов/имущества, запреты на регистрационные действия
    court_cases: int = 0  # активные дела, где хозяйство — ответчик
    subsidy_years: list[int] = field(default_factory=list)  # годы, когда получало госсубсидии
    source: str = "mock"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict | None) -> ComplianceInfo:
        return cls(**raw) if raw else cls(source="нет данных")


class Compliance(Protocol):
    def lookup(self, bin_value: str) -> ComplianceInfo: ...


# Демо-БИН для сценариев проверки (контрольные цифры валидные, в реестре они «находятся»):
#   170343000014 — КХ, налоговый долг 1,85 млн ₸ → отказ
#   160540000019 — ТОО, арест банковских счетов → отказ
#   190340000017 — ТОО, судебный спор с поставщиком → не выше класса B
DEMO_TAX_DEBT = {"170343000014": 1_850_000}
DEMO_ARRESTS = {"160540000019": ["Арест банковских счетов по исполнительному производству"]}
DEMO_COURT_CASES = {"190340000017": 1}


class MockCompliance:
    def lookup(self, bin_value: str, today: date | None = None) -> ComplianceInfo:
        today = today or date.today()
        # Субсидии — по хешу БИН: у одних хозяйств есть история, у других нет, но всегда одинаково
        h = int(hashlib.sha256(f"subsidy:{bin_value}".encode()).hexdigest(), 16)
        years = [today.year - 1 - i for i in range(5) if (h >> i) & 1]
        return ComplianceInfo(
            tax_debt=DEMO_TAX_DEBT.get(bin_value, 0),
            arrests=list(DEMO_ARRESTS.get(bin_value, [])),
            court_cases=DEMO_COURT_CASES.get(bin_value, 0),
            subsidy_years=sorted(years),
            source="mock",
        )
