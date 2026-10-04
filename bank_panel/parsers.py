from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from .models import CellValue, IndicatorSpec
from .normalize import is_group_label, match_label, parse_number


def read_tabular_bytes(content: bytes, filename: str = "download.xlsx") -> list[pd.DataFrame]:
    """Read CBR xls/xlsx/csv exports, keeping all sheets for later matching."""
    suffix = Path(filename).suffix.casefold()
    if suffix == ".csv":
        return [pd.read_csv(BytesIO(content), header=None, sep=None, engine="python")]
    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    book = pd.ExcelFile(BytesIO(content), engine=engine)
    return [pd.read_excel(BytesIO(content), sheet_name=s, header=None, engine=engine) for s in book.sheet_names]


def extract_cells(
    frame: pd.DataFrame,
    specs: list[IndicatorSpec],
    *,
    form: str,
    source_url: str,
    report_date: str | None = None,
) -> dict[str, CellValue]:
    """Find the first numeric cell to the right of an individual indicator label.

    CBR layouts changed over 2007-2021. This intentionally does not guess a
    group column: a row containing N20 or a group marker is skipped.
    """
    result: dict[str, CellValue] = {}
    for row_index, row in frame.iterrows():
        labels = [str(value) for value in row.tolist() if pd.notna(value)]
        row_text = " ".join(labels)
        if is_group_label(row_text):
            continue
        for spec in specs:
            if spec.name in result or not match_label(row_text, spec.aliases or (spec.label,)):
                continue
            # Prefer a value in the rightmost numeric region after the label.
            for value in row.tolist()[1:]:
                number = parse_number(value)
                if number is not None:
                    result[spec.name] = CellValue(
                        value=number,
                        report_date=report_date,
                        form=form,
                        row_code=_row_code(row),
                        source_url=source_url,
                        source_kind="cbr",
                    )
                    break
    return result


def _row_code(row: pd.Series) -> str | None:
    for value in row.tolist()[:3]:
        text = str(value).strip()
        if text and text.replace(".", "", 1).isdigit() and len(text) <= 8:
            return text
    return None
