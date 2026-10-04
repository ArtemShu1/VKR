from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    label: str
    form: str
    aliases: tuple[str, ...] = ()


@dataclass
class CellValue:
    value: Any
    unit: str | None = None
    report_date: str | None = None
    form: str | None = None
    row_code: str | None = None
    source_url: str | None = None
    source_kind: str | None = None
    is_group_value: bool = False


@dataclass
class BankYearRecord:
    regn_gko: str
    bank_name: str
    year: int
    values: dict[str, CellValue] = field(default_factory=dict)

    def as_flat_row(self, specs: list[IndicatorSpec]) -> dict[str, Any]:
        row: dict[str, Any] = {"regn_gko": self.regn_gko, "bank_name": self.bank_name, "year": self.year}
        for spec in specs:
            cell = self.values.get(spec.name)
            row[spec.name] = cell.value if cell else None
            row[f"{spec.name}__unit"] = cell.unit if cell else None
            row[f"{spec.name}__form"] = cell.form if cell else spec.form
            row[f"{spec.name}__row_code"] = cell.row_code if cell else None
            row[f"{spec.name}__source"] = cell.source_url if cell else None
        return row
