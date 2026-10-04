from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from .normalize import is_group_label


KEY_COLUMNS = ["regn_gko", "bank_name", "year"]


def validate_panel(frame: pd.DataFrame, *, strict: bool = True) -> list[str]:
    errors: list[str] = []
    missing = [c for c in KEY_COLUMNS if c not in frame.columns]
    if missing:
        return [f"missing required columns: {', '.join(missing)}"]
    if frame["regn_gko"].isna().any() or (frame["regn_gko"].astype(str).str.strip() == "").any():
        errors.append("REGN_GKO is missing for at least one observation")
    if frame["bank_name"].isna().any() or (frame["bank_name"].astype(str).str.strip() == "").any():
        errors.append("bank_name is missing for at least one observation")
    if not frame["year"].between(2007, 2021).all():
        errors.append("year must be in the requested 2007-2021 period")
    duplicates = frame.duplicated(KEY_COLUMNS, keep=False)
    if duplicates.any():
        errors.append(f"duplicate bank-year observations: {int(duplicates.sum())}")
    for col in frame.columns:
        if "n20" in col.casefold():
            errors.append(f"forbidden group indicator column: {col}")
    for col in frame.columns:
        if col.endswith("__source"):
            values = frame[col].dropna().astype(str)
            if any("analizbankov" in value.casefold() for value in values):
                errors.append(f"numeric data source must not be analizbankov: {col}")
    if strict and errors:
        raise ValueError("; ".join(errors))
    return errors


def validate_source_labels(labels: Iterable[Any]) -> None:
    forbidden = [label for label in labels if is_group_label(label)]
    if forbidden:
        raise ValueError(f"group indicators N20.x are forbidden in the individual-bank panel: {forbidden[:3]}")
