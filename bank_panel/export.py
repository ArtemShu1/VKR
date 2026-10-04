from __future__ import annotations

from pathlib import Path

import pandas as pd

from .validation import validate_panel


def stable_columns(frame: pd.DataFrame) -> list[str]:
    keys = ["regn_gko", "bank_name", "year"]
    base = [c for c in frame.columns if not c.endswith(("__unit", "__form", "__row_code", "__source")) and c not in keys]
    metadata = [c for c in frame.columns if c not in keys + base]
    return [c for c in keys if c in frame.columns] + sorted(base) + sorted(metadata)


def write_outputs(frame: pd.DataFrame, xlsx_path: str | Path, csv_path: str | Path | None = None, sheet_name: str = "bank_year") -> None:
    validate_panel(frame, strict=True)
    ordered = frame.loc[:, stable_columns(frame)]
    xlsx = Path(xlsx_path)
    xlsx.parent.mkdir(parents=True, exist_ok=True)
    ordered.to_excel(xlsx, index=False, sheet_name=sheet_name)
    if csv_path:
        csv = Path(csv_path)
        csv.parent.mkdir(parents=True, exist_ok=True)
        ordered.to_csv(csv, index=False, encoding="utf-8-sig")


def append_rows(existing: pd.DataFrame, additions: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([existing, additions], ignore_index=True)
    combined = combined.drop_duplicates(["regn_gko", "bank_name", "year"], keep="last")
    return combined.sort_values(["year", "regn_gko"], kind="stable").reset_index(drop=True)
